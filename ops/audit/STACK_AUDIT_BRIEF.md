# STR Solutions AI — Stack Audit Brief

**Prepared:** 2026-03-16
**Server:** 134.209.11.87 (DigitalOcean, sfo2, 2 vCPU / 4 GB)
**OS:** Ubuntu 24.04, Kernel 6.8.0

---

## What This Stack Does

STR Solutions is a short-term rental (STR) lead generation and sales automation platform. The stack scrapes property data from OTA sources (AirDNA, etc.), enriches contacts, pushes them into outbound campaigns (Instantly, Apollo), manages CRM workflows (GoHighLevel), handles inbound/outbound voice calls (Vapi + ElevenLabs), and runs an AI assistant (OpenClaw + Discord) for internal ops.

**In short:** scrape leads → enrich → outbound campaigns → CRM → voice/AI follow-up.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│  DROPLET (134.209.11.87)                                │
│                                                         │
│  ┌──────────────┐  ┌────────────┐  ┌────────────────┐  │
│  │ OpenClaw GW   │  │ Vapi Relay │  │ Voice Stack    │  │
│  │ :18789 local  │  │ :8443 pub  │  │ router/tts/stt │  │
│  └──────┬───────┘  └─────┬──────┘  └────────────────┘  │
│         │                │                              │
│  ┌──────┴───────┐  ┌─────┴──────┐  ┌────────────────┐  │
│  │ Discord Bot  │  │ Vapi (PAM) │  │ n8n (:5678)    │  │
│  │ via Gateway  │  │ voice agent│  │ workflow engine │  │
│  └──────────────┘  └────────────┘  └────────────────┘  │
│                                                         │
│  ┌──────────────┐  ┌────────────────────────────────┐  │
│  │ Flowise      │  │ Lead Pipeline (Python)          │  │
│  │ :3000        │  │ AirDNA scraper → Instantly push │  │
│  └──────────────┘  └────────────────────────────────┘  │
└─────────────────────────────────────────────────────────┘
         │
         ▼  External Services
