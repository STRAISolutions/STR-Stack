#!/usr/bin/env python3
"""Hostfully Properties + Bookings Collector
Fetches property list and active bookings, writes JSON for dashboard.
Cron: */15 * * * *
"""
import json, subprocess, datetime

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

def api_get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "15", url,
        "-H", f"X-HOSTFULLY-APIKEY: {API_KEY}"], capture_output=True, text=True)
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except:
        return {}

# --- Properties ---
print("Fetching properties...")
pdata = api_get(f"{BASE}/properties?agencyUid={AGENCY}&_limit=100")
props = pdata.get("properties", [])
print(f"  Got {len(props)} properties")

prop_list = []
for p in props:
    prop_list.append({
        "uid": p.get("uid", ""),
        "name": p.get("name", "Unnamed"),
        "isActive": p.get("isActive", False),
        "propertyType": p.get("propertyType", ""),
        "bedrooms": p.get("bedrooms", "?"),
        "bathrooms": p.get("bathrooms", "?"),
        "city": p.get("city", ""),
        "state": p.get("state", ""),
        "maxGuests": p.get("maxGuests", "?"),
    })

with open(OUT_PROPS, "w") as f:
    json.dump({"updated_at": NOW, "count": len(prop_list), "properties": prop_list}, f, indent=2)
print(f"  Wrote {OUT_PROPS}")

# --- Bookings ---
print("Fetching bookings...")
ldata = api_get(f"{BASE}/leads?agencyUid={AGENCY}&_limit=500")
all_leads = ldata.get("leads", [])
booked = [l for l in all_leads if l.get("type") != "BLOCK" and l.get("status") == "BOOKED"]
print(f"  Got {len(booked)} active bookings from {len(all_leads)} leads")

booking_list = []
for l in booked:
    gi = l.get("guestInformation") or {}
    first = gi.get("firstName") or ""
    last = gi.get("lastName") or ""
    name = (first + " " + last).strip() or "(No name)"
    booking_list.append({
        "uid": l.get("uid", ""),
        "guest": name,
        "email": gi.get("email", ""),
        "phone": gi.get("phoneNumber", ""),
        "channel": l.get("channel", "UNKNOWN"),
        "checkin": l.get("checkInLocalDateTime") or l.get("checkInLocalDate") or "?",
        "checkout": l.get("checkOutLocalDateTime") or l.get("checkOutLocalDate") or "?",
        "property": l.get("propertyUid", ""),
        "status": l.get("status", ""),
    })

with open(OUT_BOOKINGS, "w") as f:
    json.dump({"updated_at": NOW, "count": len(booking_list), "bookings": booking_list}, f, indent=2)
print(f"  Wrote {OUT_BOOKINGS}")

print(f"[{NOW}] Properties: {len(prop_list)}, Active Bookings: {len(booking_list)}")
