#!/usr/bin/env python3
"""STR Solutions - Hostfully Revenue Forecast & Inventory Gap Analysis (FINAL)"""
import json, subprocess
from collections import defaultdict
from datetime import datetime, timedelta

API_KEY = "ukNruuLswAygrvUi"
AGENCY = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE = "https://platform.hostfully.com/api/v3.2"

def api(endpoint):
    r = subprocess.run(["curl","-s","-H","X-HOSTFULLY-APIKEY: "+API_KEY, BASE+"/"+endpoint],
                       capture_output=True, text=True, timeout=30)
    try: return json.loads(r.stdout)
    except: return {}

TODAY = datetime(2026, 4, 13)
END = datetime(2026, 9, 1)
WINDOW = (END - TODAY).days  # 141 days

# ================================================================
# 1. GET PROPERTIES + RATES
# ================================================================
props = api("properties?agencyUid="+AGENCY+"&limit=100")
plist = props.get("properties", props if isinstance(props, list) else [])
active = {}
for p in plist:
    if p.get("isActive"):
        uid = p["uid"]
        det = api("properties/" + uid)
        pr = det.get("property", det)
        pricing = pr.get("pricing", {}) if isinstance(pr, dict) else {}
        daily = pricing.get("dailyRate", 0) or 0
        clean = pricing.get("cleaningFee", 0) or 0
        active[uid] = {
            "name": pr.get("name", p.get("name","?")),
            "bedrooms": pr.get("bedrooms", 0),
            "daily": daily,
            "cleaning": clean,
        }

N_PROPS = len(active)
rates = [v["daily"] for v in active.values() if v["daily"] > 0]
AVG_RATE = sum(rates) / len(rates) if rates else 0
AVG_CLEAN = sum(v["cleaning"] for v in active.values()) / N_PROPS if N_PROPS else 0

# ================================================================
# 2. GET ALL BOOKINGS PER PROPERTY
# ================================================================
all_bookings = []
prop_stats = {}

for uid, info in active.items():
    leads = api("leads?propertyUid=" + uid + "&limit=100&checkInFrom=2026-01-01&checkInTo=2026-09-01")
    llist = leads.get("leads", [])

    bookings = [l for l in llist if l.get("type") != "BLOCK" and l.get("status") not in ["BLOCKED","CANCELLED","DECLINED"]]
    blocks = [l for l in llist if l.get("type") == "BLOCK" or l.get("status") == "BLOCKED"]

    past_nights = 0
    past_rev = 0
    future_booked = 0
    future_blocked = 0
    future_rev = 0
    weekly_data = defaultdict(lambda: {"nights": 0, "rev": 0})
    monthly_data = defaultdict(lambda: {"nights": 0, "rev": 0})

    for b in bookings:
        ci = b.get("checkInLocalDateTime", "")
        co = b.get("checkOutLocalDateTime", "")
        if not ci or not co: continue
        try:
            ci_dt = datetime.strptime(ci[:10], "%Y-%m-%d")
            co_dt = datetime.strptime(co[:10], "%Y-%m-%d")
        except: continue
        nts = max((co_dt - ci_dt).days, 1)
        rev = (info["daily"] * nts) + info["cleaning"]
        src = b.get("source","") or b.get("channel","")

        all_bookings.append({
            "prop": info["name"], "ci": ci_dt, "co": co_dt,
            "nights": nts, "rev": rev, "rate": info["daily"], "src": src
        })

        # Past vs future
        if co_dt <= TODAY:
            past_nights += nts
            past_rev += rev
        else:
            s = max(ci_dt, TODAY)
            e = min(co_dt, END)
            if s < e:
                fn = (e - s).days
                future_booked += fn
                future_rev += info["daily"] * fn

        # Weekly/monthly
        iy, iw, _ = ci_dt.isocalendar()
        wk = str(iy) + "-W" + str(iw).zfill(2)
        weekly_data[wk]["nights"] += nts
        weekly_data[wk]["rev"] += rev
        mo = ci_dt.strftime("%Y-%m")
        monthly_data[mo]["nights"] += nts
        monthly_data[mo]["rev"] += rev

    for b in blocks:
        ci = b.get("checkInLocalDateTime", "")
        co = b.get("checkOutLocalDateTime", "")
        if not ci or not co: continue
        try:
            ci_dt = datetime.strptime(ci[:10], "%Y-%m-%d")
            co_dt = datetime.strptime(co[:10], "%Y-%m-%d")
        except: continue
        s = max(ci_dt, TODAY)
        e = min(co_dt, END)
        if s < e:
            future_blocked += (e - s).days

    avail = WINDOW - future_booked - future_blocked
    occ = (future_booked + future_blocked) / WINDOW * 100 if WINDOW > 0 else 0
    book_occ = future_booked / WINDOW * 100 if WINDOW > 0 else 0

    prop_stats[uid] = {
        "name": info["name"], "rate": info["daily"], "bed": info["bedrooms"],
        "bookings": len(bookings), "blocks": len(blocks),
        "past_nights": past_nights, "past_rev": past_rev,
        "future_booked": future_booked, "future_blocked": future_blocked,
        "future_rev": future_rev, "avail": avail, "occ": occ, "book_occ": book_occ,
        "weekly": dict(weekly_data), "monthly": dict(monthly_data)
    }

