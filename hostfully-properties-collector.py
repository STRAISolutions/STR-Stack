#!/usr/bin/env python3
"""Hostfully Properties + Bookings Collector v2
Fetches property list, active bookings, and order financials.
Writes enriched JSON for dashboard with collapsible detail + filters.
Cron: */15 * * * *
"""
import json, subprocess, datetime, time

OUT_PROPS = "/srv/str-stack-public/hostfully-properties.json"
OUT_BOOKINGS = "/srv/str-stack-public/hostfully-bookings.json"
now = datetime.datetime.now(datetime.timezone.utc)
NOW = now.strftime("%Y-%m-%dT%H:%M:%SZ")

with open("/root/str-stack/.env") as f:
    env = {}
    for line in f:
        if "=" in line and not line.startswith("#"):
            k, v = line.strip().split("=", 1)
            env[k] = v.strip('"')

API_KEY = env.get("HOSTFULLY_API_KEY", "")
AGENCY = env.get("HOSTFULLY_AGENCY_UID", "")
BASE = "https://platform.hostfully.com/api/v3.2"

def api_get(url, retries=2):
    for attempt in range(retries + 1):
        r = subprocess.run(["curl", "-s", "--max-time", "20", url,
            "-H", "X-HOSTFULLY-APIKEY: " + API_KEY], capture_output=True, text=True)
        try:
            d = json.loads(r.stdout) if r.stdout.strip() else {}
            if "apiErrorMessage" not in d:
                return d
        except:
            pass
        if attempt < retries:
            time.sleep(1)
    return {}

# --- Properties (with pagination fix: _limit not limit) ---
print("Fetching properties...")
pdata = api_get(BASE + "/properties?agencyUid=" + AGENCY + "&_limit=100")
props = pdata.get("properties", [])

# Handle pagination
paging = pdata.get("_paging") or {}
cursor = paging.get("_nextCursor")
while cursor:
    page = api_get(BASE + "/properties?agencyUid=" + AGENCY + "&_limit=100&_cursor=" + cursor)
    batch = page.get("properties", [])
    if not batch:
        break
    props.extend(batch)
    paging = page.get("_paging") or {}
    cursor = paging.get("_nextCursor")

print("  Got " + str(len(props)) + " properties total")

# Build property lookup map
prop_map = {}
prop_list = []
for p in props:
    uid = p.get("uid", "")
    name = p.get("name", "Unnamed")
    city = p.get("city", "")
    state = p.get("state", "")
    if isinstance(p.get("address"), dict):
        city = city or p["address"].get("city", "")
        state = state or p["address"].get("state", "")
    active = p.get("isActive", False)

    prop_map[uid] = {"name": name, "city": city, "state": state, "active": active}
    prop_list.append({
        "uid": uid,
        "name": name,
        "isActive": active,
        "propertyType": p.get("propertyType", ""),
        "bedrooms": p.get("bedrooms", "?"),
        "bathrooms": p.get("bathrooms", "?"),
        "city": city,
        "state": state,
        "maxGuests": p.get("maxGuests", "?"),
    })

# Fetch individual property details for pricing + city
print("  Enriching properties with pricing + location...")
for i, p in enumerate(prop_list):
    if not p["isActive"]:
        continue
    detail = api_get(BASE + "/properties/" + p["uid"])
    prop_detail = detail.get("property", detail)
    pricing = prop_detail.get("pricing") or {}
    rate = pricing.get("dailyRate", 0)
    cleaning = pricing.get("cleaningFee", 0)
    # Update city from detail if missing
    if not p["city"]:
        addr = prop_detail.get("address") or {}
        p["city"] = addr.get("city", "") or prop_detail.get("city", "")
        p["state"] = addr.get("state", "") or prop_detail.get("state", "")
        prop_map[p["uid"]]["city"] = p["city"]
        prop_map[p["uid"]]["state"] = p["state"]
    prop_map[p["uid"]]["dailyRate"] = rate
    prop_map[p["uid"]]["cleaningFee"] = cleaning
    p["dailyRate"] = rate
    p["cleaningFee"] = cleaning
    if (i + 1) % 10 == 0:
        print("    ...enriched " + str(i + 1) + " properties")
        time.sleep(0.5)

with open(OUT_PROPS, "w") as f:
    json.dump({"updated_at": NOW, "count": len(prop_list), "properties": prop_list}, f, indent=2)
print("  Wrote " + OUT_PROPS)

# --- Bookings (with pagination) ---
print("Fetching bookings...")
all_leads = []
ldata = api_get(BASE + "/leads?agencyUid=" + AGENCY + "&_limit=500")
all_leads.extend(ldata.get("leads", []))
paging = ldata.get("_paging") or {}
cursor = paging.get("_nextCursor")
while cursor:
    page = api_get(BASE + "/leads?agencyUid=" + AGENCY + "&_limit=500&_cursor=" + cursor)
    batch = page.get("leads", [])
    if not batch:
        break
    all_leads.extend(batch)
    paging = page.get("_paging") or {}
    cursor = paging.get("_nextCursor")

