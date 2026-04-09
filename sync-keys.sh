#!/usr/bin/env bash
# ============================================================
# STR Solutions — API Key Sync Script
# Single source of truth: /root/str-stack/.env
# Run after updating any key in .env to propagate everywhere.
# Usage: bash /root/str-stack/sync-keys.sh
# ============================================================
set -uo pipefail

SOURCE="/root/str-stack/.env"
LOG="/root/str-stack/logs/key-sync.log"
mkdir -p /root/str-stack/logs

echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Key sync started" | tee -a "$LOG"

# ── Parse .env safely (handles spaces in values) ──
get_val() {
  local key="$1"
  grep "^${key}=" "$SOURCE" 2>/dev/null | head -1 | sed "s/^${key}=//" | sed 's/^"//;s/"$//'
}

CHANGED=0

# ── Helper: update a key=value in a target file ──
sync_key() {
  local file="$1" key="$2" value="$3"
  if [ ! -f "$file" ]; then
    echo "  SKIP $key -> $file (file not found)" | tee -a "$LOG"
    return
  fi
  if [ -z "$value" ]; then
    return
  fi
  if grep -q "^${key}=" "$file" 2>/dev/null; then
    local current
    current=$(grep "^${key}=" "$file" | head -1 | sed "s/^${key}=//" | sed 's/^"//;s/"$//')
    if [ "$current" != "$value" ]; then
      sed -i "s|^${key}=.*|${key}=${value}|" "$file"
      echo "  UPDATED $key in $file" | tee -a "$LOG"
      CHANGED=1
    fi
  else
    echo "${key}=${value}" >> "$file"
    echo "  ADDED $key to $file" | tee -a "$LOG"
    CHANGED=1
  fi
}

# Read all needed values from source
OPENAI_API_KEY=$(get_val OPENAI_API_KEY)
INSTANTLY_API_KEY=$(get_val INSTANTLY_API_KEY)
INSTANTLY_API_KEY_V2=$(get_val INSTANTLY_API_KEY_V2)
INSTANTLY_API_KEY_ALT=$(get_val INSTANTLY_API_KEY_ALT)
GHL_API_KEY=$(get_val GHL_API_KEY)
GHL_MASTER_API_KEY=$(get_val GHL_MASTER_API_KEY)
GHL_MASTER_OAUTH=$(get_val GHL_MASTER_OAUTH)
GHL_CALL_CENTER_OAUTH=$(get_val GHL_CALL_CENTER_OAUTH)
GHL_MARKETPLACE_CLIENT_SECRET=$(get_val GHL_MARKETPLACE_CLIENT_SECRET)
VAPI_API_KEY=$(get_val VAPI_API_KEY)
VAPI_SERVER_SECRET=$(get_val VAPI_SERVER_SECRET)
CLAY_API_KEY=$(get_val CLAY_API_KEY)
CLAY_ADMIN_API_KEY=$(get_val CLAY_ADMIN_API_KEY)
MAKE_API_TOKEN=$(get_val MAKE_API_TOKEN)
SLACK_TOKEN=$(get_val SLACK_TOKEN)
DISCORD_TOKEN=$(get_val DISCORD_TOKEN)
ELEVENLABS_API_KEY=$(get_val ELEVENLABS_API_KEY)
APOLLO_API_KEY=$(get_val APOLLO_API_KEY)
APOLLO_API_KEY_ALT=$(get_val APOLLO_API_KEY_ALT)
APOLLO_API_KEY_LEADGEN=$(get_val APOLLO_API_KEY_LEADGEN)
FLOWISE_API_KEY=$(get_val FLOWISE_API_KEY)
APIFY_API_KEY=$(get_val APIFY_API_KEY)
AIRDNA_API_KEY=$(get_val AIRDNA_API_KEY)
GOOGLE_API_KEY=$(get_val GOOGLE_API_KEY)
GOOGLE_CLIENT_SECRET=$(get_val GOOGLE_CLIENT_SECRET)
ANTHROPIC_API_KEY=$(get_val ANTHROPIC_API_KEY)

# ── 1. Sync to /root/.openclaw/.env ──
echo "Syncing to /root/.openclaw/.env ..." | tee -a "$LOG"
OC="/root/.openclaw/.env"
sync_key "$OC" OPENAI_API_KEY "$OPENAI_API_KEY"
sync_key "$OC" INSTANTLY_API_KEY "$INSTANTLY_API_KEY"
sync_key "$OC" INSTANTLY_API_KEY_V2 "$INSTANTLY_API_KEY_V2"
sync_key "$OC" INSTANTLY_API_KEY_ALT "$INSTANTLY_API_KEY_ALT"
sync_key "$OC" GHL_API_KEY "$GHL_API_KEY"
sync_key "$OC" GHL_MASTER_API_KEY "$GHL_MASTER_API_KEY"
sync_key "$OC" GHL_MASTER_OAUTH "$GHL_MASTER_OAUTH"
sync_key "$OC" GHL_CALL_CENTER_OAUTH "$GHL_CALL_CENTER_OAUTH"
sync_key "$OC" GHL_MARKETPLACE_CLIENT_SECRET "$GHL_MARKETPLACE_CLIENT_SECRET"
sync_key "$OC" VAPI_API_KEY "$VAPI_API_KEY"
sync_key "$OC" VAPI_SERVER_SECRET "$VAPI_SERVER_SECRET"
sync_key "$OC" CLAY_API_KEY "$CLAY_API_KEY"
sync_key "$OC" CLAY_ADMIN_API_KEY "$CLAY_ADMIN_API_KEY"
sync_key "$OC" MAKE_API_TOKEN "$MAKE_API_TOKEN"
sync_key "$OC" SLACK_TOKEN "$SLACK_TOKEN"
sync_key "$OC" DISCORD_TOKEN "$DISCORD_TOKEN"
sync_key "$OC" ELEVENLABS_API_KEY "$ELEVENLABS_API_KEY"
sync_key "$OC" APOLLO_API_KEY "$APOLLO_API_KEY"
sync_key "$OC" APOLLO_API_KEY_ALT "$APOLLO_API_KEY_ALT"
sync_key "$OC" APOLLO_API_KEY_LEADGEN "$APOLLO_API_KEY_LEADGEN"
sync_key "$OC" FLOWISE_API_KEY "$FLOWISE_API_KEY"
sync_key "$OC" APIFY_API_KEY "$APIFY_API_KEY"
sync_key "$OC" AIRDNA_API_KEY "$AIRDNA_API_KEY"
sync_key "$OC" GOOGLE_API_KEY "$GOOGLE_API_KEY"
sync_key "$OC" GOOGLE_CLIENT_SECRET "$GOOGLE_CLIENT_SECRET"

