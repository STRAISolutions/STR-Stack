#!/usr/bin/env python3
import json, subprocess
from collections import defaultdict

API_KEY = "ukNruuLswAygrvUi"
AGENCY = "b87d17a1-5eb0-445d-8d3b-2b7bde5d6b30"
BASE = "https://platform.hostfully.com/api/v3.2"

def api(endpoint):
    r = subprocess.run(["curl","-s","-H","X-HOSTFULLY-APIKEY: "+API_KEY, BASE+"/"+endpoint],
                       capture_output=True, text=True, timeout=30)
    try: return json.loads(r.stdout)
    except: return {}

props = api("properties?agencyUid="+AGENCY+"&limit=100")
plist = props.get("properties", props if isinstance(props, list) else [])
active_uids = set()
prop_names = {}
for p in plist:
    prop_names[p["uid"]] = p.get("name","?")
    if p.get("isActive"):
        active_uids.add(p["uid"])
        print("Active: " + p["uid"][:12] + " = " + p.get("name","?"))

print("\nActive UIDs: " + str(len(active_uids)))
print("All property UIDs: " + str(len(prop_names)))

# Get first 200 leads in window
all_leads = []
cursor = None
for pg in range(10):
    url = "leads?agencyUid="+AGENCY+"&limit=100&checkInFrom=2026-01-01&checkInTo=2026-09-01"
    if cursor:
        url += "&cursor=" + cursor
    data = api(url)
    ld = data.get("leads", [])
    all_leads.extend(ld)
    cursor = data.get("_paging",{}).get("_nextCursor")
    if not cursor or not ld:
        break

print("\nTotal leads fetched: " + str(len(all_leads)))

# Property UID analysis
puid_counts = defaultdict(int)
puid_types = defaultdict(lambda: defaultdict(int))
for l in all_leads:
    puid = l.get("propertyUid","none")
    puid_counts[puid] += 1
    tp = l.get("type","?") + "/" + l.get("status","?")
    puid_types[puid][tp] += 1

print("\nProperty UID breakdown (top 25):")
for puid, cnt in sorted(puid_counts.items(), key=lambda x: -x[1])[:25]:
    in_act = "ACTIVE" if puid in active_uids else ("INACTIVE" if puid in prop_names else "UNKNOWN")
    nm = prop_names.get(puid, "???")
    types_str = ", ".join(k+":"+str(v) for k,v in puid_types[puid].items())
    print("  " + puid[:16] + " x" + str(cnt).rjust(4) + "  " + in_act.ljust(10) + " " + nm[:30] + "  [" + types_str + "]")

# Get financial data for a real booking
for l in all_leads:
    if l.get("type") != "BLOCK" and l.get("status") not in ["BLOCKED","CANCELLED"]:
        uid = l["uid"]
        print("\n--- Sample booking: " + uid[:20] + " ---")
        print("  Property: " + l.get("propertyUid","?")[:20])
        print("  Status: " + str(l.get("status")))
        print("  CheckIn: " + str(l.get("checkInLocalDateTime","?")))
        print("  CheckOut: " + str(l.get("checkOutLocalDateTime","?")))
        print("  Source: " + str(l.get("source","?")))

        # Try financials endpoint
        fin = api("leads/" + uid + "/financials")
        if fin and "error" not in str(fin).lower()[:50]:
            print("  Financials: " + json.dumps(fin, indent=2)[:1500])
        else:
            print("  Financials endpoint: " + str(fin)[:200])

        # Try order endpoint
        order = api("leads/" + uid + "/order")
        if order and "error" not in str(order).lower()[:50]:
            print("  Order: " + json.dumps(order, indent=2)[:1500])
        break

# Summary of booking types
print("\n--- Lead Types Summary ---")
type_counts = defaultdict(int)
status_counts = defaultdict(int)
for l in all_leads:
    type_counts[l.get("type","?")] += 1
    status_counts[l.get("status","?")] += 1
print("Types: " + str(dict(type_counts)))
print("Statuses: " + str(dict(status_counts)))

# Count only BOOKING type with BOOKED status for active properties
real = [l for l in all_leads if l.get("type") != "BLOCK"
        and l.get("status") not in ["BLOCKED","CANCELLED","DECLINED"]
        and l.get("propertyUid") in active_uids]
print("\nReal bookings for active properties: " + str(len(real)))
for r in real[:10]:
    ci = r.get("checkInLocalDateTime","?")[:10]
    co = r.get("checkOutLocalDateTime","?")[:10]
    nm = prop_names.get(r.get("propertyUid",""), "?")
    print("  " + ci + " -> " + co + "  " + nm[:30] + "  " + str(r.get("source","")))
