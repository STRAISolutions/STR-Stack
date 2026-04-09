#!/usr/bin/env bash
# ============================================================
# STR Solutions — Instantly Campaign Stats Collector
# Fetches campaign list + analytics from Instantly API
# Writes /srv/str-stack-public/instantly-stats.json
# Cron: */5 * * * * (every 5 min)
# ============================================================
set -uo pipefail

OUT=/srv/str-stack-public/instantly-stats.json
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Load API key
API_KEY=$(grep '^INSTANTLY_API_KEY=' /root/str-stack/.env | head -1 | sed 's/^INSTANTLY_API_KEY=//' | sed 's/^"//;s/"$//')
GT_CAMPAIGN_ID='d637ffed-b225-48a9-8369-867bea05ae62'

if [ -z "$API_KEY" ]; then
  echo '{"error":"No API key"}' > "$OUT"
  exit 1
fi

AUTH="Authorization: Bearer $API_KEY"

# Fetch all campaigns
CAMPAIGNS=$(curl -s --max-time 10 'https://api.instantly.ai/api/v2/campaigns?limit=100' -H "$AUTH" 2>/dev/null)
TOTAL=$(echo "$CAMPAIGNS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len(d.get('items',[])))" 2>/dev/null || echo 0)
ACTIVE=$(echo "$CAMPAIGNS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d.get('items',[]) if c.get('status')==1]))" 2>/dev/null || echo 0)
PAUSED=$(echo "$CAMPAIGNS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d.get('items',[]) if c.get('status')==2]))" 2>/dev/null || echo 0)
COMPLETED=$(echo "$CAMPAIGNS" | python3 -c "import json,sys; d=json.load(sys.stdin); print(len([c for c in d.get('items',[]) if c.get('status')==3]))" 2>/dev/null || echo 0)

# Get campaign names for active ones
ACTIVE_NAMES=$(echo "$CAMPAIGNS" | python3 -c "
import json,sys
d=json.load(sys.stdin)
active=[c['name'] for c in d.get('items',[]) if c.get('status')==1]
print(json.dumps(active))
" 2>/dev/null || echo '[]')

# Fetch overall analytics
OVERVIEW=$(curl -s --max-time 10 'https://api.instantly.ai/api/v2/campaigns/analytics/overview' -H "$AUTH" 2>/dev/null)

# Fetch GT ICP 1 campaign analytics specifically
GT_ANALYTICS=$(curl -s --max-time 10 "https://api.instantly.ai/api/v2/campaigns/analytics/overview?campaign_id=$GT_CAMPAIGN_ID" -H "$AUTH" 2>/dev/null)

# Build output JSON
python3 -c "
import json,sys

overview = json.loads('''''')
gt = json.loads('''''')

result = {
  'updated_at': '',
  'campaigns': {
    'total': ,
    'active': ,
    'paused': ,
    'completed': ,
    'active_names': json.loads('''''')
  },
  'overview': {
    'emails_sent': overview.get('emails_sent_count', 0),
    'contacted': overview.get('contacted_count', 0),
    'new_leads_contacted': overview.get('new_leads_contacted_count', 0),
    'opened': overview.get('open_count_unique', 0),
    'replied': overview.get('reply_count_unique', 0),
    'bounced': overview.get('bounced_count', 0),
    'interested': overview.get('total_interested', 0),
    'opportunities': overview.get('total_opportunities', 0),
    'opportunity_value': overview.get('total_opportunity_value', 0),
    'meetings_booked': overview.get('total_meeting_booked', 0),
    'meetings_completed': overview.get('total_meeting_completed', 0)
  },
  'gt_icp1': {
    'campaign_id': '',
    'campaign_name': 'GT | CAMPAIGN 1: Side-Hustle Host',
    'emails_sent': gt.get('emails_sent_count', 0),
    'contacted': gt.get('contacted_count', 0),
    'new_leads': gt.get('new_leads_contacted_count', 0),
    'opened': gt.get('open_count_unique', 0),
    'replied': gt.get('reply_count_unique', 0),
    'bounced': gt.get('bounced_count', 0),
    'interested': gt.get('total_interested', 0),
    'opportunities': gt.get('total_opportunities', 0)
  }
}
print(json.dumps(result, indent=2))
" > "$OUT"

echo "[$NOW] Instantly stats updated: $ACTIVE active / $TOTAL total"
