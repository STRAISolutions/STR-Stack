# STRBOSS Delegation Prompts
# Copy/paste these into SwarmClaw chat with STRBOSS to delegate tasks.
# Updated: 2026-03-22

---

## 1. SECURITY — Apply Audit Fixes

```
STRBOSS, delegate to STR Ops Agent:

Priority: HIGH
Task: Apply security audit fixes from /root/str-stack/security-audit-report.txt

Actions:
1. Disable SSH password auth: set PasswordAuthentication no in /etc/ssh/sshd_config.d/99-hardening.conf
2. Set PermitRootLogin prohibit-password in the same file
3. Restart sshd
4. Fix file permissions: chmod 600 /opt/swarmclaw/.next/standalone/.env.local /opt/flowise/.env /opt/flowise/docker-compose.yml
5. Install fail2ban: apt install -y fail2ban, enable sshd jail, start service
6. Clean /root/.ssh/authorized_keys — remove lines containing "PASTE_YOUR_PUBLIC_KEY_HERE" and duplicate keys
7. Confirm all changes and report back

Do NOT restart SwarmClaw or Flowise — only sshd and fail2ban.
```

---

## 2. GHL PIPELINE — Stale Lead Audit

```
STRBOSS, delegate to GHL Operations Analyst:

Task: Full pipeline audit for both GHL locations
- Master Location: 1OOZ4AKIgxO8QKKMnIcK
- Call Center Location: 7hTDBClatcBgmUv36bZX

Report back:
1. Total contacts per location
2. Contacts with no activity in 7+ days
3. Opportunities stuck in same stage for 5+ days
4. Any contacts missing email or phone
5. Top 3 pipeline bottlenecks with recommended actions

Format as a brief table I can forward to Concentrix.
```

---

## 3. SALES — Weekly Call Scoring

```
STRBOSS, delegate to Sales Strategy Coach:

Task: Weekly sales performance review

1. Pull any call recordings or notes logged this week
2. Score each on: Discovery (1-10), Objection Handling (1-10), Close Attempt (1-10), Follow-up (1-10)
3. Identify top 3 coaching points for next week
4. Update the running best-practices playbook if any new patterns emerged
5. Flag any calls that need immediate follow-up

Keep it to 1 page max. Concentrix-ready format.
```

---

## 4. COMMS — Concentrix Weekly Summary

```
STRBOSS, delegate to Communications Router:

Task: Draft weekly Concentrix summary

Format:
- 3 bullets max: KPIs, wins, action items
- Professional tone, data-backed
- Flag for human review before sending

Include:
1. Pipeline velocity (new leads in vs closed)
2. Response time metrics (avg first response, SLA compliance)
3. Key wins or blockers this week
4. Any open action items

Draft as email body ready for Gmail send.
```

---

## 5. SYSTEM — Full Health Check

```
STRBOSS, delegate to STR Ops Agent:

Task: Full system health check

Check and report status of:
1. OpenClaw Gateway (curl 127.0.0.1:18789/health)
2. SwarmClaw (curl 127.0.0.1:3456/api/system/status with access key)
3. Vapi relay (curl 127.0.0.1:8443/health)
4. Flowise (curl https://flowise.strsolutionsusa.com)
5. Ollama (curl 127.0.0.1:11434/api/tags)
6. Tailscale funnel status
7. Disk usage, RAM usage, swap
8. Docker containers status
9. Any systemd services in failed state

Report as a table: Service | Status | Notes
```

---

## 6. LEAD GEN — Apollo Enrichment Run

```
STRBOSS, delegate to GHL Operations Analyst:

Task: Enrich new GHL contacts via Apollo

1. Pull contacts from Master location created in last 7 days that are missing company data
2. For each, attempt Apollo enrichment (company name, title, LinkedIn)
3. Update GHL contact records with enriched data
4. Report: X contacts enriched, Y failed, Z already complete

Flag any high-value contacts (VP+ title, 50+ employee company) for priority follow-up.
```

---

## 7. DISCORD — Status Broadcast

```
STRBOSS, delegate to STR Ops Agent:

Task: Post daily status update to Discord #str-command channel

Include:
- System health: all services UP/DOWN
- Pipeline snapshot: X active leads, Y opportunities
- Today's scheduled tasks
- Any alerts or blockers

Keep it under 10 lines. Use markdown formatting.
```

---

## 8. COST — Token Spend Review

```
STRBOSS, this one's for you directly:

Task: Review agent token consumption for the past 24 hours.

Report:
1. Which agents ran and how many cycles
2. Estimated token spend by provider (OpenAI, Groq, Ollama)
3. Any agents with unusually high consumption
4. Recommendations for shifting workload to Ollama where quality permits

Flag any agent spending more than $1/day on OpenAI.
```

---

## 9. MAINTENANCE — Ollama Model Management

```
STRBOSS, delegate to STR Ops Agent:

Task: Ollama model maintenance

1. Check current models: ollama list
2. Check disk space available
3. If space permits (>10GB free), pull llama3.2:1b as a fast lightweight option
4. Run a quick test prompt on each model to verify they're responding
5. Report model inventory with sizes and response times
```

---

## 10. WEEKLY FULL CYCLE — Monday Morning Kickoff

```
STRBOSS, run the Monday morning cycle:

1. Delegate to STR Ops Agent: Full system health check (prompt #5)
2. Delegate to GHL Ops Analyst: Pipeline audit (prompt #2)
3. Delegate to Sales Coach: Weekly call scoring (prompt #3)
4. Delegate to Comms Router: Draft Concentrix summary (prompt #4)
5. Once all reports are in, compile a single executive summary
6. Post the summary to Discord #str-command
7. Flag anything that needs my attention

Run all 4 delegations in parallel. Compile when all complete.
```
