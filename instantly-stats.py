#!/usr/bin/env python3
"""Instantly Campaign Stats Collector — writes instantly-stats.json"""
import json, subprocess, datetime

OUT = "/srv/str-stack-public/instantly-stats.json"
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open("/root/str-stack/.env") as f:
    for line in f:
        if line.startswith("INSTANTLY_API_KEY="):
            API_KEY = line.strip().split("=", 1)[1].strip("\"")
            break

GT_ID = "d637ffed-b225-48a9-8369-867bea05ae62"

def api_get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "10", url,
        "-H", f"Authorization: Bearer {API_KEY}"], capture_output=True, text=True)
    return json.loads(r.stdout)

camps = api_get("https://api.instantly.ai/api/v2/campaigns?limit=100")
items = camps.get("items", [])
active = [c for c in items if c.get("status") == 1]
paused = [c for c in items if c.get("status") == 2]
completed = [c for c in items if c.get("status") == 3]

overview = api_get("https://api.instantly.ai/api/v2/campaigns/analytics/overview")
gt = api_get(f"https://api.instantly.ai/api/v2/campaigns/analytics/overview?campaign_id={GT_ID}")

result = {
    "updated_at": NOW,
    "campaigns": {
        "total": len(items), "active": len(active),
        "paused": len(paused), "completed": len(completed),
        "active_names": [c["name"] for c in active],
        "all_campaigns": [{"name":c["name"],"id":c["id"],"status":c.get("status",-1)} for c in items]
    },
    "overview": {
        "emails_sent": overview.get("emails_sent_count",0),
        "contacted": overview.get("contacted_count",0),
        "new_leads": overview.get("new_leads_contacted_count",0),
        "opened": overview.get("open_count_unique",0),
        "replied": overview.get("reply_count_unique",0),
        "bounced": overview.get("bounced_count",0),
        "interested": overview.get("total_interested",0),
        "opportunities": overview.get("total_opportunities",0),
        "opp_value": overview.get("total_opportunity_value",0),
        "meetings_booked": overview.get("total_meeting_booked",0)
    },
    "gt_icp1": {
        "id": GT_ID, "name": "GT | CAMPAIGN 1: Side-Hustle Host",
        "emails_sent": gt.get("emails_sent_count",0),
        "contacted": gt.get("contacted_count",0),
        "new_leads": gt.get("new_leads_contacted_count",0),
        "opened": gt.get("open_count_unique",0),
        "replied": gt.get("reply_count_unique",0),
        "bounced": gt.get("bounced_count",0),
        "interested": gt.get("total_interested",0),
        "opportunities": gt.get("total_opportunities",0)
    }
}

with open(OUT, "w") as f:
    json.dump(result, f, indent=2)
print(f"[{NOW}] Instantly: {len(active)} active / {len(items)} total")