booked = [l for l in all_leads if l.get("type") != "BLOCK" and l.get("status") == "BOOKED"]
print("  Got " + str(len(booked)) + " active bookings from " + str(len(all_leads)) + " total leads")

# Fetch orders (financials) for each booking
print("  Enriching bookings with financial data...")
booking_list = []
for i, l in enumerate(booked):
    gi = l.get("guestInformation") or {}
    first = gi.get("firstName") or ""
    last = gi.get("lastName") or ""
    name = (first + " " + last).strip() or "(No name)"
    lead_uid = l.get("uid", "")
    prop_uid = l.get("propertyUid", "")

    # Calculate nights
    checkin = l.get("checkInLocalDateTime") or l.get("checkInLocalDate") or ""
    checkout = l.get("checkOutLocalDateTime") or l.get("checkOutLocalDate") or ""
    nights = 0
    try:
        ci = datetime.datetime.fromisoformat(checkin[:10])
        co = datetime.datetime.fromisoformat(checkout[:10])
        nights = (co - ci).days
    except:
        pass

    # Get property info
    pm = prop_map.get(prop_uid, {})
    prop_name = pm.get("name", "Unknown Property")
    prop_city = pm.get("city", "")
    prop_state = pm.get("state", "")

    # Fetch order financials
    total_amount = 0
    nightly_rate = 0
    cleaning_fee = 0
    tax_amount = 0
    currency = "USD"
    rent_net = 0

    order_data = api_get(BASE + "/orders?leadUid=" + lead_uid)
    orders = order_data.get("orders", [])
    if orders:
        o = orders[0]
        total_amount = o.get("totalAmount", 0) or 0
        currency = o.get("currency", "USD")
        tax_amount = o.get("totalTaxesAmount", 0) or 0
        rent = o.get("rent") or {}
        rent_net = rent.get("netPrice", 0) or 0
        breakdowns = rent.get("rentBreakdowns", [])
        if breakdowns:
            nightly_rate = breakdowns[0].get("nightlyAmount", 0) or 0
        fees = o.get("fees") or {}
        cf = fees.get("cleaningFee") or {}
        cleaning_fee = cf.get("grossPrice", 0) or 0

    booking_list.append({
        "uid": lead_uid,
        "guest": name,
        "email": gi.get("email", ""),
        "phone": gi.get("phoneNumber", "") or gi.get("cellPhoneNumber", ""),
        "channel": l.get("channel", "UNKNOWN"),
        "source": l.get("source", ""),
        "checkin": checkin,
        "checkout": checkout,
        "nights": nights,
        "property": prop_uid,
        "propertyName": prop_name,
        "city": prop_city,
        "state": prop_state,
        "status": l.get("status", ""),
        "bookedDate": l.get("bookedUtcDateTime", ""),
        "adults": gi.get("adultCount", 0),
        "children": gi.get("childrenCount", 0),
        "pets": gi.get("petCount", 0),
        "country": gi.get("countryCode", ""),
        "totalAmount": round(total_amount, 2),
        "nightlyRate": round(nightly_rate, 2),
        "cleaningFee": round(cleaning_fee, 2),
        "taxAmount": round(tax_amount, 2),
        "rentNet": round(rent_net, 2),
        "currency": currency,
        "externalId": l.get("externalBookingId", ""),
    })

    if (i + 1) % 20 == 0:
        print("    ...enriched " + str(i + 1) + "/" + str(len(booked)) + " bookings")
        time.sleep(0.3)

# Sort by checkin date
booking_list.sort(key=lambda b: b.get("checkin", ""))

# Compute summary stats
cities = list(set(b["city"] for b in booking_list if b["city"]))
cities.sort()
properties_with_bookings = list(set(b["propertyName"] for b in booking_list))
properties_with_bookings.sort()
total_revenue = sum(b["totalAmount"] for b in booking_list)

with open(OUT_BOOKINGS, "w") as f:
    json.dump({
        "updated_at": NOW,
        "count": len(booking_list),
        "total_revenue": round(total_revenue, 2),
        "cities": cities,
        "properties": properties_with_bookings,
        "bookings": booking_list
    }, f, indent=2)
print("  Wrote " + OUT_BOOKINGS)

print("")
print("[" + NOW + "] Properties: " + str(len(prop_list)) + " (" + str(sum(1 for p in prop_list if p["isActive"])) + " active)")
print("  Active Bookings: " + str(len(booking_list)))
print("  Total Revenue: $" + "{:,.2f}".format(total_revenue))
print("  Cities: " + ", ".join(cities[:10]))
