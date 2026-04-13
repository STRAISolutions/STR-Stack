#!/usr/bin/env python3
"""STR Solutions - Hostfully Revenue Forecast & Inventory Analysis v2"""
import json, subprocess, sys
from collections import defaultdict
from datetime import datetime, timedelta

API_KEY = "ukNruuLswAygrvUi"
AGENCY = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE = "https://platform.hostfully.com/api/v3.2"

def api(endpoint):
    r = subprocess.run(["curl", "-s", "-H", f"X-HOSTFULLY-APIKEY: {API_KEY}",
                        f"{BASE}/{endpoint}"], capture_output=True, text=True, timeout=30)
    try:
        return json.loads(r.stdout)
    except:
        return {"error": r.stdout[:500]}

print("=" * 80)
print("HOSTFULLY REVENUE FORECAST & INVENTORY ANALYSIS")
print("=" * 80)
print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M ET')}")
print(f"Forecast Window: Apr 13 - Sep 1, 2026 (~20 weeks)\n")

# ---- STEP 1: Properties + Rates ----
props_data = api(f"properties?agencyUid={AGENCY}&limit=100")
if isinstance(props_data, dict) and "properties" in props_data:
    properties = props_data["properties"]
elif isinstance(props_data, list):
    properties = props_data
else:
    print(f"ERROR: {props_data}")
    sys.exit(1)

active_props = [p for p in properties if p.get("isActive", False)]
print(f"Total Properties: {len(properties)}")
print(f"Active Properties: {len(active_props)}\n")

# Get individual property rates
print("-" * 80)
print("PROPERTY RATES (from individual property detail)")
print("-" * 80)

prop_info = {}
for p in active_props:
    uid = p["uid"]
    detail = api(f"properties/{uid}")
    pd = detail.get("property", detail)
    pricing = pd.get("pricing", {})
    daily = pricing.get("dailyRate", 0) or 0
    cleaning = pricing.get("cleaningFee", 0) or 0
    weekend_adj = pricing.get("weekendAdjustmentRate", 0) or 0
    tax = pricing.get("taxRate", 0) or 0
    name = pd.get("name", p.get("name", "?"))
    bedrooms = pd.get("bedrooms", 0)
    prop_info[uid] = {
        "name": name, "daily": daily, "cleaning": cleaning,
        "bedrooms": bedrooms, "weekend_adj": weekend_adj, "tax": tax
    }
    print(f"  {name:<42} {bedrooms}BR  ${daily:>7.0f}/nt  clean:${cleaning:>6.0f}  tax:{tax*100:.1f}%")

rates = [v["daily"] for v in prop_info.values() if v["daily"] > 0]
avg_daily = sum(rates) / len(rates) if rates else 200
print(f"\n  Properties with rates: {len(rates)}/{len(active_props)}")
print(f"  Average daily rate: ${avg_daily:.2f}")
print(f"  Min/Max: ${min(rates):.0f} / ${max(rates):.0f}" if rates else "")

# ---- STEP 2: Get all leads (bookings) Jan-Sep 2026 ----
print(f"\n{'-'*80}")
print("BOOKING DATA (Jan 1 - Sep 1, 2026)")
print("-" * 80)

all_leads = []
cursor = None
for page in range(300):
    url = f"leads?agencyUid={AGENCY}&limit=100&checkInFrom=2026-01-01&checkInTo=2026-09-01"
    if cursor:
        url += f"&cursor={cursor}"
    data = api(url)
    if isinstance(data, dict) and "leads" in data:
        leads = data["leads"]
        all_leads.extend(leads)
        cursor = data.get("_paging", {}).get("_nextCursor")
        if not cursor or len(leads) == 0:
            break
    else:
        break

# Classify
blocks = []
cancelled = []
real_bookings = []
for l in all_leads:
    st = l.get("status", "")
    tp = l.get("type", "")
    if tp == "BLOCK" or st == "BLOCKED":
        blocks.append(l)
    elif st in ["CANCELLED", "DECLINED"]:
        cancelled.append(l)
    else:
        real_bookings.append(l)

print(f"Total leads fetched: {len(all_leads)}")
print(f"  Blocks/holds: {len(blocks)}")
print(f"  Cancelled: {len(cancelled)}")
print(f"  Active bookings: {len(real_bookings)}")

