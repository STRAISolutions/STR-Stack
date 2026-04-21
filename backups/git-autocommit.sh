#!/bin/bash
# Git auto-commit and push for all tracked repos
# Runs: every 6 hours

TIMESTAMP=$(date +"%Y-%m-%d %H:%M:%S")

for REPO in /srv/str-stack-public /root/str-stack /root/clawhip; do
    if [ -d "$REPO/.git" ]; then
        cd "$REPO"
        git add -A 2>/dev/null
        if ! git diff --cached --quiet 2>/dev/null; then
            git commit -m "Auto-backup: $TIMESTAMP" 2>/dev/null
            git push origin master 2>/dev/null || git push origin main 2>/dev/null
            echo "[$(date)] Committed and pushed changes in $REPO"
        else
            echo "[$(date)] No changes in $REPO"
        fi
    else
        echo "[$(date)] WARNING: No git repo at $REPO"
    fi
done

echo "[$(date)] Git auto-commit and push complete."
