# STR Solutions AI — Ops Center

Single source of truth for stack operations, audits, and developer onboarding.

## Structure

```
ops/
├── README.md              ← you are here
├── audit/                 ← stack audits, webhook registry, token validation reports
├── runbooks/              ← how to restart services, rotate tokens, deploy changes
├── logs/                  ← log aggregation notes, retention policy
└── config-reference/      ← sanitized service configs (no secrets)
```

## Quick Start (for new developers)

1. Read `audit/STACK_AUDIT_BRIEF.md` for the full architecture overview
2. Check `/root/CLAUDE.md` for server details, IPs, and integration status
3. All secrets live in `/root/.openclaw/.env` and `/root/str-stack/.env` — never commit these
4. Services are managed via systemd (`systemctl status <name>`) except Flowise (Docker)

## Key Services

| Service | Manage With | Config |
|---------|------------|--------|
| OpenClaw Gateway | `systemctl restart openclaw-gateway` | `/root/.openclaw/openclaw.json` |
| Vapi Relay | `systemctl restart vapi-relay` | `/root/vapi-relay.js` |
| Voice (router/TTS/STT) | `systemctl restart router tts-service stt-service` | `/root/voice-stack/` |
| n8n | `systemctl restart n8n` | `/root/.n8n/` |
| Flowise | `cd /opt/flowise && docker compose restart` | `/opt/flowise/docker-compose.yml` |
| Lead Pipeline | `bash /root/str-stack/run_parallel_scrape.sh` | `/root/str-stack/Stack/` |

## Last Updated
2026-03-16
