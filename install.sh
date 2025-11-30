#!/bin/bash
# ============================================
# Claude Code Productivities - Installer
# Sets up hooks, agents, commands, and templates
# ============================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
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
echo ""

# ============================================
# Component Selection
# ============================================
echo -e "${CYAN}Select components to install:${NC}"
echo ""

# Default all to yes
INSTALL_SLACK="y"
INSTALL_CHARLIE="y"
INSTALL_DEVJOURNAL="y"

read -p "  [x] Slack Notifications (hooks) [Y/n]: " input
[[ "$input" =~ ^[nN] ]] && INSTALL_SLACK="n"

read -p "  [x] Charlie - Thinking Partner (agent) [Y/n]: " input
[[ "$input" =~ ^[nN] ]] && INSTALL_CHARLIE="n"

read -p "  [x] DevJournal & DevReview (commands) [Y/n]: " input
[[ "$input" =~ ^[nN] ]] && INSTALL_DEVJOURNAL="n"

echo ""

# ============================================
# Create Directories
# ============================================
echo -e "${YELLOW}Creating directories...${NC}"
mkdir -p "$CONFIG_DIR"
mkdir -p "$CLAUDE_DIR/agents"
mkdir -p "$CLAUDE_DIR/commands"
mkdir -p "$CLAUDE_DIR/templates"
mkdir -p "$CLAUDE_DIR/notification-counters"
mkdir -p "$HOME/DevJournals"
echo -e "${GREEN}✓ Directories created${NC}"
echo ""

# ============================================
# Slack Notifications
# ============================================
if [ "$INSTALL_SLACK" = "y" ]; then
    echo -e "${CYAN}[Slack Notifications]${NC}"

    SLACK_CONFIG="$CONFIG_DIR/slack-config.json"

    if [ -f "$SLACK_CONFIG" ]; then
        echo -e "${GREEN}✓ Slack config already exists${NC}"
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

    # Set permissions
    chmod +x "$SCRIPT_DIR/lib/"*.sh 2>/dev/null || true
    chmod +x "$SCRIPT_DIR/hooks/slack/"*.sh 2>/dev/null || true

    # Configure hooks
    HOOKS_FILE="$CLAUDE_DIR/hooks.json"
    NOTIFY_SCRIPT="$SCRIPT_DIR/hooks/slack/notify.sh"
    PERMISSION_SCRIPT="$SCRIPT_DIR/hooks/slack/permission.sh"

    python3 << PYEOF
import json
import os

hooks_file = "$HOOKS_FILE"
notify_script = "$NOTIFY_SCRIPT"
permission_script = "$PERMISSION_SCRIPT"

if os.path.exists(hooks_file):
    with open(hooks_file) as f:
        data = json.load(f)
else:
    data = {}

if "hooks" not in data:
    data["hooks"] = {}

slack_notify_hook = {
    "matcher": "",
    "hooks": [{"type": "command", "command": notify_script}]
}

slack_permission_hook = {
    "matcher": "",
    "hooks": [{"type": "command", "command": permission_script}]
}

def add_hook(event_name, new_hook):
    if event_name not in data["hooks"]:
        data["hooks"][event_name] = []
    for existing in data["hooks"][event_name]:
        for h in existing.get("hooks", []):
            if h.get("command") == new_hook["hooks"][0]["command"]:
                return False
    data["hooks"][event_name].append(new_hook)
    return True

add_hook("Notification", slack_notify_hook)
add_hook("Stop", slack_notify_hook)
add_hook("PreToolUse", slack_permission_hook)

with open(hooks_file, "w") as f:
    json.dump(data, f, indent=2)
PYEOF

    echo -e "${GREEN}✓ Hooks registered${NC}"
    echo ""
fi

