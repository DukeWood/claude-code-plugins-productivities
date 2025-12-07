#!/bin/bash
# PATH must be set BEFORE any commands (hooks run in minimal environment)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load libraries
source "$SCRIPT_DIR/lib/slack.sh"
source "$SCRIPT_DIR/lib/enrichers.sh"

# Read all stdin at once (don't block)
PAYLOAD=$(cat)

# Debug logging (optional - comment out if not needed)
DEBUG_LOG="$HOME/.claude/logs/notify-stop-debug.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Received payload: $PAYLOAD" >> "$DEBUG_LOG" 2>/dev/null

# Parse payload
HOOK_EVENT=$(echo "$PAYLOAD" | jq -r '.hook_event_name // empty' 2>/dev/null)
SESSION_ID=$(echo "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)
CWD=$(echo "$PAYLOAD" | jq -r '.cwd // empty' 2>/dev/null)

# Only process Stop events
if [ "$HOOK_EVENT" != "Stop" ]; then
  exit 0
fi

# Check if Slack is enabled
if ! is_slack_enabled; then
  exit 0
fi

# Check if task complete notifications are enabled
if ! is_notification_type_enabled "task_complete"; then
  exit 0
fi

# Check if we should notify
# Only notify if: in tmux OR notify_always=true
IN_TMUX=$(detect_tmux "$CWD")
CONFIG=$(load_slack_config)
NOTIFY_ALWAYS=$(echo "$CONFIG" | jq -r '.notify_always // false' 2>/dev/null)

if [ "$IN_TMUX" != "true" ] && [ "$NOTIFY_ALWAYS" != "true" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Skipping notification (not in tmux and notify_always=false)" >> "$DEBUG_LOG" 2>/dev/null
  exit 0
fi

# Gather context (all functions from enrichers.sh)
PROJECT_NAME=$(get_project_name "$CWD")
GIT_STATUS=$(get_git_status "$CWD")
TERMINAL_INFO=$(get_terminal_info "$CWD")
TOKEN_USAGE=$(get_token_usage "$SESSION_ID" "$CWD")
TASK_DESCRIPTION=$(get_task_description "$SESSION_ID" "$CWD")
SWITCH_CMD=$(get_switch_command "$CWD")
SERIAL=$(get_session_serial "$SESSION_ID")
TIMESTAMP=$(get_timestamp)

# Build Slack notification
WEBHOOK_URL=$(get_webhook_url)

if [ -z "$WEBHOOK_URL" ]; then
  echo "No webhook URL configured" >> "$DEBUG_LOG" 2>/dev/null
  exit 0
fi

# Escape special characters for JSON
TASK_DESCRIPTION_ESCAPED=$(echo "$TASK_DESCRIPTION" | sed 's/"/\\"/g')
SWITCH_CMD_ESCAPED=$(echo "$SWITCH_CMD" | sed 's/"/\\"/g')

SLACK_PAYLOAD=$(cat <<EOF
{
  "text": "✅ Task Complete | $PROJECT_NAME",
  "attachments": [{
    "color": "#36a64f",
    "blocks": [
      {
        "type": "header",
        "text": {
          "type": "plain_text",
          "text": "✅ Task Complete"
        }
      },
      {
        "type": "context",
        "elements": [{
          "type": "mrkdwn",
          "text": "\`$SERIAL\` | *$PROJECT_NAME* | $TERMINAL_INFO | $GIT_STATUS | $TIMESTAMP | 📊 $TOKEN_USAGE"
        }]
      },
      {
        "type": "divider"
      },
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "$TASK_DESCRIPTION_ESCAPED"
        }
      },
      {
        "type": "context",
        "elements": [{
          "type": "mrkdwn",
          "text": "**Quick Action:** \`$SWITCH_CMD_ESCAPED\`"
        }]
      }
    ]
  }]
}
EOF
)

# Send notification (async - runs in background)
send_slack_notification "$WEBHOOK_URL" "$SLACK_PAYLOAD"

# Log successful send
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Sent task complete notification" >> "$DEBUG_LOG" 2>/dev/null

exit 0
