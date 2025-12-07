#!/bin/bash
# PATH must be set BEFORE any commands (hooks run in minimal environment)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Send Slack notification (async - runs in background)
send_slack_notification() {
  local webhook_url="$1"
  local payload="$2"

  # Send with curl, suppress output, run in background
  curl -X POST "$webhook_url" \
    -H 'Content-Type: application/json' \
    -d "$payload" \
    --max-time 10 \
    >/dev/null 2>&1 &
}

# Load Slack config
load_slack_config() {
  local config_file="${SLACK_CONFIG_FILE:-$HOME/.claude/config/slack-config.json}"

  if [ ! -f "$config_file" ]; then
    echo ""
    return 1
  fi

  cat "$config_file"
}

# Check if Slack notifications are enabled
is_slack_enabled() {
  local config=$(load_slack_config)

  if [ -z "$config" ]; then
    return 1
  fi

  local enabled=$(echo "$config" | jq -r '.enabled // true')

  if [ "$enabled" = "true" ]; then
    return 0
  else
    return 1
  fi
}

# Get webhook URL from config
get_webhook_url() {
  local config=$(load_slack_config)

  if [ -z "$config" ]; then
    echo ""
    return 1
  fi

  echo "$config" | jq -r '.webhook_url // empty'
}

# Check if specific notification type is enabled
is_notification_type_enabled() {
  local notif_type="$1"
  local config=$(load_slack_config)

  if [ -z "$config" ]; then
    return 1
  fi

  local enabled=$(echo "$config" | jq -r ".notify_on.${notif_type} // true")

  if [ "$enabled" = "true" ]; then
    return 0
  else
    return 1
  fi
}
