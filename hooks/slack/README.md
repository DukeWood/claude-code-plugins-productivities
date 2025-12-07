# Slack Notification Hooks for Claude Code

Get notified in Slack when Claude Code needs your attention or completes tasks.

## Features

**Permission Notifications** 🔐
- Know when Claude is waiting for approval (Edit, Bash, WebFetch, etc.)
- See which terminal/tmux session needs attention
- One-click command to switch to the right terminal

**Task Completion Notifications** ✅
- Get notified when long-running tasks finish (especially in tmux)
- See git status, token usage, and task summary
- Work on other things while Claude works in background

## Architecture

This project has two implementations:

| Feature | V1 (Shell) | V2 (Python) |
|---------|------------|-------------|
| Storage | JSON files | SQLite with WAL |
| Retry | None | Exponential backoff |
| Encryption | None | Fernet (AES-128) |
| Queue | Synchronous | Async with dead-letter |
| Tests | Manual | 210 automated tests |

**V1** is production-ready and currently active.
**V2** is feature-complete with full test coverage (210 tests passing).

## Quick Start

### 1. Install

```bash
cd /Users/Jason-uk/AI/AI_Coding/Repositories/claude-code-plugins-productivities/hooks/slack
./setup.sh
```

The setup script will:
- Create config directory
- Prompt for your Slack webhook URL
- Register hooks in `~/.claude/settings.json`
- Run test notifications

### 2. Get Slack Webhook URL

1. Go to https://api.slack.com/messaging/webhooks
2. Create a new webhook for your workspace
3. Copy the webhook URL (looks like `https://hooks.slack.com/services/...`)
4. Paste it when `setup.sh` prompts you

### 3. Test

Start a Claude Code session in tmux:

```bash
tmux new-session -s test
claude code
```

Try a command that needs permission:
```
User: Edit /tmp/test.txt and add "hello world"
```

You should get a Slack notification!

## Configuration

Edit `~/.claude/config/slack-config.json`:

```json
{
  "webhook_url": "https://hooks.slack.com/services/YOUR/WEBHOOK/URL",
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": false
}
```

**Settings:**
- `enabled`: Master on/off switch
- `notify_on.permission_required`: Alert when Claude needs permission
- `notify_on.task_complete`: Alert when session ends
- `notify_on.input_required`: Alert when Claude asks questions
- `notify_always`: If `true`, send Stop notifications even outside tmux

## Example Notifications

### Permission Required
```
🔐 Permission Required

`5f73` | torly-wordpress-setup | tmux `0:0.0` | `feat/auth` | 7:05 PM

────────────────────────────────

Edit Permission
📄 File: auth.ts
📁 Path: .../project/src

Quick Action: `tmux switch-client -t 0:0.0`
```

### Task Complete
```
✅ Task Complete

`5f73` | torly-wordpress-setup | tmux `0:0.0` | main | S:3 M:5 U:0 | 7:25 PM | 📊 45.2K in / 18.7K out

────────────────────────────────

Help me refactor the authentication system to use JWT instead of sessions

Quick Action: `tmux switch-client -t 0:0.0`
```

## File Structure

```
hooks/slack/
├── notify-permission.sh   # V1: Notification hook (permission prompts)
├── notify-stop.sh         # V1: Stop hook (task completion)
├── setup.sh               # Setup wizard
├── hook.py                # V2: Unified Python entry point
├── lib/
│   ├── slack.sh           # V1: Slack API helpers
│   ├── enrichers.sh       # V1: Context enrichment (git, terminal, tokens)
│   ├── database.py        # V2: SQLite database layer
│   ├── notification_queue.py  # V2: Queue with retry logic
│   ├── encryption.py      # V2: Fernet credential encryption
│   ├── handlers.py        # V2: Hook event handlers
│   └── sender.py          # V2: Notification dispatcher
├── tests/                 # V2: Pytest test suite (210 tests)
│   ├── test_database.py
│   ├── test_notification_queue.py
│   ├── test_encryption.py
│   ├── test_handlers.py
│   └── test_sender.py
└── README.md

~/.claude/config/
├── slack-config.json      # Your configuration
└── settings.json          # Claude Code settings (hooks registered here)

~/.claude/state/
├── notifications.db       # V2: SQLite database
└── encryption.key         # V2: Fernet encryption key (0o600)

~/.claude/logs/
├── notify-permission-debug.log
└── notify-stop-debug.log
```

## Debugging

### Check if hooks are registered

```bash
cat ~/.claude/settings.json | jq '.hooks'
```

You should see `Notification` and `Stop` hooks pointing to the scripts.

### View debug logs

```bash
# Permission notifications
tail -f ~/.claude/logs/notify-permission-debug.log

# Task completion notifications
tail -f ~/.claude/logs/notify-stop-debug.log
```

### Test hooks manually

```bash
# Test permission notification
echo '{"hook_event_name":"Notification","notification_type":"permission_prompt","tool_name":"Edit","tool_input":{"file_path":"/tmp/test.txt"},"session_id":"test-123","cwd":"'$PWD'"}' | ./notify-permission.sh

# Test stop notification
echo '{"hook_event_name":"Stop","session_id":"test-123","cwd":"'$PWD'"}' | ./notify-stop.sh
```

### Check Slack config

```bash
cat ~/.claude/config/slack-config.json | jq .
```

### Test in minimal environment (like Claude Code runs it)