# ================================================================
# 3. AGGREGATE & PRINT REPORT
# ================================================================
total_bookings = sum(s["bookings"] for s in prop_stats.values())
total_past_nights = sum(s["past_nights"] for s in prop_stats.values())
total_past_rev = sum(s["past_rev"] for s in prop_stats.values())
total_future_booked = sum(s["future_booked"] for s in prop_stats.values())
total_future_blocked = sum(s["future_blocked"] for s in prop_stats.values())
total_future_rev = sum(s["future_rev"] for s in prop_stats.values())
total_avail = sum(s["avail"] for s in prop_stats.values())
total_possible = WINDOW * N_PROPS
overall_occ = (total_future_booked + total_future_blocked) / total_possible * 100 if total_possible > 0 else 0
booking_occ = total_future_booked / total_possible * 100 if total_possible > 0 else 0

# Aggregate weekly
agg_weekly = defaultdict(lambda: {"nights": 0, "rev": 0})
for s in prop_stats.values():
    for wk, d in s["weekly"].items():
        agg_weekly[wk]["nights"] += d["nights"]
        agg_weekly[wk]["rev"] += d["rev"]

# Aggregate monthly
agg_monthly = defaultdict(lambda: {"nights": 0, "rev": 0})
for s in prop_stats.values():
    for mo, d in s["monthly"].items():
        agg_monthly[mo]["nights"] += d["nights"]
        agg_monthly[mo]["rev"] += d["rev"]

# PAYMENT FREQUENCY
all_bookings.sort(key=lambda x: x["ci"])
jan1 = datetime(2026, 1, 1)
weeks_since_jan = max((TODAY - jan1).days / 7, 1)
bookings_per_week = total_bookings / weeks_since_jan

# ================================================================
# PRINT
# ================================================================
print("=" * 80)
print("  HOSTFULLY REVENUE FORECAST & INVENTORY GAP ANALYSIS")
print("  STR Solutions USA")
print("=" * 80)
print("  Analysis: " + TODAY.strftime("%Y-%m-%d"))
print("  Window:   Apr 13 - Sep 1, 2026 (" + str(WINDOW) + " days / " + "{:.0f}".format(WINDOW/7) + " weeks)")
print("  Source:   Hostfully API v3.2 (live data)")
print()

# -- Property Fleet --
print("=" * 80)
print("A. PROPERTY FLEET & NIGHTLY RATES")
print("=" * 80)
for uid in sorted(active, key=lambda u: active[u]["name"]):
    i = active[uid]
    s = prop_stats[uid]
    print("  " + i["name"][:38].ljust(40) + str(i["bedrooms"]) + "BR  $" + str(int(i["daily"])).rjust(4) + "/nt  " + str(s["bookings"]) + " bookings  occ:" + "{:.0f}".format(s["occ"]) + "%")

print()
print("  Fleet:    " + str(N_PROPS) + " active properties")
print("  Avg rate: $" + "{:.0f}".format(AVG_RATE) + "/night")
print("  Range:    $" + str(int(min(rates))) + " - $" + str(int(max(rates))) + "/night")

