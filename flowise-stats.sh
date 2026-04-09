#!/bin/bash
# flowise-stats.sh — Writes flowise-stats.json for dashboard consumption
# Runs via cron every 5 minutes

set -euo pipefail
OUT="/root/str-stack/flowise-stats.json"
DB_CMD="docker exec flowise-db psql -U flowise_admin -d flowise -t -A"

# Total chatflows
total_flows=$($DB_CMD -c "SELECT COUNT(*) FROM chat_flow;" 2>/dev/null || echo 0)

# Deployed chatflows
deployed_flows=$($DB_CMD -c "SELECT COUNT(*) FROM chat_flow WHERE deployed = true;" 2>/dev/null || echo 0)

# Total messages (executions)
total_messages=$($DB_CMD -c "SELECT COUNT(*) FROM chat_message;" 2>/dev/null || echo 0)

# Messages in last 24h
messages_24h=$($DB_CMD -c "SELECT COUNT(*) FROM chat_message WHERE \"createdDate\" > NOW() - INTERVAL '24 hours';" 2>/dev/null || echo 0)

# Messages in last 7 days
messages_7d=$($DB_CMD -c "SELECT COUNT(*) FROM chat_message WHERE \"createdDate\" > NOW() - INTERVAL '7 days';" 2>/dev/null || echo 0)

# Total tools
total_tools=$($DB_CMD -c "SELECT COUNT(*) FROM tool;" 2>/dev/null || echo 0)

# Total credentials
total_creds=$($DB_CMD -c "SELECT COUNT(*) FROM credential;" 2>/dev/null || echo 0)

# Feedback stats (if any)
positive_feedback=$($DB_CMD -c "SELECT COUNT(*) FROM chat_message_feedback WHERE rating = 'THUMBS_UP';" 2>/dev/null || echo 0)
negative_feedback=$($DB_CMD -c "SELECT COUNT(*) FROM chat_message_feedback WHERE rating = 'THUMBS_DOWN';" 2>/dev/null || echo 0)

# HTTP health probe
http_status=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:3000/ 2>/dev/null || echo 0)

# Build JSON
cat > "$OUT" <<EOF
{
  "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "health": {
    "http_status": $http_status,
    "status": "$([ "$http_status" = "200" ] && echo "healthy" || echo "degraded")"
  },
  "flows": {
    "total": $total_flows,
    "deployed": $deployed_flows
  },
  "executions": {
    "total": $total_messages,
    "last_24h": $messages_24h,
    "last_7d": $messages_7d
  },
  "tools": $total_tools,
  "credentials": $total_creds,
  "feedback": {
    "positive": $positive_feedback,
    "negative": $negative_feedback
  }
}
EOF

echo "[$(date)] flowise-stats.json updated" >> /var/log/flowise-stats.log
