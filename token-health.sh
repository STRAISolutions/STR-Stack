#!/usr/bin/env bash
# ============================================================
# STR Solutions — API Token Health Monitor
# Checks ALL GHL tokens across all config locations.
# Writes /srv/str-stack-public/token-health.json
# Cron: */30 * * * * (every 30 min) + 12h deep check w/ alerts
# ============================================================
set -uo pipefail

OUT="/srv/str-stack-public/token-health.json"
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ)
ALERT_MODE="${1:-check}"  # "check" (silent) or "alert" (send Discord notification)

GHL_BASE="https://services.leadconnectorhq.com"
GHL_VERSION="2021-07-28"
MASTER_LOC="1OOZ4AKIgxO8QKKMnIcK"
CC_LOC="7hTDBClatcBgmUv36bZX"

# Discord webhook for alerts (from main .env)
DISCORD_ALERT_WH=""
[ -f /root/str-stack/.env ] && DISCORD_ALERT_WH=$(grep "^DISCORD_WEBHOOK_URL=" /root/str-stack/.env 2>/dev/null | head -1 | sed 's/^DISCORD_WEBHOOK_URL=//' | sed 's/^"//;s/"$//')

# ── Token registry: name, token, location_id, source_file ──
declare -a TOKEN_NAMES=()
declare -a TOKEN_VALUES=()
declare -a TOKEN_LOCS=()
declare -a TOKEN_SOURCES=()
declare -a TOKEN_ROLES=()

add_token() {
  TOKEN_NAMES+=("$1")
  TOKEN_VALUES+=("$2")
  TOKEN_LOCS+=("$3")
  TOKEN_SOURCES+=("$4")
  TOKEN_ROLES+=("$5")
}

# Load from /root/str-stack/.env
get_env_val() {
  grep "^${1}=" /root/str-stack/.env 2>/dev/null | head -1 | sed "s/^${1}=//" | sed 's/^"//;s/"$//'
}

ENV_MASTER=$(get_env_val GHL_MASTER_OAUTH)
ENV_CC=$(get_env_val GHL_CALL_CENTER_OAUTH)
ENV_API=$(get_env_val GHL_API_KEY)

[ -n "$ENV_MASTER" ] && add_token "GHL Master (main .env)" "$ENV_MASTER" "$MASTER_LOC" "/root/str-stack/.env" "KPIs, Dashboards, OpenClaw"
[ -n "$ENV_CC" ] && add_token "GHL Call Center (main .env)" "$ENV_CC" "$CC_LOC" "/root/str-stack/.env" "CC Flows, Clawhip"
[ -n "$ENV_API" ] && add_token "GHL API Key (main .env)" "$ENV_API" "$CC_LOC" "/root/str-stack/.env" "Flowise Tools, MCP"

# Load from /root/.swarmclaw/.env
get_swarm_val() {
  grep "^${1}=" /root/.swarmclaw/.env 2>/dev/null | head -1 | sed "s/^${1}=//" | sed 's/^"//;s/"$//'
}

SWARM_MASTER=$(get_swarm_val GHL_MASTER_TOKEN)
SWARM_CC=$(get_swarm_val GHL_CALL_CENTER_TOKEN)

[ -n "$SWARM_MASTER" ] && add_token "GHL Master (SwarmClaw)" "$SWARM_MASTER" "$MASTER_LOC" "/root/.swarmclaw/.env" "SwarmClaw BDR/OPS agents"
[ -n "$SWARM_CC" ] && add_token "GHL Call Center (SwarmClaw)" "$SWARM_CC" "$CC_LOC" "/root/.swarmclaw/.env" "SwarmClaw CC agent"

