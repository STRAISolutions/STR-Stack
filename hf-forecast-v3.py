#!/usr/bin/env python3
"""
Hostfully Revenue Forecast v3 -- STR Portfolio Analysis
Covers Apr 13 - Sep 1, 2026 (~20 weekly buckets)
Uses _limit=100 and cursor pagination for ALL data.
Factors 25% natural booking growth on remaining availability.

API FIELD NOTES (v3.2):
  - Properties list response: {"properties": [...], "_metadata": {...}, "_paging": {...}}
  - Individual property: {"property": {...}} with pricing.dailyRate, pricing.cleaningFee
  - Leads list response: {"leads": [...], "_metadata": {...}, "_paging": {...}}
  - Lead dates: checkInLocalDateTime, checkOutLocalDateTime (ISO format)
  - Lead revenue: NOT in API -- calculated from property pricing
"""

import json, sys, time, math
from datetime import datetime, timedelta, date
from urllib.request import Request, urlopen
from urllib.parse import urlencode
from urllib.error import HTTPError

API_KEY   = "ukNruuLswAygrvUi"
AGENCY    = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE      = "https://platform.hostfully.com/api/v3.2"
HEADERS   = {"X-HOSTFULLY-APIKEY": API_KEY, "Accept": "application/json"}

FORECAST_START = date(2026, 4, 13)   # Monday
FORECAST_END   = date(2026, 9, 1)    # Tuesday
GROWTH_FACTOR  = 0.25                 # 25% natural booking growth

# -- helpers -------------------------------------------------------------------
def api_get(path, params=None, retries=3):
    url = BASE + path
    if params:
        url += ("&" if "?" in url else "?") + urlencode(params)
    for attempt in range(retries):
        try:
            req = Request(url, headers=HEADERS)
            with urlopen(req, timeout=30) as resp:
                return json.loads(resp.read())
        except HTTPError as e:
            body = e.read().decode() if hasattr(e, "read") else ""
            if e.code == 429 or e.code >= 500:
                wait = 2 ** (attempt + 1)
                print("  [retry {}] HTTP {} on {} -- waiting {}s".format(
                    attempt+1, e.code, path, wait), file=sys.stderr)
                time.sleep(wait)
                continue
            print("  HTTP {}: {}".format(e.code, body[:300]), file=sys.stderr)
            raise
        except Exception:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return None


def parse_lead_date(lead, prefix):
    """Extract date from a lead using checkIn/checkOut fields."""
    for field in [prefix + "LocalDateTime", prefix + "ZonedDateTime",
                  prefix + "Date", prefix]:
        val = lead.get(field)
        if val and isinstance(val, str) and len(val) >= 10:
            try:
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except ValueError:
                continue
    return None


def count_weekend_nights(ci, co):
    """Count Friday and Saturday nights in a stay (for weekend surcharge)."""
    count = 0
    d = ci
    while d < co:
        if d.weekday() in (4, 5):  # Friday=4, Saturday=5
            count += 1
        d += timedelta(days=1)
    return count


# == 1. Fetch ALL properties ===================================================
print("=" * 80)
print("  HOSTFULLY REVENUE FORECAST v3  --  STR Portfolio Analysis")
print("  Forecast window: {} -> {}".format(FORECAST_START, FORECAST_END))
print("=" * 80)
print()

print("[1/4] Fetching properties ...")

all_properties = []
cursor = None
page = 0
while True:
    page += 1
    params = {"agencyUid": AGENCY, "_limit": 100}
    if cursor:
        params["_cursor"] = cursor
    data = api_get("/properties", params)
    if not data:
        break
    if isinstance(data, dict):
        batch = data.get("properties", [])
        all_properties.extend(batch)
        paging = data.get("_paging", {})
        cursor = paging.get("_nextCursor")
        if not cursor:
            break
    elif isinstance(data, list):
        all_properties.extend(data)
        break
    else:
        break

print("  -> Total properties fetched: {} (pages: {})".format(len(all_properties), page))

# Filter active
active_props = [p for p in all_properties if p.get("isActive") is True]
if not active_props:
    active_props = [p for p in all_properties if p.get("isActive") is not False]

