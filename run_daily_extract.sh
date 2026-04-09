#!/bin/bash
# Daily Lead Extract — runs at 5AM via cron
# Outputs exactly 10,000 qualified leads per day

cd /root/str-stack
LOG_DIR=/root/str-stack/daily_leads/logs
mkdir -p "$LOG_DIR"

DATESTAMP=$(date +%Y%m%d)
LOGFILE="$LOG_DIR/extract_${DATESTAMP}.log"

echo "=== Daily Extract started at $(date) ===" >> "$LOGFILE"

python3 daily_lead_extract.py \
  /root/str-stack/PPD-USA_property_file_v3.csv.gz \
  -o /root/str-stack/daily_leads \
  -n 10000 \
  --lookback 6 \
  --min-score 30 \
  >> "$LOGFILE" 2>&1

EXIT_CODE=$?
echo "=== Finished at $(date) with exit code $EXIT_CODE ===" >> "$LOGFILE"

# Keep only last 30 days of logs
find "$LOG_DIR" -name "extract_*.log" -mtime +30 -delete 2>/dev/null

# Keep only last 7 days of lead files (archive older ones)
find /root/str-stack/daily_leads -name "leads_*.csv" -mtime +7 -exec gzip {} \; 2>/dev/null
