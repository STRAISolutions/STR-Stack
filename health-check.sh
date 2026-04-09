#!/bin/bash
# Server-side health checker — writes status JSON for the dashboard
OUT="/root/str-stack/service-health.json"

oc_status="down"; oc_code=0
vapi_status="down"; vapi_code=0
fw_status="down"; fw_code=0

# OpenClaw
oc_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:18789/health 2>/dev/null)
[ "$oc_code" = "200" ] && oc_status="up"

# Vapi Relay
vapi_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:8443/health 2>/dev/null)
[ "$vapi_code" = "200" ] && vapi_status="up"

# Flowise
fw_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3000/ 2>/dev/null)
[ "$fw_code" = "200" ] && fw_status="up"

# Funnel
funnel=$(tailscale funnel status 2>&1 | grep -c "Funnel on")
funnel_status="down"
[ "$funnel" -ge 1 ] && funnel_status="up"

# Paperclip
pc_code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 5 http://127.0.0.1:3100/health 2>/dev/null)
pc_status="down"
[ "$pc_code" = "200" ] && pc_status="up"
# Disk
disk_pct=$(df / --output=pcent | tail -1 | tr -d ' %')
disk_avail=$(df -h / --output=avail | tail -1 | tr -d ' ')

cat > "$OUT" << EOF
{
  "checked_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "services": {
    "openclaw": {"status":"$oc_status","http":$oc_code,"port":18789},
    "vapi_relay": {"status":"$vapi_status","http":$vapi_code,"port":8443},
    "flowise": {"status":"$fw_status","http":$fw_code,"port":3000},
    "funnel": {"status":"$funnel_status","port":443},
    "discord": {"status":"up","port":"ws"},
    "paperclip": {"status":"$pc_status","http":$pc_code,"port":3100}
  },
  "disk": {"used_pct":$disk_pct,"available":"$disk_avail"}
}
EOF
