#!/bin/bash
# Docker volume backups
# Runs: daily at 2:30am
# Retention: 7 days
# Note: This droplet uses bind mounts, not named volumes.
# This script backs up key docker bind-mount data directories.

BACKUP_DIR="/root/str-stack/backups/docker-volumes"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "[$(date)] Starting docker data backup..."

# Back up named volumes (if any exist)
VOLUMES=$(docker volume ls -q 2>/dev/null)
if [ -n "$VOLUMES" ]; then
    for VOL in $VOLUMES; do
        ARCHIVE="${BACKUP_DIR}/vol_${VOL}_${TIMESTAMP}.tar.gz"
        docker run --rm -v "${VOL}:/data" -v "${BACKUP_DIR}:/backup" alpine \
            tar -czf "/backup/vol_${VOL}_${TIMESTAMP}.tar.gz" -C /data . 2>/dev/null
        if [ -s "$ARCHIVE" ]; then
            echo "  Backed up volume: $VOL"
        fi
    done
fi

# Back up key bind-mount directories used by containers
for DATADIR in /root/str-stack/flowise-data /root/str-stack/n8n-data /root/str-stack/redis-data; do
    if [ -d "$DATADIR" ]; then
        DIRNAME=$(basename "$DATADIR")
        tar -czf "${BACKUP_DIR}/${DIRNAME}_${TIMESTAMP}.tar.gz" -C "$(dirname $DATADIR)" "$DIRNAME" 2>/dev/null
        echo "  Backed up: $DIRNAME"
    fi
done

# Cleanup: keep 7 days
find "$BACKUP_DIR" -name "*.tar.gz" -mtime +7 -delete
REMAINING=$(ls -1 "$BACKUP_DIR"/*.tar.gz 2>/dev/null | wc -l)
echo "[$(date)] Docker data backup complete. $REMAINING archives retained."
