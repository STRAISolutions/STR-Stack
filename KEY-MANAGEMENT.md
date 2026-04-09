# STR Solutions — API Key Management

## Standing Rule: Single Source of Truth
**All API keys live in ONE file: `/root/str-stack/.env`**

When you update ANY key:
1. Edit `/root/str-stack/.env`
2. Run: `bash /root/str-stack/sync-keys.sh`
3. Done. The script propagates to all other locations automatically.

## What the sync script does
It reads keys from `/root/str-stack/.env` and pushes them to:
- `/root/.openclaw/.env` (OpenClaw gateway)
- `/opt/flowise/.env` (Flowise container)
- `/etc/environment` (system-wide OpenAI key)
- `/root/.config/systemd/user/openclaw-gateway.service` (gateway service)
- Flowise Postgres DB (GHL keys hardcoded in tool functions)

If any key changed, it automatically restarts:
- OpenClaw gateway (`systemctl --user restart openclaw-gateway`)
- Flowise container (`docker restart flowise`)

## Quick reference
```bash
# Edit the master key file
nano /root/str-stack/.env

# Sync to all locations + restart services
bash /root/str-stack/sync-keys.sh

# Check sync log
cat /root/str-stack/logs/key-sync.log

# Verify a specific key is in sync everywhere
grep OPENAI_API_KEY /root/str-stack/.env /root/.openclaw/.env /opt/flowise/.env /etc/environment
```

## File locations
| File | What it contains | Updated by |
|---|---|---|
| `/root/str-stack/.env` | **ALL keys (master)** | You (manual edit) |
| `/root/.openclaw/.env` | OpenClaw keys | sync-keys.sh |
| `/opt/flowise/.env` | Flowise keys | sync-keys.sh |
| `/etc/environment` | System OpenAI key | sync-keys.sh |
| `openclaw-gateway.service` | Gateway env vars | sync-keys.sh |
| Flowise DB tools | GHL keys in JS code | sync-keys.sh |

## For AI agents (Claude, Devin, STU)
When asked to update an API key:
1. Update ONLY `/root/str-stack/.env`
2. Run `bash /root/str-stack/sync-keys.sh`
3. Never edit the other files directly — they are managed by the sync script
