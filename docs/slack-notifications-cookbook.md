# Slack Notifications Cookbook

A comprehensive guide to setting up, customizing, and troubleshooting Claude Code Slack notifications.

## Table of Contents

1. [Prerequisites](#prerequisites)
2. [Installation](#installation)
3. [How It Works](#how-it-works)
4. [Customization](#customization)
5. [Troubleshooting](#troubleshooting)
6. [Advanced Usage](#advanced-usage)
7. [FAQ](#faq)

---

## Prerequisites

### Required

- **Claude Code** installed (`~/.claude` directory exists)
- **Python 3** available in PATH
- **Slack workspace** with permission to create apps

### Supported Environments

| Platform | Status |
|----------|--------|
| macOS (Apple Silicon) | ✅ Fully supported |
| macOS (Intel) | ✅ Fully supported |
| Linux | ⚠️ Should work (untested) |
| Windows WSL | ⚠️ Should work (untested) |

---

## Installation

### Step 1: Create Slack App & Webhook

1. Go to [Slack API Apps](https://api.slack.com/apps)
2. Click **Create New App** → **From scratch**
3. Name it (e.g., "Claude Code Notifications")
4. Select your workspace
5. Go to **Incoming Webhooks** → Enable it
6. Click **Add New Webhook to Workspace**
7. Select the channel for notifications
8. Copy the webhook URL (starts with `https://hooks.slack.com/services/...`)

### Step 2: Install the Hooks

```bash
# Clone the repository
git clone https://github.com/DukeWood/claude-code-plugins-productivities.git
cd claude-code-plugins-productivities

# Run the installer
./install.sh
```

The installer will:
- Prompt for your Slack webhook URL
- Configure `~/.claude/hooks.json`
- Set up the config file
- Test the installation

### Step 3: Verify Installation

Test manually:
```bash
./hooks/slack/permission.sh << 'EOF'
{"tool_name": "Test", "tool_input": {"hello": "world"}, "cwd": "/tmp"}
EOF
```

You should see:
- `{"decision": "allow"}` in terminal
- A test notification in Slack

---

## How It Works

### Hook Events

Claude Code triggers hooks at specific events:

| Event | When | Hook Script |
|-------|------|-------------|
| `PreToolUse` | Before using any tool | `permission.sh` |
| `Notification` | When Claude sends a notification | `notify.sh` |
| `Stop` | When Claude finishes a task | `notify.sh` |

### Data Flow

```
Claude Code
    │
    ▼
hooks.json (routes event to script)
    │
    ▼
permission.sh / notify.sh
    │
    ├─► lib.sh (Slack functions)
    │      │
    │      └─► common.sh (shared utilities)
    │
    ▼
Slack API (webhook)
    │
    ▼
Your Slack Channel
```

### PreToolUse Flow

```
1. Claude wants to use a tool (e.g., Bash)
2. PreToolUse hook fires with JSON input:
   {"tool_name": "Bash", "tool_input": {...}, "cwd": "/path"}
3. permission.sh processes input
4. Outputs {"decision": "allow"} immediately (so Claude doesn't wait)
5. Sends notification to Slack asynchronously
```

---

## Customization

### Change Notification Channel

Edit `~/.claude/config/slack-config.json`:
```json
{
    "webhook_url": "https://hooks.slack.com/services/NEW/WEBHOOK/URL",
    "enabled": true
}
```

### Customize Colors

Edit `hooks/slack/lib.sh`, function `get_tool_style()`:

```bash
get_tool_style() {
    local tool_name="$1"

    case "$tool_name" in
        Bash|bash)
            emoji="💻"
            ntype="Bash Command"
            color="#E01E5A"  # Change this hex color
            ;;
        # Add more cases...
    esac
}
```

### Add New Tool Types

In `hooks/slack/lib.sh`, add to `get_tool_style()`:

```bash
        MyCustomTool)
            emoji="🎯"
            ntype="Custom Tool"
            color="#FF5733"
            ;;
```

### Customize Message Format

Edit `build_pretooluse_payload()` or `build_notification_payload()` in `hooks/slack/lib.sh`.

Example - add timestamp to header:
```bash
# In build_pretooluse_payload()
"text": "$emoji *$ntype* | \`$tool_name\` | $terminal_type | $timestamp"
```

### Filter Notifications

To skip notifications for certain tools, add to `permission.sh`:

```bash
# Skip read-only tools
case "$tool_name" in
    Read|Glob|Grep|LS)
        echo '{"decision": "allow"}'
        exit 0
        ;;
esac
```

---

## Troubleshooting

### No Notifications Received

1. **Check webhook URL:**
   ```bash
   cat ~/.claude/config/slack-config.json
   ```

2. **Test webhook directly:**
   ```bash
   curl -X POST -H 'Content-type: application/json' \
     --data '{"text":"Test from terminal"}' \
     YOUR_WEBHOOK_URL
   ```

3. **Check hooks.json:**
   ```bash
   cat ~/.claude/hooks.json
   ```
   Verify paths point to correct script locations.

4. **Enable debug logging:**
   ```bash
   DEBUG=1 ./hooks/slack/permission.sh << 'EOF'
   {"tool_name": "Test", "tool_input": {}, "cwd": "/tmp"}
   EOF

   cat ~/.claude/productivities-debug.log
   ```

### "decision" Not Output

The `PreToolUse` hook MUST output `{"decision": "allow"}` or `{"decision": "block"}`.

Check for errors:
```bash
./hooks/slack/permission.sh << 'EOF'
{"tool_name": "Test", "tool_input": {}, "cwd": "/tmp"}
EOF
```

Should output exactly: `{"decision": "allow"}`

### Wrong Terminal Detected

Check environment variables:
```bash
echo "TERM_PROGRAM: $TERM_PROGRAM"
echo "ITERM_SESSION_ID: $ITERM_SESSION_ID"
echo "TMUX: $TMUX"
echo "VSCODE_INJECTION: $VSCODE_INJECTION"
```

### Duplicate Notifications

Check `~/.claude/hooks.json` for duplicate entries:
```bash
cat ~/.claude/hooks.json | python3 -m json.tool
```

Remove any duplicate hook configurations.

---

## Advanced Usage

### Multiple Slack Channels

Create separate config files and scripts:

```bash
# For different projects
SLACK_CONFIG_FILE=~/.claude/config/slack-project-a.json ./hooks/slack/permission.sh
```

### Conditional Notifications

Modify `permission.sh` to check conditions:

```bash
# Only notify for specific projects
case "$project" in
    important-project|critical-app)
        # Send notification
        ;;
    *)
        # Skip notification, just allow
        echo '{"decision": "allow"}'
        exit 0
        ;;
esac
```

### Rate Limiting

Add to `hooks/slack/lib.sh`:

```bash
# Rate limit: max 1 notification per 5 seconds
RATE_LIMIT_FILE="/tmp/slack-rate-limit"
if [ -f "$RATE_LIMIT_FILE" ]; then
    last_send=$(cat "$RATE_LIMIT_FILE")
    now=$(date +%s)
    if [ $((now - last_send)) -lt 5 ]; then
        return 0  # Skip this notification
    fi
fi
echo $(date +%s) > "$RATE_LIMIT_FILE"
```

### Blocking Dangerous Commands

Modify `permission.sh` to block instead of allow:

```bash
# Block dangerous commands
if echo "$tool_input" | grep -qE "rm -rf|sudo|chmod 777"; then
    echo '{"decision": "block", "reason": "Dangerous command blocked"}'
    # Send alert to Slack
    exit 0
fi
```

### Integration with Other Services

The `send_to_slack()` function can be adapted for other webhooks:

```bash
# Discord webhook
send_to_discord() {
    local message="$1"
    curl -H "Content-Type: application/json" \
         -d "{\"content\": \"$message\"}" \
         "$DISCORD_WEBHOOK"
}
```

---

## FAQ

### Q: Will this slow down Claude Code?

**A:** No. The `PreToolUse` hook outputs the decision immediately, then sends the Slack notification. Claude doesn't wait for Slack.

### Q: Can I use this with project-level hooks?

**A:** Yes. Copy the hooks to your project's `.claude/hooks/` directory and update `.claude/hooks.json` with project-specific paths.

### Q: How do I temporarily disable notifications?

**A:** Either:
1. Set `"enabled": false` in `slack-config.json`
2. Rename `~/.claude/hooks.json` temporarily
3. Comment out the webhook URL

### Q: Can I get notifications on mobile?

**A:** Yes! Slack mobile app will receive notifications. Make sure Slack notifications are enabled on your phone.

### Q: How do I update the hooks?

**A:**
```bash
cd /path/to/claude-code-plugins-productivities
git pull
```

No reinstall needed - hooks.json points to the repo scripts.

### Q: Can multiple Macs share the same config?

**A:** The scripts can be shared via git, but `~/.claude/config/slack-config.json` (containing the webhook URL) should be created locally on each machine via the installer.

---

## Support

- **Issues:** [GitHub Issues](https://github.com/DukeWood/claude-code-plugins-productivities/issues)
- **Claude Code Docs:** [claude.ai/code](https://claude.ai/code)