```bash
env -i HOME=$HOME PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
  ./notify-permission.sh <<< '{"hook_event_name":"Notification","notification_type":"permission_prompt","tool_name":"Bash","tool_input":{"command":"ls"},"session_id":"test","cwd":"'$PWD'"}'
```

## Troubleshooting

### No notifications received

1. **Check config:**
   ```bash
   cat ~/.claude/config/slack-config.json
   ```
   - Verify `enabled: true`
   - Verify `webhook_url` is correct

2. **Check hooks are registered:**
   ```bash
   cat ~/.claude/settings.json | jq '.hooks.Notification'
   cat ~/.claude/settings.json | jq '.hooks.Stop'
   ```

3. **Check debug logs:**
   ```bash
   tail -20 ~/.claude/logs/notify-permission-debug.log
   tail -20 ~/.claude/logs/notify-stop-debug.log
   ```

4. **Test webhook URL manually:**
   ```bash
   curl -X POST "YOUR_WEBHOOK_URL" \
     -H 'Content-Type: application/json' \
     -d '{"text":"Test from command line"}'
   ```

### Stop notifications not firing in tmux

Check if tmux is detected:
```bash
source ./lib/enrichers.sh
detect_tmux
```

Should output `true` if in tmux.

If it outputs `false`, set `notify_always: true` in config:
```bash
cat > ~/.claude/config/slack-config.json <<EOF
{
  "webhook_url": "YOUR_URL",
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": true
}
EOF
```

### Hook errors in Claude Code

Check for `hook error` messages in Claude Code output.

Common causes:
1. **PATH not set** - Check line 2 of hook scripts has `export PATH=...`
2. **Script not executable** - Run `chmod +x hooks/slack/*.sh`
3. **Missing dependencies** - Ensure `jq`, `curl`, `python3` are installed

Test with minimal environment:
```bash
env -i HOME=$HOME ./notify-permission.sh <<< '{}'
```

## Disable Notifications

### Temporarily disable

Edit `~/.claude/config/slack-config.json`:
```json
{
  "enabled": false
}
```

### Permanently remove

Edit `~/.claude/settings.json` and remove the `Notification` and `Stop` hook entries.

## Advanced Usage

### Only notify for specific tools

Edit `notify-permission.sh` and add filtering:

```bash
# Only notify for Bash and WebFetch
if [ "$TOOL_NAME" != "Bash" ] && [ "$TOOL_NAME" != "WebFetch" ]; then
  exit 0
fi
```

### Custom notification format

Edit the `SLACK_PAYLOAD` section in `notify-permission.sh` or `notify-stop.sh` to customize the Slack message format.

See: https://api.slack.com/block-kit

### Send to multiple channels

Create multiple webhook URLs in Slack, then modify `send_slack_notification` in `lib/slack.sh`:

```bash
send_slack_notification() {
  local payload="$2"

  curl -X POST "https://hooks.slack.com/services/AAA/BBB/CCC" -d "$payload" &
  curl -X POST "https://hooks.slack.com/services/XXX/YYY/ZZZ" -d "$payload" &
}
```

## Performance

**Hook execution time:** ~20-30ms (does not block Claude Code)

The webhook call runs in background (`&`), so Claude Code never waits for Slack's response.

**Breakdown:**
- Read stdin: 1ms
- Parse JSON: 5ms
- Gather context (git, terminal): 10-20ms
- Send webhook (async): 0ms (background)

## Security

**V1 (Shell):**
- Webhook URL stored in plaintext in `~/.claude/config/slack-config.json`
- Consider using file permissions: `chmod 600 ~/.claude/config/slack-config.json`

**V2 (Python):**
- Webhook URL encrypted with Fernet (AES-128-CBC with HMAC)
- Encryption key stored at `~/.claude/state/encryption.key` with 0o600 permissions
- Automatic secure key generation on first use

**Both:**
- Tool payloads may contain sensitive data (file paths, commands)
- Logs contain full payloads - rotate regularly or disable debug logging

## V2 Features

V2 is a complete rewrite with these improvements:

### SQLite Database
- WAL mode for concurrent access
- Session tracking with lifecycle management
- Audit logging for all operations
- Metrics recording for analytics

### Notification Queue
- Persistent queue survives process restarts
- Exponential backoff retry (1min → 5min → 15min → 1hr → 4hr)
- Dead-letter queue after 5 failed attempts
- Batch processing for efficiency

### Credential Encryption
- Fernet symmetric encryption (AES-128-CBC + HMAC-SHA256)
- Automatic key generation with secure permissions
- Key rotation support without data loss
- Encrypted value detection

### Running V2 Tests

```bash
cd hooks/slack

# Install test dependencies
pip install -r requirements-test.txt

# Run all tests
python3 -m pytest tests/ -v

# Run specific test file
python3 -m pytest tests/test_database.py -v

# Run with coverage
python3 -m pytest tests/ --cov=lib --cov-report=term-missing
```

**Test Coverage:** 210 tests covering database, queue, encryption, handlers, and sender.

## Future Enhancements

- Interactive approval from Slack (approve/deny buttons)
- Multiple backend support (Discord, email, webhooks)
- Web dashboard for metrics and queue monitoring
- Rate limiting and notification deduplication

## Support

File issues at: https://github.com/DukeWood/claude-code-plugins-productivities/issues

## License

MIT
