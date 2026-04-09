#!/bin/bash
# Generates /srv/str-stack-public/config-data.json from /root/str-stack/.env
# Cron: */5 * * * * /root/str-stack/gen-config-data.sh

SOURCE="/root/str-stack/.env"
OUT="/srv/str-stack-public/config-data.json"

get_val() {
  grep "^${1}=" "$SOURCE" 2>/dev/null | head -1 | sed "s/^${1}=//" | sed 's/^"//;s/"$//'
}

mask() {
  local v="$1"
  local len=${#v}
  if [ "$len" -le 8 ]; then
    echo "***"
  elif [ "$len" -le 20 ]; then
    echo "${v:0:6}...${v: -4}"
  else
    echo "${v:0:8}...${v: -6}"
  fi
}

cat > "$OUT" << JSONEOF
{
  "generated_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "ghl": {
    "master_oauth": "$(get_val GHL_MASTER_OAUTH)",
    "callcenter_oauth": "$(get_val GHL_CALL_CENTER_OAUTH)",
    "api_key": "$(get_val GHL_API_KEY)",
    "master_location": "$(get_val GHL_MASTER_LOCATION_ID)",
    "callcenter_location": "$(get_val GHL_CALL_CENTER_LOCATION)",
    "marketplace_client_id": "$(get_val GHL_MARKETPLACE_CLIENT_ID)",
    "api_base": "$(get_val GHL_API_BASE)",
    "api_version": "$(get_val GHL_VERSION)"
  },
  "leadgen": {
    "instantly_key": "$(mask "$(get_val INSTANTLY_API_KEY)")",
    "apollo_key": "$(mask "$(get_val APOLLO_API_KEY)")",
    "clay_key": "$(mask "$(get_val CLAY_API_KEY)")",
    "airdna_key": "$(mask "$(get_val AIRDNA_API_KEY)")",
    "apify_key": "$(mask "$(get_val APIFY_API_KEY)")"
  },
  "ai_voice": {
    "openai_key": "$(mask "$(get_val OPENAI_API_KEY)")",
    "anthropic_key": "$(mask "$(get_val ANTHROPIC_API_KEY)")",
    "elevenlabs_key": "$(mask "$(get_val ELEVENLABS_API_KEY)")",
    "vapi_key": "$(mask "$(get_val VAPI_API_KEY)")",
    "discord_token": "$(mask "$(get_val DISCORD_TOKEN)")"
  },
  "infra": {
    "flowise_url": "https://flowise.strsolutionsusa.com",
    "server_ip": "134.209.11.87",
    "make_token": "$(mask "$(get_val MAKE_API_TOKEN)")",
    "slack_token": "$(mask "$(get_val SLACK_TOKEN)")",
    "google_key": "$(mask "$(get_val GOOGLE_API_KEY)")"
  }
}
JSONEOF

echo "[$(date)] config-data.json regenerated"
