#!/usr/bin/env python3
"""
Hostfully Revenue Forecast v3 -- STR Portfolio Analysis
Covers Apr 13 - Sep 1, 2026 (~20 weekly buckets)
Uses _limit=100 and cursor pagination for ALL data.
Factors 25% natural booking growth on remaining availability.
"""

import json, sys, time, math
from datetime import datetime, timedelta, date
from urllib.request import Request, urlopen
from urllib.parse import urlencode, quote
from urllib.error import HTTPError

API_KEY   = "ukNruuLswAygrvUi"
AGENCY    = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE      = "https://platform.hostfully.com/api/v3.2"
HEADERS   = {"X-HOSTFULLY-APIKEY": API_KEY, "Accept": "application/json"}

FORECAST_START = date(2026, 4, 13)   # Monday
FORECAST_END   = date(2026, 9, 1)    # Tuesday -- last partial week ends here
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
                wait = 2 ** attempt
                print("  [retry {}] HTTP {} on {} -- waiting {}s".format(attempt+1, e.code, path, wait), file=sys.stderr)
                time.sleep(wait)
                continue
            print("  HTTP {}: {}".format(e.code, body[:200]), file=sys.stderr)
            raise
        except Exception as exc:
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise
    return None

def fetch_all_paginated(path, params):
    """Fetch all pages using _paging._nextCursor."""
    all_items = []
    p = dict(params)
    p["_limit"] = 100
    while True:
        data = api_get(path, p)
        if data is None:
            break
        if isinstance(data, list):
            all_items.extend(data)
            break  # no cursor wrapper
        if isinstance(data, dict):
            items = data.get("content") or data.get("items") or data.get("results") or []
            if not items and "_embedded" in data:
                items = data["_embedded"].get("leads", [])
            if not items:
                for k, v in data.items():
                    if isinstance(v, list):
                        items = v
                        break
            all_items.extend(items)
            paging = data.get("_paging") or data.get("paging") or {}
            cursor = paging.get("_nextCursor") or paging.get("nextCursor")
            if cursor:
                p["_cursor"] = cursor
            else:
                break
        else:
            break
    return all_items

# -- 1. Fetch ALL properties --------------------------------------------------
print("=" * 80)
print("  HOSTFULLY REVENUE FORECAST v3  --  STR Portfolio Analysis")
print("  Forecast window: {} -> {}".format(FORECAST_START, FORECAST_END))
print("=" * 80)
print()

print("[1/4] Fetching properties ...")
props_raw = api_get("/properties?agencyUid={}&_limit=100".format(AGENCY))

# Handle both list and paginated dict
if isinstance(props_raw, list):
    all_properties = props_raw
elif isinstance(props_raw, dict):
    all_properties = props_raw.get("content", props_raw.get("items", []))
    if not all_properties:
        # Try to find list in any key
        for k, v in props_raw.items():
            if isinstance(v, list) and len(v) > 0:
                all_properties = v
                break
    # check for next page
    paging = props_raw.get("_paging", {})
    cursor = paging.get("_nextCursor")
    while cursor:
        extra = api_get("/properties?agencyUid={}&_limit=100&_cursor={}".format(AGENCY, cursor))
        if isinstance(extra, dict):
            more = extra.get("content", extra.get("items", []))
            all_properties.extend(more)
            cursor = extra.get("_paging", {}).get("_nextCursor")
        else:
            if isinstance(extra, list):
                all_properties.extend(extra)
            break
else:
    all_properties = []

print("  -> Total properties fetched: {}".format(len(all_properties)))

# Filter active
active_props = [p for p in all_properties if p.get("isActive") is True or p.get("status") == "ACTIVE"]
if not active_props:
    # If no explicit active flag, check for inactive markers
    inactive_keywords = {"INACTIVE", "DEACTIVATED", "ARCHIVED"}
    active_props = [p for p in all_properties
                    if str(p.get("status", "ACTIVE")).upper() not in inactive_keywords
                    and p.get("isActive") is not False]

print("  -> Active properties: {}".format(len(active_props)))
print()

# -- 2. For each property: get detail + leads ----------------------------------
print("[2/4] Fetching property details + bookings ...")

property_data = []  # list of dicts with all property info
total_leads_fetched = 0

