#!/usr/bin/env python3
"""Debug: check unknown property UIDs from leads and get ALL leads for active properties"""
import json, subprocess
from collections import defaultdict
from datetime import datetime

API_KEY = "ukNruuLswAygrvUi"
AGENCY = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE = "https://platform.hostfully.com/api/v3.2"

def api(endpoint):
    r = subprocess.run(["curl","-s","-H","X-HOSTFULLY-APIKEY: "+API_KEY, BASE+"/"+endpoint],
                       capture_output=True, text=True, timeout=30)
    try: return json.loads(r.stdout)
    except: return {"error": r.stdout[:300]}

# Get active properties
props = api("properties?agencyUid="+AGENCY+"&limit=100")
plist = props.get("properties", props if isinstance(props, list) else [])
active_uids = {}
for p in plist:
    if p.get("isActive"):
        active_uids[p["uid"]] = p.get("name","?")

print("=== ACTIVE PROPERTIES ===")
for uid, name in sorted(active_uids.items(), key=lambda x: x[1]):
    print("  " + uid + " = " + name)

# Check unknown property UIDs from leads
unknown_uids = [
    "f34c94e0-f4f9-4b9d-b37d-d1c09efc9f64",
    "878e3abd-d809-4428-b5a3-ff2b12ce4d49",
    "625ce688-f5e3-4236-9c94-bfab0e0bdea1",
    "94b7040c-36e9-44a7-99df-74e5e2d7cd63",
    "a6613f40-e839-4973-926e-d3e6e458d72a",
]
print("\n=== UNKNOWN PROPERTY UIDs FROM LEADS ===")
for uid in unknown_uids:
    pd = api("properties/" + uid)
    prop = pd.get("property", pd)
    if isinstance(prop, dict):
        name = prop.get("name", "?")
        active = prop.get("isActive", "?")
        agency = prop.get("agencyUid", "?")
        print("  " + uid[:20] + " = " + str(name) + " | active=" + str(active) + " | agency=" + str(agency)[:20])
    else:
        print("  " + uid[:20] + " = ERROR: " + str(pd)[:100])

# Now try getting leads per active property
print("\n=== LEADS PER ACTIVE PROPERTY ===")
total_bookings = 0
total_nights = 0
total_rev = 0
prop_data = {}

for uid, name in sorted(active_uids.items(), key=lambda x: x[1]):
    leads_data = api("leads?propertyUid=" + uid + "&limit=100&checkInFrom=2026-01-01&checkInTo=2026-09-01")
    leads = leads_data.get("leads", [])

    bookings = [l for l in leads if l.get("type") != "BLOCK" and l.get("status") not in ["BLOCKED","CANCELLED","DECLINED"]]
    blocks = [l for l in leads if l.get("type") == "BLOCK" or l.get("status") == "BLOCKED"]

    # Get rate
    pd = api("properties/" + uid)
    pr = pd.get("property", pd)
    pricing = pr.get("pricing", {}) if isinstance(pr, dict) else {}
    daily_rate = pricing.get("dailyRate", 0) or 0
    cleaning = pricing.get("cleaningFee", 0) or 0

    # Calculate nights and revenue
    prop_nights = 0
    prop_rev = 0
    booking_details = []
    for b in bookings:
        ci = b.get("checkInLocalDateTime", "")
        co = b.get("checkOutLocalDateTime", "")
        if not ci or not co:
            continue
        try:
            ci_dt = datetime.strptime(ci[:10], "%Y-%m-%d")
            co_dt = datetime.strptime(co[:10], "%Y-%m-%d")
        except:
            continue
        nts = max((co_dt - ci_dt).days, 1)
        rev = (daily_rate * nts) + cleaning
        prop_nights += nts
        prop_rev += rev
        src = b.get("source","") or b.get("channel","")
        booking_details.append(ci[:10] + " -> " + co[:10] + " (" + str(nts) + "n) $" + str(int(rev)) + " " + src)

    # Count blocked future nights
    today = datetime(2026, 4, 13)
    end = datetime(2026, 9, 1)
    blocked_future = 0
    booked_future = 0
    for b in blocks:
        ci = b.get("checkInLocalDateTime", "")
        co = b.get("checkOutLocalDateTime", "")
        if not ci or not co: continue
        try:
            ci_dt = datetime.strptime(ci[:10], "%Y-%m-%d")
            co_dt = datetime.strptime(co[:10], "%Y-%m-%d")
        except: continue
        s = max(ci_dt, today)
        e = min(co_dt, end)
        if s < e:
            blocked_future += (e - s).days

    for b in bookings:
        ci = b.get("checkInLocalDateTime", "")
        co = b.get("checkOutLocalDateTime", "")
        if not ci or not co: continue
        try:
            ci_dt = datetime.strptime(ci[:10], "%Y-%m-%d")
            co_dt = datetime.strptime(co[:10], "%Y-%m-%d")
        except: continue
        s = max(ci_dt, today)
        e = min(co_dt, end)
        if s < e:
            booked_future += (e - s).days

    window = (end - today).days
    avail = window - booked_future - blocked_future
    occ = (booked_future + blocked_future) / window * 100 if window > 0 else 0

    total_bookings += len(bookings)
    total_nights += prop_nights
    total_rev += prop_rev

    prop_data[uid] = {
        "name": name, "rate": daily_rate, "cleaning": cleaning,
        "bookings": len(bookings), "blocks": len(blocks),
        "nights": prop_nights, "rev": prop_rev,
        "booked_future": booked_future, "blocked_future": blocked_future,
        "avail": avail, "occ": occ
    }

    print("\n  " + name + " ($" + str(int(daily_rate)) + "/nt)")
    print("    Bookings: " + str(len(bookings)) + " | Blocks: " + str(len(blocks)))
    print("    Total nights: " + str(prop_nights) + " | Revenue: $" + "{:,.0f}".format(prop_rev))
    print("    Future (Apr13-Sep1): Booked " + str(booked_future) + "d | Blocked " + str(blocked_future) + "d | Avail " + str(avail) + "d | Occ " + "{:.1f}".format(occ) + "%")
    for d in booking_details[:5]:
        print("      " + d)
    if len(booking_details) > 5:
        print("      ... +" + str(len(booking_details)-5) + " more")

# Summary
print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
print("Total active properties: " + str(len(active_uids)))
print("Total bookings (Jan-Sep): " + str(total_bookings))
print("Total nights: " + str(total_nights))
print("Total revenue: $" + "{:,.2f}".format(total_rev))
if total_nights > 0:
    print("Avg rate per night: $" + "{:,.2f}".format(total_rev / total_nights))

window = 141
total_possible = window * len(active_uids)
total_booked_f = sum(d["booked_future"] for d in prop_data.values())
total_blocked_f = sum(d["blocked_future"] for d in prop_data.values())
total_avail = sum(d["avail"] for d in prop_data.values())
occ_pct = (total_booked_f + total_blocked_f) / total_possible * 100 if total_possible > 0 else 0

print("\nFuture (Apr 13 - Sep 1):")
print("  Possible nights: " + str(total_possible))
print("  Booked: " + str(total_booked_f))
print("  Blocked: " + str(total_blocked_f))
print("  Available: " + str(total_avail))
print("  Occupancy: " + "{:.1f}".format(occ_pct) + "%")