# Status breakdown
statuses = defaultdict(int)
channels = defaultdict(int)
for b in real_bookings:
    statuses[b.get("status", "?")] += 1
    ch = b.get("source", "") or b.get("channel", "")
    channels[ch] += 1
print(f"  Statuses: {dict(statuses)}")
print(f"  Channels: {dict(channels)}")

# ---- STEP 3: Revenue calculation ----
print(f"\n{'='*80}")
print("REVENUE ANALYSIS")
print("=" * 80)

weekly_rev = defaultdict(float)
weekly_nights = defaultdict(int)
monthly_rev = defaultdict(float)
monthly_nights = defaultdict(int)
total_rev = 0
total_nights = 0
total_cleaning = 0
prop_nights = defaultdict(int)
prop_revenue = defaultdict(float)
booking_list = []

for b in real_bookings:
    ci_str = b.get("checkInLocalDateTime", b.get("checkInZonedDateTime", ""))
    co_str = b.get("checkOutLocalDateTime", b.get("checkOutZonedDateTime", ""))
    puid = b.get("propertyUid", "")
    if not ci_str or not co_str:
        continue
    try:
        ci = datetime.strptime(ci_str[:10], "%Y-%m-%d")
        co = datetime.strptime(co_str[:10], "%Y-%m-%d")
    except:
        continue

    nights = max((co - ci).days, 1)
    info = prop_info.get(puid, {"daily": avg_daily, "cleaning": 150, "name": "Unknown"})
    rev = (info["daily"] * nights) + info["cleaning"]

    total_rev += rev
    total_nights += nights
    total_cleaning += info["cleaning"]
    prop_nights[puid] += nights
    prop_revenue[puid] += rev

    booking_list.append({"ci": ci, "co": co, "nights": nights, "rev": rev,
                         "prop": info["name"], "puid": puid, "rate": info["daily"]})

    iso_y, iso_w, _ = ci.isocalendar()
    wk = f"{iso_y}-W{iso_w:02d}"
    weekly_rev[wk] += rev
    weekly_nights[wk] += nights
    mo = ci.strftime("%Y-%m")
    monthly_rev[mo] += rev
    monthly_nights[mo] += nights

print(f"\nTotal revenue (computed): ${total_rev:,.2f}")
print(f"  Nightly portion: ${total_rev - total_cleaning:,.2f}")
print(f"  Cleaning fees: ${total_cleaning:,.2f}")
print(f"Total booked nights: {total_nights}")
if total_nights > 0:
    print(f"Effective avg rate: ${total_rev/total_nights:,.2f}/night (incl cleaning)")
    print(f"Avg nightly-only rate: ${(total_rev-total_cleaning)/total_nights:,.2f}/night")

# Monthly
print(f"\n--- Monthly Revenue ---")
for mo in sorted(monthly_rev):
    r = monthly_rev[mo]
    n = monthly_nights[mo]
    a = r / n if n > 0 else 0
    print(f"  {mo}: ${r:>10,.2f}  ({n:>3} nights)  ${a:>7,.2f}/night")

# Weekly
print(f"\n--- Weekly Revenue ---")
wk_vals = []
for wk in sorted(weekly_rev):
    r = weekly_rev[wk]
    n = weekly_nights[wk]
    wk_vals.append(r)
    print(f"  {wk}: ${r:>10,.2f}  ({n:>3} nights)")

if wk_vals:
    print(f"\n  Avg weekly: ${sum(wk_vals)/len(wk_vals):,.2f}")
    print(f"  Min weekly: ${min(wk_vals):,.2f}")
    print(f"  Max weekly: ${max(wk_vals):,.2f}")
    # Last 8 weeks trend
    recent = wk_vals[-8:] if len(wk_vals) >= 8 else wk_vals
    print(f"  Recent {len(recent)}-wk avg: ${sum(recent)/len(recent):,.2f}")

# Per-property
print(f"\n--- Revenue by Property ---")
for uid in sorted(prop_info, key=lambda u: prop_revenue.get(u, 0), reverse=True):
    info = prop_info[uid]
    r = prop_revenue.get(uid, 0)
    n = prop_nights.get(uid, 0)
    if r > 0:
        print(f"  {info['name']:<42} ${r:>10,.2f}  ({n:>3} nights)  ${info['daily']:>6.0f}/nt")

# ---- STEP 4: Future Availability ----
print(f"\n{'='*80}")
print("AVAILABILITY & OCCUPANCY (Apr 13 - Sep 1, 2026)")
print("=" * 80)

