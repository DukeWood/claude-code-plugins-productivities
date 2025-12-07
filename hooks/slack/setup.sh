#!/bin/bash
# PATH must be set BEFORE any commands (hooks run in minimal environment)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

echo "=================================================="
echo "  Slack Notification Hooks Setup"
echo "=================================================="
echo ""

# Get the directory where this script is located
HOOKS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CONFIG_DIR="$HOME/.claude/config"
SETTINGS_FILE="$HOME/.claude/settings.json"
CONFIG_FILE="$CONFIG_DIR/slack-config.json"

# Step 1: Create config directory
echo "Step 1: Creating config directory..."
mkdir -p "$CONFIG_DIR"
mkdir -p "$HOME/.claude/logs"
echo "✓ Created $CONFIG_DIR"
echo ""

# Step 2: Create config file if it doesn't exist
if [ -f "$CONFIG_FILE" ]; then
  echo "Step 2: Config file already exists at $CONFIG_FILE"
  echo "⚠️  Skipping config creation to preserve existing settings"
else
  echo "Step 2: Creating Slack config file..."
  echo "Please enter your Slack webhook URL:"
  echo "(Get it from: https://api.slack.com/messaging/webhooks)"
  read -r WEBHOOK_URL

  cat > "$CONFIG_FILE" <<EOF
{
  "webhook_url": "$WEBHOOK_URL",
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": false
}
EOF
  echo "✓ Created $CONFIG_FILE"
fi
echo ""

# Step 3: Register hooks in settings.json
echo "Step 3: Registering hooks in Claude Code settings..."

if [ ! -f "$SETTINGS_FILE" ]; then
  # Create new settings file
  cat > "$SETTINGS_FILE" <<EOF
{
  "hooks": {
    "Notification": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOOKS_DIR/notify-permission.sh"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          {
            "type": "command",
            "command": "$HOOKS_DIR/notify-stop.sh"
          }
        ]
      }
    ]
  }
}
EOF
  echo "✓ Created new settings file with hooks registered"
else
  echo "⚠️  Settings file already exists at $SETTINGS_FILE"
  echo ""
  echo "Please manually add these hooks to your settings.json:"
  echo ""
  echo "\"Notification\": ["
  echo "  {"
  echo "    \"matcher\": \"\","
  echo "    \"hooks\": ["
  echo "      {"
  echo "        \"type\": \"command\","
  echo "        \"command\": \"$HOOKS_DIR/notify-permission.sh\""
  echo "      }"
  echo "    ]"
  echo "  }"
  echo "],"
  echo ""
  echo "\"Stop\": ["
  echo "  {"
  echo "    \"matcher\": \"\","
  echo "    \"hooks\": ["
  echo "      {"
  echo "        \"type\": \"command\","
  echo "        \"command\": \"$HOOKS_DIR/notify-stop.sh\""
  echo "      }"
  echo "    ]"
  echo "  }"
  echo "]"
fi
echo ""

# Step 4: Test the setup
echo "Step 4: Testing hooks..."
echo ""

# Test notify-permission.sh
echo "Testing notify-permission.sh..."
TEST_PAYLOAD_PERMISSION='{"hook_event_name":"Notification","notification_type":"permission_prompt","tool_name":"Edit","tool_input":{"file_path":"/tmp/test.txt"},"session_id":"test-123","cwd":"'"$HOME"'"}'

if echo "$TEST_PAYLOAD_PERMISSION" | "$HOOKS_DIR/notify-permission.sh" 2>&1; then
  echo "✓ notify-permission.sh executed successfully"
else
  echo "✗ notify-permission.sh failed"
fi
echo ""

# Test notify-stop.sh
echo "Testing notify-stop.sh..."
TEST_PAYLOAD_STOP='{"hook_event_name":"Stop","session_id":"test-123","cwd":"'"$HOME"'"}'

if echo "$TEST_PAYLOAD_STOP" | "$HOOKS_DIR/notify-stop.sh" 2>&1; then
  echo "✓ notify-stop.sh executed successfully"
else
  echo "✗ notify-stop.sh failed"
fi
echo ""

echo "=================================================="
echo "  Setup Complete!"
echo "=================================================="
echo ""
echo "Configuration:"
echo "  - Config: $CONFIG_FILE"
echo "  - Settings: $SETTINGS_FILE"
echo "  - Debug logs: $HOME/.claude/logs/"
echo ""
echo "Next steps:"
echo "  1. Verify webhook URL in $CONFIG_FILE"
echo "  2. Check Slack for test notifications"
echo "  3. Start a Claude Code session in tmux to test"
echo ""
echo "To disable notifications:"
echo "  Edit $CONFIG_FILE and set \"enabled\": false"
echo ""
echo "Debug logs:"
echo "  tail -f $HOME/.claude/logs/notify-permission-debug.log"
echo "  tail -f $HOME/.claude/logs/notify-stop-debug.log"
echo ""
