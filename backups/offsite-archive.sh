#!/bin/bash
# Off-site backup to DigitalOcean Spaces
TIMESTAMP=$(date +%Y%m%d)
ARCHIVE="/tmp/str-stack-backup-${TIMESTAMP}.tar.gz"
BUCKET="s3://str-backup-key/backups"

echo "[$(date)] Starting off-site archive..."

# Create compressed archive of critical directories
tar -czf "$ARCHIVE" \
  --exclude="*.log" \
  --exclude="node_modules" \
  --exclude="__pycache__" \
  --exclude="*.pyc" \
  --exclude="venv" \
  --exclude="Stack" \
  --exclude="filtered_output" \
  --exclude="*.duckdb" \
  /srv/str-stack-public/ \
  /root/clawhip/ \
  /root/.openclaw/ \
  /opt/paperclip/data/ \
  /opt/ghl-mcp/ \
  /etc/nginx/sites-enabled/ \
  2>/dev/null

SIZE=$(du -sh "$ARCHIVE" 2>/dev/null | cut -f1)
echo "[$(date)] Archive created: $ARCHIVE ($SIZE)"

# Upload to DO Spaces
s3cmd put "$ARCHIVE" "$BUCKET/" 2>&1
echo "[$(date)] Uploaded to $BUCKET/"

# Keep only last 3 archives in Spaces
ARCHIVES=$(s3cmd ls "$BUCKET/" | grep "str-stack-backup" | sort | head -n -3 | awk "{print \$4}")
for OLD in $ARCHIVES; do
  s3cmd del "$OLD" 2>&1
  echo "[$(date)] Deleted old archive: $OLD"
done

# Cleanup local
rm -f "$ARCHIVE"
echo "[$(date)] Off-site archive complete."
