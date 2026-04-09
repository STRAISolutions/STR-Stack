#!/bin/bash
# Append a completed task entry
# Usage: bash /root/str-stack/log-change.sh "Task subject" "Short detail"
SUBJECT="$1"
DETAIL="$2"
LOG="/srv/str-stack-public/changelog.json"
NOW=$(TZ="America/New_York" date +"%Y-%m-%d %H:%M")

python3 << PYEOF
import json
with open("$LOG") as f:
    data = json.load(f)
data["log"].append({"time": "$NOW", "subject": "$SUBJECT", "detail": "$DETAIL"})
with open("$LOG", "w") as f:
    json.dump(data, f, indent=2)
print("Logged: $NOW | $SUBJECT | $DETAIL")
PYEOF
