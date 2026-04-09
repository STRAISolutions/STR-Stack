#!/usr/bin/env python3
"""Interactive AirDNA query tool powered by DuckDB.

Usage:
  python3 duckdb_query.py                          # interactive mode
  python3 duckdb_query.py "SELECT COUNT(*) FROM raw_listings"  # one-shot query
  python3 duckdb_query.py --export results.csv "SELECT ..."    # export to CSV

Prebuilt shortcuts:
  python3 duckdb_query.py --top 100 --state Florida             # top 100 leads in FL
  python3 duckdb_query.py --market "Austin"                     # market snapshot
  python3 duckdb_query.py --host 12345678                       # host portfolio view
  python3 duckdb_query.py --stats                               # full dataset stats
"""
import duckdb, argparse, sys, os, csv

DB_PATH = "/root/str-stack/airdna.duckdb"

def run_query(con, sql, export_path=None):
    try:
        result = con.execute(sql)
        cols = [desc[0] for desc in result.description]
        rows = result.fetchall()

        if export_path:
            with open(export_path, "w", newline="") as f:
                w = csv.writer(f)
                w.writerow(cols)
                w.writerows(rows)
            print(f"Exported {len(rows)} rows to {export_path}")
            return

        # Pretty print
        col_widths = [max(len(str(c)), max((len(str(r[i])) for r in rows[:50]), default=0)) for i, c in enumerate(cols)]
        col_widths = [min(w, 40) for w in col_widths]
        header = " | ".join(str(c).ljust(w)[:w] for c, w in zip(cols, col_widths))
        print(header)
        print("-" * len(header))
        for row in rows[:100]:
            print(" | ".join(str(v).ljust(w)[:w] for v, w in zip(row, col_widths)))
        if len(rows) > 100:
            print(f"\n... {len(rows)} total rows (showing first 100). Use --export to get all.")
        else:
            print(f"\n{len(rows)} rows")
    except Exception as e:
        print(f"Error: {e}")

def main():
    parser = argparse.ArgumentParser(description="AirDNA DuckDB Query Tool")
    parser.add_argument("sql", nargs="?", help="SQL query to run")
    parser.add_argument("--export", help="Export results to CSV file")
    parser.add_argument("--top", type=int, help="Top N leads (uses scoring model)")
    parser.add_argument("--state", help="Filter by state (with --top)")
    parser.add_argument("--city", help="Filter by city (with --top)")
    parser.add_argument("--market", help="Market snapshot for MSA keyword")
    parser.add_argument("--host", help="View host portfolio by host ID")
    parser.add_argument("--stats", action="store_true", help="Full dataset statistics")
    args = parser.parse_args()

    con = duckdb.connect(DB_PATH, read_only=True)
    print(f"Connected to {DB_PATH}")

    if args.stats:
        run_query(con, """
            SELECT
                COUNT(*) AS total_rows,
                COUNT(DISTINCT property_id) AS unique_properties,
                COUNT(DISTINCT airbnb_host_id) AS unique_hosts,
                COUNT(DISTINCT state) AS states,
                MIN(reporting_month) AS earliest_month,
                MAX(reporting_month) AS latest_month,
                ROUND(AVG(adr_usd), 2) AS overall_avg_adr,
                ROUND(AVG(occupancy_rate) * 100, 1) AS overall_avg_occ
            FROM raw_listings
        """)

    elif args.market:
        run_query(con, f"""
            SELECT
                state, city, msa,
                COUNT(DISTINCT property_id) AS properties,
                ROUND(AVG(adr_usd), 2) AS avg_adr,
                ROUND(AVG(occupancy_rate) * 100, 1) AS avg_occ_pct,
                ROUND(AVG(revenue_usd), 2) AS avg_monthly_rev,
                ROUND(SUM(revenue_usd), 0) AS total_revenue
            FROM raw_listings
            WHERE reporting_month >= CURRENT_DATE - INTERVAL '6 months'
              AND (msa ILIKE '%{args.market}%' OR city ILIKE '%{args.market}%')
            GROUP BY state, city, msa
            ORDER BY properties DESC
            LIMIT 50
        """)

    elif args.host:
        run_query(con, f"""
            SELECT
                property_id, property_type, bedrooms, city, state,
                ROUND(AVG(revenue_usd), 2) AS avg_monthly_rev,
                ROUND(AVG(occupancy_rate) * 100, 1) AS avg_occ,
                ROUND(AVG(adr_usd), 2) AS avg_adr,
                COUNT(*) AS months_of_data,
                active
            FROM raw_listings
            WHERE airbnb_host_id = '{args.host}'
              AND reporting_month >= CURRENT_DATE - INTERVAL '6 months'
            GROUP BY property_id, property_type, bedrooms, city, state, active
            ORDER BY avg_monthly_rev DESC
        """)

    elif args.top:
        where = []
        if args.state:
            where.append(f"state = '{args.state}'")
        if args.city:
            where.append(f"city ILIKE '%{args.city}%'")
        where_clause = "AND " + " AND ".join(where) if where else ""

        run_query(con, f"""
            SELECT
                property_id, property_type, bedrooms, city, state, msa,
                ROUND(avg_adr, 2) AS avg_adr,
                ROUND(adr_high_season, 2) AS adr_high,
                ROUND(adr_low_season, 2) AS adr_low,
                ROUND(avg_occupancy_pct, 1) AS occ_pct,
                ROUND(booking_rate_pct, 1) AS booking_pct,
                ROUND(annual_revenue_est, 0) AS annual_rev,
                ROUND(revenue_vs_potential_pct, 1) AS rev_potential,
                host_property_count,
                zero_booking_months,
                months_of_data,
                active
            FROM property_summary
            WHERE active = true {where_clause}
            ORDER BY booking_rate_pct ASC, avg_occupancy_pct ASC
            LIMIT {args.top}
        """, export_path=args.export)

    elif args.sql:
        run_query(con, args.sql, export_path=args.export)

    else:
        # Interactive mode
        print("Interactive mode. Type SQL queries, or 'quit' to exit.")
        print("Tables: raw_listings | Views: property_summary")
        print("Tip: property_summary has pre-aggregated 6-month stats per property\n")
        while True:
            try:
                sql = input("duckdb> ").strip()
                if sql.lower() in ("quit", "exit", "q"):
                    break
                if not sql:
                    continue
                run_query(con, sql, export_path=args.export)
                print()
            except (EOFError, KeyboardInterrupt):
                break

    con.close()

if __name__ == "__main__":
    main()
