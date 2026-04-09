#!/usr/bin/env bash
###############################################################################
# STR Solutions — DigitalOcean Droplet Security Audit
# Run as root:  bash /root/str-stack/security-audit.sh
# Output: /root/str-stack/security-audit-report.txt
###############################################################################
set +e  # Don't exit on non-zero — audit checks may return non-zero

REPORT="/root/str-stack/security-audit-report.txt"
PASS=0; WARN=0; FAIL=0; INFO=0

sep()  { printf '\n%s\n' "$(printf '=%.0s' {1..72})"; }
hdr()  { sep; printf '  %s\n' "$1"; sep; }
ok()   { ((PASS++)); printf '[PASS] %s\n' "$*"; }
warn() { ((WARN++)); printf '[WARN] %s\n' "$*"; }
fail() { ((FAIL++)); printf '[FAIL] %s\n' "$*"; }
info() { ((INFO++)); printf '[INFO] %s\n' "$*"; }

exec > >(tee "$REPORT") 2>&1

printf 'STR Solutions Security Audit — %s\n' "$(date -u '+%Y-%m-%d %H:%M UTC')"
printf 'Hostname: %s | IP: %s\n' "$(hostname)" "$(hostname -I | awk '{print $1}')"

###############################################################################
hdr "1. OS & KERNEL"
###############################################################################
info "$(lsb_release -ds 2>/dev/null || cat /etc/os-release | grep PRETTY_NAME | cut -d= -f2)"
info "Kernel: $(uname -r)"

# Pending security updates
if command -v apt &>/dev/null; then
  UPDATES=$(apt list --upgradable 2>/dev/null | grep -i securi | wc -l)
  if [[ $UPDATES -gt 0 ]]; then
    warn "$UPDATES pending security update(s) — run: apt update && apt upgrade"
  else
    ok "No pending security updates"
  fi
fi

# Automatic updates
if dpkg -l unattended-upgrades 2>/dev/null | grep -q '^ii'; then
  ok "unattended-upgrades is installed"
else
  warn "unattended-upgrades not installed — consider: apt install unattended-upgrades"
fi

###############################################################################
hdr "2. FIREWALL (UFW)"
###############################################################################
if command -v ufw &>/dev/null; then
  UFW_STATUS=$(ufw status verbose 2>/dev/null)
  if echo "$UFW_STATUS" | grep -q "Status: active"; then
    ok "UFW is active"
    echo "$UFW_STATUS" | grep -E '^[0-9]|ALLOW|DENY|REJECT' | while read -r line; do
      info "  $line"
    done
  else
    fail "UFW is installed but NOT active"
  fi
else
  fail "UFW is not installed"
fi

###############################################################################
hdr "3. SSH HARDENING"
###############################################################################
SSHD_CFG="/etc/ssh/sshd_config"
SSHD_DIR="/etc/ssh/sshd_config.d"

ssh_param() {
  local param=$1
  # Check drop-in dir first, then main config
  val=""
  if [[ -d "$SSHD_DIR" ]]; then
    val=$(grep -rhi "^$param" "$SSHD_DIR"/ 2>/dev/null | tail -1 | awk '{print $2}')
  fi
  if [[ -z "$val" ]]; then
    val=$(grep -hi "^$param" "$SSHD_CFG" 2>/dev/null | tail -1 | awk '{print $2}')
  fi
  echo "${val:-}"
}

# Password auth
PA=$(ssh_param PasswordAuthentication)
if [[ "${PA,,}" == "no" ]]; then
  ok "SSH PasswordAuthentication disabled"
else
  fail "SSH PasswordAuthentication is '${PA:-yes(default)}' — should be 'no'"
fi

# Root login
RL=$(ssh_param PermitRootLogin)
if [[ "${RL,,}" == "no" || "${RL,,}" == "prohibit-password" ]]; then
  ok "SSH PermitRootLogin: $RL"
else
  warn "SSH PermitRootLogin is '${RL:-yes(default)}' — consider 'prohibit-password' or 'no'"
fi

# Port
SP=$(ssh_param Port)
if [[ "${SP:-22}" == "22" ]]; then
  info "SSH on default port 22 (acceptable, but non-standard port adds obscurity)"
else
  info "SSH on port $SP"
