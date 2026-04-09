#!/bin/bash
###############################################################################
# health-monitor.sh  STRBOSS System Health Monitor with Email Alerts
# Checks critical services every 5 min via cron.
# Sends email ONLY on state changes (up->down or down->up).
# Calls health-recover.sh for auto-restart of failed services.
# Email via Gmail API (SMTP ports blocked on DigitalOcean).
###############################################################################

STATE_FILE="/root/str-stack/.health-monitor-state"
LOG="/root/str-stack/logs/health-monitor.log"
ALERT_EMAIL="mike@strincsolutions.com"
SEND_EMAIL="/root/str-stack/send-alert-email.py"
HOSTNAME=$(hostname)
TS=$(date "+%Y-%m-%d %H:%M:%S")

mkdir -p /root/str-stack/logs
[ -f "$STATE_FILE" ] || touch "$STATE_FILE"

declare -A PREV_STATE
while IFS="=" read -r key val; do
    [[ -z "$key" || "$key" == "#"* ]] && continue
    PREV_STATE["$key"]="$val"
done < "$STATE_FILE"

declare -A CURR_STATE
FAILED_SERVICES=()
RECOVERED_SERVICES=()
DIAGNOSTICS=""

get_http_code() {
    local url="$1"
    local code
    code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 8 "$url" 2>/dev/null)
    if [ -z "$code" ]; then
        code="000"
    fi
    echo "$code"
}

check_http() {
    local name="$1" url="$2" expect="$3"
    local code
    code=$(get_http_code "$url")

    if echo "$expect" | grep -q "$code"; then
        CURR_STATE["$name"]="up"
        echo "[$TS] OK: $name (HTTP $code)"
    else
        CURR_STATE["$name"]="down"
        echo "[$TS] FAIL: $name (HTTP $code, expected $expect)"
        DIAGNOSTICS+="
--- $name ---
HTTP response code: $code (expected: $expect)
"
        local unit=""
        case "$name" in
            openclaw) unit="openclaw.service" ;;
            swarmclaw) unit="swarmclaw.service" ;;
            nginx) unit="nginx.service" ;;
        esac
        if [ -n "$unit" ]; then
            DIAGNOSTICS+="$(systemctl status "$unit" --no-pager -l 2>&1 | head -15)
"
        fi
    fi
}

check_http_any() {
    local name="$1" url="$2"
    local code
    code=$(get_http_code "$url")

    if [ "$code" != "000" ] && [ -n "$code" ]; then
        CURR_STATE["$name"]="up"
        echo "[$TS] OK: $name (HTTP $code)"
    else
        CURR_STATE["$name"]="down"
        echo "[$TS] FAIL: $name (no response)"
        DIAGNOSTICS+="
--- $name ---
No HTTP response (connection refused or timeout)
$(ss -tlnp | grep ':3001' || echo 'Port 3001 not listening')
"
    fi
}

check_redis() {
    local result
    result=$(redis-cli ping 2>/dev/null)
    if [ "$result" = "PONG" ]; then
        CURR_STATE["redis"]="up"
        echo "[$TS] OK: redis (PONG)"
    else
        CURR_STATE["redis"]="down"
        echo "[$TS] FAIL: redis ($result)"
        DIAGNOSTICS+="
--- redis ---
redis-cli ping returned: $result
$(systemctl status redis-server --no-pager -l 2>&1 | head -15)
"
    fi
}

check_file() {
    local name="$1" path="$2"
    if [ -f "$path" ]; then
        CURR_STATE["$name"]="up"
        local fsize
        fsize=$(stat -c%s "$path" 2>/dev/null || echo "unknown")
        echo "[$TS] OK: $name (file exists, ${fsize} bytes)"
    else
        CURR_STATE["$name"]="down"
        echo "[$TS] FAIL: $name (file missing: $path)"
        DIAGNOSTICS+="
--- $name ---
File not found: $path
"
    fi
}

###############################################################################
# Run all checks
###############################################################################

