#!/bin/bash
# Config & secrets backup
# Runs: daily at 2:15am
# Retention: 14 days

BACKUP_DIR="/root/str-stack/backups/configs"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
ARCHIVE="${BACKUP_DIR}/config_${TIMESTAMP}.tar.gz"

echo "[$(date)] Starting config backup..."

TMPDIR=$(mktemp -d)

# Crontab
crontab -l > "$TMPDIR/crontab.txt" 2>/dev/null

# Nginx configs
cp -r /etc/nginx/sites-enabled "$TMPDIR/nginx-sites-enabled" 2>/dev/null || true
cp /etc/nginx/nginx.conf "$TMPDIR/nginx.conf" 2>/dev/null || true

# All .env files
mkdir -p "$TMPDIR/env-files"
for ENV in /root/str-stack/.env /root/clawhip/.env /root/.openclaw/.env /opt/ghl-mcp/.env /opt/paperclip/.env /srv/str-stack-public/.env; do
    if [ -f "$ENV" ]; then
        DEST="$TMPDIR/env-files/$(echo "$ENV" | tr '/' '_')"
        cp "$ENV" "$DEST"
    fi
done

# Docker state snapshot
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}" > "$TMPDIR/docker-ps.txt" 2>/dev/null
docker compose -f /root/str-stack/docker-compose.yml config > "$TMPDIR/docker-compose-resolved.yml" 2>/dev/null || true
docker network ls > "$TMPDIR/docker-networks.txt" 2>/dev/null

# Package tar
tar -czf "$ARCHIVE" -C "$TMPDIR" . 2>/dev/null

rm -rf "$TMPDIR"

if [ -s "$ARCHIVE" ]; then
    SIZE=$(du -h "$ARCHIVE" | cut -f1)
    echo "[$(date)] Config backup successful: $ARCHIVE ($SIZE)"
else
    echo "[$(date)] ERROR: Config backup failed!"
    exit 1
fi

# Cleanup: keep 14 days
find "$BACKUP_DIR" -name "config_*.tar.gz" -mtime +14 -delete
echo "[$(date)] Config backup complete."
