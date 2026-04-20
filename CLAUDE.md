# STR Solutions — Dashboard & Stack Context
# READ THIS FIRST on every session in /root/str-stack

## What this repo is
`/root/str-stack` is the live operations directory for STR Solutions USA.
It is a LOCAL git repo (no GitHub remote). It auto-commits every 6 hours.
Changes to files here are LIVE immediately — no deploy step needed.

## The Dashboard (PRIMARY)
- **File:** `/root/str-stack/dashboard.html`
- **Served at:** https://dashboard.strsolutionsusa.com
- **Nginx root:** `/srv/str-stack-public/` (hardlinked — same file, edit either path)
- **Auth:** HTTP Basic auth (credentials in nginx config)
- **To update:** Edit dashboard.html directly. Changes are live instantly.
- **Always backup first:** `cp dashboard.html dashboard.html.bak.$(date +%s)`

## The GHL Workflows Dashboard (SECONDARY)
- **File:** `/root/str-stack/ghl-workflow-dashboard.html`
- **Loaded as:** iframe inside the main dashboard GHL Workflows tab
- **Note:** Has DIFFERENT CSS variable names than dashboard.html — keep in sync when styling

## Navigation sections in dashboard.html
- KPI & Revenue (tab-financials) — deposit tiles, revenue metrics, Tools card
- Operations nav dropdown — includes Calculator link (/calculator)
- GHL Workflows tab — loads ghl-workflow-dashboard.html as iframe

## How to update the dashboard (natural language)
1. Tell Claude what to change ("add X tile", "update Y section", "change the nav")
2. Claude edits /root/str-stack/dashboard.html directly
3. Refresh dashboard.strsolutionsusa.com — change is live immediately
4. No git push, no deploy command needed

## Key paths
- Dashboard: /root/str-stack/dashboard.html (= /srv/str-stack-public/dashboard.html)
- GHL Workflows iframe: /root/str-stack/ghl-workflow-dashboard.html
- Calculator: /var/www/dashboard/calculator/index.html
- Credentials: /root/str-stack/.env (master key file)
- Wiring diagram: /root/str-stack/wiring.html
- Tasks: /root/str-stack/TASKS.md
- Context: /root/str-stack/CONTEXT.md (legacy — this file supersedes it)

## Deploying Bigstacks/Big-Stacks-1 changes to droplet
Run: `deploy-bigstacks` (script at /usr/local/bin/deploy-bigstacks)
This pulls /opt/bigstacks main from GitHub and restarts affected services.

For Big-Stacks-1: `cd /opt/big-stacks-1 && git pull origin main`

## Services quick reference
- nginx: serves dashboard + other sites
- str-dashboard.service: Flask on :5005 (PayPal + BMO deposits + Vapi PAM)
- openclaw.service: OpenClaw gateway :18789
- swarmclaw.service: SwarmClaw :3456
- ghl-mcp.service: GHL MCP :8010/:8011
- flowise: Docker on :3000 → flowise.strsolutionsusa.com
- str-repo-sync.timer: syncs Big-Stacks-1 repo every 6 hours

## Repos on this droplet
- /root/str-stack → LOCAL ONLY (this repo, dashboard lives here)
- /opt/big-stacks-1 → github.com/STRAISolutions/Big-Stacks-1 (services/automation)
- /opt/bigstacks → github.com/STRAISolutions/Bigstacks (infra scripts, CLAUDE.md)

## Current dashboard state (as of April 20, 2026)
- Tools & Stack card: links to /tools, shows 68 tools
- Calculator: accessible at /calculator (auth_basic off)
- BMO deposits tile: pulls from str-dashboard.service /deposits/summary
- KPI & Revenue section: in tab-financials, accessible via dropdown nav
