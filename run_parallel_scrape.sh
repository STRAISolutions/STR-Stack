#!/bin/bash
# Parallel STR Scraper — launches 3 agents across US markets + Ontario
# Output goes to separate CSVs then merged

cd /root/str-stack/Stack
mkdir -p output/parallel

echo "=== Launching 3 parallel scraping agents ==="
echo "$(date)"

# Agent 1: Texas markets
HOSPITALITY_CSV=output/parallel/texas_contacts.csv \
python3 main.py \
  --locations /dev/stdin \
  --max-contacts 500 \
  --sources municipal,tourism,chamber,operators \
  << 'LOCS' > /root/str-stack/logs/agent_texas.log 2>&1 &
location
Fredericksburg, Texas
Wimberley, Texas
South Padre Island, Texas
New Braunfels, Texas
Galveston, Texas
Port Aransas, Texas
Marble Falls, Texas
Boerne, Texas
Bandera, Texas
Canyon Lake, Texas
LOCS
AGENT1_PID=$!
echo "Agent 1 (Texas) PID: $AGENT1_PID"

sleep 3

# Agent 2: Arizona + Colorado markets
HOSPITALITY_CSV=output/parallel/az_co_contacts.csv \
python3 main.py \
  --locations /dev/stdin \
  --max-contacts 500 \
  --sources municipal,tourism,chamber,operators \
  << 'LOCS' > /root/str-stack/logs/agent_az_co.log 2>&1 &
location
Sedona, Arizona
Scottsdale, Arizona
Flagstaff, Arizona
Prescott, Arizona
Jerome, Arizona
Breckenridge, Colorado
Telluride, Colorado
Steamboat Springs, Colorado
Estes Park, Colorado
Crested Butte, Colorado
LOCS
AGENT2_PID=$!
echo "Agent 2 (AZ/CO) PID: $AGENT2_PID"

sleep 3

# Agent 3: Ontario (extend existing run)
HOSPITALITY_CSV=output/parallel/ontario_contacts.csv \
python3 main.py \
  --locations /dev/stdin \
  --max-contacts 500 \
  --sources municipal,tourism,chamber,operators \
  << 'LOCS' > /root/str-stack/logs/agent_ontario.log 2>&1 &
location
Muskoka, Ontario
Prince Edward County, Ontario
Blue Mountains, Ontario
Kawartha Lakes, Ontario
Haliburton, Ontario
Parry Sound, Ontario
Niagara-on-the-Lake, Ontario
Huntsville, Ontario
Collingwood, Ontario
Wasaga Beach, Ontario
LOCS
AGENT3_PID=$!
echo "Agent 3 (Ontario) PID: $AGENT3_PID"

echo ""
echo "All 3 agents running. Monitor with:"
echo "  tail -f /root/str-stack/logs/agent_texas.log"
echo "  tail -f /root/str-stack/logs/agent_az_co.log"
echo "  tail -f /root/str-stack/logs/agent_ontario.log"
echo ""
echo "Waiting for completion..."
wait $AGENT1_PID $AGENT2_PID $AGENT3_PID

echo ""
echo "=== All agents done. Merging results ==="
python3 - << 'PYEOF'
import csv, os, glob

output_file = "output/parallel/merged_contacts.csv"
seen_emails = set()
all_rows = []
fieldnames = None

for f in glob.glob("output/parallel/*_contacts.csv"):
    if "merged" in f:
        continue
    try:
        with open(f, newline='', encoding='utf-8') as cf:
            reader = csv.DictReader(cf)
            if not fieldnames:
                fieldnames = reader.fieldnames
            for row in reader:
                email = row.get('email', '').strip()
                if email and email not in seen_emails:
                    seen_emails.add(email)
                    all_rows.append(row)
                elif not email:
                    all_rows.append(row)
        print(f"  Loaded: {f}")
    except Exception as e:
        print(f"  Skip {f}: {e}")

if all_rows and fieldnames:
    with open(output_file, 'w', newline='', encoding='utf-8') as out:
        writer = csv.DictWriter(out, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(all_rows)
    print(f"\nMerged {len(all_rows)} contacts → {output_file}")
else:
    print("No data to merge")
PYEOF

echo "$(date) — Done"