# ============================================
# Charlie Agent
# ============================================
if [ "$INSTALL_CHARLIE" = "y" ]; then
    echo -e "${CYAN}[Charlie Agent]${NC}"

    # Create charlie-sessions directory
    mkdir -p "$CLAUDE_DIR/charlie-sessions"

    # Symlink agent
    AGENT_SOURCE="$SCRIPT_DIR/agents/charlie/agent.md"
    AGENT_TARGET="$CLAUDE_DIR/agents/charlie.md"

    if [ -L "$AGENT_TARGET" ]; then
        rm "$AGENT_TARGET"
    elif [ -f "$AGENT_TARGET" ]; then
        backup="${AGENT_TARGET}.bak.$(date +%Y%m%d)"
        mv "$AGENT_TARGET" "$backup"
        echo -e "${YELLOW}  Backed up existing: $backup${NC}"
    fi

    ln -sf "$AGENT_SOURCE" "$AGENT_TARGET"
    echo -e "${GREEN}✓ Agent symlinked → ~/.claude/agents/charlie.md${NC}"

    # Symlink command
    COMMAND_SOURCE="$SCRIPT_DIR/commands/charlie/command.md"
    COMMAND_TARGET="$CLAUDE_DIR/commands/charlie.md"

    if [ -L "$COMMAND_TARGET" ]; then
        rm "$COMMAND_TARGET"
    elif [ -f "$COMMAND_TARGET" ]; then
        backup="${COMMAND_TARGET}.bak.$(date +%Y%m%d)"
        mv "$COMMAND_TARGET" "$backup"
        echo -e "${YELLOW}  Backed up existing: $backup${NC}"
    fi

    ln -sf "$COMMAND_SOURCE" "$COMMAND_TARGET"
    echo -e "${GREEN}✓ Command symlinked → ~/.claude/commands/charlie.md${NC}"

    echo -e "${GREEN}✓ Session directory created${NC}"
    echo ""
fi

# ============================================
# DevJournal & DevReview Commands
# ============================================
if [ "$INSTALL_DEVJOURNAL" = "y" ]; then
    echo -e "${CYAN}[DevJournal & DevReview]${NC}"

    # Symlink devjournal command
    SOURCE="$SCRIPT_DIR/commands/devjournal/command.md"
    TARGET="$CLAUDE_DIR/commands/devjournal.md"

    if [ -L "$TARGET" ]; then
        rm "$TARGET"
    elif [ -f "$TARGET" ]; then
        backup="${TARGET}.bak.$(date +%Y%m%d)"
        mv "$TARGET" "$backup"
        echo -e "${YELLOW}  Backed up existing: $backup${NC}"
    fi

    ln -sf "$SOURCE" "$TARGET"
    echo -e "${GREEN}✓ /devjournal command symlinked${NC}"

    # Symlink devreview command
    SOURCE="$SCRIPT_DIR/commands/devreview/command.md"
    TARGET="$CLAUDE_DIR/commands/devreview.md"

    if [ -L "$TARGET" ]; then
        rm "$TARGET"
    elif [ -f "$TARGET" ]; then
        backup="${TARGET}.bak.$(date +%Y%m%d)"
        mv "$TARGET" "$backup"
        echo -e "${YELLOW}  Backed up existing: $backup${NC}"
    fi

    ln -sf "$SOURCE" "$TARGET"
    echo -e "${GREEN}✓ /devreview command symlinked${NC}"

    # Copy template (only if not exists)
    TEMPLATE_SOURCE="$SCRIPT_DIR/templates/dev-journal.md"
    TEMPLATE_TARGET="$CLAUDE_DIR/templates/dev-journal.md"

    if [ ! -f "$TEMPLATE_TARGET" ]; then
        cp "$TEMPLATE_SOURCE" "$TEMPLATE_TARGET"
        echo -e "${GREEN}✓ Template installed → ~/.claude/templates/dev-journal.md${NC}"
    else
        echo -e "${GREEN}✓ Template already exists (preserved)${NC}"
    fi

    echo -e "${GREEN}✓ Journal directory: ~/DevJournals${NC}"
    echo ""
fi

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
echo ""

# ============================================
# Test (Dry Run)
# ============================================
if [ "$INSTALL_SLACK" = "y" ]; then
    echo -e "${YELLOW}Testing Slack hook...${NC}"

    if DRY_RUN=1 "$SCRIPT_DIR/hooks/slack/permission.sh" << 'EOF' | grep -q "decision"
{"tool_name": "Test", "tool_input": {}, "cwd": "/tmp"}
EOF
    then
        echo -e "${GREEN}✓ Permission hook test passed${NC}"
    else
        echo -e "${RED}✗ Permission hook test failed${NC}"
    fi
    echo ""
fi

# ============================================
# Done!
# ============================================
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Installation Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""

echo "Available commands:"
if [ "$INSTALL_CHARLIE" = "y" ]; then
    echo "  /charlie [topic]     - Start thinking session with Charlie"
fi
if [ "$INSTALL_DEVJOURNAL" = "y" ]; then
    echo "  /devjournal [name]   - Log a development session"
    echo "  /devreview [name]    - Analyze development patterns"
fi
echo ""

if [ "$INSTALL_SLACK" = "y" ]; then
    echo "Slack notifications active for all tool use."
    echo ""
fi

echo "Repo location: $SCRIPT_DIR"
echo ""
echo "To update later:"
echo "  cd $SCRIPT_DIR && git pull"
echo ""
