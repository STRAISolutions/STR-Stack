#!/usr/bin/env python3
"""Daily lead extract using DuckDB — replaces 600-line Python pipeline."""
import duckdb, argparse, time, os
from datetime import datetime

DB_PATH = "/root/str-stack/airdna.duckdb"
KNOWN_PMS = "('Vacasa','Evolve','Sonder','Guesty','Hostaway','TurnKey','RedAwning','Casago','Grand Welcome','Blueground')"
EXCLUDED_TYPES = "('Hotel','Hostel','Motel','Hotel room','Boutique hotel')"

# --- Scoring SQL ---
# This mirrors the Python scoring model but runs entirely in SQL
SCORING_QUERY = """
WITH scored AS (
    SELECT *,
        -- HARD FILTERS (nullify score)
        CASE
            WHEN latitude IS NULL OR longitude IS NULL THEN 0
            WHEN NOT active THEN 0
            WHEN property_type IN {excluded_types} THEN 0
            WHEN property_manager IN {known_pms} THEN 0
            WHEN adr_high_season IS NOT NULL AND adr_high_season > 0 AND adr_high_season < 250 THEN 0
            WHEN adr_low_season IS NOT NULL AND adr_low_season > 0 AND adr_low_season < 180 THEN 0
            ELSE
                -- T1: Distress signals (20-25 pts each)
                (CASE WHEN booking_rate_pct < 15 THEN 25 WHEN booking_rate_pct < 30 THEN 15 ELSE 0 END)
                + (CASE WHEN revenue_vs_potential_pct < 50 THEN 20 WHEN revenue_vs_potential_pct < 75 THEN 10 ELSE 0 END)
                + (CASE WHEN avg_occupancy_pct < 25 THEN 20 WHEN avg_occupancy_pct < 40 THEN 12 ELSE 0 END)
                + (CASE WHEN months_of_data > 0 AND (zero_booking_months * 100.0 / months_of_data) >= 60 THEN 20
                        WHEN months_of_data > 0 AND (zero_booking_months * 100.0 / months_of_data) >= 40 THEN 12 ELSE 0 END)
                + (CASE WHEN months_of_data <= 3 AND booking_rate_pct < 20 THEN 15 ELSE 0 END)
                -- T2: Profile signals
                + (CASE WHEN host_property_count BETWEEN 2 AND 5 THEN 18
                        WHEN host_property_count = 1 THEN 10
                        WHEN host_property_count BETWEEN 6 AND 10 THEN 5 ELSE 0 END)
                + (CASE WHEN msa IS NOT NULL AND msa LIKE '%New York%' THEN 15
                        WHEN msa IS NOT NULL AND (msa LIKE '%Los Angeles%' OR msa LIKE '%San Francisco%' OR msa LIKE '%Miami%') THEN 12 ELSE 0 END)
                + (CASE WHEN state IN ('California','New York','Hawaii','Colorado','Florida','New Jersey') THEN 8 ELSE 0 END)
                + (CASE WHEN property_type IN ('House','Cabin','Cottage','Villa','Townhouse','Bungalow','Chalet') THEN 10 ELSE 0 END)
                + (CASE WHEN bedrooms BETWEEN 2 AND 5 THEN 8 ELSE 0 END)
                + (CASE WHEN annual_revenue_est >= 50000 THEN 15
                        WHEN annual_revenue_est >= 25000 THEN 10 ELSE 0 END)
                -- Composites
                + (CASE WHEN booking_rate_pct < 15 AND avg_occupancy_pct < 25 AND revenue_vs_potential_pct < 50 THEN 15 ELSE 0 END)
                + (CASE WHEN avg_adr >= 300 AND booking_rate_pct < 20 THEN 12 ELSE 0 END)
                -- Penalties
                + (CASE WHEN host_property_count > 10 THEN -10 ELSE 0 END)
                + (CASE WHEN annual_revenue_est < 15000 THEN -5 ELSE 0 END)
        END AS icp_score
    FROM property_summary
)
SELECT * FROM scored
WHERE icp_score >= {min_score}
ORDER BY icp_score DESC, booking_rate_pct ASC
LIMIT {limit}
"""

def main():
    parser = argparse.ArgumentParser(description="DuckDB daily lead extract")
    parser.add_argument("-n", "--num-leads", type=int, default=10000)
    parser.add_argument("-o", "--output-dir", default="/root/str-stack/daily_leads")
    parser.add_argument("--min-score", type=int, default=30)
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)
    today = datetime.now().strftime("%Y%m%d")
    outfile = os.path.join(args.output_dir, f"leads_{today}.csv")

    print(f"[DuckDB Extract] Opening {DB_PATH}...")
    start = time.time()
    con = duckdb.connect(DB_PATH, read_only=True)

    query = SCORING_QUERY.format(
        excluded_types=EXCLUDED_TYPES,
        known_pms=KNOWN_PMS,
        min_score=args.min_score,
        limit=args.num_leads
    )

    print(f"[DuckDB Extract] Running scoring query for top {args.num_leads} leads (min_score={args.min_score})...")
    t0 = time.time()
    result = con.execute(query)
    cols = [desc[0] for desc in result.description]

    # Write CSV
    import csv
    rows_written = 0
    with open(outfile, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(cols)
        while True:
            batch = result.fetchmany(10000)
            if not batch:
                break
            for row in batch:
                writer.writerow(row)
                rows_written += 1

    elapsed = time.time() - t0
    total = time.time() - start

    print(f"[DuckDB Extract] Scored and exported {rows_written} leads in {elapsed:.1f}s")
    print(f"[DuckDB Extract] Output: {outfile}")
    print(f"[DuckDB Extract] Total time: {total:.1f}s")

    # Quick tier breakdown
    tier_q = con.execute(f"""
        WITH scored AS ({SCORING_QUERY.format(excluded_types=EXCLUDED_TYPES, known_pms=KNOWN_PMS, min_score=args.min_score, limit=args.num_leads)})
        SELECT
            CASE WHEN icp_score >= 90 THEN 'T1_HOT (90+)'
                 WHEN icp_score >= 70 THEN 'T2_WARM (70-89)'
                 WHEN icp_score >= 50 THEN 'T3_COOL (50-69)'
                 ELSE 'T4_WATCH (30-49)' END AS tier,
            COUNT(*) AS cnt,
            ROUND(AVG(avg_adr), 2) AS avg_adr,
            ROUND(AVG(booking_rate_pct), 1) AS avg_booking_rate,
            ROUND(AVG(avg_occupancy_pct), 1) AS avg_occ
        FROM scored
        GROUP BY 1 ORDER BY 1
    """).fetchall()
    print("\nTier Breakdown:")
    for row in tier_q:
        print(f"  {row[0]}: {row[1]:,} leads | ADR ${row[2]} | Booking {row[3]}% | Occ {row[4]}%")

    con.close()

if __name__ == "__main__":
    main()
