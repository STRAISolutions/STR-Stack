#!/usr/bin/env python3
"""STR Solutions — Hostfully Revenue Forecast & Inventory Analysis"""
import json, subprocess, sys
from datetime import datetime, timedelta
from collections import defaultdict

API_KEY = "ukNruuLswAygrvUi"
AGENCY = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE = "https://platform.hostfully.com/api/v3.2"

def api(endpoint):
    r = subprocess.run(["curl", "-s", "-H", f"X-HOSTFULLY-APIKEY: {API_KEY}", f"{BASE}/{endpoint}"],
                       capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {"error": r.stdout[:500]}

# Step 1: Get all properties
print("=" * 80)
print("HOSTFULLY REVENUE FORECAST & INVENTORY ANALYSIS")
print("=" * 80)
print(f"\nAnalysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
print(f"Forecast Window: Apr 13, 2026 -> Sep 1, 2026 (~20 weeks)")
print()

props_data = api(f"properties?agencyUid={AGENCY}&limit=100")
if isinstance(props_data, dict) and "properties" in props_data:
    properties = props_data["properties"]
elif isinstance(props_data, list):
    properties = props_data
else:
    print(f"ERROR fetching properties: {props_data}")
    sys.exit(1)

active_props = [p for p in properties if p.get("isActive", False)]
print(f"Total Properties: {len(properties)}")
print(f"Active Properties: {len(active_props)}")
print()

# Step 2: Get base rates for each property
print("-" * 80)
print("PROPERTY INVENTORY & RATES")
print("-" * 80)

prop_rates = {}
for p in active_props:
    uid = p["uid"]
    name = p.get("name", "Unknown")
    bedrooms = p.get("bedrooms", 0)
    base_rate = 0

    pricing = p.get("pricing", {})
    if pricing:
        base_rate = pricing.get("baseRate", 0) or 0
        if not base_rate:
            base_rate = pricing.get("weeklyRate", 0) or 0
            if base_rate:
                base_rate = base_rate / 7

    if not base_rate:
        pr = api(f"properties/{uid}/pricing")
        if isinstance(pr, dict):
            base_rate = pr.get("baseRate", 0) or pr.get("basePrice", 0) or 0
            if not base_rate and pr.get("weeklyRate"):
                base_rate = (pr.get("weeklyRate", 0) or 0) / 7

    prop_rates[uid] = {"name": name, "bedrooms": bedrooms, "base_rate": base_rate}
    print(f"  {name:<35} {bedrooms}BR  ${base_rate:>8.2f}/night")

print()

# Step 3: Get all bookings since Jan 1 2026
print("-" * 80)
print("BOOKING HISTORY (Jan 1 - Present)")
print("-" * 80)

all_bookings = []
for status in ["CONFIRMED", "CHECKED_IN", "CHECKED_OUT", "CANCELLED"]:
    bdata = api(f"bookings?agencyUid={AGENCY}&status={status}&limit=200&checkInDate=2026-01-01")
    if isinstance(bdata, dict) and "bookings" in bdata:
        all_bookings.extend(bdata["bookings"])
    elif isinstance(bdata, list):
        all_bookings.extend(bdata)

bdata2 = api(f"bookings?agencyUid={AGENCY}&limit=200&checkInDate=2026-01-01")
if isinstance(bdata2, dict) and "bookings" in bdata2:
    existing_ids = {b.get("uid") for b in all_bookings}
    for b in bdata2["bookings"]:
        if b.get("uid") not in existing_ids:
            all_bookings.append(b)
elif isinstance(bdata2, list):
    existing_ids = {b.get("uid") for b in all_bookings}
    for b in bdata2:
        if b.get("uid") not in existing_ids:
            all_bookings.append(b)

print(f"Total bookings since Jan 1: {len(all_bookings)}")
print()

# Parse booking data
weekly_revenue = defaultdict(float)
weekly_nights = defaultdict(int)
booking_details = []
total_revenue = 0
total_nights = 0

for b in all_bookings:
    status = b.get("status", "")
    if status in ["CANCELLED", "DECLINED"]:
        continue

    checkin_str = b.get("checkInDate", "") or b.get("arrivalDate", "")
    checkout_str = b.get("checkOutDate", "") or b.get("departureDate", "")
    amount = b.get("totalPrice", 0) or b.get("basePrice", 0) or b.get("totalAmount", 0) or 0
    prop_uid = b.get("propertyUid", "")
    channel = b.get("source", "") or b.get("channel", "") or b.get("bookingChannel", "")

    if not checkin_str or not checkout_str:
        continue

    try:
        checkin = datetime.strptime(checkin_str[:10], "%Y-%m-%d")
        checkout = datetime.strptime(checkout_str[:10], "%Y-%m-%d")
    except:
        continue

    nights = (checkout - checkin).days
    if nights <= 0:
        nights = 1

    nightly_rate = amount / nights if nights > 0 else 0
    total_revenue += amount
    total_nights += nights

    prop_name = prop_rates.get(prop_uid, {}).get("name", prop_uid[:12])
    booking_details.append({
        "checkin": checkin, "checkout": checkout, "nights": nights,
        "amount": amount, "nightly_rate": nightly_rate,
        "property": prop_name, "channel": channel, "status": status
    })

    iso_year, iso_week, _ = checkin.isocalendar()
    week_key = f"{iso_year}-W{iso_week:02d}"
    weekly_revenue[week_key] += amount
    weekly_nights[week_key] += nights

booking_details.sort(key=lambda x: x["checkin"])
print(f"Active bookings (non-cancelled): {len(booking_details)}")
print(f"Total revenue since Jan 1: ${total_revenue:,.2f}")
print(f"Total booked nights: {total_nights}")
if total_nights > 0:
    print(f"Average nightly rate: ${total_revenue / total_nights:,.2f}")
print()

# Step 4: Weekly revenue breakdown
print("-" * 80)
print("WEEKLY REVENUE BREAKDOWN (Jan - Present)")
print("-" * 80)
print(f"{'Week':<12} {'Revenue':>12} {'Nights':>8} {'Avg/Night':>12}")
print("-" * 48)

sorted_weeks = sorted(weekly_revenue.keys())
week_revenues = []
for w in sorted_weeks:
    rev = weekly_revenue[w]
    nts = weekly_nights[w]
    avg = rev / nts if nts > 0 else 0
    week_revenues.append(rev)
    print(f"{w:<12} ${rev:>11,.2f} {nts:>8} ${avg:>11,.2f}")

if week_revenues:
    avg_weekly = sum(week_revenues) / len(week_revenues)
    print("-" * 48)
    print(f"{'AVERAGE':<12} ${avg_weekly:>11,.2f}")
    print(f"{'MEDIAN':<12} ${sorted(week_revenues)[len(week_revenues)//2]:>11,.2f}")
print()

# Step 5: Calendar availability
print("-" * 80)
print("CALENDAR AVAILABILITY (Apr 13 - Sep 1, 2026)")
print("-" * 80)

today = datetime(2026, 4, 13)
end_date = datetime(2026, 9, 1)
total_future_days = (end_date - today).days
total_possible_nights = total_future_days * len(active_props)

future_bookings = [b for b in booking_details if b["checkout"] > today]
booked_nights_future = 0
future_revenue_booked = 0
prop_booked_days = defaultdict(set)

for b in future_bookings:
    start = max(b["checkin"], today)
    end = min(b["checkout"], end_date)
    if start < end:
        nights = (end - start).days
        booked_nights_future += nights
        future_revenue_booked += b["nightly_rate"] * nights
        prop_uid_match = None
        for uid, info in prop_rates.items():
            if info["name"] == b["property"]:
                prop_uid_match = uid
                break
        if prop_uid_match:
            d = start
            while d < end:
                prop_booked_days[prop_uid_match].add(d.strftime("%Y-%m-%d"))
                d += timedelta(days=1)

available_nights = total_possible_nights - booked_nights_future
occupancy_rate = (booked_nights_future / total_possible_nights * 100) if total_possible_nights > 0 else 0

print(f"Active properties:           {len(active_props)}")
print(f"Days in forecast window:     {total_future_days}")
print(f"Total possible nights:       {total_possible_nights:,}")
print(f"Already booked nights:       {booked_nights_future:,}")
print(f"Available nights (inventory): {available_nights:,}")
print(f"Current occupancy rate:      {occupancy_rate:.1f}%")
print(f"Revenue already booked:      ${future_revenue_booked:,.2f}")
print()

print("Per-Property Availability:")
for uid in sorted(prop_rates.keys(), key=lambda u: prop_rates[u]["name"]):
    info = prop_rates[uid]
    booked = len(prop_booked_days.get(uid, set()))
    avail = total_future_days - booked
    occ = (booked / total_future_days * 100) if total_future_days > 0 else 0
    print(f"  {info['name']:<35} Booked: {booked:>3}d  Avail: {avail:>3}d  Occ: {occ:>5.1f}%")
print()

# Step 6: Revenue Forecast
print("=" * 80)
print("REVENUE FORECAST (Next 10-16 Weeks)")
print("=" * 80)

if week_revenues:
    recent_weeks = week_revenues[-8:] if len(week_revenues) >= 8 else week_revenues
    current_weekly_rate = sum(recent_weeks) / len(recent_weeks)
else:
    current_weekly_rate = 0

avg_nightly = total_revenue / total_nights if total_nights > 0 else 200

seasonal = {4: 1.0, 5: 1.1, 6: 1.3, 7: 1.4, 8: 1.3}

print(f"\nCurrent weekly run rate:     ${current_weekly_rate:,.2f}")
print(f"Average nightly rate:        ${avg_nightly:,.2f}")
print(f"Active properties:           {len(active_props)}")
print()

print(f"{'Week':<8} {'Month':<6} {'Seas.':>6} {'Proj. Occ':>10} {'Proj Rev':>12} {'Nights':>8}")
print("-" * 56)

forecast_weeks = []
d = today
week_num = 1
while d < end_date and week_num <= 20:
    week_end = d + timedelta(days=7)
    if week_end > end_date:
        week_end = end_date
    week_days = (week_end - d).days
    month = d.month
    sfactor = seasonal.get(month, 1.0)

    proj_occ = min(occupancy_rate * sfactor / 100, 0.85)
    if proj_occ < 0.15:
        proj_occ = 0.15

    proj_nights = int(len(active_props) * week_days * proj_occ)
    proj_rev = proj_nights * avg_nightly * sfactor

    forecast_weeks.append({
        "week": week_num, "start": d, "days": week_days,
        "month": month, "sfactor": sfactor,
        "occ": proj_occ, "nights": proj_nights, "revenue": proj_rev
    })

    mo_name = d.strftime("%b")
    print(f"W{week_num:<6} {mo_name:<6} {sfactor:>5.1f}x {proj_occ*100:>8.1f}% ${proj_rev:>11,.2f} {proj_nights:>8}")

    d = week_end
    week_num += 1

total_forecast_rev = sum(w["revenue"] for w in forecast_weeks)
avg_forecast_weekly = total_forecast_rev / len(forecast_weeks) if forecast_weeks else 0
print("-" * 56)
print(f"{'TOTAL':<8} {'':6} {'':>6} {'':>10} ${total_forecast_rev:>11,.2f}")
print(f"{'AVG/WK':<8} {'':6} {'':>6} {'':>10} ${avg_forecast_weekly:>11,.2f}")

# Step 7: $6000/week increase analysis
print()
print("=" * 80)
print("$6,000/WEEK REVENUE INCREASE — INVENTORY ANALYSIS")
print("=" * 80)

target_increase = 6000
target_weekly = avg_forecast_weekly + target_increase

print(f"\nCurrent projected avg weekly:  ${avg_forecast_weekly:,.2f}")
print(f"Target weekly revenue:         ${target_weekly:,.2f}")
if avg_forecast_weekly > 0:
    print(f"Required increase:             ${target_increase:,.2f}/week (+{target_increase/avg_forecast_weekly*100:.1f}%)")
print()

additional_nights_per_week = target_increase / avg_nightly if avg_nightly > 0 else 0
print(f"At current avg rate (${avg_nightly:.2f}/night):")
print(f"  Additional nights needed/week:  {additional_nights_per_week:.1f}")
print()

avg_occ_rate = sum(w["occ"] for w in forecast_weeks) / len(forecast_weeks) if forecast_weeks else 0.3
nights_per_prop_per_week = 7 * avg_occ_rate
additional_props_needed = additional_nights_per_week / nights_per_prop_per_week if nights_per_prop_per_week > 0 else 0

print(f"At projected avg occupancy ({avg_occ_rate*100:.1f}%):")
print(f"  Nights/property/week:           {nights_per_prop_per_week:.1f}")
print(f"  Additional properties needed:   {additional_props_needed:.1f} (~{int(round(additional_props_needed))} properties)")
print()

current_inventory = available_nights
current_weekly_inventory = current_inventory / (total_future_days / 7)
additional_weekly_inventory = additional_nights_per_week / avg_occ_rate if avg_occ_rate > 0 else 0
inventory_increase_pct = (additional_weekly_inventory / current_weekly_inventory * 100) if current_weekly_inventory > 0 else 0
prop_increase_pct = (additional_props_needed / len(active_props) * 100) if len(active_props) > 0 else 0

print(f"INVENTORY INCREASE REQUIRED:")
print(f"  Current active properties:      {len(active_props)}")
print(f"  Additional properties needed:   {int(round(additional_props_needed))}")
print(f"  New total properties:           {len(active_props) + int(round(additional_props_needed))}")
print(f"  Property increase:              {prop_increase_pct:.1f}%")
print()
print(f"  Current weekly inventory:       {current_weekly_inventory:.0f} available nights/week")
print(f"  Additional inventory needed:    {additional_weekly_inventory:.0f} available nights/week")
print(f"  Inventory increase:             {inventory_increase_pct:.1f}%")
print()

# Sensitivity table
print("-" * 80)
print("SENSITIVITY: Inventory Increase % at Different Scenarios")
print("-" * 80)
print(f"{'Scenario':<30} {'Nightly Rate':>12} {'Occ Rate':>10} {'Props Needed':>14} {'Inv. Increase':>14}")
print("-" * 80)

scenarios = [
    ("Conservative (low rate/occ)", avg_nightly * 0.85, avg_occ_rate * 0.8),
    ("Current trajectory", avg_nightly, avg_occ_rate),
    ("Summer peak rates", avg_nightly * 1.3, avg_occ_rate * 1.15),
    ("Optimistic (high occ)", avg_nightly * 1.1, min(avg_occ_rate * 1.3, 0.85)),
    ("Premium pricing only", avg_nightly * 1.5, avg_occ_rate),
]

for label, rate, occ in scenarios:
    add_nights = target_increase / rate if rate > 0 else 0
    npw = 7 * occ
    add_props = add_nights / npw if npw > 0 else 0
    add_inv = add_nights / occ if occ > 0 else 0
    inv_pct = (add_inv / current_weekly_inventory * 100) if current_weekly_inventory > 0 else 0
    prop_pct = (add_props / len(active_props) * 100) if len(active_props) > 0 else 0
    print(f"{label:<30} ${rate:>11,.2f} {occ*100:>9.1f}% {add_props:>10.1f} ({prop_pct:.0f}%) {inv_pct:>12.1f}%")

print()
print("=" * 80)
print("KEY TAKEAWAY")
print("=" * 80)
if avg_forecast_weekly > 0 and len(active_props) > 0:
    print(f"""
To increase weekly revenue by $6,000:
  - You need approximately {int(round(additional_props_needed))} additional properties
  - This represents a {prop_increase_pct:.0f}% increase in property count ({len(active_props)} -> {len(active_props) + int(round(additional_props_needed))})
  - Or a {inventory_increase_pct:.0f}% increase in available inventory (sellable nights)
  - At ${avg_nightly:.0f}/night avg rate and {avg_occ_rate*100:.0f}% occupancy
  - Summer months (Jun-Aug) will naturally outperform this target
  - Adding properties before June maximizes summer revenue capture
""")
