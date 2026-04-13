#!/usr/bin/env python3
"""Instantly Campaign Stats Collector v2
Fetches campaign list + per-campaign analytics for ICP campaigns.
Writes instantly-stats.json for dashboard Cold Outbound + Marketing tabs.
Cron: */15 * * * *
"""
import json, subprocess, datetime, time

OUT = "/srv/str-stack-public/instantly-stats.json"
NOW = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

with open("/root/str-stack/.env") as f:
    for line in f:
        if line.startswith("INSTANTLY_API_KEY="):
            API_KEY = line.strip().split("=", 1)[1].strip('"')
            break

GT_ID = "d637ffed-b225-48a9-8369-867bea05ae62"

def api_get(url):
    r = subprocess.run(["curl", "-s", "--max-time", "10", url,
        "-H", "Authorization: Bearer " + API_KEY], capture_output=True, text=True)
    try:
        return json.loads(r.stdout) if r.stdout.strip() else {}
    except:
        return {}

# Fetch all campaigns
camps = api_get("https://api.instantly.ai/api/v2/campaigns?limit=100")
items = camps.get("items", [])
active = [c for c in items if c.get("status") == 1]
paused = [c for c in items if c.get("status") == 2]
completed = [c for c in items if c.get("status") == 3]

# Global overview
overview = api_get("https://api.instantly.ai/api/v2/campaigns/analytics/overview")
gt = api_get("https://api.instantly.ai/api/v2/campaigns/analytics/overview?campaign_id=" + GT_ID)

# --- ICP Campaign Per-Campaign Analytics ---
# Find all campaigns with "icp" in the name
icp_campaigns = [c for c in items if "icp" in c.get("name", "").lower()]
print("Found " + str(len(icp_campaigns)) + " ICP campaigns")

# Group by ICP number (1-6)
icp_groups = {}
for c in icp_campaigns:
    name = c.get("name", "")
    name_lower = name.lower()
    # Extract ICP number
    icp_num = None
    for i in range(1, 7):
        if "icp " + str(i) in name_lower or "icp" + str(i) in name_lower:
            icp_num = i
            break
    if icp_num is None:
        continue
    if icp_num not in icp_groups:
        icp_groups[icp_num] = []
    icp_groups[icp_num].append(c)

# Fetch analytics for each ICP campaign
icp_analytics = {}
for icp_num in sorted(icp_groups.keys()):
    group = icp_groups[icp_num]
    group_data = {
        "campaigns": [],
        "total_sent": 0,
        "total_contacted": 0,
        "total_opened": 0,
        "total_replied": 0,
        "total_bounced": 0,
        "total_interested": 0,
        "total_opportunities": 0,
        "total_opp_value": 0,
        "total_meetings": 0,
        "active_count": 0,
        "inactive_count": 0,
    }
    for c in group:
        cid = c.get("id", "")
        cname = c.get("name", "")
        cstatus = c.get("status", -1)
        is_active = cstatus == 1

        # Fetch per-campaign analytics
        analytics = {}
        if is_active or cstatus == 2 or cstatus == 3:
            analytics = api_get("https://api.instantly.ai/api/v2/campaigns/analytics/overview?campaign_id=" + cid)
            time.sleep(0.3)

        sent = analytics.get("emails_sent_count", 0) or 0
        contacted = analytics.get("contacted_count", 0) or 0
        opened = analytics.get("open_count_unique", 0) or 0
        replied = analytics.get("reply_count_unique", 0) or 0
        bounced = analytics.get("bounced_count", 0) or 0
        interested = analytics.get("total_interested", 0) or 0
        opportunities = analytics.get("total_opportunities", 0) or 0
        opp_value = analytics.get("total_opportunity_value", 0) or 0
        meetings = analytics.get("total_meeting_booked", 0) or 0

        camp_entry = {
            "id": cid,
            "name": cname,
            "status": cstatus,
            "is_active": is_active,
            "emails_sent": sent,
            "contacted": contacted,
            "opened": opened,
            "replied": replied,
            "bounced": bounced,
            "interested": interested,
            "opportunities": opportunities,
            "opp_value": opp_value,
            "meetings": meetings,
        }
        group_data["campaigns"].append(camp_entry)

        # Only aggregate active campaign stats into KPIs
        if is_active:
            group_data["active_count"] += 1
            group_data["total_sent"] += sent
            group_data["total_contacted"] += contacted
            group_data["total_opened"] += opened
            group_data["total_replied"] += replied
            group_data["total_bounced"] += bounced
            group_data["total_interested"] += interested
            group_data["total_opportunities"] += opportunities
            group_data["total_opp_value"] += opp_value
            group_data["total_meetings"] += meetings
        else:
            group_data["inactive_count"] += 1

    icp_analytics["icp" + str(icp_num)] = group_data
    print("  ICP " + str(icp_num) + ": " + str(len(group)) + " campaigns (" + str(group_data["active_count"]) + " active)")

# Build ICP label map
icp_labels = {
    "icp1": "Side-Hustle Host",
    "icp2": "Local Property Manager",
    "icp3": "Multi-Unit Pro",
    "icp4": "Boutique Hotelier",
    "icp5": "Franchisee",
    "icp6": "Traveller / Guest",
}

# Add labels to analytics
for k, v in icp_analytics.items():
    v["label"] = icp_labels.get(k, "Unknown")

result = {
    "updated_at": NOW,
    "campaigns": {
        "total": len(items), "active": len(active),
        "paused": len(paused), "completed": len(completed),
        "active_names": [c["name"] for c in active],
        "all_campaigns": [{"name":c["name"],"id":c["id"],"status":c.get("status",-1)} for c in items]
    },
    "overview": {
        "emails_sent": overview.get("emails_sent_count", 0),
        "contacted": overview.get("contacted_count", 0),
        "new_leads": overview.get("new_leads_contacted_count", 0),
        "opened": overview.get("open_count_unique", 0),
        "replied": overview.get("reply_count_unique", 0),
        "bounced": overview.get("bounced_count", 0),
        "interested": overview.get("total_interested", 0),
        "opportunities": overview.get("total_opportunities", 0),
        "opp_value": overview.get("total_opportunity_value", 0),
        "meetings_booked": overview.get("total_meeting_booked", 0)
    },
    "gt_icp1": {
        "id": GT_ID, "name": "GT | CAMPAIGN 1: Side-Hustle Host",
        "emails_sent": gt.get("emails_sent_count", 0),
        "contacted": gt.get("contacted_count", 0),
        "new_leads": gt.get("new_leads_contacted_count", 0),
        "opened": gt.get("open_count_unique", 0),
        "replied": gt.get("reply_count_unique", 0),
        "bounced": gt.get("bounced_count", 0),
        "interested": gt.get("total_interested", 0),
        "opportunities": gt.get("total_opportunities", 0)
    },
    "icp_analytics": icp_analytics
}

with open(OUT, "w") as f:
    json.dump(result, f, indent=2)
print("[" + NOW + "] Instantly: " + str(len(active)) + " active / " + str(len(items)) + " total, " + str(len(icp_campaigns)) + " ICP campaigns")
