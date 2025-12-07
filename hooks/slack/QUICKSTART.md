# Quick Start: Get Notified When Claude Needs Permission

## You're 3 Steps Away From Async Claude Code

### Step 1: Get Your Slack Webhook URL (2 minutes)

1. Go to https://api.slack.com/messaging/webhooks
2. Click "Create your Slack app"
3. Choose "From scratch"
4. Name it "Claude Code" and select your workspace
5. Click "Incoming Webhooks" → Enable it
6. Click "Add New Webhook to Workspace"
7. Choose a channel (e.g., #claude-notifications or DM yourself)
8. Copy the webhook URL (looks like `https://hooks.slack.com/services/T.../B.../...`)

### Step 2: Run Setup Script (1 minute)

```bash
cd /Users/Jason-uk/AI/AI_Coding/Repositories/claude-code-plugins-productivities/hooks/slack
./setup.sh
```

When prompted, paste your webhook URL from Step 1.

The script will:
- Create config file
- Register hooks in Claude Code
- Send test notifications to Slack

### Step 3: Test It (30 seconds)

Start a Claude session in tmux:
```bash
tmux new-session -s test
claude code
```

Ask Claude to edit a file:
```
User: Create a file /tmp/hello.txt with "hello world"
```

**You should get a Slack notification!** 🎉

```
🔐 Permission Required

Write Permission
📄 File: hello.txt
📁 Path: /tmp

Quick Action: `tmux switch-client -t 0:0.0`
```

## What You Get

### Permission Notifications
- Know when Claude is waiting for approval
- See which terminal/tmux pane needs attention
- Quick command to switch to the right session

### Task Completion Notifications
- Get notified when long-running tasks finish
- See git status, token usage, task summary
- Work on other things while Claude works in background

## Example Workflow

**Before (synchronous):**
```
7:00 PM - You: "Refactor the auth system"
7:01 PM - You wait at terminal...
7:15 PM - Claude needs permission, you approve
7:16 PM - You wait at terminal...
7:30 PM - Task done
```

**After (async):**
```
7:00 PM - You: "Refactor the auth system"
7:01 PM - You switch to browser to research
7:15 PM - Slack: "🔐 Permission Required | tmux 0:0.0"
7:16 PM - You switch to tmux, approve, back to browser
7:30 PM - Slack: "✅ Task Complete | Modified 8 files"
7:35 PM - You review changes when convenient
```

## Configuration

Edit `~/.claude/config/slack-config.json`:

```json
{
  "webhook_url": "YOUR_URL",
  "enabled": true,
  "notify_on": {
    "permission_required": true,  // Alert when Claude needs approval
    "task_complete": true,         // Alert when session ends
    "input_required": true         // Alert when Claude asks questions
  },
  "notify_always": false           // If true, notify even outside tmux
}
```

## Troubleshooting

### No notifications?

1. **Check config exists:**
   ```bash
   cat ~/.claude/config/slack-config.json
   ```

2. **Test webhook manually:**
   ```bash
   curl -X POST "YOUR_WEBHOOK_URL" \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test message"}'
   ```

3. **Check debug logs:**
   ```bash
   tail ~/.claude/logs/notify-permission-debug.log
   ```

### Stop notifications not firing?

The Stop hook only fires in tmux by default. To get notifications outside tmux:

```bash
# Edit config
nano ~/.claude/config/slack-config.json

# Set notify_always to true:
{
  "notify_always": true
}
```

## What's Next?

Read the full docs: `/Users/Jason-uk/AI/AI_Coding/Repositories/claude-code-plugins-productivities/hooks/slack/README.md`

Or explore advanced features in the PRD:
- SQLite-based V2 architecture with retry queue
- Multiple notification backends (Discord, email)
- Interactive approval from Slack
- Metrics dashboard

See: `/Users/Jason-uk/AI/AI_Coding/Repositories/claude-code-plugins-productivities/docs/PRD_SLACK_NOTIFICATIONS_V2_OPTIMIZED.md`

## Support

Questions or issues? File at: https://github.com/DukeWood/claude-code-plugins-productivities/issues

---

**You're all set!** Start a Claude session and watch the magic happen. ✨
