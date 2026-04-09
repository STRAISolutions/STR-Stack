#!/usr/bin/env python3
"""One-time import of AirDNA CSV.GZ into persistent DuckDB file."""
import duckdb, time, os

DB_PATH = "/root/str-stack/airdna.duckdb"
CSV_PATH = "/root/str-stack/PPD-USA_property_file_v3.csv.gz"

print(f"Importing {CSV_PATH} into {DB_PATH}...")
start = time.time()

if os.path.exists(DB_PATH):
    os.remove(DB_PATH)

con = duckdb.connect(DB_PATH)
con.execute("SET memory_limit = '3GB'")
con.execute("SET threads TO 2")

con.execute(f"""
CREATE TABLE raw_listings AS
SELECT
    "Property ID" AS property_id,
    "Property Type" AS property_type,
    "Listing Type" AS listing_type,
    CAST("Bedrooms" AS INTEGER) AS bedrooms,
    CAST("Reporting Month" AS DATE) AS reporting_month,
    CAST("Occupancy Rate" AS DOUBLE) AS occupancy_rate,
    "Currency" AS currency,
    CAST("Revenue (USD)" AS DOUBLE) AS revenue_usd,
    CAST("Revenue Potential (USD)" AS DOUBLE) AS revenue_potential_usd,
    CAST("ADR (USD)" AS DOUBLE) AS adr_usd,
    CAST("Number of Reservations" AS INTEGER) AS num_reservations,
    CAST("Reservation Days" AS INTEGER) AS reservation_days,
    CAST("Available Days" AS INTEGER) AS available_days,
    CAST("Blocked Days" AS INTEGER) AS blocked_days,
    "Country" AS country,
    "State" AS state,
    "City" AS city,
    CAST("Postal Code" AS VARCHAR) AS zip,
    "Neighborhood" AS neighborhood,
    "Metropolitan Statistical Area" AS msa,
    CAST("Latitude" AS DOUBLE) AS latitude,
    CAST("Longitude" AS DOUBLE) AS longitude,
    "Active" AS active,
    CAST("Airbnb Property ID" AS VARCHAR) AS airbnb_property_id,
    CAST("Airbnb Host ID" AS VARCHAR) AS airbnb_host_id,
    CAST("Vrbo Property ID" AS VARCHAR) AS vrbo_property_id,
    CAST("Vrbo Host ID" AS VARCHAR) AS vrbo_host_id,
    "Property Manager" AS property_manager
FROM read_csv_auto('{CSV_PATH}', header=true, ignore_errors=true)
WHERE "Country" = 'United States'
""")

rows = con.execute("SELECT COUNT(*) FROM raw_listings").fetchone()[0]
elapsed = time.time() - start
print(f"Imported {rows:,} US rows in {elapsed:.1f}s")

print("Creating indexes...")
con.execute("CREATE INDEX idx_property_id ON raw_listings(property_id)")
con.execute("CREATE INDEX idx_reporting_month ON raw_listings(reporting_month)")
con.execute("CREATE INDEX idx_host ON raw_listings(airbnb_host_id)")
con.execute("CREATE INDEX idx_state ON raw_listings(state)")

print("Creating aggregated property view...")
con.execute("""
CREATE OR REPLACE VIEW property_summary AS
WITH recent AS (
    SELECT * FROM raw_listings
    WHERE reporting_month >= CURRENT_DATE - INTERVAL '6 months'
),
agg AS (
    SELECT
        property_id,
        ANY_VALUE(property_type) AS property_type,
        ANY_VALUE(listing_type) AS listing_type,
        ANY_VALUE(bedrooms) AS bedrooms,
        ANY_VALUE(city) AS city,
        ANY_VALUE(state) AS state,
        ANY_VALUE(zip) AS zip,
        ANY_VALUE(neighborhood) AS neighborhood,
        ANY_VALUE(msa) AS msa,
        ANY_VALUE(latitude) AS latitude,
        ANY_VALUE(longitude) AS longitude,
        ANY_VALUE(active) AS active,
        ANY_VALUE(airbnb_property_id) AS airbnb_property_id,
        ANY_VALUE(airbnb_host_id) AS airbnb_host_id,
        ANY_VALUE(vrbo_property_id) AS vrbo_property_id,
        ANY_VALUE(vrbo_host_id) AS vrbo_host_id,
        ANY_VALUE(property_manager) AS property_manager,
        AVG(revenue_usd) AS avg_monthly_revenue,
        AVG(revenue_usd) * 12 AS annual_revenue_est,
        AVG(occupancy_rate) * 100 AS avg_occupancy_pct,
        AVG(adr_usd) AS avg_adr,
        AVG(CASE WHEN EXTRACT(MONTH FROM reporting_month) IN (6,7,8,12) THEN adr_usd END) AS adr_high_season,
        AVG(CASE WHEN EXTRACT(MONTH FROM reporting_month) NOT IN (6,7,8,12) THEN adr_usd END) AS adr_low_season,
        SUM(num_reservations) AS total_reservations,
        SUM(reservation_days) AS total_reservation_days,
        SUM(available_days) AS total_available_days,
        SUM(blocked_days) AS total_blocked_days,
        SUM(CASE WHEN reservation_days = 0 THEN 1 ELSE 0 END) AS zero_booking_months,
        COUNT(*) AS months_of_data,
        CASE WHEN SUM(revenue_potential_usd) > 0
             THEN SUM(revenue_usd) / SUM(revenue_potential_usd) * 100
             ELSE 0 END AS revenue_vs_potential_pct
    FROM recent
    GROUP BY property_id
)
SELECT
    a.*,
    COALESCE(h.host_count, 1) AS host_property_count,
    CASE WHEN (a.total_reservation_days + a.total_available_days + a.total_blocked_days) > 0
         THEN a.total_reservation_days * 100.0 / (a.total_reservation_days + a.total_available_days + a.total_blocked_days)
         ELSE 0 END AS booking_rate_pct
FROM agg a
LEFT JOIN (
    SELECT airbnb_host_id, COUNT(DISTINCT property_id) AS host_count
    FROM recent
    WHERE airbnb_host_id IS NOT NULL AND airbnb_host_id != ''
    GROUP BY airbnb_host_id
) h ON a.airbnb_host_id = h.airbnb_host_id
""")

props = con.execute("SELECT COUNT(*) FROM property_summary").fetchone()[0]
db_size = os.path.getsize(DB_PATH) / (1024**3)
total_elapsed = time.time() - start
print(f"\nDone! {props:,} unique US properties in view")
print(f"DB size: {db_size:.2f} GB")
print(f"Total time: {total_elapsed:.1f}s")
con.close()
