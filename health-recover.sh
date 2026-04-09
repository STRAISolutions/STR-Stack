#!/bin/bash
###############################################################################
# health-recover.sh — Auto-restart failed services
# Called by health-monitor.sh after alerting on failures
###############################################################################

LOG="/root/str-stack/logs/health-monitor.log"
TS=$(date "+%Y-%m-%d %H:%M:%S")

recover_service() {
    local name="$1"
    local unit="$2"
    echo "[$TS] RECOVERY: Attempting restart of $name ($unit)" >> "$LOG"
    systemctl restart "$unit" 2>> "$LOG"
    sleep 3
    if systemctl is-active --quiet "$unit"; then
        echo "[$TS] RECOVERY: $name restarted successfully" >> "$LOG"
        return 0
    else
        echo "[$TS] RECOVERY: $name restart FAILED" >> "$LOG"
        return 1
    fi
}

# Read failed services from argument list
for svc in "$@"; do
    case "$svc" in
        openclaw)
            recover_service "OpenClaw" "openclaw.service"
            ;;
        swarmclaw)
            recover_service "SwarmClaw" "swarmclaw.service"
            ;;
        nginx)
            recover_service "Nginx" "nginx.service"
            ;;
        redis)
            recover_service "Redis" "redis-server.service"
            ;;
        flowise)
            # Flowise may be docker-based; try systemd first, then docker
            if systemctl list-units --type=service --all 2>/dev/null | grep -q flowise; then
                recover_service "Flowise" "flowise.service"
            else
                echo "[$TS] RECOVERY: Flowise has no systemd unit; trying docker" >> "$LOG"
                docker restart flowise 2>> "$LOG" && \
                    echo "[$TS] RECOVERY: Flowise docker container restarted" >> "$LOG" || \
                    echo "[$TS] RECOVERY: Flowise docker restart FAILED" >> "$LOG"
            fi
            ;;
        *)
            echo "[$TS] RECOVERY: Unknown service $svc — skipping" >> "$LOG"
            ;;
    esac
done
