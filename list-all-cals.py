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
    slug = c.get("widgetSlug", "?")
    dur = c.get("slotDuration", "?")
    print(f"  {name} | slug: {slug} | {dur} min")
print(f"\nTotal: {len(data.get('calendars', []))}")
