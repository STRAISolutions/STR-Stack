#!/bin/bash
# Run all 3 scraping agents in parallel via screen sessions
# Usage: bash run_now.sh

mkdir -p /root/str-stack/logs
mkdir -p /root/str-stack/Stack/output/parallel
cd /root/str-stack/Stack

# Texas
screen -dmS scrape_texas bash -c "
HOSPITALITY_CSV=output/parallel/texas_contacts.csv \
python3 main.py \
  --sources municipal,tourism,chamber,operator,book_direct \
  --max-contacts 300 \
  --locations /root/str-stack/texas_locations.csv \
  > /root/str-stack/logs/agent_texas.log 2>&1
echo 'Texas done' >> /root/str-stack/logs/master.log
"

# AZ + CO
screen -dmS scrape_azco bash -c "
HOSPITALITY_CSV=output/parallel/az_co_contacts.csv \
python3 main.py \
  --sources municipal,tourism,chamber,operator,book_direct \
  --max-contacts 300 \
  --locations /root/str-stack/azco_locations.csv \
  > /root/str-stack/logs/agent_az_co.log 2>&1
echo 'AZ/CO done' >> /root/str-stack/logs/master.log
"

# Ontario
screen -dmS scrape_ontario bash -c "
HOSPITALITY_CSV=output/parallel/ontario_contacts.csv \
python3 main.py \
  --sources municipal,tourism,chamber,operator,book_direct \
  --max-contacts 300 \
  --locations /root/str-stack/ontario_locations.csv \
  > /root/str-stack/logs/agent_ontario.log 2>&1
echo 'Ontario done' >> /root/str-stack/logs/master.log
"

echo "3 screen sessions launched:"
screen -ls | grep scrape