check_http     "openclaw"  "http://127.0.0.1:18789"  "200"
check_http     "swarmclaw" "http://127.0.0.1:3456"   "200"
check_http     "nginx"     "http://127.0.0.1:80"     "200\|301\|302"
check_http_any "flowise"   "http://127.0.0.1:3001"
check_redis
check_file     "duckdb"    "/root/str-stack/airdna.duckdb"

###############################################################################
# Compare states - alert only on state changes
###############################################################################

for svc in "${!CURR_STATE[@]}"; do
    prev="${PREV_STATE[$svc]:-unknown}"
    curr="${CURR_STATE[$svc]}"

    if [ "$curr" = "down" ] && [ "$prev" != "down" ]; then
        FAILED_SERVICES+=("$svc")
        echo "[$TS] STATE CHANGE: $svc went DOWN (was: $prev)"
    elif [ "$curr" = "up" ] && [ "$prev" = "down" ]; then
        RECOVERED_SERVICES+=("$svc")
        echo "[$TS] STATE CHANGE: $svc RECOVERED (was: down)"
    fi
done

###############################################################################
# Save current state
###############################################################################

: > "$STATE_FILE"
for svc in "${!CURR_STATE[@]}"; do
    echo "${svc}=${CURR_STATE[$svc]}" >> "$STATE_FILE"
done

###############################################################################
# Send failure alert email (via Gmail API)
###############################################################################

if [ ${#FAILED_SERVICES[@]} -gt 0 ]; then
    SUBJECT="[ALERT] Service DOWN on $HOSTNAME: ${FAILED_SERVICES[*]}"
    BODY="STRBOSS Health Monitor -- Service Failure Alert
================================================================
Timestamp: $TS
Server:    $HOSTNAME

FAILED SERVICES: ${FAILED_SERVICES[*]}

Diagnostics:
$DIAGNOSTICS

---
Auto-recovery will be attempted.
Monitor log: /root/str-stack/logs/health-monitor.log
State file:  $STATE_FILE"

    echo "[$TS] ALERT: Sending failure email for: ${FAILED_SERVICES[*]}"

    python3 "$SEND_EMAIL" "$SUBJECT" "$BODY" "$ALERT_EMAIL" 2>> "$LOG"
    if [ $? -eq 0 ]; then
        echo "[$TS] ALERT: Email sent successfully"
    else
        echo "[$TS] ALERT: Email send FAILED"
    fi

    # Attempt auto-recovery
    /root/str-stack/health-recover.sh "${FAILED_SERVICES[@]}"
fi

###############################################################################
# Send recovery alert email
###############################################################################

if [ ${#RECOVERED_SERVICES[@]} -gt 0 ]; then
    SUBJECT="[RECOVERED] Service UP on $HOSTNAME: ${RECOVERED_SERVICES[*]}"
    BODY="STRBOSS Health Monitor -- Service Recovery Notice
================================================================
Timestamp: $TS
Server:    $HOSTNAME

RECOVERED SERVICES: ${RECOVERED_SERVICES[*]}

All monitored services are now responding normally.

---
Monitor log: /root/str-stack/logs/health-monitor.log"

    echo "[$TS] RECOVERY ALERT: Sending recovery email for: ${RECOVERED_SERVICES[*]}"

    python3 "$SEND_EMAIL" "$SUBJECT" "$BODY" "$ALERT_EMAIL" 2>> "$LOG"
    if [ $? -eq 0 ]; then
        echo "[$TS] RECOVERY ALERT: Email sent successfully"
    else
        echo "[$TS] RECOVERY ALERT: Email send FAILED"
    fi
fi

###############################################################################
# Summary
###############################################################################

UP_COUNT=0
DOWN_COUNT=0
for svc in "${!CURR_STATE[@]}"; do
    if [ "${CURR_STATE[$svc]}" = "up" ]; then
        UP_COUNT=$((UP_COUNT + 1))
    else
        DOWN_COUNT=$((DOWN_COUNT + 1))
    fi
done

echo "[$TS] SUMMARY: $UP_COUNT up, $DOWN_COUNT down | Failed: ${FAILED_SERVICES[*]:-none} | Recovered: ${RECOVERED_SERVICES[*]:-none}"
