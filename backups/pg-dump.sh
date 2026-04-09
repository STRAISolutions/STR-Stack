#!/bin/bash
# Flowise PostgreSQL auto-dump
# Runs: 2x daily (2am, 2pm)
# Retention: 14 days

BACKUP_DIR="/root/str-stack/backups/db-dumps"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DUMP_FILE="${BACKUP_DIR}/flowise_${TIMESTAMP}.sql.gz"

echo "[$(date)] Starting PostgreSQL dump..."

docker exec flowise-db pg_dump -U flowise_admin -d flowise | gzip > "$DUMP_FILE"

if [ $? -eq 0 ] && [ -s "$DUMP_FILE" ]; then
    SIZE=$(du -h "$DUMP_FILE" | cut -f1)
    echo "[$(date)] DB dump successful: $DUMP_FILE ($SIZE)"
else
    echo "[$(date)] ERROR: DB dump failed!"
    rm -f "$DUMP_FILE"
    exit 1
fi

# Cleanup: keep last 14 days
find "$BACKUP_DIR" -name "flowise_*.sql.gz" -mtime +14 -delete
REMAINING=$(ls -1 "$BACKUP_DIR"/flowise_*.sql.gz 2>/dev/null | wc -l)
echo "[$(date)] Retention cleanup done. $REMAINING dumps retained."