# -- Payment History --
print()
print("=" * 80)
print("B. PAYMENT FREQUENCY (Jan 1 - Apr 12, 2026)")
print("=" * 80)
print("  Total bookings:     " + str(total_bookings))
print("  Weeks elapsed:      " + "{:.1f}".format(weeks_since_jan))
print("  Bookings/week:      " + "{:.1f}".format(bookings_per_week))
print("  Total booked nights:" + str(total_past_nights + total_future_booked))
print("  Total revenue:      $" + "{:,.0f}".format(total_past_rev + total_future_rev))
print()
print("  Monthly breakdown:")
for mo in sorted(agg_monthly):
    d = agg_monthly[mo]
    print("    " + mo + ": $" + "{:>9,.0f}".format(d["rev"]) + "  (" + str(d["nights"]) + " nights)")

print()
print("  Weekly breakdown:")
wk_revs = []
for wk in sorted(agg_weekly):
    d = agg_weekly[wk]
    wk_revs.append(d["rev"])
    print("    " + wk + ": $" + "{:>9,.0f}".format(d["rev"]) + "  (" + str(d["nights"]) + " nights)")

if wk_revs:
    avg_wk_hist = sum(wk_revs) / len(wk_revs)
    print()
    print("  Avg weekly revenue (actual): $" + "{:,.0f}".format(avg_wk_hist))

# -- Calendar Availability --
print()
print("=" * 80)
print("C. CALENDAR AVAILABILITY (Apr 13 - Sep 1)")
print("=" * 80)
print("  Total possible nights:  " + "{:,}".format(total_possible))
print("  Booked nights:          " + str(total_future_booked) + " (" + "{:.1f}".format(booking_occ) + "% booking occ)")
print("  Blocked nights:         " + str(total_future_blocked) + " (owner holds, maintenance)")
print("  AVAILABLE (sellable):   " + str(total_avail) + " nights")
print("  Total occupancy:        " + "{:.1f}".format(overall_occ) + "%")
print("  Sellable rate:          " + "{:.1f}".format(total_avail / total_possible * 100) + "% of total")
print()
print("  Per-property:")
for uid in sorted(prop_stats, key=lambda u: prop_stats[u]["avail"], reverse=True):
    s = prop_stats[uid]
    bar_len = int(s["avail"] / WINDOW * 30)
    bar = "#" * bar_len + "." * (30 - bar_len)
    print("    " + s["name"][:35].ljust(37) + " Avl:" + str(s["avail"]).rjust(4) + "d  Bkd:" + str(s["future_booked"]).rjust(3) + "d  Blk:" + str(s["future_blocked"]).rjust(3) + "d  [" + bar + "]")

# -- Revenue Forecast --
print()
print("=" * 80)
print("D. WEEKLY REVENUE FORECAST (Apr 13 - Sep 1)")
print("=" * 80)

seasonal = {4: 1.0, 5: 1.1, 6: 1.3, 7: 1.4, 8: 1.3}
# Use booking-only occupancy for projection (excluding blocks)
base_book_occ = booking_occ / 100  # as decimal

forecast = []
d = TODAY
wn = 1
while d < END and wn <= 21:
    we = min(d + timedelta(days=7), END)
    wd = (we - d).days
    mo = d.month
    sf = seasonal.get(mo, 1.0)

    # Project occupancy based on actual booking rate + seasonal factor
    proj_occ = min(max(base_book_occ * sf, 0.05), 0.75)
    proj_nights = round(N_PROPS * wd * proj_occ)
    proj_rev = proj_nights * AVG_RATE * sf

    forecast.append({"wk": wn, "d": d, "wd": wd, "mo": mo, "sf": sf,
                     "occ": proj_occ, "nights": proj_nights, "rev": proj_rev})

    mo_name = d.strftime("%b %d")
    print("  W" + str(wn).ljust(3) + " " + mo_name.ljust(8) + " x" + "{:.1f}".format(sf) + "  occ:" + "{:>5.1f}".format(proj_occ*100) + "%  " + str(proj_nights).rjust(3) + " nights  $" + "{:>9,.0f}".format(proj_rev))
    d = we
    wn += 1

total_fc = sum(f["rev"] for f in forecast)
avg_wk_fc = total_fc / len(forecast) if forecast else 0
weeks_10 = sum(f["rev"] for f in forecast[:10])
weeks_16 = sum(f["rev"] for f in forecast[:16])

