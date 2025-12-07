# Notification Sender & Dispatcher (V2)

## Overview

The notification sender is the core component of the Slack Notification V2 system. It handles:

- **Building Slack Block Kit payloads** for different notification types
- **Validating webhook URLs** for security (SSRF protection)
- **Sending notifications** via HTTP webhook with retry logic
- **Processing the notification queue** with configurable batch size
- **Updating notification status** in the database

## Architecture

### Design Principles

1. **Pure functions for payload building** - Easy to test, no side effects
2. **Database connection as parameter** - No global state, testable
3. **Graceful error handling** - Detailed error messages, never crash
4. **Security-first** - Webhook URL validation prevents SSRF attacks

### Components

```
sender.py
├── Validation
│   ├── validate_webhook_url()       # HTTPS + domain whitelist
│   └── ALLOWED_WEBHOOK_DOMAINS      # Slack, Discord, Zapier
│
├── Payload Builders
│   ├── build_permission_payload()   # Permission requests
│   ├── build_stop_payload()         # Task completion
│   ├── build_idle_payload()         # Waiting for input
│   ├── _format_tool_details()       # Tool-specific formatting
│   └── _format_git_summary()        # Git status formatting
│
├── Sending
│   ├── send_notification()          # Send single notification
│   ├── _update_notification_sent()  # Mark as sent
│   └── _update_notification_failed()# Mark as failed + retry
│
└── Queue Processing
    ├── process_queue()              # Process batch of notifications
    └── run_dispatcher()             # Daemon mode (continuous loop)
```

## Security Features

### Webhook URL Validation

All webhook URLs are validated before sending to prevent SSRF (Server-Side Request Forgery) attacks:

```python
# Only HTTPS allowed
validate_webhook_url("http://hooks.slack.com/...")  # ❌ Rejected

# Only whitelisted domains allowed
validate_webhook_url("https://evil.com/webhook")    # ❌ Rejected
validate_webhook_url("https://hooks.slack.com/...")  # ✅ Allowed

# Internal IPs rejected
validate_webhook_url("https://192.168.1.1/webhook") # ❌ Rejected
validate_webhook_url("https://localhost/webhook")   # ❌ Rejected
```

### Allowed Domains

- `hooks.slack.com` - Slack webhooks
- `discord.com` - Discord webhooks
- `hooks.zapier.com` - Zapier webhooks

To add more domains, edit `ALLOWED_WEBHOOK_DOMAINS` in `sender.py`.

## Usage

### 1. Send Single Notification

```python
import sqlite3
from sender import send_notification

# Connect to database
db = sqlite3.connect("~/.claude/state/notifications.db")
db.row_factory = sqlite3.Row

# Send notification by ID
success = send_notification(db, notification_id=123)

if success:
    print("Notification sent successfully")
else:
    print("Notification failed (will retry)")
```

### 2. Process Queue (Batch)

```python
from sender import process_queue

# Process up to 10 pending notifications
processed = process_queue(db, batch_size=10, max_retries=3)

print(f"Processed {processed} notifications")
```

### 3. Run as Daemon

```bash
# Run dispatcher every 60 seconds
python3 sender.py --daemon 60

# Run dispatcher every 30 seconds (lower latency)
python3 sender.py --daemon 30
```

### 4. Run Once (Cron Mode)

```bash
# Process queue once (for cron jobs)
python3 sender.py --once
```

Add to crontab for periodic processing:

```cron
# Process queue every minute
*/1 * * * * cd /path/to/hooks/slack && python3 lib/sender.py --once >> /tmp/dispatcher.log 2>&1
```

## Payload Structure

### Permission Request

```json
{
  "text": "my-project: Edit permission required",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "🔔 my-project: Permission Required"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Edit Permission*\n📄 File: `app.ts`\n📁 Path: `/Users/test/project/src`"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "```tmux select-window -t main:0```"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "main | S:2 M:1 U:0 | tmux | #1234"
        }
      ]
    }
  ]
}
```

### Task Complete