┌────────────────────────────────────────────────────┐
│ OpenAI (gpt-5.1-codex)  │  GoHighLevel (2 locations) │
│ Vapi (voice AI)         │  Instantly (email outbound) │
│ Apollo (contact enrich) │  Clay (enrichment tables)   │
│ ElevenLabs (TTS)        │  Make.com (scenarios)       │
│ Gmail (OAuth)           │  Discord (bot + voice)      │
│ Tailscale (networking)  │  GitHub (repo access)       │
└────────────────────────────────────────────────────┘
```

---

## Live Services (confirmed 2026-03-16)

| Service | Port | Status | Notes |
|---------|------|--------|-------|
| OpenClaw Gateway | 18789 (loopback) | **LIVE** | `{"ok":true,"status":"live"}` |
| Vapi Relay | 8443 (0.0.0.0) | **LIVE** | Returns 401 without auth (correct) |
| Discord Bot | via Gateway | **LIVE** | Router + TTS service both running |
| n8n | 5678 | **LIVE** | HTTP 200 |
| Flowise | 3000 | **LIVE** | HTTP 200 |
| Tailscale | — | **LIVE** | Node online at 100.101.4.1 |
| SSH | 22 | **LIVE** | Key-only auth |

---

## Integrations & API Keys (all configured in `/root/.openclaw/.env`)

| Integration | Key Present | Last Verified | Action Needed |
|-------------|-------------|---------------|---------------|
| OpenAI | Yes | Live (Gateway running) | None |
| GHL Master | Yes (OAuth + API key) | Token verified Mar 4 | **Test token validity** |
| GHL Call Center | Yes (OAuth + location) | Token verified Mar 4 | **Test token validity** |
| Vapi | Yes (API key + secret) | Relay live | **Confirm Vapi dashboard Server URL matches** |
| Discord | Yes (bot token) | Bot running | None |
| Instantly | Yes (2 keys) | Unverified | **Test API call, confirm webhook URLs** |
| Apollo | Yes (3 keys) | Unverified | **Test API call** |
| Clay | Yes (key + table URL) | Unverified | **Test API call, confirm table webhook** |
| Make.com | Yes (token) | Unverified | **Check scenarios for old IP refs (138.197.217.251)** |
| Gmail | Yes (OAuth creds) | Unverified | **Test refresh token, confirm OAuth not expired** |
| ElevenLabs | Yes | Unverified | **Test API call** |
| Slack | Yes | Unverified | **Test token** |
| GitHub | Yes | Unverified | Low priority |

---

## Known Issues

1. **Tailscale mode mismatch** — CLAUDE.md says `funnel` (public HTTPS) but config shows `serve` (tailnet-only). The Vapi relay works anyway because port 8443 is directly exposed via UFW, but the docs and config are out of sync.

2. **No reserved IP** — The droplet IP changed once already (138→134). Any hardcoded IP references in external webhooks (Make, Instantly, Zapier) will break on the next rebuild.

3. **Webhook URLs unconfirmed** — Make.com scenarios, Instantly webhooks, and Zapier zaps may still reference the old IP or outdated endpoints. These have not been verified since the IP change.

4. **GHL OAuth tokens** — OAuth tokens expire. The Master and Call Center tokens were last confirmed Mar 4 (12 days ago). Need a live API call to confirm they're still valid.

5. **No automated backups** — No cron jobs, no scheduled snapshots. A disk failure loses everything.

---

## What a Developer Should Audit (8-hour scope)

### Hour 1–2: Webhook & Endpoint Inventory
- [ ] Grep the entire server for the old IP `138.197.217.251` — fix any remaining references
- [ ] Document every inbound webhook URL this server exposes (Vapi relay, n8n webhooks, pipeline webhooks, Flowise endpoints)
- [ ] Document every outbound webhook/callback URL configured in external services (GHL, Make, Instantly, Vapi dashboard, Clay)
- [ ] Cross-reference: does every external service point to a valid, reachable endpoint on this server?

### Hour 3–4: API Token Validation
- [ ] Hit each external API with a lightweight test call to confirm tokens are valid:
  - GHL Master: `GET /contacts?limit=1`
  - GHL Call Center: same
  - Instantly: `GET /api/v1/account/status`
  - Apollo: `GET /v1/auth/health`
  - Clay: test table webhook
  - Gmail: request a token refresh
  - ElevenLabs: `GET /v1/voices`
  - Make.com: `GET /api/v2/scenarios/{id}`
  - Slack: `POST /api/auth.test`
- [ ] For any expired tokens, document the re-auth steps

### Hour 5–6: Workflow Trace
- [ ] Trace the lead pipeline end-to-end: scraper → enrichment → Instantly push → GHL CRM
- [ ] Trace a Vapi inbound call: webhook hit → relay → OpenClaw → response
- [ ] Trace the Discord bot: message → OpenClaw Gateway → response
- [ ] Check n8n workflows — list active workflows, confirm trigger URLs
- [ ] Check Flowise chatflows — list active flows, confirm they're reachable

### Hour 7: Fix & Harden
- [ ] Fix any broken webhooks or expired tokens found above
- [ ] Resolve Tailscale serve/funnel config discrepancy
- [ ] Add UFW rule comments for clarity
- [ ] Set up a DigitalOcean reserved IP (or document why not)

### Hour 8: Document & Handoff
- [ ] Update CLAUDE.md with current verified state
- [ ] Create a webhook registry (source → URL → purpose → last verified)
- [ ] Note any remaining items that need ongoing monitoring

---

## Key File Locations

| Path | Purpose |
|------|---------|
| `/root/.openclaw/openclaw.json` | OpenClaw Gateway + Discord bot config |
| `/root/.openclaw/.env` | All API keys and secrets |
| `/root/.openclaw/workspace` | OpenClaw agent workspace |
| `/root/vapi-relay.js` | Vapi webhook relay (port 8443) |
| `/root/voice-stack/` | Discord voice: router, TTS, STT, voice agent |
| `/root/str-stack/Stack/` | Lead scraping pipeline (AirDNA → Instantly) |
| `/root/str-stack/prompts/` | Enrichment pipeline, contact CSVs, Clay prompts |
| `/root/str-stack/prompts/pipeline_webhook.py` | Pipeline webhook handler |

---

## Quick Commands

```bash
# Health checks
curl http://127.0.0.1:18789/health          # OpenClaw Gateway
curl http://127.0.0.1:8443/health            # Vapi Relay
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:5678  # n8n
curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:3000  # Flowise

# Process list
ps aux | grep -E '(openclaw|node|python)' | grep -v grep

# Firewall
ufw status

# Tailscale
tailscale status
tailscale serve status

# Logs
journalctl -u openclaw-gateway --since "1 hour ago"
```