today = datetime(2026, 4, 13)
end_date = datetime(2026, 9, 1)
window = (end_date - today).days
total_possible = window * len(active_props)

future_booked = 0
future_blocked = 0
prop_future = defaultdict(int)
future_rev_booked = 0

for b in booking_list:
    start = max(b["ci"], today)
    stop = min(b["co"], end_date)
    if start < stop:
        n = (stop - start).days
        future_booked += n
        prop_future[b["puid"]] += n
        future_rev_booked += b["rate"] * n

for b in blocks:
    ci_str = b.get("checkInLocalDateTime", b.get("checkInZonedDateTime", ""))
    co_str = b.get("checkOutLocalDateTime", b.get("checkOutZonedDateTime", ""))
    puid = b.get("propertyUid", "")
    if not ci_str or not co_str:
        continue
    try:
        ci = datetime.strptime(ci_str[:10], "%Y-%m-%d")
        co = datetime.strptime(co_str[:10], "%Y-%m-%d")
    except:
        continue
    start = max(ci, today)
    stop = min(co, end_date)
    if start < stop:
        n = (stop - start).days
        future_blocked += n
        prop_future[puid] += n

unavailable = future_booked + future_blocked
available = total_possible - unavailable
occ_rate = unavailable / total_possible if total_possible > 0 else 0
booking_occ = future_booked / total_possible if total_possible > 0 else 0

print(f"Window: {window} days ({window/7:.1f} weeks)")
print(f"Active properties: {len(active_props)}")
print(f"Total possible nights: {total_possible:,}")
print(f"  Booked nights: {future_booked:,}")
print(f"  Blocked nights: {future_blocked:,}")
print(f"  Unavailable total: {unavailable:,}")
print(f"Available nights (sellable inventory): {available:,}")
print(f"Occupancy rate (booked+blocked): {occ_rate*100:.1f}%")
print(f"Booking-only occupancy: {booking_occ*100:.1f}%")
print(f"Revenue already booked (future): ${future_rev_booked:,.2f}")

print(f"\nPer-property future occupancy:")
for uid in sorted(prop_info, key=lambda u: prop_info[u]["name"]):
    info = prop_info[uid]
    bkd = prop_future.get(uid, 0)
    avl = window - bkd
    occ = bkd / window if window > 0 else 0
    print(f"  {info['name']:<42} Bkd:{bkd:>3}d  Avl:{avl:>3}d  Occ:{occ*100:>5.1f}%  ${info['daily']:>6.0f}/nt")

# ---- STEP 5: Forecast ----
print(f"\n{'='*80}")
print("WEEKLY REVENUE FORECAST (Apr 13 - Sep 1)")
print("=" * 80)

seasonal = {4: 1.0, 5: 1.1, 6: 1.3, 7: 1.4, 8: 1.3}
forecast = []
d = today
wn = 1

while d < end_date and wn <= 21:
    we = min(d + timedelta(days=7), end_date)
    wd = (we - d).days
    mo = d.month
    sf = seasonal.get(mo, 1.0)
    proj_occ = min(max(occ_rate * sf, 0.15), 0.85)
    proj_nights = int(len(active_props) * wd * proj_occ)
    proj_rev = proj_nights * avg_daily * sf
    forecast.append({"wk": wn, "d": d, "wd": wd, "mo": mo, "sf": sf,
                     "occ": proj_occ, "nights": proj_nights, "rev": proj_rev})
    print(f"  W{wn:<3} {d.strftime('%b %d'):<8} x{sf:.1f}  occ:{proj_occ*100:>5.1f}%  {proj_nights:>3} nights  ${proj_rev:>10,.2f}")
    d = we
    wn += 1

total_fc = sum(f["rev"] for f in forecast)
avg_wk = total_fc / len(forecast) if forecast else 0
print(f"\n  Total forecast: ${total_fc:,.2f}")
print(f"  Avg weekly:     ${avg_wk:,.2f}")

# ---- STEP 6: $6000/week analysis ----
print(f"\n{'='*80}")
print("$6,000/WEEK REVENUE INCREASE - INVENTORY ANALYSIS")
print("=" * 80)

target = 6000
avg_occ = sum(f["occ"] for f in forecast) / len(forecast) if forecast else 0.3