# Load from ghl_audit_builder.py (if exists)
if [ -f /root/ghl_audit_builder.py ] || [ -f /tmp/ghl_audit_builder.py ]; then
  AUDIT_FILE=$([ -f /root/ghl_audit_builder.py ] && echo "/root/ghl_audit_builder.py" || echo "/tmp/ghl_audit_builder.py")
  AUDIT_M=$(python3 -c "
import re
with open('$AUDIT_FILE') as f: text = f.read()
m = re.search(r\"token_m\s*=\s*'([^']+)'\", text)
print(m.group(1) if m else '')
" 2>/dev/null)
  AUDIT_CC=$(python3 -c "
import re
with open('$AUDIT_FILE') as f: text = f.read()
m = re.search(r\"token_cc\s*=\s*'([^']+)'\", text)
print(m.group(1) if m else '')
" 2>/dev/null)
  [ -n "$AUDIT_M" ] && add_token "GHL Master (audit script)" "$AUDIT_M" "$MASTER_LOC" "$AUDIT_FILE" "Audit/cleanup scripts"
  [ -n "$AUDIT_CC" ] && add_token "GHL CC (audit script)" "$AUDIT_CC" "$CC_LOC" "$AUDIT_FILE" "Audit/cleanup scripts"
fi

# ── Check each token ──
RESULTS="["
ALIVE=0
DEAD=0
TOTAL=${#TOKEN_NAMES[@]}
DEAD_LIST=""

for i in "${!TOKEN_NAMES[@]}"; do
  name="${TOKEN_NAMES[$i]}"
  token="${TOKEN_VALUES[$i]}"
  loc="${TOKEN_LOCS[$i]}"
  source="${TOKEN_SOURCES[$i]}"
  role="${TOKEN_ROLES[$i]}"
  
  # Mask token for display
  masked="${token:0:8}...${token: -4}"
  
  # Test token against GHL contacts endpoint
  code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 \
    "${GHL_BASE}/contacts/?locationId=${loc}&limit=1" \
    -H "Authorization: Bearer ${token}" \
    -H "Version: ${GHL_VERSION}" 2>/dev/null || echo "000")
  
  status="dead"
  detail="HTTP $code"
  if [ "$code" = "200" ]; then
    status="live"
    ALIVE=$((ALIVE + 1))
  else
    DEAD=$((DEAD + 1))
    DEAD_LIST="${DEAD_LIST}\n- ${name} (${masked}) → HTTP ${code}"
    if [ "$code" = "401" ]; then
      detail="Invalid/expired token"
    elif [ "$code" = "000" ]; then
      detail="Connection timeout"
    elif [ "$code" = "422" ]; then
      detail="Invalid location ID"
    fi
  fi
  
  # Deduplicate check — is this the same token value as another entry?
  is_dup="false"
  for j in "${!TOKEN_VALUES[@]}"; do
    if [ "$j" -lt "$i" ] && [ "${TOKEN_VALUES[$j]}" = "$token" ]; then
      is_dup="true"
      break
    fi
  done
  
  [ "$i" -gt 0 ] && RESULTS="${RESULTS},"
  RESULTS="${RESULTS}
    {\"name\":\"${name}\",\"masked\":\"${masked}\",\"status\":\"${status}\",\"http\":${code},\"detail\":\"${detail}\",\"source\":\"${source}\",\"role\":\"${role}\",\"duplicate\":${is_dup}}"
done

RESULTS="${RESULTS}
  ]"

# ── Detect mismatches between config files ──
MISMATCHES="[]"
if [ -n "$ENV_MASTER" ] && [ -n "$SWARM_MASTER" ] && [ "$ENV_MASTER" != "$SWARM_MASTER" ]; then
  MISMATCHES="[{\"issue\":\"Master token mismatch\",\"detail\":\"main .env and SwarmClaw .env have different Master tokens\",\"env_masked\":\"${ENV_MASTER:0:8}...${ENV_MASTER: -4}\",\"swarm_masked\":\"${SWARM_MASTER:0:8}...${SWARM_MASTER: -4}\"}]"
fi
if [ -n "$ENV_CC" ] && [ -n "$SWARM_CC" ] && [ "$ENV_CC" != "$SWARM_CC" ]; then
  if [ "$MISMATCHES" = "[]" ]; then
    MISMATCHES="[{\"issue\":\"CC token mismatch\",\"detail\":\"main .env and SwarmClaw .env have different Call Center tokens\",\"env_masked\":\"${ENV_CC:0:8}...${ENV_CC: -4}\",\"swarm_masked\":\"${SWARM_CC:0:8}...${SWARM_CC: -4}\"}]"
  else
    MISMATCHES="${MISMATCHES%]},{\"issue\":\"CC token mismatch\",\"detail\":\"main .env and SwarmClaw .env have different Call Center tokens\",\"env_masked\":\"${ENV_CC:0:8}...${ENV_CC: -4}\",\"swarm_masked\":\"${SWARM_CC:0:8}...${SWARM_CC: -4}\"}]"
  fi
fi

# ── Load previous check for comparison ──
PREV_DEAD=0
[ -f "$OUT" ] && PREV_DEAD=$(python3 -c "import json; d=json.load(open('$OUT')); print(d.get('summary',{}).get('dead',0))" 2>/dev/null || echo "0")

# ── Write JSON ──
cat > "$OUT" << ENDJSON
{
  "checked_at": "$NOW",
  "next_deep_check": "$(date -u -d '+12 hours' +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "N/A")",
  "tokens": $RESULTS,
  "mismatches": $MISMATCHES,
  "summary": {
    "total": $TOTAL,
    "live": $ALIVE,
    "dead": $DEAD,
    "health_pct": $(( TOTAL > 0 ? (ALIVE * 100 / TOTAL) : 0 )),
    "status": "$([ "$DEAD" -eq 0 ] && echo "all_healthy" || ([ "$ALIVE" -eq 0 ] && echo "all_dead" || echo "degraded"))"
  }
}
ENDJSON

# ── Discord alert on 12h check or new failures ──
if [ "$ALERT_MODE" = "alert" ] && [ -n "$DISCORD_ALERT_WH" ] && [ "$DEAD" -gt 0 ]; then
  EMBED_COLOR=16744576  # Orange
  [ "$ALIVE" -eq 0 ] && EMBED_COLOR=11534368  # Red
  
  curl -s -o /dev/null -X POST "$DISCORD_ALERT_WH" \
    -H "Content-Type: application/json" \
    -d "{
      \"embeds\": [{
        \"title\": \"⚠️ GHL Token Health Alert\",
        \"description\": \"**${DEAD}/${TOTAL}** tokens are dead/expired.\n\n**Dead tokens:**$(echo -e "$DEAD_LIST" | sed 's/"/\\"/g')\n\n**Healthy:** ${ALIVE}/${TOTAL}\n\nRegenerate at: GHL → Settings → Integrations → Private Integration\",
        \"color\": $EMBED_COLOR,
        \"footer\": {\"text\": \"Token Health Monitor · $(date -u +'%b %d %H:%M UTC')\"}
      }]
    }" 2>/dev/null
fi

echo "[${NOW}] Token health: ${ALIVE}/${TOTAL} live, ${DEAD} dead"
