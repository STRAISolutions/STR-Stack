#!/bin/bash
# Monday Morning Push Script
# Run this after getting new Instantly API key
# Usage: INSTANTLY_API_KEY_V2=<new_key> bash monday_push.sh
#     OR: bash monday_push.sh  (uses key from .env)

set -e
cd /root/str-stack/Stack

echo "=============================="
echo " STR Solutions — Monday Push"
echo " $(date)"
echo "=============================="

# Load .env
export $(grep -v '^#' /root/str-stack/.env | xargs)

# Override if key passed as env var
if [ -n "$1" ]; then
  export INSTANTLY_API_KEY_V2="$1"
  echo "Using provided Instantly key"
fi

# Step 1: Merge all scraped CSVs
echo ""
echo "[1/4] Merging all scraped leads..."
python3 - <<'PYEOF'
import csv, os, glob
from datetime import datetime

OUTPUT_DIR = "/root/str-stack/Stack/output"
sources = glob.glob(f"{OUTPUT_DIR}/parallel/*.csv") + \
          glob.glob(f"{OUTPUT_DIR}/geo_str_*.csv") + \
          [f"{OUTPUT_DIR}/hospitality_contacts.csv"]

all_rows = []
seen_emails = set()
fieldnames = None

for path in sources:
    if not os.path.exists(path):
        continue
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if not fieldnames:
            fieldnames = reader.fieldnames
        for row in reader:
            email = row.get("email","").strip().lower()
            if email and email not in seen_emails:
                seen_emails.add(email)
                all_rows.append(row)

out = f"{OUTPUT_DIR}/master_leads_{datetime.now().strftime('%Y%m%d')}.csv"
with open(out, "w", newline="", encoding="utf-8") as f:
    writer = csv.DictWriter(f, fieldnames=fieldnames or list(all_rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(all_rows)

print(f"  Merged {len(all_rows)} unique leads → {out}")
with open("/tmp/master_leads_path.txt","w") as f:
    f.write(out)
PYEOF

MASTER=$(cat /tmp/master_leads_path.txt)
echo "  Master CSV: $MASTER"

# Step 2: Apollo enrichment for leads missing email
echo ""
echo "[2/4] Apollo enrichment (gaps only)..."
python3 pipeline.py --stage enrich --input "$MASTER"
ENRICHED=$(ls -t output/enriched_*.csv 2>/dev/null | head -1)
if [ -z "$ENRICHED" ]; then
  ENRICHED="$MASTER"
  echo "  No enrichment output — using master directly"
else
  echo "  Enriched CSV: $ENRICHED"
fi

# Step 3: AirDNA filter (if export uploaded)
echo ""
echo "[3/4] Checking for AirDNA export..."
AIRDNA=$(ls -t /root/uploads/airdna_*.csv 2>/dev/null | head -1)
if [ -n "$AIRDNA" ]; then
  echo "  Found AirDNA export: $AIRDNA"
  python3 airdna_processor.py --input "$AIRDNA" --route apollo
  AIRDNA_OUT=$(ls -t output/airdna_qualified_*.csv 2>/dev/null | head -1)
  echo "  AirDNA qualified: $AIRDNA_OUT"
else
  echo "  No AirDNA export found — skipping (upload to /root/uploads/ to use)"
fi

# Step 4: Push to Instantly
echo ""
echo "[4/4] Pushing to Instantly campaign..."
python3 pipeline.py --stage push --input "$ENRICHED"

echo ""
echo "=============================="
echo " Done! Check Instantly dashboard"
echo " Campaign: Side-Hustle Host"
echo " https://app.instantly.ai"
echo "=============================="