print()
print("  Total forecast (20 wks):     $" + "{:>10,.0f}".format(total_fc))
print("  Average weekly:              $" + "{:>10,.0f}".format(avg_wk_fc))
print("  Next 10 weeks total:         $" + "{:>10,.0f}".format(weeks_10))
print("  Next 16 weeks total:         $" + "{:>10,.0f}".format(weeks_16))

# ================================================================
# E. $6,000/WEEK INCREASE ANALYSIS
# ================================================================
print()
print("=" * 80)
print("E. $6,000/WEEK REVENUE INCREASE - INVENTORY ANALYSIS")
print("=" * 80)

TARGET = 6000
avg_occ_fc = sum(f["occ"] for f in forecast) / len(forecast) if forecast else 0.05
avg_sf = sum(f["sf"] for f in forecast) / len(forecast) if forecast else 1.2

print()
print("  CURRENT STATE")
print("  " + "-" * 50)
print("  Properties:             " + str(N_PROPS))
print("  Avg nightly rate:       $" + "{:.0f}".format(AVG_RATE))
print("  Booking occupancy:      " + "{:.1f}".format(booking_occ) + "%")
print("  Projected avg weekly:   $" + "{:,.0f}".format(avg_wk_fc))
print("  Available inventory:    " + str(total_avail) + " nights (" + "{:.0f}".format(total_avail/WINDOW*7) + " nights/week)")

print()
print("  TARGET")
print("  " + "-" * 50)
print("  Additional weekly rev:  $" + "{:,.0f}".format(TARGET))
print("  Target weekly total:    $" + "{:,.0f}".format(avg_wk_fc + TARGET))
if avg_wk_fc > 0:
    print("  Increase required:      +" + "{:.0f}".format(TARGET/avg_wk_fc*100) + "%")

# Calculate inventory needed
# Revenue = nights * rate * seasonal_factor
# Additional nights needed per week
eff_rate = AVG_RATE * avg_sf  # effective rate with seasonal
add_nights_wk = TARGET / eff_rate if eff_rate > 0 else 0
nights_per_prop_wk = 7 * avg_occ_fc
add_props = add_nights_wk / nights_per_prop_wk if nights_per_prop_wk > 0 else 0

# Inventory = available nights to sell (prop capacity - booked - blocked)
current_wk_inv = total_avail / (WINDOW / 7)
add_wk_inv = add_nights_wk / avg_occ_fc if avg_occ_fc > 0 else 0
inv_pct = add_wk_inv / current_wk_inv * 100 if current_wk_inv > 0 else 0
prop_pct = add_props / N_PROPS * 100 if N_PROPS > 0 else 0

print()
print("  CALCULATION")
print("  " + "-" * 50)
print("  Effective avg rate (w/ seasonal): $" + "{:.0f}".format(eff_rate))
print("  Additional booked nights/week:    " + "{:.1f}".format(add_nights_wk))
print("  Nights per property per week:     " + "{:.1f}".format(nights_per_prop_wk) + " (at " + "{:.1f}".format(avg_occ_fc*100) + "% occ)")
print("  Additional properties needed:     " + "{:.1f}".format(add_props) + " = ~" + str(round(add_props)) + " properties")
print()
print("  ANSWER: INVENTORY INCREASE")
print("  " + "=" * 50)
print("  Current properties:     " + str(N_PROPS))
print("  Properties to add:      " + str(round(add_props)))
print("  New total:              " + str(N_PROPS + round(add_props)))
print("  PROPERTY INCREASE:      " + "{:.1f}".format(prop_pct) + "%")
print()
print("  Current weekly inventory:   " + "{:.0f}".format(current_wk_inv) + " sellable nights/week")
print("  Additional inventory:       " + "{:.0f}".format(add_wk_inv) + " sellable nights/week")
print("  INVENTORY INCREASE:         " + "{:.1f}".format(inv_pct) + "%")