```json
{
  "text": "my-project: Task complete",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "✅ my-project: Task Complete"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "*Task:* Fix authentication bug\n*Tokens:* 15.2K in / 8.5K out\n*Git:* main | S:3 M:2 U:1"
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "tmux | #1234"
        }
      ]
    }
  ]
}
```

### Idle Prompt

```json
{
  "text": "my-project: Waiting for input",
  "blocks": [
    {
      "type": "header",
      "text": {
        "type": "plain_text",
        "text": "⏸️ my-project: Waiting for Input"
      }
    },
    {
      "type": "section",
      "text": {
        "type": "mrkdwn",
        "text": "Claude is waiting for your response."
      }
    },
    {
      "type": "context",
      "elements": [
        {
          "type": "mrkdwn",
          "text": "tmux | #1234"
        }
      ]
    }
  ]
}
```

## Error Handling

### Retry Logic

Failed notifications are automatically retried up to 3 times:

1. **First attempt** - Send immediately
2. **Retry 1** - Next queue processing cycle
3. **Retry 2** - Next queue processing cycle
4. **Retry 3** - Next queue processing cycle
5. **After 3 failures** - Notification marked as permanently failed

### Error Messages

All errors are captured in the `notifications.error` column:

```sql
-- View failed notifications with errors
SELECT id, notification_type, retry_count, error
FROM notifications
WHERE status = 'failed'
ORDER BY created_at DESC;
```

Common errors:

- `HTTP 500: Internal Server Error` - Slack webhook error
- `Connection timeout` - Network timeout (10s)
- `Invalid webhook URL: Domain 'evil.com' not allowed` - Security validation failed
- `Request failed: ...` - Network error

## Testing

### Run Unit Tests

```bash
cd hooks/slack
python3 -m pytest tests/test_sender.py -v
```

### Run Specific Test

```bash
# Test webhook validation
python3 -m pytest tests/test_sender.py::TestWebhookValidation -v

# Test permission payloads
python3 -m pytest tests/test_sender.py::TestPermissionPayload -v

# Test notification sending
python3 -m pytest tests/test_sender.py::TestSendNotification -v
```

### Test Coverage

```bash
python3 -m pytest tests/test_sender.py --cov=lib.sender --cov-report=html
open htmlcov/index.html
```

## Performance

### Benchmarks (Expected)

| Metric | Target | Notes |
|--------|--------|-------|
| Webhook send time | <500ms | Network dependent |
| Payload build time | <10ms | Pure function, fast |
| Queue processing (10 notifs) | <5s | Parallel sends possible |
| Database query time | <50ms | Indexed queries |

### Optimization Tips

1. **Increase batch size** for high-volume scenarios:
   ```python
   process_queue(db, batch_size=100)
   ```

2. **Reduce daemon interval** for lower latency:
   ```bash
   python3 sender.py --daemon 15  # Check every 15s
   ```

3. **Use connection pooling** for daemon mode (future enhancement)

## Debugging

### Enable Debug Logging

```python
import logging

logging.basicConfig(level=logging.DEBUG)
```

### Check Notification Status

```bash
# Check pending notifications
sqlite3 ~/.claude/state/notifications.db \
  "SELECT * FROM notifications WHERE status='pending'"

# Check failed notifications
sqlite3 ~/.claude/state/notifications.db \
  "SELECT * FROM notifications WHERE status='failed' ORDER BY created_at DESC LIMIT 10"

# Check sent notifications (last hour)
sqlite3 ~/.claude/state/notifications.db \
  "SELECT * FROM notifications WHERE status='sent' AND sent_at > strftime('%s', 'now', '-1 hour')"
```

### Manual Retry

```python
from sender import send_notification
import sqlite3

db = sqlite3.connect("~/.claude/state/notifications.db")
db.row_factory = sqlite3.Row

# Retry failed notification
send_notification(db, notification_id=123)
```

## Tool-Specific Formatting

### Edit Tool

Shows file path and directory:

