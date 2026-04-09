#!/usr/bin/env python3
"""
Daily Lead Extract — 10,000 Qualified STR Leads/Day
====================================================
Reads the raw AirDNA CSV.GZ, aggregates per-property across recent months,
applies the ICP scoring model, deduplicates, and outputs a clean list of
10,000 unique properties sorted by score.

TWO-PASS STREAMING APPROACH (stays under 2GB RAM):
  Pass 1: Stream CSV rows into a file-based SQLite database (/tmp/icp_agg.db)
  Pass 2: Query SQLite, score each property, keep top 10K via min-heap

Runs daily at 5AM via cron.
"""

import argparse
import csv
import gzip
import heapq
import io
import json
import logging
import os
import re
import sqlite3
import sys
import tempfile
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

LOG_FORMAT = "%(asctime)s [%(levelname)s] %(message)s"
log = logging.getLogger("DailyExtract")

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

# Only consider data from the last N months
LOOKBACK_MONTHS = 6

# High season months (Jun-Aug, Dec) and low season (rest)
HIGH_SEASON_MONTHS = {6, 7, 8, 12}

# Minimum ADR thresholds
MIN_ADR_HIGH_SEASON = 250.0
MIN_ADR_LOW_SEASON = 180.0

# Default output count
DEFAULT_LEAD_COUNT = 10000

# Markets with STR regulations (compliance burden = conversion opportunity)
REGULATED_MARKETS = {
    "new york", "nyc", "manhattan", "brooklyn",
    "los angeles", "santa monica", "west hollywood",
    "nashville", "davidson county",
    "austin", "dallas", "san antonio", "houston",
    "denver", "colorado springs",
    "miami", "miami beach", "fort lauderdale", "broward",
    "new orleans", "orleans parish",
    "honolulu", "maui", "hawaii",
    "san francisco", "san diego",
    "chicago", "portland", "seattle",
    "savannah", "charleston", "asheville",
    "scottsdale", "sedona", "flagstaff",
    "park city", "big bear", "lake tahoe",
    "jersey city", "atlantic city",
    "key west", "destin", "panama city beach",
    "gatlinburg", "pigeon forge", "sevierville",
    "orlando", "kissimmee", "davenport",
    "gulf shores", "orange beach",
    "myrtle beach", "hilton head",
    "cape cod", "nantucket", "martha's vineyard",
    "outer banks", "virginia beach",
    "lake havasu", "palm springs", "joshua tree",
    "breckenridge", "steamboat springs", "vail", "aspen",
}

# Oversaturated markets (ADR/occupancy declining)
OVERSATURATED_MARKETS = {
    "gatlinburg", "pigeon forge", "sevierville",
    "gulf shores", "orange beach",
    "orlando", "kissimmee", "davenport",
    "panama city beach", "destin",
    "myrtle beach", "north myrtle beach",
    "scottsdale", "phoenix",
    "branson", "big bear",
    "poconos", "pocono",
    "lake of the ozarks", "galveston",
    "fort myers", "cape coral", "puerto rico",
}

# States with complex STR tax regimes
HIGH_TAX_STATES = {
    "CA", "NY", "HI", "FL", "CO", "TN", "TX", "AZ", "OR", "WA",
    "NV", "SC", "NC", "GA", "LA", "MA", "NJ", "CT", "VT", "ME",
}

# Preferred sole-prop property types
PREFERRED_TYPES = {
    "house", "entire home", "cabin", "condo", "condominium",
    "apartment", "townhouse", "villa", "cottage", "bungalow",
    "chalet", "loft", "guest house", "guesthouse", "ranch",
    "farmhouse", "tiny house", "yurt", "treehouse", "a-frame",
}

# Corporate / PM company indicators
CORPORATE_RE = re.compile(
    r"\b(vacasa|evolve|sonder|turnkey|casago|avantstar|"
    r"property management|pm company)\b", re.IGNORECASE
)


def safe_float(val, default=0.0):
    if val is None or val == "":
        return default
    try:
        return float(str(val).strip().rstrip("%"))
    except (ValueError, TypeError):
        return default


def parse_month(s):
    """Parse '2026-01-01' to (year, month)."""
    try:
        parts = s.strip().split("-")
        return int(parts[0]), int(parts[1])
    except (IndexError, ValueError):
        return 0, 0


