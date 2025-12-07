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
DEBUG_LOG="$HOME/.claude/logs/notify-permission-debug.log"
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Received payload: $PAYLOAD" >> "$DEBUG_LOG" 2>/dev/null

# Parse payload
HOOK_EVENT=$(echo "$PAYLOAD" | jq -r '.hook_event_name // empty' 2>/dev/null)
NOTIF_TYPE=$(echo "$PAYLOAD" | jq -r '.notification_type // empty' 2>/dev/null)

# Only process Notification hook events
if [ "$HOOK_EVENT" != "Notification" ]; then
  exit 0
fi

# Process permission_prompt and idle_prompt notifications
if [ "$NOTIF_TYPE" != "permission_prompt" ] && [ "$NOTIF_TYPE" != "idle_prompt" ]; then
  exit 0
fi

# Check if Slack is enabled
if ! is_slack_enabled; then
  exit 0
fi

# Check if permission notifications are enabled
if ! is_notification_type_enabled "permission_required"; then
  exit 0
fi

# Extract basic info from payload
SESSION_ID=$(echo "$PAYLOAD" | jq -r '.session_id // empty' 2>/dev/null)
CWD=$(echo "$PAYLOAD" | jq -r '.cwd // empty' 2>/dev/null)

# Try to extract tool info from payload (might not be present)
TOOL_NAME=$(echo "$PAYLOAD" | jq -r '.tool_name // empty' 2>/dev/null)
TOOL_INPUT=$(echo "$PAYLOAD" | jq -r '.tool_input // empty' 2>/dev/null)

# If tool info not in Notification payload, try to read from PreToolUse capture
# (This makes the hook work with or without PreToolUse)
if [ -z "$TOOL_NAME" ] || [ "$TOOL_NAME" = "null" ]; then
  # Try to read from last captured tool request
  TOOL_REQUEST_FILE="$HOME/.claude/config/last_tool_request.json"
  if [ -f "$TOOL_REQUEST_FILE" ]; then
    TOOL_NAME=$(jq -r '.tool_name // empty' "$TOOL_REQUEST_FILE" 2>/dev/null)
    TOOL_INPUT=$(jq -r '.tool_input // empty' "$TOOL_REQUEST_FILE" 2>/dev/null)
  fi
fi

# If still no tool info, use generic message
if [ -z "$TOOL_NAME" ] || [ "$TOOL_NAME" = "null" ] || [ "$TOOL_NAME" = "empty" ]; then
  TOOL_NAME="Unknown"
  TOOL_INPUT='{}'
fi

# Gather context
PROJECT_NAME=$(get_project_name "$CWD")
TERMINAL_INFO=$(get_terminal_info "$CWD")
GIT_BRANCH=$(get_git_branch "$CWD")
SWITCH_CMD=$(get_switch_command "$CWD")
SERIAL=$(get_session_serial "$SESSION_ID")
TIMESTAMP=$(get_timestamp)

# Build notification based on type
if [ "$NOTIF_TYPE" = "idle_prompt" ]; then
  # For idle prompts, show "Waiting for Input" message
  NOTIF_TITLE="⏳ Waiting for Input"
  NOTIF_COLOR="#FFA500"
  NOTIF_EMOJI="⏳"
  TOOL_DETAILS="**Claude is waiting for your response**\nPlease check the terminal to continue."
else
  # For permission prompts, show tool details
  NOTIF_TITLE="🔐 Permission Required"
  NOTIF_COLOR="#E01E5A"
  NOTIF_EMOJI="🔐"
  TOOL_DETAILS=$(format_tool_details "$TOOL_NAME" "$TOOL_INPUT")
fi

# Build Slack notification
WEBHOOK_URL=$(get_webhook_url)

if [ -z "$WEBHOOK_URL" ]; then
  echo "No webhook URL configured" >> "$DEBUG_LOG" 2>/dev/null
  exit 0
fi

# Escape special characters for JSON
TOOL_DETAILS_ESCAPED=$(echo "$TOOL_DETAILS" | sed 's/"/\\"/g')
SWITCH_CMD_ESCAPED=$(echo "$SWITCH_CMD" | sed 's/"/\\"/g')

SLACK_PAYLOAD=$(cat <<EOF
{
  "text": "$NOTIF_EMOJI $NOTIF_TITLE | $PROJECT_NAME",
  "attachments": [{
    "color": "$NOTIF_COLOR",
    "blocks": [
      {
        "type": "header",
        "text": {
          "type": "plain_text",
          "text": "$NOTIF_TITLE"
        }
      },
      {
        "type": "context",
        "elements": [{
          "type": "mrkdwn",
          "text": "\`$SERIAL\` | *$PROJECT_NAME* | $TERMINAL_INFO | \`$GIT_BRANCH\` | $TIMESTAMP"
        }]
      },
      {
        "type": "divider"
      },
      {
        "type": "section",
        "text": {
          "type": "mrkdwn",
          "text": "$TOOL_DETAILS_ESCAPED"
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
if [ "$NOTIF_TYPE" = "idle_prompt" ]; then
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Sent idle_prompt notification (waiting for input)" >> "$DEBUG_LOG" 2>/dev/null
else
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] Sent permission_prompt notification for $TOOL_NAME" >> "$DEBUG_LOG" 2>/dev/null
fi

exit 0
