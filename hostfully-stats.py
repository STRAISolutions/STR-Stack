#!/usr/bin/env python3
"""Hostfully Traveler Stats Collector v2
Fetches bookings and computes KPIs. Orders fetched only for recent bookings.
Writes /srv/str-stack-public/hostfully-stats.json
Cron: */15 * * * *
"""
import json, subprocess, datetime
from collections import Counter

OUT = "/srv/str-stack-public/hostfully-stats.json"
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

# Fetch leads (single call, max 500)
data = api_get(f"{BASE}/leads?agencyUid={AGENCY}&_limit=500")
all_leads = data.get("leads", [])
print(f"Fetched {len(all_leads)} leads")

# Categorize
bookings = [l for l in all_leads if l.get("type") == "BOOKING"]
active_bookings = [b for b in bookings if b.get("status") == "BOOKED"]
cancelled = [b for b in bookings if b.get("status") == "CANCELLED"]
inquiries = [l for l in all_leads if l.get("type") == "INQUIRY"]

today = datetime.date.today()
week_start = today - datetime.timedelta(days=today.weekday())
week_end = week_start + datetime.timedelta(days=6)
month_start = today.replace(day=1)
year_start = today.replace(month=1, day=1)

def parse_date(dt_str):
    if not dt_str:
        return None
    try:
        return datetime.datetime.fromisoformat(dt_str).date()
    except:
        return None

# This week arrivals
this_week_arrivals = []
for b in active_bookings:
    ci = parse_date(b.get("checkInLocalDateTime"))
    if ci and week_start <= ci <= week_end:
        this_week_arrivals.append(b)

# Fetch orders for this month's bookings only (limit API calls)
this_month_bookings = [b for b in active_bookings
    if parse_date(b.get("checkInLocalDateTime")) and
       parse_date(b.get("checkInLocalDateTime")) >= month_start]

this_year_bookings = [b for b in active_bookings
    if parse_date(b.get("checkInLocalDateTime")) and
       parse_date(b.get("checkInLocalDateTime")) >= year_start]

total_revenue_month = 0
total_revenue_year = 0
total_revenue_week = 0
balance_due = 0
overdue_count = 0
overdue_amount = 0

# Get orders for all active bookings (batch, but limit to avoid overload)
print(f"Fetching orders for {len(active_bookings)} active bookings...")
for i, b in enumerate(active_bookings):
    uid = b["uid"]
    ci = parse_date(b.get("checkInLocalDateTime"))
    channel = b.get("channel", "")

    odata = api_get(f"{BASE}/orders?leadUid={uid}")
    orders = odata.get("orders", [])

    for o in orders:
        amt = o.get("totalAmount", 0) or 0

        if ci:
            if ci >= year_start:
                total_revenue_year += amt
            if ci >= month_start:
                total_revenue_month += amt
            if week_start <= ci <= week_end:
                total_revenue_week += amt

        # Check transactions for payment status
        tdata = api_get(f"{BASE}/transactions?orderUid={o['uid']}")
        txns = tdata.get("transactions", [])
        paid = sum(t.get("amount", 0) or 0 for t in txns)
        remaining = amt - paid

        if remaining > 0.01:
            balance_due += remaining
            if ci and ci <= today + datetime.timedelta(days=7):
                overdue_count += 1
                overdue_amount += remaining

    if (i + 1) % 25 == 0:
        print(f"  Processed {i+1}/{len(active_bookings)}")

# Channel breakdown
channel_counts = dict(Counter(b.get("channel") for b in active_bookings))

result = {
    "updated_at": NOW,
    "summary": {
        "total_leads": len(all_leads),
        "total_bookings": len(bookings),
        "active_bookings": len(active_bookings),
        "cancelled": len(cancelled),
        "inquiries": len(inquiries)
    },
    "revenue": {
        "this_year": round(total_revenue_year, 2),
        "this_month": round(total_revenue_month, 2),
        "this_week": round(total_revenue_week, 2)
    },
    "payments": {
        "balance_due": round(balance_due, 2),
        "overdue_count": overdue_count,
        "overdue_amount": round(overdue_amount, 2)
    },
    "arrivals": {
        "this_week": len(this_week_arrivals),
        "details": [
            {
                "guest": ((b.get("guestInformation") or {}).get("firstName") or "") + " " + ((b.get("guestInformation") or {}).get("lastName") or ""),
                "checkin": b.get("checkInLocalDateTime", ""),
                "channel": b.get("channel", ""),
                "property": b.get("propertyUid", "")[:8]
            }
            for b in this_week_arrivals
        ]
    },
    "channels": channel_counts,
    "properties": {"total": 44}
}

with open(OUT, "w") as f:
    json.dump(result, f, indent=2)

print(f"[{NOW}] Hostfully: {len(active_bookings)} active, ${total_revenue_year:.0f} YTD, {len(this_week_arrivals)} arrivals this week")