# ---------------------------------------------------------------------------
# SQLite schema and helpers
# ---------------------------------------------------------------------------

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS properties (
    pid TEXT PRIMARY KEY,
    property_type TEXT,
    listing_type TEXT,
    bedrooms REAL,
    city TEXT,
    state TEXT,
    zip TEXT,
    neighborhood TEXT,
    msa TEXT,
    lat REAL,
    lng REAL,
    airbnb_id TEXT,
    airbnb_host_id TEXT,
    vrbo_id TEXT,
    property_manager TEXT,
    active INT,
    months INT,
    total_revenue REAL,
    total_rev_potential REAL,
    total_reservations INT,
    total_res_days INT,
    total_avail_days INT,
    total_blocked_days INT,
    occ_sum REAL,
    occ_count INT,
    adr_high_sum REAL,
    adr_high_count INT,
    adr_low_sum REAL,
    adr_low_count INT,
    adr_all_sum REAL,
    adr_all_count INT,
    latest_year INT,
    latest_month INT,
    latest_active INT,
    latest_scraped INT,
    zero_booking_months INT
)
"""

UPSERT_SQL = """
INSERT INTO properties (
    pid, property_type, listing_type, bedrooms, city, state, zip,
    neighborhood, msa, lat, lng, airbnb_id, airbnb_host_id, vrbo_id,
    property_manager, active, months,
    total_revenue, total_rev_potential, total_reservations,
    total_res_days, total_avail_days, total_blocked_days,
    occ_sum, occ_count,
    adr_high_sum, adr_high_count, adr_low_sum, adr_low_count,
    adr_all_sum, adr_all_count,
    latest_year, latest_month, latest_active, latest_scraped,
    zero_booking_months
) VALUES (
    ?, ?, ?, ?, ?, ?, ?,
    ?, ?, ?, ?, ?, ?, ?,
    ?, ?, 1,
    ?, ?, ?,
    ?, ?, ?,
    ?, ?,
    ?, ?, ?, ?,
    ?, ?,
    ?, ?, ?, ?,
    ?
)
ON CONFLICT(pid) DO UPDATE SET
    months = months + 1,
    total_revenue = total_revenue + excluded.total_revenue,
    total_rev_potential = total_rev_potential + excluded.total_rev_potential,
    total_reservations = total_reservations + excluded.total_reservations,
    total_res_days = total_res_days + excluded.total_res_days,
    total_avail_days = total_avail_days + excluded.total_avail_days,
    total_blocked_days = total_blocked_days + excluded.total_blocked_days,
    occ_sum = occ_sum + excluded.occ_sum,
    occ_count = occ_count + excluded.occ_count,
    adr_high_sum = adr_high_sum + excluded.adr_high_sum,
    adr_high_count = adr_high_count + excluded.adr_high_count,
    adr_low_sum = adr_low_sum + excluded.adr_low_sum,
    adr_low_count = adr_low_count + excluded.adr_low_count,
    adr_all_sum = adr_all_sum + excluded.adr_all_sum,
    adr_all_count = adr_all_count + excluded.adr_all_count,
    zero_booking_months = zero_booking_months + excluded.zero_booking_months,
    -- Update property info if this row is from a later month
    property_manager = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.property_manager ELSE properties.property_manager END,
    active = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.active ELSE properties.active END,
    latest_active = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.latest_active ELSE properties.latest_active END,
    latest_scraped = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.latest_scraped ELSE properties.latest_scraped END,
    latest_year = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.latest_year ELSE properties.latest_year END,
    latest_month = CASE
        WHEN excluded.latest_year > properties.latest_year
             OR (excluded.latest_year = properties.latest_year AND excluded.latest_month > properties.latest_month)
        THEN excluded.latest_month ELSE properties.latest_month END