fi

###############################################################################
hdr "4. LISTENING SERVICES"
###############################################################################
info "Ports listening on 0.0.0.0 / [::]  (public-facing):"
ss -tlnp | grep -E '0\.0\.0\.0|::' | while read -r line; do
  port=$(echo "$line" | awk '{print $4}' | rev | cut -d: -f1 | rev)
  proc=$(echo "$line" | grep -oP 'users:\(\("\K[^"]+' || echo "unknown")
  if [[ "$port" == "22" ]]; then
    info "  :$port ($proc) — SSH"
  elif [[ "$port" == "8443" ]]; then
    info "  :$port ($proc) — Vapi relay (expected, public via Funnel)"
  elif [[ "$port" == "80" || "$port" == "443" ]]; then
    info "  :$port ($proc) — HTTP/S"
  else
    warn "  :$port ($proc) — unexpected public listener, verify intent"
  fi
done

info ""
info "Ports listening on 127.0.0.1 (loopback only — good):"
ss -tlnp | grep '127.0.0.1' | while read -r line; do
  port=$(echo "$line" | awk '{print $4}' | rev | cut -d: -f1 | rev)
  proc=$(echo "$line" | grep -oP 'users:\(\("\K[^"]+' || echo "unknown")
  info "  :$port ($proc)"
done

###############################################################################
hdr "5. DOCKER SECURITY"
###############################################################################
if command -v docker &>/dev/null; then
  info "Docker version: $(docker --version | awk '{print $3}')"

  # Check containers running as root
  docker ps --format '{{.ID}} {{.Names}}' | while read -r cid cname; do
    user=$(docker inspect --format '{{.Config.User}}' "$cid" 2>/dev/null)
    if [[ -z "$user" || "$user" == "root" || "$user" == "0" ]]; then
      warn "Container '$cname' runs as root"
    else
      ok "Container '$cname' runs as user '$user'"
    fi
  done

  # Docker socket permissions
  if [[ -S /var/run/docker.sock ]]; then
    SOCK_PERMS=$(stat -c %a /var/run/docker.sock)
    if [[ "$SOCK_PERMS" == "660" ]]; then
      ok "Docker socket permissions: $SOCK_PERMS"
    else
      warn "Docker socket permissions: $SOCK_PERMS (recommend 660)"
    fi
  fi
else
  info "Docker not installed"
fi

###############################################################################
hdr "6. SECRETS & SENSITIVE FILES"
###############################################################################

# Check for world-readable env files
ENV_FILES=(
  /root/.openclaw/.env
  /opt/swarmclaw/.next/standalone/.env.local
  /opt/flowise/.env
  /opt/flowise/docker-compose.yml
)

for f in "${ENV_FILES[@]}"; do
  if [[ -f "$f" ]]; then
    perms=$(stat -c %a "$f")
    owner=$(stat -c %U "$f")
    if [[ "${perms:2:1}" != "0" ]]; then
      fail "$f is world-readable (perms: $perms) — fix: chmod 600 $f"
    elif [[ "${perms:1:1}" != "0" ]]; then
      warn "$f is group-readable (perms: $perms) — consider chmod 600"
    else
      ok "$f permissions: $perms (owner: $owner)"
    fi
  else
    info "$f not found (skipped)"
  fi
done

# Check for API keys in common locations that shouldn't have them
info "Scanning for potential leaked secrets in home directories..."
LEAKED=$(grep -rIl --include='*.sh' --include='*.log' --include='*.txt' \
  -E '(sk-[a-zA-Z0-9]{20,}|AKIA[A-Z0-9]{16}|ghp_[a-zA-Z0-9]{36})' \
  /root/ /home/ /opt/ 2>/dev/null | head -10 || true)
if [[ -n "$LEAKED" ]]; then
  warn "Possible API keys found in plaintext files:"
  echo "$LEAKED" | while read -r f; do warn "  $f"; done
else
  ok "No obvious API keys in plaintext .sh/.log/.txt files"
fi

###############################################################################
hdr "7. USER ACCOUNTS & SUDO"
###############################################################################

# Users with UID 0
UID0=$(awk -F: '$3==0 {print $1}' /etc/passwd)
if [[ "$UID0" == "root" ]]; then
  ok "Only 'root' has UID 0"