print("  -> Active properties: {}".format(len(active_props)))
print()

# == 2. For each property: get detail + leads ==================================
print("[2/4] Fetching property details + bookings ...")

property_data = []
total_leads_fetched = 0

for i, prop in enumerate(active_props):
    uid = prop.get("uid")
    name = prop.get("name", uid[:12])

    sys.stdout.write("\r  Processing {}/{}: {:<40}".format(
        i+1, len(active_props), name[:40]))
    sys.stdout.flush()

    # --- Get individual property detail for pricing ---
    detail_raw = api_get("/properties/{}".format(uid))
    daily_rate = 0.0
    cleaning_fee = 0.0
    weekend_adj = 0.0
    bedrooms = 0
    tax_rate = 0.0

    if detail_raw:
        # Response is {"property": {...}} for single property
        detail = detail_raw.get("property", detail_raw) if isinstance(detail_raw, dict) else detail_raw
        pricing = detail.get("pricing") or {}
        daily_rate = float(pricing.get("dailyRate") or 0)
        cleaning_fee = float(pricing.get("cleaningFee") or 0)
        weekend_adj = float(pricing.get("weekendAdjustmentRate") or 0)
        tax_rate = float(pricing.get("taxRate") or 0)
        bedrooms = detail.get("bedrooms") or 0
        name = detail.get("name") or name

    # --- Get all leads (bookings + blocks) with pagination ---
    leads = []
    lead_cursor = None
    while True:
        lparams = {
            "propertyUid": uid,
            "_limit": 100,
            "checkInFrom": "2026-01-01",
            "checkInTo": "2026-09-01",
        }
        if lead_cursor:
            lparams["_cursor"] = lead_cursor
        leads_raw = api_get("/leads", lparams)
        if not leads_raw:
            break
        if isinstance(leads_raw, dict):
            batch = leads_raw.get("leads", [])
            leads.extend(batch)
            paging = leads_raw.get("_paging", {})
            lead_cursor = paging.get("_nextCursor")
            if not lead_cursor:
                break
        elif isinstance(leads_raw, list):
            leads.extend(leads_raw)
            break
        else:
            break

    total_leads_fetched += len(leads)

    # --- Classify leads ---
    BLOCK_TYPES = {"BLOCK", "BLOCKED"}
    BAD_STATUSES = {"BLOCKED", "CANCELLED", "CANCELED", "DECLINED"}

    real_bookings = []
    block_entries = []
    for lead in leads:
        lead_type = str(lead.get("type", "")).upper()
        lead_status = str(lead.get("status", "")).upper()

        if lead_type in BLOCK_TYPES:
            block_entries.append(lead)
            continue
        if lead_status in BAD_STATUSES:
            continue
        real_bookings.append(lead)

    # --- Calculate per-property stats ---
    total_booked_nights = 0
    total_revenue = 0.0
    booking_details = []

    for bk in real_bookings:
        ci = parse_lead_date(bk, "checkIn")
        co = parse_lead_date(bk, "checkOut")
        if not ci or not co:
            continue
        nights = (co - ci).days
        if nights <= 0:
            continue

        # Calculate revenue from property pricing
        weekday_nights = nights - count_weekend_nights(ci, co)
        weekend_nights = count_weekend_nights(ci, co)
        weekday_rev = weekday_nights * daily_rate
        weekend_rev = weekend_nights * daily_rate * (1.0 + weekend_adj)
        bk_revenue = weekday_rev + weekend_rev + cleaning_fee

        total_booked_nights += nights
        total_revenue += bk_revenue
        booking_details.append({
            "checkIn": ci,
            "checkOut": co,
            "nights": nights,
            "revenue": bk_revenue,
            "status": bk.get("status", ""),
            "channel": bk.get("channel", ""),
        })

    # --- Block details ---
    total_blocked_nights = 0
    block_details = []
    for blk in block_entries:
        ci = parse_lead_date(blk, "checkIn")
        co = parse_lead_date(blk, "checkOut")
        if not ci or not co:
            continue
        nights = (co - ci).days
        if nights <= 0:
            continue
        total_blocked_nights += nights
        block_details.append({"checkIn": ci, "checkOut": co, "nights": nights})

    effective_rate = (total_revenue / total_booked_nights) if total_booked_nights > 0 else daily_rate

    property_data.append({
        "uid": uid,
        "name": name,
        "dailyRate": daily_rate,
        "cleaningFee": cleaning_fee,
        "weekendAdj": weekend_adj,
        "bedrooms": bedrooms,
        "effectiveRate": effective_rate,
        "totalBookedNights": total_booked_nights,
        "totalBlockedNights": total_blocked_nights,
        "totalRevenue": total_revenue,
        "bookings": booking_details,
        "blocks": block_details,
        "bookingCount": len(real_bookings),
        "blockCount": len(block_entries),
    })

    time.sleep(0.15)  # rate-limit courtesy