"""


# ---------------------------------------------------------------------------
# Phase 1: Stream & Aggregate per Property into SQLite
# ---------------------------------------------------------------------------

def aggregate_properties(csv_path: str, cutoff_year: int, cutoff_month: int, db_path: str):
    """
    Stream the raw AirDNA CSV.GZ and build per-property aggregates in SQLite.
    Only considers rows from cutoff_year/cutoff_month onward.
    Returns (db_path, property_count).
    """
    log.info("Phase 1: Streaming %s (cutoff: %d-%02d)", csv_path, cutoff_year, cutoff_month)
    log.info("  SQLite DB: %s", db_path)

    path_lower = csv_path.lower()
    if path_lower.endswith(".gz"):
        fh = io.TextIOWrapper(gzip.open(csv_path, "rb"), encoding="utf-8-sig")
    else:
        fh = open(csv_path, "r", encoding="utf-8-sig")

    # Set up SQLite
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = OFF")
    conn.execute("PRAGMA cache_size = -64000")  # 64MB cache
    conn.execute(CREATE_TABLE_SQL)
    conn.commit()

    total_rows = 0
    skipped_old = 0
    skipped_non_us = 0
    batch_count = 0

    try:
        reader = csv.DictReader(fh)
        for row in reader:
            total_rows += 1

            # Parse month
            year, month = parse_month(row.get("Reporting Month", ""))
            if year == 0:
                continue

            # Skip old data
            if (year, month) < (cutoff_year, cutoff_month):
                skipped_old += 1
                if total_rows % 500000 == 0:
                    log.info("  %dk rows | %dk skipped old",
                             total_rows // 1000, skipped_old // 1000)
                continue

            # Must be US
            country = (row.get("Country") or "").strip()
            if country and country != "United States":
                skipped_non_us += 1
                continue

            pid = row.get("Property ID", "").strip()
            if not pid:
                continue

            # Extract numeric fields
            revenue = safe_float(row.get("Revenue (USD)"))
            rev_potential = safe_float(row.get("Revenue Potential (USD)"))
            adr = safe_float(row.get("ADR (USD)"))
            occ_rate = safe_float(row.get("Occupancy Rate"))
            reservations = int(safe_float(row.get("Number of Reservations")))
            res_days = int(safe_float(row.get("Reservation Days")))
            avail_days = int(safe_float(row.get("Available Days")))
            blocked_days = int(safe_float(row.get("Blocked Days")))
            bedrooms = safe_float(row.get("Bedrooms"))

            is_high_season = month in HIGH_SEASON_MONTHS
            is_active = 1 if (row.get("Active") or "").strip().lower() == "true" else 0
            is_scraped = 1 if (row.get("Scraped During Month") or "").strip().lower() == "true" else 0

            # Occupancy accumulation
            occ_s = occ_rate if occ_rate > 0 else 0.0
            occ_c = 1 if occ_rate > 0 else 0

            # ADR accumulation
            adr_high_s = adr if (adr > 0 and is_high_season) else 0.0
            adr_high_c = 1 if (adr > 0 and is_high_season) else 0
            adr_low_s = adr if (adr > 0 and not is_high_season) else 0.0
            adr_low_c = 1 if (adr > 0 and not is_high_season) else 0
            adr_all_s = adr if adr > 0 else 0.0
            adr_all_c = 1 if adr > 0 else 0

            zero_bm = 1 if (reservations == 0 and res_days == 0) else 0

            conn.execute(UPSERT_SQL, (
                pid,
                (row.get("Property Type") or "").strip(),
                (row.get("Listing Type") or "").strip(),
                bedrooms,
                (row.get("City") or "").strip(),
                (row.get("State") or "").strip(),
                (row.get("Postal Code") or "").strip(),
                (row.get("Neighborhood") or "").strip(),
                (row.get("Metropolitan Statistical Area") or "").strip(),
                safe_float(row.get("Latitude")),
                safe_float(row.get("Longitude")),
                (row.get("Airbnb Property ID") or "").strip(),
                (row.get("Airbnb Host ID") or "").strip(),
                (row.get("Vrbo Property ID") or "").strip(),
                (row.get("Property Manager") or "").strip(),
                is_active,
                # months = 1 (initial, handled by INSERT default)
                revenue, rev_potential, reservations,
                res_days, avail_days, blocked_days,
                occ_s, occ_c,
                adr_high_s, adr_high_c, adr_low_s, adr_low_c,
                adr_all_s, adr_all_c,
                year, month, is_active, is_scraped,
                zero_bm,
            ))

            batch_count += 1
            if batch_count >= 10000:
                conn.commit()
                batch_count = 0

            if total_rows % 500000 == 0:
                log.info("  %dk rows | %dk skipped old",
                         total_rows // 1000, skipped_old // 1000)

    finally:
        fh.close()

    # Final commit
    conn.commit()

    # Get property count
    prop_count = conn.execute("SELECT COUNT(*) FROM properties").fetchone()[0]

    log.info("Phase 1 complete: %d total rows | %d unique properties | %d skipped (old) | %d skipped (non-US)",
             total_rows, prop_count, skipped_old, skipped_non_us)

    return conn, prop_count


# ---------------------------------------------------------------------------
# Phase 3: Score Each Property
# ---------------------------------------------------------------------------

def score_property(p: dict, host_property_count: int) -> Tuple[int, List[str]]:
    """
    Score a single aggregated property record.
    Returns (score, [reasons]).
    """
    score = 0
    reasons = []

    # --- Computed metrics ---
    months = max(p["months"], 1)
    avg_revenue_monthly = p["total_revenue"] / months
    annual_revenue_est = avg_revenue_monthly * 12
    avg_occ = (p["occ_sum"] / p["occ_count"]) if p["occ_count"] > 0 else 0
    avg_occ_pct = avg_occ * 100 if avg_occ <= 1 else avg_occ  # handle 0-1 vs 0-100 scale

    adr_high = (p["adr_high_sum"] / p["adr_high_count"]) if p["adr_high_count"] > 0 else 0
    adr_low = (p["adr_low_sum"] / p["adr_low_count"]) if p["adr_low_count"] > 0 else 0
    adr_avg = (p["adr_all_sum"] / p["adr_all_count"]) if p["adr_all_count"] > 0 else 0

    city_lower = p["city"].lower()
    state = p["state"].upper()
    msa_lower = p["msa"].lower()
    prop_type_lower = p["property_type"].lower()
    pm = p["property_manager"]
    bedrooms = p["bedrooms"]

    # ===================================================================
    # HARD FILTERS (instant disqualify — return score 0)
    # ===================================================================

    # Must have coordinates
    if not p["lat"] and not p["lng"]:
        return (0, ["NO_COORDS"])

    # Must be US (lat/lng bounds)
    lat, lng = p["lat"], p["lng"]
    if lat and lng:
        in_conus = (24.0 <= lat <= 49.5 and -125.0 <= lng <= -66.0)
        in_hawaii = (18.0 <= lat <= 23.0 and -161.0 <= lng <= -154.0)
        in_alaska = (51.0 <= lat <= 72.0 and -180.0 <= lng <= -130.0)
        in_pr = (17.5 <= lat <= 18.6 and -67.5 <= lng <= -65.0)
        if not (in_conus or in_hawaii or in_alaska or in_pr):
            return (0, ["NOT_US"])

    # Must be currently active
    if not p["active"]:
        return (0, ["INACTIVE"])

    # ADR minimum: $250 high season, $180 low season
    if adr_high > 0 and adr_high < MIN_ADR_HIGH_SEASON:
        return (0, [f"ADR_HIGH_SEASON_TOO_LOW_{adr_high:.0f}"])
    if adr_low > 0 and adr_low < MIN_ADR_LOW_SEASON:
        return (0, [f"ADR_LOW_SEASON_TOO_LOW_{adr_low:.0f}"])
    # If we only have overall ADR (no seasonal split), use low season threshold
    if p["adr_high_count"] == 0 and p["adr_low_count"] == 0 and adr_avg > 0:
        if adr_avg < MIN_ADR_LOW_SEASON:
            return (0, [f"ADR_OVERALL_TOO_LOW_{adr_avg:.0f}"])

    # Exclude known PM companies (Vacasa, Evolve, Sonder, etc.)
    if pm and CORPORATE_RE.search(pm):
        return (0, [f"KNOWN_PM_COMPANY_{pm[:30]}"])

    # Exclude hotels/hostels
    if "hotel" in prop_type_lower or "hostel" in prop_type_lower:
        return (0, ["HOTEL_TYPE"])

    # ===================================================================
    # TIER 1 SIGNALS (20-25 pts) — Strongest conversion indicators
    # ===================================================================

    # --- Low calendar bookings (high Available Days vs Reservation Days) ---
    total_calendar_days = p["total_res_days"] + p["total_avail_days"] + p["total_blocked_days"]
    if total_calendar_days > 0:
        booking_rate = p["total_res_days"] / total_calendar_days
        if booking_rate < 0.15:
            score += 25
            reasons.append(f"VERY_LOW_BOOKINGS_{booking_rate:.0%}")
        elif booking_rate < 0.30:
            score += 20
            reasons.append(f"LOW_BOOKINGS_{booking_rate:.0%}")
        elif booking_rate < 0.45:
            score += 12
            reasons.append(f"BELOW_AVG_BOOKINGS_{booking_rate:.0%}")

    # --- Revenue underperformance vs potential ---
    if p["total_rev_potential"] > 0 and p["total_revenue"] > 0:
        perf_ratio = p["total_revenue"] / p["total_rev_potential"]
        if perf_ratio < 0.50:
            score += 25
            reasons.append(f"SEVERE_UNDERPERFORMANCE_{perf_ratio:.0%}")
        elif perf_ratio < 0.65:
            score += 20
            reasons.append(f"UNDERPERFORMING_{perf_ratio:.0%}")
        elif perf_ratio < 0.80:
            score += 12
            reasons.append(f"SLIGHT_UNDERPERFORMANCE_{perf_ratio:.0%}")

    # --- Low occupancy ---
    if avg_occ_pct > 0:
        if avg_occ_pct < 25:
            score += 25
            reasons.append(f"VERY_LOW_OCCUPANCY_{avg_occ_pct:.0f}%")
        elif avg_occ_pct < 40:
            score += 20
            reasons.append(f"LOW_OCCUPANCY_{avg_occ_pct:.0f}%")
        elif avg_occ_pct < 55:
            score += 12
            reasons.append(f"BELOW_AVG_OCCUPANCY_{avg_occ_pct:.0f}%")

    # --- Zero booking months (calendar sitting empty) ---
    if months >= 3:
        zero_pct = p["zero_booking_months"] / months
        if zero_pct >= 0.60:
            score += 22
            reasons.append(f"MOSTLY_EMPTY_CALENDAR_{zero_pct:.0%}")
        elif zero_pct >= 0.40:
            score += 15
            reasons.append(f"MANY_EMPTY_MONTHS_{zero_pct:.0%}")

    # --- New property with few bookings (< 3 months of data, low res days) ---
    if months <= 3 and p["total_res_days"] < 10:
        score += 20
        reasons.append(f"NEW_LISTING_LOW_TRACTION_{months}mo_{p['total_res_days']}days")

    # ===================================================================
    # TIER 2 SIGNALS (10-18 pts)
    # ===================================================================

    # --- Portfolio size (host property count) ---
    if host_property_count >= 1:
        if 2 <= host_property_count <= 5:
            score += 18
            reasons.append(f"SWEET_SPOT_{host_property_count}_PROPERTIES")
        elif host_property_count == 1:
            score += 10
            reasons.append("SINGLE_PROPERTY")
        elif host_property_count <= 10:
            score += 5
            reasons.append(f"SMALL_PORTFOLIO_{host_property_count}")
        else:
            score -= 10
            reasons.append(f"LARGE_OPERATOR_{host_property_count}")

    # --- Regulated market ---
    in_regulated = any(rm in msa_lower or rm in city_lower for rm in REGULATED_MARKETS)
    if in_regulated:
        score += 15
        reasons.append("REGULATED_MARKET")

    # --- Oversaturated market ---
    in_oversaturated = any(om in msa_lower or om in city_lower for om in OVERSATURATED_MARKETS)
    if in_oversaturated:
        score += 12
        reasons.append("OVERSATURATED_MARKET")

    # --- High tax complexity state ---
    if state in HIGH_TAX_STATES:
        score += 8
        reasons.append(f"HIGH_TAX_STATE_{state}")

    # --- Property type fit ---
    type_match = any(pt in prop_type_lower for pt in PREFERRED_TYPES)
    if type_match:
        score += 10
        reasons.append("PREFERRED_PROPERTY_TYPE")

    # --- Bedroom sweet spot (2-5 BR) ---
    if 2 <= bedrooms <= 5:
        score += 8
        reasons.append(f"IDEAL_SIZE_{bedrooms:.0f}BR")
    elif bedrooms == 1:
        score += 2
        reasons.append("STUDIO_1BR")
    elif bedrooms > 5:
        score += 5
        reasons.append("LARGE_PROPERTY")

    # --- Revenue tier (must be worth managing) ---
    if annual_revenue_est >= 50000:
        score += 15
        reasons.append(f"HIGH_REVENUE_{annual_revenue_est:,.0f}")
    elif annual_revenue_est >= 30000:
        score += 10
        reasons.append(f"MODERATE_REVENUE_{annual_revenue_est:,.0f}")
    elif annual_revenue_est > 0 and annual_revenue_est < 15000:
        score -= 5
        reasons.append("LOW_VALUE_PROPERTY")

    # ===================================================================
    # COMPOSITE BONUSES
    # ===================================================================

    # Triple threat: low occupancy + underperforming + regulated
    if avg_occ_pct > 0 and avg_occ_pct < 50 and in_regulated:
        if p["total_rev_potential"] > 0 and p["total_revenue"] / p["total_rev_potential"] < 0.70:
            score += 15
            reasons.append("TRIPLE_THREAT_BONUS")

    # High ADR but low bookings = money left on table
    if adr_avg >= 300 and avg_occ_pct > 0 and avg_occ_pct < 45:
        score += 12
        reasons.append("HIGH_ADR_LOW_BOOKINGS")

    # Clamp
    score = max(0, min(100, score))

    return (score, reasons)


# ---------------------------------------------------------------------------
# Phase 4: Output
# ---------------------------------------------------------------------------

def write_leads(props_scored: list, output_path: Path, count: int):
    """Write top N scored properties to CSV."""
    # props_scored is already a min-heap of (score, counter, reasons, p, hcount)
    # Convert to sorted list (highest score first)
    top_n = []
    while props_scored:
        s, _counter, reasons, p, hcount = heapq.heappop(props_scored)
        top_n.append((s, reasons, p, hcount))
    top_n.reverse()  # heappop gives smallest first, we want descending

    # Take top N (already limited by heap size, but just in case)
    top_n = top_n[:count]

    fieldnames = [
        "icp_score", "icp_tier", "icp_reasons",
        "property_id", "airbnb_property_id", "vrbo_property_id",
        "airbnb_host_id", "property_type", "listing_type",
        "bedrooms", "city", "state", "zip", "neighborhood", "msa",
        "latitude", "longitude",
        "avg_monthly_revenue", "annual_revenue_est",
        "avg_occupancy_pct", "avg_adr",
        "adr_high_season", "adr_low_season",
        "total_reservations", "total_reservation_days",
        "total_available_days", "zero_booking_months",
        "months_of_data", "revenue_vs_potential_pct",
        "host_property_count", "property_manager",
        "booking_rate_pct", "active",
    ]

    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()

        for score, reasons, p, host_count in top_n:
            months = max(p["months"], 1)
            avg_rev = p["total_revenue"] / months
            annual_rev = avg_rev * 12
            avg_occ = (p["occ_sum"] / p["occ_count"] * 100) if p["occ_count"] > 0 else 0
            adr_h = (p["adr_high_sum"] / p["adr_high_count"]) if p["adr_high_count"] > 0 else 0
            adr_l = (p["adr_low_sum"] / p["adr_low_count"]) if p["adr_low_count"] > 0 else 0
            adr_a = (p["adr_all_sum"] / p["adr_all_count"]) if p["adr_all_count"] > 0 else 0
            total_cal = p["total_res_days"] + p["total_avail_days"] + p["total_blocked_days"]
            booking_rate = (p["total_res_days"] / total_cal * 100) if total_cal > 0 else 0
            perf = (p["total_revenue"] / p["total_rev_potential"] * 100) if p["total_rev_potential"] > 0 else 0

            tier = (
                "T1_HOT" if score >= 90 else
                "T2_HIGH" if score >= 70 else
                "T3_MODERATE" if score >= 50 else
                "T4_NURTURE"
            )

            writer.writerow({
                "icp_score": score,
                "icp_tier": tier,
                "icp_reasons": "|".join(reasons),
                "property_id": p["pid"],
                "airbnb_property_id": p["airbnb_id"],
                "vrbo_property_id": p["vrbo_id"],
                "airbnb_host_id": p["airbnb_host_id"],
                "property_type": p["property_type"],
                "listing_type": p["listing_type"],
                "bedrooms": int(p["bedrooms"]),
                "city": p["city"],
                "state": p["state"],
                "zip": p["zip"],
                "neighborhood": p["neighborhood"],
                "msa": p["msa"],
                "latitude": p["lat"],
                "longitude": p["lng"],
                "avg_monthly_revenue": round(avg_rev, 2),
                "annual_revenue_est": round(annual_rev, 2),
                "avg_occupancy_pct": round(avg_occ, 1),
                "avg_adr": round(adr_a, 2),
                "adr_high_season": round(adr_h, 2),
                "adr_low_season": round(adr_l, 2),
                "total_reservations": p["total_reservations"],
                "total_reservation_days": p["total_res_days"],
                "total_available_days": p["total_avail_days"],
                "zero_booking_months": p["zero_booking_months"],
                "months_of_data": months,
                "revenue_vs_potential_pct": round(perf, 1),
                "host_property_count": host_count,
                "property_manager": p["property_manager"],
                "booking_rate_pct": round(booking_rate, 1),
                "active": p["active"],
            })

    log.info("Wrote %d leads to %s", len(top_n), output_path)
    return len(top_n)


# ---------------------------------------------------------------------------
# Helper: Convert SQLite row to dict
# ---------------------------------------------------------------------------

def row_to_dict(row):
    """Convert a sqlite3.Row to a plain dict for scoring."""
    return {
        "pid": row["pid"],
        "property_type": row["property_type"] or "",
        "listing_type": row["listing_type"] or "",
        "bedrooms": row["bedrooms"] or 0.0,
        "city": row["city"] or "",
        "state": row["state"] or "",
        "zip": row["zip"] or "",
        "neighborhood": row["neighborhood"] or "",
        "msa": row["msa"] or "",
        "lat": row["lat"] or 0.0,
        "lng": row["lng"] or 0.0,
        "airbnb_id": row["airbnb_id"] or "",
        "airbnb_host_id": row["airbnb_host_id"] or "",
        "vrbo_id": row["vrbo_id"] or "",
        "property_manager": row["property_manager"] or "",
        "active": bool(row["active"]),
        "months": row["months"] or 0,
        "total_revenue": row["total_revenue"] or 0.0,
        "total_rev_potential": row["total_rev_potential"] or 0.0,
        "total_reservations": row["total_reservations"] or 0,
        "total_res_days": row["total_res_days"] or 0,
        "total_avail_days": row["total_avail_days"] or 0,
        "total_blocked_days": row["total_blocked_days"] or 0,
        "occ_sum": row["occ_sum"] or 0.0,
        "occ_count": row["occ_count"] or 0,
        "adr_high_sum": row["adr_high_sum"] or 0.0,
        "adr_high_count": row["adr_high_count"] or 0,
        "adr_low_sum": row["adr_low_sum"] or 0.0,
        "adr_low_count": row["adr_low_count"] or 0,
        "adr_all_sum": row["adr_all_sum"] or 0.0,
        "adr_all_count": row["adr_all_count"] or 0,
        "latest_year": row["latest_year"] or 0,
        "latest_month": row["latest_month"] or 0,
        "latest_active": bool(row["latest_active"]),
        "latest_scraped": bool(row["latest_scraped"]),
        "zero_booking_months": row["zero_booking_months"] or 0,
    }


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Daily 10K Lead Extract from AirDNA")
    parser.add_argument("input", help="AirDNA CSV or CSV.GZ file")
    parser.add_argument("-o", "--output-dir", default="./daily_leads", help="Output directory")
    parser.add_argument("-n", "--count", type=int, default=DEFAULT_LEAD_COUNT, help="Number of leads to output (default: 10000)")
    parser.add_argument("--lookback", type=int, default=LOOKBACK_MONTHS, help="Months of data to consider (default: 6)")
    parser.add_argument("--min-score", type=int, default=30, help="Minimum score to qualify (default: 30)")
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(level=level, format=LOG_FORMAT)

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Calculate cutoff date
    now = datetime.now()
    cutoff = now - timedelta(days=args.lookback * 30)
    cutoff_year, cutoff_month = cutoff.year, cutoff.month

    log.info("=" * 70)
    log.info("DAILY LEAD EXTRACT — %s", now.strftime("%Y-%m-%d %H:%M"))
    log.info("Target: %d leads | Lookback: %d months | Min score: %d",
             args.count, args.lookback, args.min_score)
    log.info("ADR minimums: $%.0f high season / $%.0f low season",
             MIN_ADR_HIGH_SEASON, MIN_ADR_LOW_SEASON)
    log.info("=" * 70)

    # SQLite temp database path
    db_path = os.path.join(tempfile.gettempdir(), "icp_agg.db")
    # Remove stale DB from previous run
    if os.path.exists(db_path):
        os.remove(db_path)

    conn = None
    try:
        # Phase 1: Aggregate into SQLite
        conn, prop_count = aggregate_properties(args.input, cutoff_year, cutoff_month, db_path)
        conn.row_factory = sqlite3.Row

        # Phase 2: Host property counts (via SQL)
        log.info("Phase 2: Counting host properties via SQL...")
        host_counts = {}
        cursor = conn.execute(
            "SELECT airbnb_host_id, COUNT(*) as cnt FROM properties "
            "WHERE airbnb_host_id != '' GROUP BY airbnb_host_id"
        )
        for row in cursor:
            host_counts[row["airbnb_host_id"]] = row["cnt"]
        log.info("Phase 2: %d unique hosts", len(host_counts))

        # Phase 3: Score — stream from SQLite, use min-heap for top N
        log.info("Phase 3: Scoring %d properties...", prop_count)
        heap = []  # min-heap of (score, counter, reasons, p_dict, hcount)
        counter = 0  # tie-breaker for heap
        disqualified = 0
        disq_reasons = defaultdict(int)
        qualified_count = 0

        cursor = conn.execute("SELECT * FROM properties")
        for row in cursor:
            p = row_to_dict(row)
            hid = p.get("airbnb_host_id", "")
            hcount = host_counts.get(hid, 1)

            s, reasons = score_property(p, hcount)

            if s >= args.min_score:
                qualified_count += 1
                counter += 1
                if len(heap) < args.count:
                    heapq.heappush(heap, (s, counter, reasons, p, hcount))
                elif s > heap[0][0]:
                    heapq.heapreplace(heap, (s, counter, reasons, p, hcount))
            else:
                disqualified += 1
                if reasons:
                    disq_reasons[reasons[0]] += 1

        log.info("Phase 3 complete: %d qualified | %d disqualified", qualified_count, disqualified)
        log.info("Top disqualification reasons:")
        for reason, count in sorted(disq_reasons.items(), key=lambda x: -x[1])[:10]:
            log.info("  %s: %d", reason, count)

        # Phase 4: Output
        timestamp = now.strftime("%Y%m%d")
        output_path = output_dir / f"leads_{timestamp}.csv"

        # Check for existing file (don't overwrite today's run)
        if output_path.exists():
            output_path = output_dir / f"leads_{now.strftime('%Y%m%d_%H%M%S')}.csv"

        written = write_leads(heap, output_path, args.count)

        # Write summary — count tiers from the heap before it was consumed
        # Re-read from output to count tiers
        tier_counts = {"T1": 0, "T2": 0, "T3": 0, "T4": 0}
        with open(output_path, "r", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                tier = row.get("icp_tier", "")
                if tier == "T1_HOT":
                    tier_counts["T1"] += 1
                elif tier == "T2_HIGH":
                    tier_counts["T2"] += 1
                elif tier == "T3_MODERATE":
                    tier_counts["T3"] += 1
                elif tier == "T4_NURTURE":
                    tier_counts["T4"] += 1

        summary = {
            "date": now.isoformat(),
            "total_properties_analyzed": prop_count,
            "qualified": qualified_count,
            "output_count": written,
            "tiers": tier_counts,
            "disqualified": disqualified,
            "top_disq_reasons": dict(sorted(disq_reasons.items(), key=lambda x: -x[1])[:10]),
            "output_file": str(output_path),
        }
        summary_path = output_dir / f"summary_{timestamp}.json"
        with open(summary_path, "w") as f:
            json.dump(summary, f, indent=2)

        log.info("=" * 70)
        log.info("DAILY EXTRACT COMPLETE")
        log.info("  Properties analyzed: %d", prop_count)
        log.info("  Qualified: %d | Output: %d", qualified_count, written)
        log.info("  T1 (90+): %d | T2 (70-89): %d | T3 (50-69): %d | T4 (30-49): %d",
                 tier_counts["T1"], tier_counts["T2"], tier_counts["T3"], tier_counts["T4"])
        log.info("  Output: %s", output_path)
        log.info("=" * 70)

    finally:
        if conn:
            conn.close()
        # Clean up temp database
        if os.path.exists(db_path):
            try:
                os.remove(db_path)
                log.info("Cleaned up temp DB: %s", db_path)
            except OSError:
                log.warning("Could not remove temp DB: %s", db_path)


if __name__ == "__main__":
    main()
