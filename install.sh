#!/bin/bash
# ============================================
# Claude Code Productivities - Installer
# Sets up Slack notification hooks
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Get script directory (where repo is cloned)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="$HOME/.claude"
CONFIG_DIR="$CLAUDE_DIR/config"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}Claude Code Productivities Installer${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# ============================================
# Check Prerequisites
# ============================================
echo -e "${YELLOW}Checking prerequisites...${NC}"

if [ ! -d "$CLAUDE_DIR" ]; then
    echo -e "${RED}Error: Claude Code not installed (~/.claude not found)${NC}"
    echo "Please install Claude Code first: https://claude.ai/code"
    exit 1
fi

echo -e "${GREEN}✓ Claude Code found${NC}"

# ============================================
# Create Config Directory
# ============================================
mkdir -p "$CONFIG_DIR"
mkdir -p "$CLAUDE_DIR/notification-counters"

# ============================================
# Configure Slack Webhook
# ============================================
SLACK_CONFIG="$CONFIG_DIR/slack-config.json"

if [ -f "$SLACK_CONFIG" ]; then
    echo -e "${GREEN}✓ Slack config already exists${NC}"
    # Verify it has webhook_url
    if python3 -c "import json; assert json.load(open('$SLACK_CONFIG')).get('webhook_url')" 2>/dev/null; then
        echo -e "${GREEN}✓ Webhook URL configured${NC}"
    else
        echo -e "${YELLOW}⚠ Webhook URL missing in config${NC}"
        read -p "Enter your Slack webhook URL: " webhook_url
        cat > "$SLACK_CONFIG" << EOF
{
    "webhook_url": "$webhook_url",
    "enabled": true
}
EOF
        echo -e "${GREEN}✓ Slack config updated${NC}"
    fi
else
    echo -e "${YELLOW}Slack webhook not configured${NC}"
    echo ""
    echo "To get a Slack webhook URL:"
    echo "1. Go to https://api.slack.com/apps"
    echo "2. Create a new app or use existing"
    echo "3. Enable 'Incoming Webhooks'"
    echo "4. Create a webhook for your channel"
    echo ""
    read -p "Enter your Slack webhook URL: " webhook_url

    if [ -z "$webhook_url" ]; then
        echo -e "${RED}No webhook URL provided. Skipping Slack setup.${NC}"
    else
        cat > "$SLACK_CONFIG" << EOF
{
    "webhook_url": "$webhook_url",
    "enabled": true
}
EOF
        echo -e "${GREEN}✓ Slack config created${NC}"
    fi
fi

# ============================================
# Set Executable Permissions
# ============================================
echo -e "${YELLOW}Setting permissions...${NC}"
chmod +x "$SCRIPT_DIR/lib/"*.sh 2>/dev/null || true
chmod +x "$SCRIPT_DIR/hooks/slack/"*.sh 2>/dev/null || true
echo -e "${GREEN}✓ Permissions set${NC}"

# ============================================
# Update hooks.json
# ============================================
echo -e "${YELLOW}Configuring hooks...${NC}"

HOOKS_FILE="$CLAUDE_DIR/hooks.json"
NOTIFY_SCRIPT="$SCRIPT_DIR/hooks/slack/notify.sh"
PERMISSION_SCRIPT="$SCRIPT_DIR/hooks/slack/permission.sh"

# Create hooks.json with Slack hooks
# Note: This will preserve existing hooks by merging
python3 << PYEOF
import json
import os

hooks_file = "$HOOKS_FILE"
notify_script = "$NOTIFY_SCRIPT"
permission_script = "$PERMISSION_SCRIPT"

# Load existing hooks or start fresh
if os.path.exists(hooks_file):
    with open(hooks_file) as f:
        data = json.load(f)
else:
    data = {}

if "hooks" not in data:
    data["hooks"] = {}

# Define our Slack hooks
slack_notify_hook = {
    "matcher": "",
    "hooks": [{"type": "command", "command": notify_script}]
}

slack_permission_hook = {
    "matcher": "",
    "hooks": [{"type": "command", "command": permission_script}]
}

# Helper to add hook if not already present
def add_hook(event_name, new_hook):
    if event_name not in data["hooks"]:
        data["hooks"][event_name] = []

    # Check if this script is already configured
    for existing in data["hooks"][event_name]:
        for h in existing.get("hooks", []):
            if h.get("command") == new_hook["hooks"][0]["command"]:
                return False  # Already exists

    data["hooks"][event_name].append(new_hook)
    return True

# Add hooks
added_notify = add_hook("Notification", slack_notify_hook)
added_stop = add_hook("Stop", slack_notify_hook)
added_permission = add_hook("PreToolUse", slack_permission_hook)

# Write back
with open(hooks_file, "w") as f:
    json.dump(data, f, indent=2)

if added_notify or added_stop or added_permission:
    print("Hooks updated")
else:
    print("Hooks already configured")
PYEOF

echo -e "${GREEN}✓ Hooks configured${NC}"

# ============================================
# Clean Up Old Scripts (Migration)
# ============================================
echo -e "${YELLOW}Checking for old scripts to migrate...${NC}"

OLD_SCRIPTS=(
    "$CLAUDE_DIR/slack-notify.sh"
    "$CLAUDE_DIR/slack-notify-permission.sh"
    "$CLAUDE_DIR/lib/slack-common.sh"
)

migrated=0
for old_script in "${OLD_SCRIPTS[@]}"; do
    if [ -f "$old_script" ]; then
        backup="${old_script}.bak.$(date +%Y%m%d)"
        mv "$old_script" "$backup"
        echo -e "${YELLOW}  Backed up: $old_script → $backup${NC}"
        migrated=1
    fi
done

if [ $migrated -eq 1 ]; then
    echo -e "${GREEN}✓ Old scripts backed up${NC}"
else
    echo -e "${GREEN}✓ No old scripts to migrate${NC}"
fi

# ============================================
# Test (Dry Run)
# ============================================
echo -e "${YELLOW}Testing installation...${NC}"

if DRY_RUN=1 "$PERMISSION_SCRIPT" << 'EOF' | grep -q "decision"
{"tool_name": "Test", "tool_input": {}, "cwd": "/tmp"}
EOF
then
    echo -e "${GREEN}✓ Permission hook test passed${NC}"
else
    echo -e "${RED}✗ Permission hook test failed${NC}"
fi

# ============================================
# Done!
# ============================================
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo "Repo location: $SCRIPT_DIR"
echo "Hooks configured in: $HOOKS_FILE"
echo "Slack config: $SLACK_CONFIG"
echo ""
echo "To test manually:"
echo "  $PERMISSION_SCRIPT < test-input.json"
echo ""
echo "To update later:"
echo "  cd $SCRIPT_DIR && git pull"
echo ""