print("\r  -> Done. {} properties processed, {} total leads fetched.         ".format(
    len(property_data), total_leads_fetched))
print()

# == 3. Build weekly forecast ===================================================
print("[3/4] Building weekly forecast ...")

weeks = []
current = FORECAST_START
while current < FORECAST_END:
    week_end = min(current + timedelta(days=6), FORECAST_END)
    weeks.append((current, week_end))
    current += timedelta(days=7)

num_active = len(property_data)

# Portfolio avg effective nightly rate
avg_rates = [p["effectiveRate"] for p in property_data if p["effectiveRate"] > 0]
portfolio_avg_nightly = sum(avg_rates) / len(avg_rates) if avg_rates else 150.0

weekly_stats = []

for week_start, week_end in weeks:
    week_days = (week_end - week_start).days + 1
    total_property_nights = num_active * week_days

    booked_in_week = 0
    blocked_in_week = 0
    revenue_in_week = 0.0

    for prop in property_data:
        for bk in prop["bookings"]:
            overlap_start = max(bk["checkIn"], week_start)
            overlap_end = min(bk["checkOut"], week_end + timedelta(days=1))
            overlap_nights = (overlap_end - overlap_start).days
            if overlap_nights > 0:
                booked_in_week += overlap_nights
                if bk["nights"] > 0:
                    revenue_in_week += bk["revenue"] * (overlap_nights / bk["nights"])

        for blk in prop["blocks"]:
            overlap_start = max(blk["checkIn"], week_start)
            overlap_end = min(blk["checkOut"], week_end + timedelta(days=1))
            overlap_nights = (overlap_end - overlap_start).days
            if overlap_nights > 0:
                blocked_in_week += overlap_nights

    available_in_week = max(0, total_property_nights - booked_in_week - blocked_in_week)

    predicted_new_nights = available_in_week * GROWTH_FACTOR
    predicted_new_revenue = predicted_new_nights * portfolio_avg_nightly
    total_predicted_revenue = revenue_in_week + predicted_new_revenue

    occ_existing = (booked_in_week / total_property_nights * 100) if total_property_nights else 0
    occ_with_growth = ((booked_in_week + predicted_new_nights) / total_property_nights * 100) if total_property_nights else 0

    weekly_stats.append({
        "week_start": week_start,
        "week_end": week_end,
        "days": week_days,
        "total_nights": total_property_nights,
        "booked": booked_in_week,
        "blocked": blocked_in_week,
        "available": available_in_week,
        "existing_revenue": revenue_in_week,
        "predicted_new_nights": predicted_new_nights,
        "predicted_new_revenue": predicted_new_revenue,
        "total_predicted_revenue": total_predicted_revenue,
        "occ_existing": occ_existing,
        "occ_with_growth": occ_with_growth,
    })

print("  -> Done.")
print()

# == 4. OUTPUT ==================================================================
print("[4/4] Generating report ...")
print()
print("=" * 110)
print("  PER-PROPERTY SUMMARY  (Jan 1 - Sep 1, 2026 bookings)")
print("=" * 110)
print("{:<4} {:<36} {:>8} {:>7} {:>5} {:>7} {:>7} {:>12} {:>8}".format(
    "#", "Property Name", "Rate", "Clean", "Bkgs", "Nights", "Blocks",
    "Revenue", "EffRate"))
print("-" * 110)

sorted_props = sorted(property_data, key=lambda x: x["totalRevenue"], reverse=True)