for i, prop in enumerate(active_props):
    uid = prop.get("uid") or prop.get("id") or prop.get("propertyUid")
    name = prop.get("name") or prop.get("title") or uid[:12]

    sys.stdout.write("\r  Processing {}/{}: {:<40}".format(i+1, len(active_props), name[:40]))
    sys.stdout.flush()

    # Get individual property detail for pricing
    detail = api_get("/properties/{}".format(uid))
    daily_rate = 0
    cleaning_fee = 0
    bedrooms = 0
    if detail:
        pricing = detail.get("pricing") or {}
        daily_rate = pricing.get("dailyRate") or pricing.get("baseRate") or pricing.get("nightlyRate") or 0
        cleaning_fee = pricing.get("cleaningFee") or 0
        bedrooms = detail.get("bedrooms") or detail.get("numberOfBedrooms") or 0
        if not name or name == uid[:12]:
            name = detail.get("name") or detail.get("title") or name

    # Get leads (bookings)
    leads_params = {
        "propertyUid": uid,
        "_limit": 100,
        "checkInFrom": "2026-01-01",
        "checkInTo": "2026-09-01"
    }
    leads_raw = api_get("/leads", leads_params)

    if isinstance(leads_raw, list):
        leads = leads_raw
    elif isinstance(leads_raw, dict):
        leads = leads_raw.get("content") or leads_raw.get("items") or leads_raw.get("results") or []
        if not leads:
            for k, v in leads_raw.items():
                if isinstance(v, list) and len(v) > 0:
                    leads = v
                    break
        # Handle pagination
        paging = leads_raw.get("_paging", {})
        cursor = paging.get("_nextCursor")
        while cursor:
            extra = api_get("/leads", dict(leads_params, _cursor=cursor))
            if isinstance(extra, dict):
                more = extra.get("content") or extra.get("items") or []
                leads.extend(more)
                cursor = extra.get("_paging", {}).get("_nextCursor")
            elif isinstance(extra, list):
                leads.extend(extra)
                break
            else:
                break
    else:
        leads = []

    total_leads_fetched += len(leads)

    # Filter to real bookings only
    BLOCK_TYPES = {"BLOCK", "BLOCKED"}
    BAD_STATUSES = {"BLOCKED", "CANCELLED", "CANCELED", "DECLINED"}

    real_bookings = []
    block_entries = []
    for lead in leads:
        lead_type = str(lead.get("type", "")).upper()
        lead_status = str(lead.get("status", "")).upper()

        if lead_type in BLOCK_TYPES or lead_status in BAD_STATUSES:
            if lead_type in BLOCK_TYPES:
                block_entries.append(lead)
            continue
        real_bookings.append(lead)

    # Calculate per-property stats
    total_booked_nights = 0
    total_blocked_nights = 0
    total_revenue = 0
    booking_details = []

    for bk in real_bookings:
        ci_str = bk.get("checkInDate") or bk.get("checkIn") or bk.get("arrivalDate") or ""
        co_str = bk.get("checkOutDate") or bk.get("checkOut") or bk.get("departureDate") or ""

        try:
            ci = datetime.strptime(ci_str[:10], "%Y-%m-%d").date() if ci_str else None
            co = datetime.strptime(co_str[:10], "%Y-%m-%d").date() if co_str else None
        except Exception:
            continue

        if not ci or not co:
            continue

        nights = (co - ci).days
        if nights <= 0:
            continue

        bk_revenue = bk.get("totalAmount") or bk.get("revenue") or bk.get("total") or 0
        if not bk_revenue and daily_rate:
            bk_revenue = nights * daily_rate + cleaning_fee

        total_booked_nights += nights
        total_revenue += float(bk_revenue)
        booking_details.append({
            "checkIn": ci,
            "checkOut": co,
            "nights": nights,
            "revenue": float(bk_revenue),
            "status": bk.get("status", ""),
        })

    # Block night details for weekly tracking
    block_details = []
    for blk in block_entries:
        ci_str = blk.get("checkInDate") or blk.get("checkIn") or blk.get("arrivalDate") or ""
        co_str = blk.get("checkOutDate") or blk.get("checkOut") or blk.get("departureDate") or ""
        try:
            ci = datetime.strptime(ci_str[:10], "%Y-%m-%d").date() if ci_str else None
            co = datetime.strptime(co_str[:10], "%Y-%m-%d").date() if co_str else None
        except Exception:
            continue
        if ci and co:
            total_blocked_nights += max(0, (co - ci).days)
            block_details.append({"checkIn": ci, "checkOut": co, "nights": max(0, (co - ci).days)})

    # Effective nightly rate from actual bookings
    effective_rate = (total_revenue / total_booked_nights) if total_booked_nights > 0 else daily_rate

    property_data.append({
        "uid": uid,
        "name": name,
        "dailyRate": daily_rate,
        "cleaningFee": cleaning_fee,
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

print("\r  -> Done. {} properties processed, {} total leads fetched.       ".format(len(property_data), total_leads_fetched))
print()

# -- 3. Build weekly forecast --------------------------------------------------
print("[3/4] Building weekly forecast ...")

# Generate week buckets (Mon-Sun)
weeks = []
current = FORECAST_START
while current < FORECAST_END:
    week_end = min(current + timedelta(days=6), FORECAST_END)
    weeks.append((current, week_end))
    current += timedelta(days=7)

num_active = len(property_data)

# For each week, calculate booked / blocked / available nights across portfolio
weekly_stats = []

for week_start, week_end in weeks:
    week_days = (week_end - week_start).days + 1
    total_property_nights = num_active * week_days  # max possible

    booked_in_week = 0
    blocked_in_week = 0
    revenue_in_week = 0.0

    for prop in property_data:
        for bk in prop["bookings"]:
            # How many nights of this booking overlap this week?
            overlap_start = max(bk["checkIn"], week_start)
            overlap_end = min(bk["checkOut"], week_end + timedelta(days=1))
            overlap_nights = (overlap_end - overlap_start).days
            if overlap_nights > 0:
                booked_in_week += overlap_nights
                # Pro-rate revenue
                if bk["nights"] > 0:
                    revenue_in_week += bk["revenue"] * (overlap_nights / bk["nights"])

        for blk in prop["blocks"]:
            overlap_start = max(blk["checkIn"], week_start)
            overlap_end = min(blk["checkOut"], week_end + timedelta(days=1))
            overlap_nights = (overlap_end - overlap_start).days
            if overlap_nights > 0:
                blocked_in_week += overlap_nights

    available_in_week = total_property_nights - booked_in_week - blocked_in_week
    if available_in_week < 0:
        available_in_week = 0

    # Predict new bookings from growth
    predicted_new_nights = available_in_week * GROWTH_FACTOR

    # Average effective nightly rate across portfolio
    avg_rates = [p["effectiveRate"] for p in property_data if p["effectiveRate"] > 0]
    avg_nightly = sum(avg_rates) / len(avg_rates) if avg_rates else 150

    predicted_new_revenue = predicted_new_nights * avg_nightly
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

# -- 4. OUTPUT -----------------------------------------------------------------
print("[4/4] Generating report ...")
print()
print("=" * 100)
print("  PER-PROPERTY SUMMARY")
print("=" * 100)
print("{:<4} {:<35} {:>8} {:>7} {:>5} {:>7} {:>12} {:>8}".format(
    "#", "Property Name", "Rate", "Clean", "Bkgs", "Nights", "Revenue", "EffRate"))
print("-" * 100)

sorted_props = sorted(property_data, key=lambda x: x["totalRevenue"], reverse=True)

grand_total_revenue = 0
grand_total_nights = 0
grand_total_bookings = 0

for idx, p in enumerate(sorted_props, 1):
    grand_total_revenue += p["totalRevenue"]
    grand_total_nights += p["totalBookedNights"]
    grand_total_bookings += p["bookingCount"]

    print("{:<4} {:<35} ${:>6.0f}  ${:>5.0f}  {:>4}  {:>6}  ${:>10,.0f}  ${:>6.0f}".format(
        idx, p["name"][:34], p["dailyRate"], p["cleaningFee"],
        p["bookingCount"], p["totalBookedNights"], p["totalRevenue"], p["effectiveRate"]))

print("-" * 100)
print("{:4} {:<35} {:>8} {:>7} {:>5} {:>7}  ${:>10,.0f}".format(
    "", "TOTAL", "", "", grand_total_bookings, grand_total_nights, grand_total_revenue))
print()

# Occupancy approximation (Jan 1 - Sep 1 = 243 days)
total_possible_nights = num_active * 243
portfolio_occ = (grand_total_nights / total_possible_nights * 100) if total_possible_nights else 0
avg_eff_rate = (grand_total_revenue / grand_total_nights) if grand_total_nights > 0 else 0

print("  Portfolio occupancy (Jan 1 - Sep 1): {} / {} = {:.1f}%".format(
    grand_total_nights, total_possible_nights, portfolio_occ))
print("  Average effective nightly rate: ${:,.2f}".format(avg_eff_rate))
print("  Average revenue per property: ${:,.0f}".format(
    grand_total_revenue / num_active if num_active else 0))
print()

# -- WEEKLY FORECAST TABLE -----------------------------------------------------
print("=" * 130)
print("  WEEKLY REVENUE FORECAST  (Apr 13 - Sep 1, 2026)")
print("  Growth assumption: 25% of remaining availability converts to new bookings")
print("=" * 130)
print("{:<5} {:<25} {:>4} {:>7} {:>7} {:>7} {:>7} {:>12} {:>7} {:>12} {:>12} {:>6} {:>6}".format(
    "Week", "Dates", "Days", "MaxNts", "Booked", "Block", "Avail",
    "ExistRev", "NewNts", "NewRev", "TotalRev", "Occ%", "w/Grw"))
print("-" * 130)

forecast_total_existing = 0
forecast_total_new = 0
forecast_total_combined = 0
forecast_total_booked = 0
forecast_total_new_nights = 0
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

print("-" * 130)
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
print("  Total revenue (existing bookings):   ${:,.0f}".format(grand_total_revenue))
print("  Average effective nightly rate:       ${:,.2f}".format(avg_eff_rate))
print("  Portfolio occupancy (Jan-Sep):        {:.1f}%".format(portfolio_occ))
print()

# Forecast period specific
print("  FORECAST PERIOD (Apr 13 - Sep 1, ~{} weeks):".format(num_weeks))
print("  " + "-" * 40)
print("  Existing booking revenue:            ${:,.0f}".format(forecast_total_existing))
print("  Predicted new booking revenue (25%): ${:,.0f}".format(forecast_total_new))
print("  TOTAL projected revenue:             ${:,.0f}".format(forecast_total_combined))
print("  Average weekly (existing):           ${:,.0f}".format(avg_weekly_existing))
print("  Average weekly (with growth):        ${:,.0f}".format(avg_weekly_combined))
print()

# How many properties needed for $6,000/week increase
print("  INVENTORY INCREASE ANALYSIS")
print("  " + "-" * 40)
target_increase = 6000  # per week

# Revenue per property per week (from existing data)
rev_per_prop_per_week_existing = avg_weekly_existing / num_active if num_active else 0
rev_per_prop_per_week_growth = avg_weekly_combined / num_active if num_active else 0

print("  Current avg weekly revenue per property (existing): ${:,.0f}".format(rev_per_prop_per_week_existing))
print("  Current avg weekly revenue per property (w/ growth): ${:,.0f}".format(rev_per_prop_per_week_growth))
print()
print("  TARGET: +${:,}/week additional revenue".format(target_increase))
print()

# Conservative: use existing booking pace
props_needed_conservative = math.ceil(target_increase / rev_per_prop_per_week_existing) if rev_per_prop_per_week_existing > 0 else 0
# With growth assumption
props_needed_growth = math.ceil(target_increase / rev_per_prop_per_week_growth) if rev_per_prop_per_week_growth > 0 else 0

print("  Conservative (existing pace):    {} additional properties".format(props_needed_conservative))
print("    Math: ${:,} / ${:,.0f} per prop/week = {} properties".format(
    target_increase, rev_per_prop_per_week_existing, props_needed_conservative))
print("    New portfolio size: {} properties".format(num_active + props_needed_conservative))
print("    New weekly revenue: ${:,.0f}".format(
    avg_weekly_existing + (props_needed_conservative * rev_per_prop_per_week_existing)))
print()
print("  With 25% growth assumption:      {} additional properties".format(props_needed_growth))
print("    Math: ${:,} / ${:,.0f} per prop/week = {} properties".format(
    target_increase, rev_per_prop_per_week_growth, props_needed_growth))
print("    New portfolio size: {} properties".format(num_active + props_needed_growth))
print("    New weekly revenue: ${:,.0f}".format(
    avg_weekly_combined + (props_needed_growth * rev_per_prop_per_week_growth)))
print()

# Tiered analysis
print("  TIERED GROWTH SCENARIOS:")
print("  " + "-" * 40)
for extra in [5, 10, 15, 20, 25]:
    new_weekly = avg_weekly_combined + (extra * rev_per_prop_per_week_growth)
    increase = extra * rev_per_prop_per_week_growth
    print("    +{:>2} properties -> {} total | weekly: ${:>10,.0f} | increase: +${:>8,.0f}/week (+${:>10,.0f}/year)".format(
        extra, num_active + extra, new_weekly, increase, increase * 52))
print()

# Seasonal breakdown (monthly summary)
print("=" * 100)
print("  MONTHLY REVENUE PROJECTIONS (with 25% growth)")
print("=" * 100)
months = {}
month_order = []
for ws in weekly_stats:
    m = ws["week_start"].strftime("%B %Y")
    if m not in months:
        months[m] = {"existing": 0, "predicted": 0, "total": 0, "weeks": 0, "booked": 0, "available": 0}
        month_order.append(m)
    months[m]["existing"] += ws["existing_revenue"]
    months[m]["predicted"] += ws["predicted_new_revenue"]
    months[m]["total"] += ws["total_predicted_revenue"]
    months[m]["weeks"] += 1
    months[m]["booked"] += ws["booked"]
    months[m]["available"] += ws["available"]

print("{:<20} {:>14} {:>16} {:>16} {:>6}".format(
    "Month", "Existing Rev", "New (25% growth)", "Total Projected", "Weeks"))
print("-" * 80)
for m in month_order:
    data = months[m]
    print("{:<20} ${:>12,.0f} ${:>14,.0f} ${:>14,.0f} {:>5}".format(
        m, data["existing"], data["predicted"], data["total"], data["weeks"]))
print()

# Final annual projection
annual_existing = avg_weekly_existing * 52
annual_with_growth = avg_weekly_combined * 52
print("=" * 100)
print("  ANNUALIZED PROJECTIONS (based on forecast period averages)")
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
