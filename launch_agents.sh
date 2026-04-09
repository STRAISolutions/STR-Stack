#!/bin/bash
# Launch 3 parallel scraping agents via screen sessions
# Usage: bash launch_agents.sh

mkdir -p /root/str-stack/logs
mkdir -p /root/str-stack/Stack/output/parallel
cd /root/str-stack/Stack

echo "=== Launching 3 parallel scraping agents ===" | tee /root/str-stack/logs/master.log
date | tee -a /root/str-stack/logs/master.log

# Kill any old screen sessions
screen -S scrape_texas   -X quit 2>/dev/null || true
screen -S scrape_azco    -X quit 2>/dev/null || true
screen -S scrape_ontario -X quit 2>/dev/null || true
sleep 1

# Agent 1: Texas
screen -dmS scrape_texas bash -c "
  cd /root/str-stack/Stack
  HOSPITALITY_CSV=output/parallel/texas_contacts.csv \
  python3 main.py \
    --locations /root/str-stack/texas_locations.csv \
    --sources municipal,tourism,chamber,operator,book_direct \
    --max-contacts 500 \
    > /root/str-stack/logs/agent_texas.log 2>&1
  echo 'Texas DONE' >> /root/str-stack/logs/master.log
"
echo "Agent 1 (Texas) launched in screen:scrape_texas" | tee -a /root/str-stack/logs/master.log

# Agent 2: AZ + CO
screen -dmS scrape_azco bash -c "
  cd /root/str-stack/Stack
  HOSPITALITY_CSV=output/parallel/az_co_contacts.csv \
  python3 main.py \
    --locations /root/str-stack/azco_locations.csv \
    --sources municipal,tourism,chamber,operator,book_direct \
    --max-contacts 500 \
    > /root/str-stack/logs/agent_az_co.log 2>&1
  echo 'AZ/CO DONE' >> /root/str-stack/logs/master.log
"
echo "Agent 2 (AZ/CO) launched in screen:scrape_azco" | tee -a /root/str-stack/logs/master.log

# Agent 3: Ontario
screen -dmS scrape_ontario bash -c "
  cd /root/str-stack/Stack
  HOSPITALITY_CSV=output/parallel/ontario_contacts.csv \
  python3 main.py \
    --locations /root/str-stack/ontario_locations.csv \
    --sources municipal,tourism,chamber,operator,book_direct \
    --max-contacts 500 \
    > /root/str-stack/logs/agent_ontario.log 2>&1
  echo 'Ontario DONE' >> /root/str-stack/logs/master.log
"
echo "Agent 3 (Ontario) launched in screen:scrape_ontario" | tee -a /root/str-stack/logs/master.log

echo ""
echo "Monitor with:"
echo "  tail -f /root/str-stack/logs/agent_texas.log"
echo "  tail -f /root/str-stack/logs/agent_az_co.log"
echo "  tail -f /root/str-stack/logs/agent_ontario.log"
screen -ls | grep scrape || echo "No screen sessions found"