grand_total_revenue = 0
grand_total_nights = 0
grand_total_bookings = 0
grand_total_blocked = 0

for idx, p in enumerate(sorted_props, 1):
    grand_total_revenue += p["totalRevenue"]
    grand_total_nights += p["totalBookedNights"]
    grand_total_bookings += p["bookingCount"]
    grand_total_blocked += p["totalBlockedNights"]

    print("{:<4} {:<36} ${:>6.0f}  ${:>5.0f}  {:>4}  {:>6}  {:>6}  ${:>10,.0f}  ${:>6.0f}".format(
        idx, p["name"][:35], p["dailyRate"], p["cleaningFee"],
        p["bookingCount"], p["totalBookedNights"], p["totalBlockedNights"],
        p["totalRevenue"], p["effectiveRate"]))

print("-" * 110)
print("{:4} {:<36} {:>8} {:>7} {:>5} {:>7} {:>7}  ${:>10,.0f}".format(
    "", "TOTAL", "", "", grand_total_bookings, grand_total_nights,
    grand_total_blocked, grand_total_revenue))
print()

# Occupancy (Jan 1 - Sep 1 = 243 days)
total_possible_nights = num_active * 243
portfolio_occ = (grand_total_nights / total_possible_nights * 100) if total_possible_nights else 0
avg_eff_rate = (grand_total_revenue / grand_total_nights) if grand_total_nights > 0 else 0

print("  Portfolio occupancy (Jan 1 - Sep 1): {} / {} nights = {:.1f}%".format(
    grand_total_nights, total_possible_nights, portfolio_occ))
print("  Avg effective nightly rate (incl cleaning fee): ${:,.2f}".format(avg_eff_rate))
print("  Avg daily rate (base, excl cleaning): ${:,.2f}".format(
    sum(p["dailyRate"] for p in property_data) / num_active if num_active else 0))
print("  Portfolio avg nightly (used for projections): ${:,.2f}".format(portfolio_avg_nightly))
print("  Average revenue per property (Jan-Sep): ${:,.0f}".format(
    grand_total_revenue / num_active if num_active else 0))
print()

# -- WEEKLY FORECAST TABLE -----------------------------------------------------
print("=" * 140)
print("  WEEKLY REVENUE FORECAST  (Apr 13 - Sep 1, 2026)")
print("  Growth assumption: 25% of remaining availability converts to new bookings")
print("  Portfolio avg nightly rate for projections: ${:,.2f}".format(portfolio_avg_nightly))
print("=" * 140)
print("{:<5} {:<25} {:>4} {:>7} {:>7} {:>7} {:>7} {:>12} {:>7} {:>12} {:>12} {:>6} {:>6}".format(
    "Week", "Dates", "Days", "MaxNts", "Booked", "Block", "Avail",
    "ExistRev", "NewNts", "NewRev", "TotalRev", "Occ%", "w/Grw"))
print("-" * 140)

forecast_total_existing = 0
forecast_total_new = 0
forecast_total_combined = 0
forecast_total_booked = 0
forecast_total_new_nights = 0.0
forecast_total_blocked = 0

for i, ws in enumerate(weekly_stats, 1):
    s = ws["week_start"].strftime("%b %d")
    e = ws["week_end"].strftime("%b %d")
    dates = "{} - {}".format(s, e)

    forecast_total_existing += ws["existing_revenue"]
    forecast_total_new += ws["predicted_new_revenue"]
    forecast_total_combined += ws["total_predicted_revenue"]
    forecast_total_booked += ws["booked"]
    forecast_total_new_nights += ws["predicted_new_nights"]
    forecast_total_blocked += ws["blocked"]

    print("W{:<4} {:<25} {:>4} {:>7} {:>7} {:>7} {:>7} ${:>10,.0f} {:>6.0f} ${:>10,.0f} ${:>10,.0f} {:>5.1f}% {:>5.1f}%".format(
        i, dates, ws["days"], ws["total_nights"], ws["booked"], ws["blocked"],
        ws["available"], ws["existing_revenue"],
        ws["predicted_new_nights"], ws["predicted_new_revenue"],
        ws["total_predicted_revenue"], ws["occ_existing"], ws["occ_with_growth"]))