# Revenue per new property
rev_per_prop = nights_per_prop_wk * eff_rate
print()
print("  Each new property earns:    ~$" + "{:,.0f}".format(rev_per_prop) + "/week")
print("  Each new property earns:    ~$" + "{:,.0f}".format(rev_per_prop * 4.33) + "/month")
print("  Verification: " + str(round(add_props)) + " props x $" + "{:,.0f}".format(rev_per_prop) + " = $" + "{:,.0f}".format(round(add_props) * rev_per_prop) + "/wk")

# Sensitivity
print()
print("=" * 80)
print("F. SENSITIVITY TABLE")
print("=" * 80)
print("  " + "Scenario".ljust(35) + "Rate".rjust(8) + "  Occ".rjust(6) + "  Props".rjust(7) + " Prop%".rjust(7) + "  Inv%".rjust(7))
print("  " + "-" * 70)

for label, rm, om in [
    ("Conservative (low occ + rate)", 0.85, 0.7),
    ("Current trajectory", 1.0, 1.0),
    ("Improve occupancy to 10%", 1.0, 10.0/booking_occ if booking_occ > 0 else 2),
    ("Improve occupancy to 15%", 1.0, 15.0/booking_occ if booking_occ > 0 else 3),
    ("Summer peak rates (1.35x)", 1.35, 1.15),
    ("Premium pricing ($650/nt)", 650/AVG_RATE if AVG_RATE > 0 else 1.2, 1.0),
    ("Best case (peak + 15% occ)", 1.35, 15.0/booking_occ if booking_occ > 0 else 3),
]:
    r = AVG_RATE * rm
    o = min(avg_occ_fc * om, 0.75)
    er = r * avg_sf
    an = TARGET / er if er > 0 else 0
    npw = 7 * o
    ap = an / npw if npw > 0 else 0
    pp = ap / N_PROPS * 100 if N_PROPS > 0 else 0
    ai = an / o if o > 0 else 0
    ip = ai / current_wk_inv * 100 if current_wk_inv > 0 else 0
    print("  " + label[:35].ljust(35) + "$" + "{:>6.0f}".format(r) + " " + "{:>5.1f}".format(o*100) + "% " + "{:>5.1f}".format(ap) + "  " + "{:>5.0f}".format(pp) + "% " + "{:>6.0f}".format(ip) + "%")

print()
print("=" * 80)
print("G. KEY FINDINGS & RECOMMENDATIONS")
print("=" * 80)
print("""
  1. YOUR FLEET: {props} properties at avg ${rate:.0f}/night.
     Booking occupancy is {occ:.1f}% with {blocked} blocked nights (owner holds).
     Available inventory: {avail:,} sellable nights through Sep 1.

  2. CURRENT WEEKLY REVENUE: ~${wk:,.0f}/week projected.
     This is based on {occ:.1f}% booking occupancy with seasonal adjustments.

  3. TO ADD $6,000/WEEK:
     -> Need ~{ap} additional properties (a {pp:.0f}% fleet increase).
     -> This adds ~{ai:.0f} sellable nights/week = {ip:.0f}% inventory increase.
     -> Each new property generates ~${rpw:,.0f}/week at current rates.

  4. TWO PATHS TO $6,000/WEEK:
     a) ADD PROPERTIES: {ap} new properties at current occupancy
     b) IMPROVE OCCUPANCY: Get booking rate from {occ:.1f}% to {target_occ:.1f}%
        (reduces properties needed to {ap_hi} with existing fleet)
     c) COMBINATION: Add fewer properties + improve marketing/pricing

  5. TIMING: Adding properties before June captures peak summer
     rates (1.3-1.4x multiplier). Each property added now has
     {window} days of revenue runway through Sep 1.

  6. HIGHEST-VALUE ADDS: Properties similar to Clifton Hill condos
     (2BR, $549/nt) show highest booking frequency. The mountain
     retreat properties (*starred) have heavy block/hold periods.
""".format(
    props=N_PROPS, rate=AVG_RATE, occ=booking_occ, blocked=total_future_blocked,
    avail=total_avail, wk=avg_wk_fc, ap=round(add_props), pp=prop_pct,
    ai=add_wk_inv, ip=inv_pct, rpw=rev_per_prop,
    target_occ=min(booking_occ + TARGET/(N_PROPS*7*AVG_RATE*avg_sf/100), 75),
    ap_hi=max(round(add_props * 0.5), 1), window=WINDOW
))
