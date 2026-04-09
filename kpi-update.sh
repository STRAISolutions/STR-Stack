#!/bin/bash
# Financial KPIs from GHL + Instantly -> JSON for dashboard
# Hot Lead Stages: Qualified-Booked + Routed to Call Center
# LTV per account = $12,500 | Monthly STR Earnings = $750/account
set -a; source <(grep -v "APP_PASSWORD" /root/str-stack/.env); set +a
OUT="/root/str-stack/financial-kpis.json"
TMP_OPPS="/tmp/ghl_opps_all.json"

# -- GHL: Fetch ALL opportunities from BOTH subaccounts --
echo "[]" > "$TMP_OPPS"

fetch_ghl_opps() {
  local LOC_ID="$1"
  local TOKEN="$2"
  local AFTER=""
  local PAGE=0

  while true; do
    URL="https://services.leadconnectorhq.com/opportunities/search?location_id=${LOC_ID}&limit=100"
    [ -n "$AFTER" ] && URL="${URL}&startAfterId=${AFTER}"

    RESP=$(curl -s "$URL" \
      -H "Authorization: Bearer ${TOKEN}" \
      -H "Version: 2021-07-28" 2>/dev/null)

    AFTER=$(echo "$RESP" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
    opps = d.get('opportunities', [])
    with open('$TMP_OPPS') as f:
        existing = json.load(f)
    existing.extend(opps)
    with open('$TMP_OPPS', 'w') as f:
        json.dump(existing, f)
    # If fewer than 100 results, this is the last page
    if len(opps) < 100:
        print('')
    else:
        meta = d.get('meta', {})
        npu = meta.get('nextPageUrl', '')
        if 'startAfterId=' in npu:
            print(npu.split('startAfterId=')[-1].split('&')[0])
        else:
            print('')
except:
    print('')
" 2>/dev/null)

    PAGE=$((PAGE + 1))
    [ -z "$AFTER" ] && break
    [ "$PAGE" -ge 20 ] && break
  done
}

# Fetch from Call Center subaccount only (primary active pipeline)
fetch_ghl_opps "$GHL_CALL_CENTER_LOCATION" "$GHL_CALL_CENTER_TOKEN"

# -- Calculate pipeline metrics --
OPPS=$(python3 << 'PYEOF'
import json
from collections import Counter
from datetime import datetime, timezone, timedelta

LTV = 12500         # Lifetime value per account (updated from 8000)
MONTHLY_EARN = 750  # Monthly STR earnings per account

# The 8 CC stages in order with their IDs
CC_STAGES = [
    {"name": "Call Queue",           "stage_id": "6e6ba196-949c-4403-b156-eb30cfeb858c"},
    {"name": "Attempted",            "stage_id": "b8e9a517-89f5-4b25-a4cb-4ef8b59f178d"},
    {"name": "Overflow - VAPI",      "stage_id": "29554f80-6207-4320-8570-a28aa382aeb4"},
    {"name": "Connected - DQ",       "stage_id": "953891d6-4e51-4f0b-848d-23169e795da1"},
    {"name": "Qualified - Not Booked","stage_id": "0e9f79c3-94b7-4f04-b858-bdee3a5eb450"},
    {"name": "BOOKED",               "stage_id": "da39d074-9fc9-4895-85d2-1b31e03491c2"},
    {"name": "Contract Sent",        "stage_id": "a0e745ad-1a58-4fee-9911-c035d521f32b"},
    {"name": "Closed - Lost",        "stage_id": "454f919b-49b3-4206-a9e1-f68896144e5f"},
]

CC_STAGE_IDS = {s["stage_id"] for s in CC_STAGES}

with open('/tmp/ghl_opps_all.json') as f:
    opps = json.load(f)

total = len(opps)

# HOT LEAD stages -- only these count for pipeline value
hot_stages = {
    "6e6ba196-949c-4403-b156-eb30cfeb858c",  # Call Queue
    "b8e9a517-89f5-4b25-a4cb-4ef8b59f178d",  # Attempted / No Answer
    "29554f80-6207-4320-8570-a28aa382aeb4",  # Overflow - VAPI
    "0e9f79c3-94b7-4f04-b858-bdee3a5eb450",  # Qualified - Not Booked
    "da39d074-9fc9-4895-85d2-1b31e03491c2",  # BOOKED
    "a0e745ad-1a58-4fee-9911-c035d521f32b",  # Contract Sent
}

# Count hot leads (open + in hot stages)
hot_leads = [o for o in opps
             if o.get('status') == 'open'
             and o.get('pipelineStageId') in hot_stages]
hot_count = len(hot_leads)

# Financial calculations
ltv_pipeline = hot_count * LTV
monthly_gross = hot_count * MONTHLY_EARN

# Overall counts
won = sum(1 for o in opps if o.get('status') == 'won')
open_count = sum(1 for o in opps if o.get('status') == 'open')
lost = sum(1 for o in opps if o.get('status') == 'lost')
ghl_value = sum(o.get('monetaryValue', 0) or 0 for o in opps)

# Stage breakdown for hot leads
stage_names = {
    "f85e7cfb-5f7e-4297-abf2-33a275416a8e": "Qualified - Booked",
    "0e8f9ce5-5db9-4529-bb37-685c39ecba7f": "Routed to Call Center",
}
stage_counts = Counter(stage_names.get(o.get('pipelineStageId',''), 'other') for o in hot_leads)
stage_breakdown = dict(stage_counts.most_common())

# Full pipeline stage breakdown (all open opps)
all_stage_names = {s["stage_id"]: s["name"] for s in CC_STAGES}
all_open = [o for o in opps if o.get('status') == 'open']
all_breakdown = Counter(all_stage_names.get(o.get('pipelineStageId',''), o.get('pipelineStageId','')[:20]) for o in all_open)

# -- 1. Per-stage ordered counts (stage_pipeline) --
stage_id_counts = Counter(o.get('pipelineStageId') for o in all_open)
stage_pipeline = []
for s in CC_STAGES:
    stage_pipeline.append({
        "name": s["name"],
        "count": stage_id_counts.get(s["stage_id"], 0),
        "stage_id": s["stage_id"]
    })

# -- 2. Operational metrics --
waiting_stages = {
    "6e6ba196-949c-4403-b156-eb30cfeb858c",  # Call Queue
    "b8e9a517-89f5-4b25-a4cb-4ef8b59f178d",  # Attempted
}
stale_stages = {
    "6e6ba196-949c-4403-b156-eb30cfeb858c",  # Call Queue
    "b8e9a517-89f5-4b25-a4cb-4ef8b59f178d",  # Attempted
    "29554f80-6207-4320-8570-a28aa382aeb4",  # Overflow - VAPI
}

leads_waiting = sum(1 for o in all_open if o.get('pipelineStageId') in waiting_stages)

now = datetime.now(timezone.utc)
one_hour_ago = now - timedelta(hours=1)
leads_stale_1hr = 0
for o in all_open:
    if o.get('pipelineStageId') not in stale_stages:
        continue
    ts_str = o.get('lastStageChangeAt') or o.get('createdAt') or ''
    if not ts_str:
        continue
    try:
        ts_str_clean = ts_str.replace('Z', '+00:00')
        ts = datetime.fromisoformat(ts_str_clean)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        if ts < one_hour_ago:
            leads_stale_1hr += 1
    except:
        pass

# Lead sources
source_counts = Counter()
for o in opps:
    src = o.get('source') or None
    if not src or str(src).strip() == '':
        src = 'Direct/Unknown'
    source_counts[src] += 1
lead_sources = dict(source_counts.most_common())

# Lead types from contact tags
lead_types = {}
for o in opps:
    contact = o.get('contact', {})
    if not contact:
        continue
    tags = contact.get('tags', [])
    if tags and isinstance(tags, list):
        for t in tags:
            lead_types[t] = lead_types.get(t, 0) + 1

operations = {
    "leads_waiting": leads_waiting,
    "leads_stale_1hr": leads_stale_1hr,
    "lead_sources": lead_sources,
    "lead_types": lead_types if lead_types else "no_tag_data_available"
}

# -- 3. Financial projections --
conversion_goal_pct = 12
revenue_per_conversion = 12500
gross_profit_potential = open_count * revenue_per_conversion * (conversion_goal_pct / 100.0)

projections = {
    "gross_profit_potential": gross_profit_potential,
    "demo_to_customer_ratio": 0.33,
    "revenue_per_conversion": revenue_per_conversion,
    "conversion_goal_pct": conversion_goal_pct,
    "commission_pending": 0,
    "commission_schedule": "TBD"
}

print(json.dumps({
    'total': total,
    'hot_leads': hot_count,
    'ltv_pipeline': ltv_pipeline,
    'monthly_gross': monthly_gross,
    'ltv_per_account': LTV,
    'monthly_per_account': MONTHLY_EARN,
    'ghl_monetary_value': ghl_value,
    'won': won,
    'open': open_count,
    'lost': lost,
    'hot_stage_breakdown': stage_breakdown,
    'all_stage_breakdown': dict(all_breakdown.most_common(15)),
    'stage_pipeline': stage_pipeline,
    'operations': operations,
    'projections': projections
}))
PYEOF
)

# -- Instantly campaign stats (v2 API with Bearer auth) --
INSTANTLY_DATA=$(curl -s "https://api.instantly.ai/api/v2/campaigns?limit=100" \
  -H "Authorization: Bearer ${INSTANTLY_API_KEY}" 2>/dev/null)

CAMP_STATS=$(echo "$INSTANTLY_DATA" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    # v2 returns {items: [...], ...}
    camps = data.get('items', data) if isinstance(data, dict) else data
    if not isinstance(camps, list):
        camps = []
    total_leads = sum(c.get('leads_count', c.get('total_leads', 0)) or 0 for c in camps)
    active = sum(1 for c in camps if c.get('status') in (1, 'active', 'Active'))
    print(json.dumps({'total_leads': total_leads, 'active_campaigns': active, 'total_campaigns': len(camps)}))
except Exception as e:
    print(json.dumps({'total_leads': 0, 'active_campaigns': 0, 'total_campaigns': 0, 'error': str(e)}))
" 2>/dev/null)

# -- Build final KPI JSON --
export OPPS_JSON="$OPPS"
export CAMPS_JSON="$CAMP_STATS"

python3 << 'PYEOF'
import json, datetime, os

try:
    opps = json.loads(os.environ.get('OPPS_JSON', '{}'))
except:
    opps = {}
try:
    camps = json.loads(os.environ.get('CAMPS_JSON', '{}'))
except:
    camps = {}

# Load yesterday's snapshot if it exists
import pathlib
snapshot_dir = pathlib.Path('/root/str-stack/kpi-snapshots')
snapshot_dir.mkdir(exist_ok=True)
today_str = datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%d')
yesterday_str = (datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
yesterday_data = {}
try:
    yf = snapshot_dir / f'{yesterday_str}.json'
    if yf.exists():
        with open(yf) as _f:
            yesterday_data = json.load(_f)
except:
    pass

kpi = {
    'timestamp': datetime.datetime.now(datetime.UTC).strftime('%Y-%m-%dT%H:%M:%SZ'),
    'pipeline': {
        'ltv_pipeline': opps.get('ltv_pipeline', 0),
        'monthly_gross': opps.get('monthly_gross', 0),
        'hot_leads': opps.get('hot_leads', 0),
        'ltv_per_account': opps.get('ltv_per_account', 12500),
        'monthly_per_account': opps.get('monthly_per_account', 750),
        'formula_ltv': 'hot_leads x $12,500 LTV',
        'formula_monthly': 'hot_leads x $750/mo',
        'open': opps.get('open', 0),
        'lost': opps.get('lost', 0),
        'won': opps.get('won', 0),
        'total': opps.get('total', 0),
        'ghl_monetary_value': opps.get('ghl_monetary_value', 0),
        'hot_stage_breakdown': opps.get('hot_stage_breakdown', {}),
        'all_stage_breakdown': opps.get('all_stage_breakdown', {}),
        'stage_pipeline': opps.get('stage_pipeline', [])
    },
    'operations': opps.get('operations', {
        'leads_waiting': 0,
        'leads_stale_1hr': 0,
        'lead_sources': {},
        'lead_types': {}
    }),
    'projections': opps.get('projections', {
        'gross_profit_potential': 0,
        'demo_to_customer_ratio': 0.33,
        'revenue_per_conversion': 12500,
        'conversion_goal_pct': 12,
        'commission_pending': 0,
        'commission_schedule': 'TBD'
    }),
    'leads': {
        'total': opps.get('total', 0),
        'active_campaigns': camps.get('active_campaigns', 0),
        'total_campaigns': camps.get('total_campaigns', 0)
    },
    'demos': {
        'booked': 0,
        'target': 30
    },
    'email': {
        'open_rate': 0,
        'reply_rate': 0
    },
    'conversion': {
        'rate': 0
    }
}

# Yesterday's Activity row data
yd = yesterday_data
kpi['yesterday'] = {
    'new_leads': yd.get('leads', {}).get('total', '--'),
    'new_leads_delta': str(yd.get('leads', {}).get('total', 0)) + ' total',
    'appointments': yd.get('demos', {}).get('booked', '--'),
    'demos': yd.get('demos', {}).get('booked', '--'),
    'demos_delta': 'vs ' + str(yd.get('demos', {}).get('target', 30)) + ' target',
    'responses': yd.get('operations', {}).get('leads_waiting', '--'),
    'lead_sources': len(yd.get('operations', {}).get('lead_sources', {})),
    'top_source': ''
}
yd_sources = yd.get('operations', {}).get('lead_sources', {})
if yd_sources and isinstance(yd_sources, dict):
    top = sorted(yd_sources.items(), key=lambda x: x[1], reverse=True)
    if top:
        kpi['yesterday']['top_source'] = top[0][0] + ' (' + str(top[0][1]) + ')'

# Save today's snapshot for tomorrow's comparison
snapshot_file = snapshot_dir / f'{today_str}.json'
with open(snapshot_file, 'w') as _f:
    json.dump(kpi, _f, indent=2)

# Clean up old snapshots (keep 7 days)
for old_snap in sorted(snapshot_dir.glob('*.json'))[:-7]:
    old_snap.unlink(missing_ok=True)

out = '/root/str-stack/financial-kpis.json'
with open(out, 'w') as f:
    json.dump(kpi, f, indent=2)
print(json.dumps(kpi, indent=2))
PYEOF

cp /root/str-stack/financial-kpis.json /srv/str-stack-public/financial-kpis.json 2>/dev/null
rm -f "$TMP_OPPS"