print("-" * 140)
num_weeks = len(weekly_stats)
print("{:<5} {:<25} {:>4} {:>7} {:>7.0f} {:>7.0f} {:>7} ${:>10,.0f} {:>6.0f} ${:>10,.0f} ${:>10,.0f}".format(
    "TOTAL", "", "", "", forecast_total_booked, forecast_total_blocked, "",
    forecast_total_existing, forecast_total_new_nights,
    forecast_total_new, forecast_total_combined))
print()

avg_weekly_existing = forecast_total_existing / num_weeks if num_weeks else 0
avg_weekly_combined = forecast_total_combined / num_weeks if num_weeks else 0

print("  Average weekly revenue (existing bookings only): ${:,.0f}".format(avg_weekly_existing))
print("  Average weekly revenue (with 25% growth):       ${:,.0f}".format(avg_weekly_combined))
print()

# -- PORTFOLIO SUMMARY + INVENTORY RECOMMENDATION ------------------------------
print("=" * 100)
print("  PORTFOLIO SUMMARY & INVENTORY GROWTH RECOMMENDATION")
print("=" * 100)
print()
print("  Current active properties:           {}".format(num_active))
print("  Total bookings (Jan-Sep 2026):       {}".format(grand_total_bookings))
print("  Total booked nights:                 {}".format(grand_total_nights))
print("  Total blocked nights:                {}".format(grand_total_blocked))
print("  Total revenue (existing bookings):   ${:,.0f}".format(grand_total_revenue))
print("  Average effective nightly rate:       ${:,.2f}".format(avg_eff_rate))
print("  Portfolio occupancy (Jan-Sep):        {:.1f}%".format(portfolio_occ))
print()

print("  FORECAST PERIOD (Apr 13 - Sep 1, ~{} weeks):".format(num_weeks))
print("  " + "-" * 45)
print("  Existing booking revenue:            ${:>12,.0f}".format(forecast_total_existing))
print("  Predicted new booking revenue (25%): ${:>12,.0f}".format(forecast_total_new))
print("  TOTAL projected revenue:             ${:>12,.0f}".format(forecast_total_combined))
print("  Average weekly (existing):           ${:>12,.0f}".format(avg_weekly_existing))
print("  Average weekly (with growth):        ${:>12,.0f}".format(avg_weekly_combined))
print()

# How many properties needed for $6,000/week increase
print("  INVENTORY INCREASE ANALYSIS")
print("  " + "-" * 45)
target_increase = 6000

rev_per_prop_per_week_existing = avg_weekly_existing / num_active if num_active else 0
rev_per_prop_per_week_growth = avg_weekly_combined / num_active if num_active else 0

print("  Revenue per property per week (existing):  ${:,.0f}".format(rev_per_prop_per_week_existing))
print("  Revenue per property per week (w/ growth):  ${:,.0f}".format(rev_per_prop_per_week_growth))
print()
print("  TARGET: +${:,}/week additional revenue".format(target_increase))
print()

props_needed_conservative = math.ceil(target_increase / rev_per_prop_per_week_existing) if rev_per_prop_per_week_existing > 0 else 999
props_needed_growth = math.ceil(target_increase / rev_per_prop_per_week_growth) if rev_per_prop_per_week_growth > 0 else 999

print("  SCENARIO A - Conservative (existing booking pace only):")
print("    {} additional properties needed".format(props_needed_conservative))
print("    ${:,} target / ${:,.0f} per prop/week = {} props".format(
    target_increase, rev_per_prop_per_week_existing, props_needed_conservative))
print("    New portfolio: {} properties".format(num_active + props_needed_conservative))
print("    Projected weekly rev: ${:,.0f}".format(
    avg_weekly_existing + (props_needed_conservative * rev_per_prop_per_week_existing)))
print()
print("  SCENARIO B - With 25% natural growth:")
print("    {} additional properties needed".format(props_needed_growth))
print("    ${:,} target / ${:,.0f} per prop/week = {} props".format(
    target_increase, rev_per_prop_per_week_growth, props_needed_growth))
print("    New portfolio: {} properties".format(num_active + props_needed_growth))
print("    Projected weekly rev: ${:,.0f}".format(
    avg_weekly_combined + (props_needed_growth * rev_per_prop_per_week_growth)))