else
  fail "Multiple UID 0 accounts: $UID0"
fi

# Users with login shells
info "Accounts with login shells:"
grep -v '/nologin\|/false' /etc/passwd | while IFS=: read -r user _ uid _ _ _ shell; do
  info "  $user (uid=$uid, shell=$shell)"
done

# Sudo access
info "Sudoers (non-comment entries):"
if [[ -f /etc/sudoers ]]; then
  grep -vE '^\s*#|^\s*$|^Defaults' /etc/sudoers 2>/dev/null | while read -r line; do
    info "  $line"
  done
fi
if [[ -d /etc/sudoers.d ]]; then
  for f in /etc/sudoers.d/*; do
    [[ -f "$f" ]] && grep -vE '^\s*#|^\s*$' "$f" 2>/dev/null | while read -r line; do
      info "  [$f] $line"
    done
  done
fi

###############################################################################
hdr "8. AUTHORIZED SSH KEYS"
###############################################################################
for home in /root /home/*; do
  AK="$home/.ssh/authorized_keys"
  if [[ -f "$AK" ]]; then
    info "Keys in $AK:"
    while read -r line; do
      [[ -z "$line" || "$line" == \#* ]] && continue
      comment=$(echo "$line" | awk '{print $NF}')
      keytype=$(echo "$line" | awk '{print $1}')
      info "  $keytype ... $comment"
    done < "$AK"
    # Check permissions
    perms=$(stat -c %a "$AK")
    if [[ "$perms" == "600" || "$perms" == "644" ]]; then
      ok "$AK permissions: $perms"
    else
      warn "$AK permissions: $perms (should be 600)"
    fi
  fi
done

###############################################################################
hdr "9. TAILSCALE & FUNNEL EXPOSURE"
###############################################################################
if command -v tailscale &>/dev/null; then
  info "Tailscale status:"
  tailscale status 2>/dev/null | head -5 | while read -r line; do info "  $line"; done

  info "Tailscale serve/funnel config:"
  tailscale serve status 2>/dev/null | while read -r line; do info "  $line"; done

  # Check if funnel is exposing unexpected ports
  FUNNEL_PORTS=$(tailscale serve status 2>/dev/null | grep -oP ':\K[0-9]+' | sort -u)
  for p in $FUNNEL_PORTS; do
    if [[ "$p" == "443" || "$p" == "8443" || "$p" == "10000" ]]; then
      ok "Funnel port :$p is expected"
    else
      warn "Funnel port :$p — verify this is intentional"
    fi
  done
else
  info "Tailscale not installed"
fi

###############################################################################
hdr "10. SYSTEMD SERVICES & CRON"
###############################################################################
info "Custom systemd services (enabled):"
systemctl list-unit-files --state=enabled --type=service --no-pager 2>/dev/null | \
  grep -vE 'systemd|dbus|ssh|ufw|cron|rsyslog|snap|cloud|getty|network|apparmor|multipathd|polkit|fwupd|ModemManager|packagekit|thermald|accounts-daemon|irqbalance|udisks|unattended' | \
  while read -r line; do
    [[ -n "$line" ]] && info "  $line"
  done

info ""
info "Cron jobs (root):"
crontab -l 2>/dev/null | grep -v '^#' | while read -r line; do
  [[ -n "$line" ]] && info "  $line"
done
if [[ -z "$(crontab -l 2>/dev/null | grep -v '^#')" ]]; then
  info "  (none)"
fi

info ""
info "System cron (/etc/cron.d/):"
for f in /etc/cron.d/*; do
  [[ -f "$f" ]] && grep -v '^#' "$f" 2>/dev/null | while read -r line; do
    [[ -n "$line" ]] && info "  [$f] $line"
  done
done

###############################################################################
hdr "11. FAIL2BAN / INTRUSION DETECTION"
###############################################################################
if command -v fail2ban-client &>/dev/null; then
  ok "fail2ban is installed"
  F2B_STATUS=$(fail2ban-client status 2>/dev/null)
  echo "$F2B_STATUS" | while read -r line; do info "  $line"; done
  # Check SSH jail
  if fail2ban-client status sshd &>/dev/null; then
    ok "fail2ban sshd jail is active"
    BANNED=$(fail2ban-client status sshd 2>/dev/null | grep 'Currently banned' | awk '{print $NF}')
    info "  Currently banned IPs: $BANNED"
  else
    warn "fail2ban sshd jail is NOT active"
  fi
else
  warn "fail2ban is NOT installed — recommended: apt install fail2ban"
fi

###############################################################################
hdr "12. DISK & RESOURCE USAGE"
###############################################################################
info "Disk usage:"
df -h / | tail -1 | awk '{printf "  / — %s used of %s (%s)\n", $3, $2, $5}'

DISK_PCT=$(df / | tail -1 | awk '{print $5}' | tr -d '%')
if [[ $DISK_PCT -gt 90 ]]; then
  fail "Root disk is ${DISK_PCT}% full — critical"
elif [[ $DISK_PCT -gt 80 ]]; then
  warn "Root disk is ${DISK_PCT}% full — getting tight"
else
  ok "Root disk usage: ${DISK_PCT}%"
fi

info "Memory:"
free -h | grep Mem | awk '{printf "  RAM: %s used / %s total (%s free)\n", $3, $2, $4}'
free -h | grep Swap | awk '{printf "  Swap: %s used / %s total\n", $3, $2}'

###############################################################################
hdr "13. RECENT AUTH FAILURES"
###############################################################################
if [[ -f /var/log/auth.log ]]; then
  FAIL_COUNT=$(grep -c 'Failed password\|Invalid user' /var/log/auth.log 2>/dev/null || echo 0)
  info "Failed SSH attempts in auth.log: $FAIL_COUNT"
  if [[ $FAIL_COUNT -gt 100 ]]; then
    warn "High number of failed SSH attempts ($FAIL_COUNT) — ensure fail2ban is active"
  fi
  info "Top 5 offending IPs:"
  grep 'Failed password\|Invalid user' /var/log/auth.log 2>/dev/null | \
    grep -oP 'from \K[0-9.]+' | sort | uniq -c | sort -rn | head -5 | \
    while read -r cnt ip; do info "  $ip — $cnt attempts"; done
else
  info "No /var/log/auth.log found (may use journald)"
fi

###############################################################################
hdr "14. NGINX SECURITY (if present)"
###############################################################################
if command -v nginx &>/dev/null; then
  info "Nginx version: $(nginx -v 2>&1 | awk -F/ '{print $2}')"

  # Check for server_tokens
  if grep -rq 'server_tokens off' /etc/nginx/ 2>/dev/null; then
    ok "server_tokens off (version hidden)"
  else
    warn "server_tokens not explicitly disabled — add 'server_tokens off;' to nginx.conf"
  fi

  # Check SSL config
  for conf in /etc/nginx/sites-enabled/*; do
    [[ -f "$conf" ]] || continue
    name=$(basename "$conf")
    if grep -q 'ssl_certificate' "$conf" 2>/dev/null; then
      ok "  $name: SSL configured"
      if grep -qE 'TLSv1[^.]|TLSv1\.0|TLSv1\.1' "$conf" 2>/dev/null; then
        warn "  $name: TLS 1.0/1.1 may be enabled — use TLSv1.2+ only"
      fi
    fi
  done
else
  info "Nginx not installed"
fi

###############################################################################
hdr "SUMMARY"
###############################################################################
TOTAL=$((PASS + WARN + FAIL + INFO))
printf '\n'
printf '  PASS: %d\n' "$PASS"
printf '  WARN: %d\n' "$WARN"
printf '  FAIL: %d\n' "$FAIL"
printf '  INFO: %d\n' "$INFO"
printf '  ---\n'
printf '  TOTAL checks: %d\n' "$TOTAL"
printf '\n'

if [[ $FAIL -gt 0 ]]; then
  printf '⚠  %d FAIL item(s) need immediate attention. Review above.\n' "$FAIL"
fi
if [[ $WARN -gt 0 ]]; then
  printf '⚡ %d WARN item(s) should be addressed soon.\n' "$WARN"
fi
if [[ $FAIL -eq 0 && $WARN -eq 0 ]]; then
  printf '✅ All checks passed. Looking good.\n'
fi

printf '\nFull report saved to: %s\n' "$REPORT"