print(f"\nCurrent projected avg weekly: ${avg_wk:,.2f}")
print(f"Target weekly revenue:        ${avg_wk + target:,.2f}")
if avg_wk > 0:
    print(f"Increase needed:              ${target:,.2f}/wk (+{target/avg_wk*100:.1f}%)")

add_nights_wk = target / avg_daily if avg_daily > 0 else 0
nights_per_prop_wk = 7 * avg_occ
add_props = add_nights_wk / nights_per_prop_wk if nights_per_prop_wk > 0 else 0
wk_inv = available / (window / 7)
add_inv_wk = add_nights_wk / avg_occ if avg_occ > 0 else 0
inv_pct = add_inv_wk / wk_inv * 100 if wk_inv > 0 else 0
prop_pct = add_props / len(active_props) * 100 if active_props else 0

print(f"\nAt avg rate ${avg_daily:.0f}/night, {avg_occ*100:.1f}% occupancy:")
print(f"  Additional nights/week needed:  {add_nights_wk:.1f}")
print(f"  Nights per property per week:   {nights_per_prop_wk:.1f}")
print(f"  Additional properties needed:   {add_props:.1f} (~{round(add_props)} properties)")
print(f"  Property increase:              {prop_pct:.1f}% ({len(active_props)} -> {len(active_props) + round(add_props)})")
print(f"\n  Current weekly inventory:       {wk_inv:.0f} available nights/week")
print(f"  Additional inventory needed:    {add_inv_wk:.0f} available nights/week")
print(f"  INVENTORY INCREASE NEEDED:      {inv_pct:.1f}%")

# Sensitivity
print(f"\n{'-'*80}")
print("SENSITIVITY TABLE")
print("-" * 80)
print(f"  {'Scenario':<32} {'Rate':>8} {'Occ':>6} {'Props':>7} {'Prop%':>7} {'Inv%':>7}")
print("  " + "-" * 68)

scenarios = [
    ("Conservative", 0.85, 0.8),
    ("Current trajectory", 1.0, 1.0),
    ("Summer peak", 1.35, 1.15),
    ("High occupancy", 1.0, 1.4),
    ("Premium pricing", 1.5, 1.0),
    ("Best case (peak+occ)", 1.35, 1.4),
]

for label, rm, om in scenarios:
    r = avg_daily * rm
    o = min(avg_occ * om, 0.85)
    an = target / r if r > 0 else 0
    npw = 7 * o
    ap = an / npw if npw > 0 else 0
    ai = an / o if o > 0 else 0
    pp = ap / len(active_props) * 100 if active_props else 0
    ip = ai / wk_inv * 100 if wk_inv > 0 else 0
    print(f"  {label:<32} ${r:>6.0f} {o*100:>5.1f}% {ap:>6.1f} {pp:>6.1f}% {ip:>6.1f}%")

# Revenue per additional property
rev_per_prop_wk = avg_daily * nights_per_prop_wk
print(f"\n  Revenue per additional property: ~${rev_per_prop_wk:,.0f}/week")
print(f"  Revenue per additional property: ~${rev_per_prop_wk * 4.33:,.0f}/month")

# Final summary
print(f"\n{'='*80}")
print("KEY FINDINGS")
print("=" * 80)
print(f"""
1. CURRENT STATE
   - {len(active_props)} active properties, avg ${avg_daily:.0f}/night
   - {occ_rate*100:.1f}% occupancy ({future_booked} booked + {future_blocked} blocked nights)
   - {available:,} available nights through Sep 1 = sellable inventory
   - Projected avg weekly revenue: ${avg_wk:,.0f}

2. TO ADD $6,000/WEEK REVENUE
   - Need ~{round(add_props)} additional properties at current rates/occupancy
   - That is a {prop_pct:.0f}% increase in property count
   - Or {inv_pct:.0f}% increase in sellable inventory (available nights)

3. REVENUE MATH
   - Each new property generates ~${rev_per_prop_wk:,.0f}/week at {avg_occ*100:.0f}% occ
   - {round(add_props)} new properties x ${rev_per_prop_wk:,.0f}/wk = ${round(add_props) * rev_per_prop_wk:,.0f}/wk
   - New fleet total: {len(active_props) + round(add_props)} properties

4. TIMING
   - Summer months (Jun-Aug) at 1.3-1.4x seasonal multiplier
   - Adding properties before June captures peak revenue
   - Each property added now has {window} days of revenue runway through Sep 1
""")