print()

# Tiered analysis
print("  TIERED GROWTH SCENARIOS:")
print("  " + "-" * 45)
print("  {:>6}  {:>8}  {:>14}  {:>14}  {:>14}".format(
    "+Props", "Total", "Weekly Rev", "Increase/wk", "Increase/yr"))
print("  " + "-" * 60)
for extra in [5, 10, 15, 20, 25, 30]:
    new_weekly = avg_weekly_combined + (extra * rev_per_prop_per_week_growth)
    increase_wk = extra * rev_per_prop_per_week_growth
    increase_yr = increase_wk * 52
    print("  {:>+5}   {:>6}   ${:>12,.0f}  +${:>11,.0f}  +${:>11,.0f}".format(
        extra, num_active + extra, new_weekly, increase_wk, increase_yr))
print()

# Monthly breakdown
print("=" * 100)
print("  MONTHLY REVENUE PROJECTIONS (with 25% growth)")
print("=" * 100)
months = {}
month_order = []
for ws in weekly_stats:
    m = ws["week_start"].strftime("%B %Y")
    if m not in months:
        months[m] = {"existing": 0, "predicted": 0, "total": 0, "weeks": 0,
                     "booked": 0, "available": 0, "blocked": 0}
        month_order.append(m)
    months[m]["existing"] += ws["existing_revenue"]
    months[m]["predicted"] += ws["predicted_new_revenue"]
    months[m]["total"] += ws["total_predicted_revenue"]
    months[m]["weeks"] += 1
    months[m]["booked"] += ws["booked"]
    months[m]["available"] += ws["available"]
    months[m]["blocked"] += ws["blocked"]

print("{:<20} {:>14} {:>16} {:>16} {:>8} {:>6}".format(
    "Month", "Existing Rev", "New (25% grw)", "Total Projected", "BkdNts", "Weeks"))
print("-" * 85)
for m in month_order:
    d = months[m]
    print("{:<20} ${:>12,.0f} ${:>14,.0f} ${:>14,.0f} {:>7} {:>5}".format(
        m, d["existing"], d["predicted"], d["total"], d["booked"], d["weeks"]))
print()

# Channel mix (if available)
channels = {}
for p in property_data:
    for bk in p["bookings"]:
        ch = bk.get("channel", "UNKNOWN") or "UNKNOWN"
        if ch not in channels:
            channels[ch] = {"bookings": 0, "nights": 0, "revenue": 0}
        channels[ch]["bookings"] += 1
        channels[ch]["nights"] += bk["nights"]
        channels[ch]["revenue"] += bk["revenue"]

if channels:
    print("=" * 80)
    print("  BOOKING CHANNEL MIX")
    print("=" * 80)
    print("{:<25} {:>8} {:>8} {:>14} {:>8}".format(
        "Channel", "Bookings", "Nights", "Revenue", "% Rev"))
    print("-" * 70)
    for ch, d in sorted(channels.items(), key=lambda x: x[1]["revenue"], reverse=True):
        pct = (d["revenue"] / grand_total_revenue * 100) if grand_total_revenue else 0
        print("{:<25} {:>8} {:>8} ${:>12,.0f} {:>7.1f}%".format(
            ch, d["bookings"], d["nights"], d["revenue"], pct))
    print()

# Annual projection
annual_existing = avg_weekly_existing * 52
annual_with_growth = avg_weekly_combined * 52
print("=" * 100)
print("  ANNUALIZED PROJECTIONS (based on forecast period weekly averages)")
print("=" * 100)
print("  Annualized revenue (existing pace):   ${:>12,.0f}".format(annual_existing))
print("  Annualized revenue (with 25% growth): ${:>12,.0f}".format(annual_with_growth))
print("  Revenue per property per year:         ${:>12,.0f}  (existing)".format(
    annual_existing / num_active if num_active else 0))
print("  Revenue per property per year:         ${:>12,.0f}  (with growth)".format(
    annual_with_growth / num_active if num_active else 0))
print()

print("=" * 100)
print("  FORECAST COMPLETE")
print("=" * 100)
