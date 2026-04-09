# STR Solutions — Session Context
Last updated: April 6, 2026

## Identity
Mike Adams, founder STR Solutions USA. Solopreneur. STR property management + AI automation consulting.
Call center: 10-agent Concentrix Mexico City = GHL Call Center Subaccount.

## Active work
- 16 OpenClaw skills installed to /root/openclaw/skills/
- Dashboard at /srv/str-stack-public/dashboard.html → serve at dashboard.strsolutionsusa.com
- Clay ICP 1 live: 4756 webhook rows → 99 enriched → Instantly pipeline running
- Flowise reconnected and healthy (HTTP 200)
- SwarmClaw active (systemd service running)
- OpenClaw Gateway running (port 18789, HTTP 200)
- Discord bot connected (@Open Claw Bot)
- KPI pipeline: $688K LTV, 86 hot leads, $64.5K/mo gross (Call Center GHL only)
- Instantly v2 API live: 16 campaigns, 1 active
- Newsletter archive live (Vol 01 + Vol 02 sent)
- Training deck deployed: /assets/training/str-training-deck-v1.html
- Brand assets hosted: /assets/brand/ (9 images, nginx public)
- Dashboard patches deployed: global clock, drag-and-drop wiring, collapsible config, chromatic logo

## Blockers (priority order)
1. Clay API key 401 — needs admin scope key — app.clay.com Settings > API
2. Make (Integromat) API returning error — verify token at app.make.com > Profile > API
3. Slack bot token missing from .env — MCP Slack connector works as alternative
4. GHL Agency token dead (HTTP 403) — pit-e19a... — may need refresh if agency-level access required

## Key paths
- Droplet: 134.209.11.87 Ubuntu 24.04
- Tailscale: openclaw-droplet (100.101.4.1)
- Skills: /root/openclaw/skills/
- STU: /opt/stu/
- Flowise: /opt/flowise/ (https://flowise.strsolutionsusa.com)
- SwarmClaw: /home/swarmclaw/ (systemd: swarmclaw.service)
- Stack: /root/str-stack/
- Dashboard: /srv/str-stack-public/dashboard.html
- Assets: /srv/str-stack-public/assets/ (brand, newsletters, training)
- Backups: /root/str-stack/backups/
- Logs: /root/str-stack/logs/
- API Keys: /root/str-stack/.env (primary source for all integration keys)

## GHL structure
Agency Master > Master Subaccount (STR ops, loc: 1OOZ4AKI) > Call Center (Concentrix, loc: 7hTDBCla)
KPIs pull from Call Center only. 8 pipeline stages, 6 hot stages.

## Lead pipeline
Apollo info@ > Clay ICP 1 (4756 rows) > Instantly (16 campaigns) > GHL Call Center > Vapi PAM > Demo 30/day target

## AI providers
Core: OpenAI (primary), Anthropic (Claude Code)
Voice: ElevenLabs, Vapi
Video: HeyGen (standby), Loom (standby), Gamma (presentations)
STU channels: Discord active, Telegram unverified, WhatsApp unverified
On-demand: Manus, Devin, NanoBanana, Perplexity

## Standing rules
- **API Keys**: Single source of truth is `/root/str-stack/.env`. After editing, run `bash /root/str-stack/sync-keys.sh` to propagate everywhere. See `/root/str-stack/KEY-MANAGEMENT.md` for details.
- **Wiring diagram**: Any new tool must be added to `/root/str-stack/wiring-check.sh` (cron runs every minute)
- **KPI data**: Sourced from Call Center GHL only. Script: `/root/str-stack/kpi-update.sh` (every 5 min)
- **Newsletters**: Archive at `/assets/newsletters/registry.json`. Include luxury vacation rental hero image.

## Resume any session
1. SSH root@134.209.11.87 (or via Tailscale: root@100.101.4.1)
2. cat /root/str-stack/CONTEXT.md (or dashboard loads /srv/str-stack-public/CONTEXT.md)
3. Claude Code picks up here instantly
