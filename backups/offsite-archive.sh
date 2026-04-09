#!/bin/bash
# Full stack off-site archive
# Runs: daily at 4am
# Creates a compressed archive of the entire stack
# TODO: Add upload to DO Spaces or S3 when credentials are available

BACKUP_DIR="/root/str-stack/backups"
TIMESTAMP=$(date +%Y%m%d)
ARCHIVE="${BACKUP_DIR}/str-full-archive_${TIMESTAMP}.tar.gz"

echo "[$(date)] Starting full stack archive..."

tar -czf "$ARCHIVE" \
    --exclude="*.duckdb" \
    --exclude="*.duckdb.wal" \
    --exclude="Stack/" \
    --exclude="filtered_output/" \
    --exclude="node_modules/" \
    --exclude="venv/" \
    --exclude=".venv/" \
    --exclude="__pycache__/" \
    --exclude="backups/db-dumps/" \
    --exclude="backups/configs/" \
    --exclude="backups/docker-volumes/" \
    --exclude="backups/str-full-archive_*" \
    --exclude="*.log" \
    /srv/str-stack-public/ \
    /root/str-stack/ \
    /root/clawhip/ \
    /root/.openclaw/ \
    /opt/paperclip/ \
    /opt/ghl-mcp/ \
    /etc/nginx/sites-enabled/ \
    2>/dev/null

if [ -s "$ARCHIVE" ]; then
    SIZE=$(du -h "$ARCHIVE" | cut -f1)
    echo "[$(date)] Archive created: $ARCHIVE ($SIZE)"
else
    echo "[$(date)] ERROR: Archive creation failed!"
    exit 1
fi

# Keep only last 3 archives
ls -1t "${BACKUP_DIR}"/str-full-archive_*.tar.gz 2>/dev/null | tail -n +4 | xargs rm -f 2>/dev/null

# =============================================
# TODO: UPLOAD TO OFF-SITE STORAGE
# =============================================
# Option A: DigitalOcean Spaces (S3-compatible)
#   apt install -y s3cmd
#   s3cmd put "$ARCHIVE" s3://your-bucket/backups/
#
# Option B: AWS S3
#   aws s3 cp "$ARCHIVE" s3://your-bucket/str-backups/
#
# Option C: rsync to another server
#   rsync -avz "$ARCHIVE" user@backup-server:/backups/
# =============================================

echo "[$(date)] Off-site archive complete. (Local only - add upload destination)"
