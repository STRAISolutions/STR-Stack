#!/usr/bin/env python3
"""Fix: Create the 2 calendars with correct GHL API schema."""
import requests
import json
import time

API_BASE = "https://services.leadconnectorhq.com"
HEADERS = {
    "Authorization": "Bearer pit-8e3c20cd-0d7f-43a3-be9d-c087e925b3e7",
    "Version": "2021-07-28",
    "Content-Type": "application/json",
    "Accept": "application/json",
}
LOCATION_ID = "1OOZ4AKIgxO8QKKMnIcK"
USER_ID = "Lc2bBJfpmmCueklVfR1B"

# ICP1 calendar already exists: "1D) Mike (STR Agent)" slug=introductory-meeting-str
# Only creating ICP5 franchise calendar
calendars = [
    {
        "name": "Franchise Discovery Call",
        "description": "ICP5 franchise candidates - 30 minute discovery call",
        "slug": "str-franchise-discovery-call",
        "slotDuration": 30,
        "slotInterval": 30,
        "slotBuffer": 15,
        "openHours": [
            {"daysOfTheWeek": [1], "hours": [{"openHour": 12, "openMinute": 0, "closeHour": 13, "closeMinute": 0}]},
            {"daysOfTheWeek": [3], "hours": [{"openHour": 19, "openMinute": 0, "closeHour": 20, "closeMinute": 0}]},
            {"daysOfTheWeek": [5], "hours": [{"openHour": 15, "openMinute": 0, "closeHour": 16, "closeMinute": 0}]},
        ],
    },
]

for cal in calendars:
    payload = {
        "locationId": LOCATION_ID,
        "name": cal["name"],
        "description": cal["description"],
        "widgetSlug": cal["slug"],
        "calendarType": "personal",
        "eventType": "RoundRobin_OptimizeForAvailability",
        "eventTitle": "{{contact.name}}",
        "slotDuration": cal["slotDuration"],
        "slotDurationUnit": "mins",
        "slotInterval": cal["slotInterval"],
        "slotIntervalUnit": "mins",
        "slotBuffer": cal.get("slotBuffer", 10),
        "slotBufferUnit": "mins",
        "appoinmentPerSlot": 1,
        "openHours": cal["openHours"],
        "autoConfirm": True,
        "teamMembers": [
            {
                "userId": USER_ID,
                "priority": 0.5,
                "meetingLocationType": "custom",
                "meetingLocation": "Zoom link will be provided",
            }
        ],
    }

    print(f"Creating: {cal['name']}...")
    r = requests.post(f"{API_BASE}/calendars/", json=payload, headers=HEADERS, timeout=15)
    if r.status_code in (200, 201):
        data = r.json()
        cal_data = data.get("calendar", data)
        cal_id = cal_data.get("id", "?")
        slug = cal_data.get("widgetSlug", cal["slug"])
        print(f"  + Created: id={cal_id}, slug={slug}")
        print(f"  Booking URL: https://api.leadconnectorhq.com/widget/booking/{slug}")
    else:
        print(f"  ERROR {r.status_code}: {r.text[:400]}")
    time.sleep(0.5)

print("\nDone.")