```
*Edit Permission*
📄 File: `app.ts`
📁 Path: `/Users/test/project/src`
```

### Bash Tool

Shows command (truncated if >100 chars):

```
*Bash Permission*
💻 Command: `npm install express`
```

### WebFetch Tool

Shows URL:

```
*Web Access Permission*
🌐 URL: https://api.github.com/repos/user/repo
```

### Task Tool

Shows subagent type and task description:

```
*Agent Task Permission*
🤖 Agent: coder
📋 Task: Fix authentication bug
```

### Write/Read Tools

Shows filename:

```
*Write Permission*
📄 File: `config.json`
```

## Integration

### With Event Queue

The sender integrates with the event queue system:

```
1. Hook fires → Event inserted into `events` table
2. Dispatcher creates notification → Inserted into `notifications` table
3. process_queue() sends notification → Updates status to 'sent'
4. On failure → Increments retry_count, marks as 'failed'
5. Next cycle → Retries failed notifications (if retry_count < 3)
```

### With Config System

Webhook URL is loaded from `config` table:

```sql
SELECT value FROM config WHERE key = 'slack_webhook_url'
```

Future: Support encrypted webhook URLs:

```sql
SELECT value, is_encrypted FROM config WHERE key = 'slack_webhook_url'
```

## Future Enhancements

### P1: High Priority

- [ ] **Parallel webhook sends** - Use `asyncio` or `threading` for faster batch processing
- [ ] **Encrypted webhook URLs** - Store webhook URLs encrypted in database
- [ ] **Discord backend** - Support Discord webhooks (already whitelisted)
- [ ] **Email backend** - Send critical notifications via email
- [ ] **Metric recording** - Track latency, success rate in `metrics` table

### P2: Nice-to-Have

- [ ] **Exponential backoff** - Wait longer between retries (30s, 60s, 120s)
- [ ] **Dead letter queue** - Move permanently failed notifications to separate table
- [ ] **Webhook response validation** - Parse Slack response for specific errors
- [ ] **Rate limiting** - Respect Slack's rate limits (1 msg/sec)
- [ ] **Payload compression** - Compress large payloads before sending

### P3: Experimental

- [ ] **Interactive buttons** - Add Slack buttons for approve/deny
- [ ] **Thread support** - Reply to previous notification threads
- [ ] **Rich previews** - Include code diff preview in notification
- [ ] **Multi-webhook support** - Send to multiple webhooks (Slack + Discord)

## Dependencies

Required Python packages:

```
requests>=2.31.0    # HTTP client for webhooks
```

For testing:

```
pytest>=7.4.0
pytest-cov>=4.1.0
responses>=0.23.0   # Mock HTTP responses
freezegun>=1.2.0    # Mock time
```

Install:

```bash
pip3 install -r requirements-test.txt
```

## Contributing

### Adding a New Notification Type

1. **Create payload builder function**:
   ```python
   def build_error_payload(event_data, context):
       # Build Slack Block Kit payload
       return {"text": "...", "blocks": [...]}
   ```

2. **Add tests** in `tests/test_sender.py`:
   ```python
   class TestErrorPayload:
       def test_basic_error_payload(self):
           payload = build_error_payload(...)
           assert "blocks" in payload
   ```

3. **Update dispatcher** to call your new builder

### Adding a New Backend

1. **Add domain to whitelist**:
   ```python
   ALLOWED_WEBHOOK_DOMAINS = [
       'hooks.slack.com',
       'discord.com',
       'hooks.zapier.com',
       'new-service.com'  # Add here
   ]
   ```

2. **Create backend-specific sender** (future):
   ```python
   def send_discord_notification(webhook_url, payload):
       # Convert Slack blocks to Discord embeds
       pass
   ```

## License

MIT License - See LICENSE file for details

## Support

For issues or questions:

1. Check debug logs: `~/.claude/logs/hooks.jsonl`
2. Query database: `sqlite3 ~/.claude/state/notifications.db`
3. Run tests: `pytest tests/test_sender.py -v`
4. Open GitHub issue with error details
