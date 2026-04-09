# STR Solutions — Active Task Registry
Last updated: 2026-04-08

## Active Tasks

### #1 — Daily Lead Extract (STRBOSS)
- **Status:** OOM fix in progress — rebuilding with SQLite backend
- **Cron:** `0 5 * * * /root/str-stack/run_daily_extract.sh` (5AM UTC daily)
- **Target:** 10,000 unique scored leads/day (user wants 5,000 for today)
- **Data:** PPD-USA_property_file_v3.csv.gz (5.8GB, ~230M rows, ~2.8M unique US properties in last 6 months)
- **Scoring model:** ADR floors ($250 high/$180 low season), booking rate, occupancy, revenue underperformance, portfolio size, market conditions
- **Scripts:** `/root/str-stack/daily_lead_extract.py`, `/root/str-stack/run_daily_extract.sh`
- **Output:** `/root/str-stack/daily_leads/`

### #2 — GHL Ask AI vs MCP Connector
- **Status:** COMPLETE
- **Decision:** Use both. Ask AI for simple in-conversation tasks, MCP for complex cross-system orchestration.

### #3 — Concentrix Litigation File
- **Status:** Searching for prior session data
- **Goal:** Compile email audit findings for litigation lawyer

### #4 — Wiring Diagram Alignment
- **Status:** Audited. Missing 9 self-hosted services from diagram.
- **Missing:** AirDNA Service, STR Pipeline Webhook, Hostfully Webhook, Clawhip, n8n, Daily Lead Extract, STT Service, TTS Service, MillionVerifier, Tracerfy
- **Issues:** Clay API down, Slack notifications trouble

### #5 — Task Registry (this file)
- **Status:** COMPLETE

## Pipeline Status

### Enrichment Pipeline (airdna_to_instantly.py)
- **Status:** PAUSED — Tracerfy credits exhausted (402)
- **Last run:** run5 — 5,000 rows processed, 112 leads enriched, 112 pushed to Instantly (0 failures)
- **Needs:** Tracerfy credit top-up, then re-run with ICP-filtered list

### ICP Pre-Filter (airdna_icp_filter.py)
- **Status:** Superseded by daily_lead_extract.py (streaming + dedup)
- **Issue:** Original version treated monthly rows as unique properties (inflated counts)

## Infrastructure

### Services (14 running)
GHL MCP Master (:8010), GHL MCP Call Center (:8011), GHL MCP Docker (:8000),
Clawhip (:8085), Hostfully Webhook (:8089), Flowise (:3000), SwarmClaw (:3456),
n8n, AirDNA Service, STR Pipeline Webhook, STT Service, TTS Service, Vapi Relay, Redis

### Down
- OpenClaw CLI Docker — exited 10 days ago (code 1)
- devin-box Tailscale — offline 15 days

### Cron Jobs: 19 total (see crontab -l for full list)

## API Keys (.env)
Instantly (3 campaigns), AirDNA, OpenAI, GHL (7 keys), Google (7 keys),
Discord, Tracerfy, MillionVerifier, and more.

## Research Completed
1. STR Industry Analysis — 1.5M active US STR listings, 70-75% self-managed
2. Conversion Triggers — #1 burnout (62-68%), #2 guest comms, #3 cleaning logistics
3. Automated Customer Journey — 6 emails + 2 voicemails + 2 SMS, 21-35 day sequence, target 80% zero-human close rate

## Goals
- 3,000 signed homeowner clients
- 2 clients/day, 50 warm replies/day, 6-8 demos/day
- 10,000 leads/day through enrichment pipeline