# ── 2. Sync to /opt/flowise/.env ──
echo "Syncing to /opt/flowise/.env ..." | tee -a "$LOG"
FW="/opt/flowise/.env"
sync_key "$FW" OPENAI_API_KEY "$OPENAI_API_KEY"
sync_key "$FW" GHL_API_KEY_1 "$GHL_MASTER_OAUTH"
sync_key "$FW" GHL_API_KEY_2 "$GHL_CALL_CENTER_OAUTH"
[ -n "$ANTHROPIC_API_KEY" ] && sync_key "$FW" ANTHROPIC_API_KEY "$ANTHROPIC_API_KEY"

# ── 3. Sync to /etc/environment ──
echo "Syncing to /etc/environment ..." | tee -a "$LOG"
sync_key /etc/environment OPENAI_API_KEY "$OPENAI_API_KEY"

# ── 4. Sync to OpenClaw gateway service file ──
echo "Syncing to openclaw-gateway.service ..." | tee -a "$LOG"
GW="/root/.config/systemd/user/openclaw-gateway.service"
if [ -f "$GW" ]; then
  for key in OPENAI_API_KEY GHL_MASTER_OAUTH; do
    eval val="\$$key"
    if grep -q "Environment=${key}=" "$GW" 2>/dev/null; then
      current=$(grep "Environment=${key}=" "$GW" | head -1 | sed "s/Environment=${key}=//")
      if [ "$current" != "$val" ]; then
        sed -i "s|Environment=${key}=.*|Environment=${key}=${val}|" "$GW"
        echo "  UPDATED $key in gateway service" | tee -a "$LOG"
        CHANGED=1
      fi
    fi
  done
fi

# ── 5. Update Flowise DB tool functions (GHL keys hardcoded in tools) ──
echo "Syncing GHL keys to Flowise DB tools ..." | tee -a "$LOG"
if command -v docker &>/dev/null && docker ps --filter name=flowise-db --format '{{.Names}}' | grep -q flowise-db; then
  CURRENT_GHL=$(docker exec flowise-db psql -U flowise_admin -d flowise -t -A -c "SELECT func FROM tool WHERE name='ghl_contact_lookup' LIMIT 1;" 2>/dev/null | grep -oP 'Bearer \K[^"]+' | head -1 || true)
  if [ -n "$CURRENT_GHL" ] && [ "$CURRENT_GHL" != "$GHL_MASTER_OAUTH" ]; then
    for tool_name in ghl_contact_lookup ghl_pipeline_scanner ghl_recent_conversations; do
      docker exec flowise-db psql -U flowise_admin -d flowise -c "UPDATE tool SET func = REPLACE(func, '$CURRENT_GHL', '$GHL_MASTER_OAUTH') WHERE name='$tool_name';" 2>/dev/null &&         echo "  UPDATED GHL key in Flowise tool: $tool_name" | tee -a "$LOG" || true
    done
    CHANGED=1
  else
    echo "  Flowise DB tools already in sync" | tee -a "$LOG"
  fi
else
  echo "  SKIP Flowise DB (container not running)" | tee -a "$LOG"
fi


# ── 5b. Sync to /opt/ghl-mcp/.env ──
echo "Syncing to /opt/ghl-mcp/.env ..." | tee -a "$LOG"
GHL_MCP="/opt/ghl-mcp/.env"
sync_key "$GHL_MCP" GHL_API_KEY "$GHL_MASTER_OAUTH"
sync_key "$GHL_MCP" GHL_LOCATION_ID "$(get_val GHL_MASTER_LOCATION)"
sync_key "$GHL_MCP" GHL_API_KEY_2 "$GHL_CALL_CENTER_OAUTH"
sync_key "$GHL_MCP" GHL_LOCATION_ID_2 "$(get_val GHL_CALL_CENTER_LOCATION)"

# ── 6. Restart services if changes were made ──
if [ "$CHANGED" -eq 1 ]; then
  echo "Changes detected — restarting services ..." | tee -a "$LOG"
  if [ -f "$GW" ]; then
    systemctl --user daemon-reload 2>/dev/null || true
    systemctl --user restart openclaw-gateway 2>/dev/null &&       echo "  Restarted openclaw-gateway" | tee -a "$LOG" || true
  fi
  docker restart ghl-mcp 2>/dev/null && 
    echo "  Restarted ghl-mcp" | tee -a "$LOG" || true
  docker restart flowise 2>/dev/null &&     echo "  Restarted Flowise" | tee -a "$LOG" || true
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Key sync completed with changes" | tee -a "$LOG"
else
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Key sync completed — no changes needed" | tee -a "$LOG"
fi

echo ""
echo "============================================"
echo " Key sync complete."
echo " Source: /root/str-stack/.env"
echo " Log:    /root/str-stack/logs/key-sync.log"
echo "============================================"
