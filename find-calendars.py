#!/usr/bin/env python3
import requests
API = "https://services.leadconnectorhq.com"
H = {
    "Authorization": "Bearer pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7",
    "Version": "2021-07-28",
    "Accept": "application/json",
}
r = requests.get(f"{API}/calendars/", params={"locationId": "1OOZ4AKIgxO8QKKMnIcK"}, headers=H, timeout=15)
data = r.json()
for c in data.get("calendars", []):
    name = c.get("name", "")
    slug = c.get("widgetSlug", "")
    if "introductory" in name.lower() or "franchise" in name.lower() or "introductory" in slug or "franchise" in slug:
        cid = c.get("id")
        dur = c.get("slotDuration")
        unit = c.get("slotDurationUnit", "mins")
        ctype = c.get("calendarType")
        print(f"NAME: {name}")
        print(f"  ID: {cid}")
        print(f"  SLUG: {slug}")
        print(f"  TYPE: {ctype}")
        print(f"  DURATION: {dur} {unit}")
        print(f"  BOOKING URL: https://api.leadconnectorhq.com/widget/booking/{slug}")
        print()

print(f"Total calendars: {len(data.get('calendars', []))}")
