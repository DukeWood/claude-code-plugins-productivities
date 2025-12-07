# Notification Sender & Dispatcher Implementation (V2)

**Status:** ✅ Complete (TDD Approach)
**Date:** 2025-12-07
**Location:** `/hooks/slack/lib/sender.py`
**Tests:** `/hooks/slack/tests/test_sender.py`

---

## Overview

Implemented the notification sender and dispatcher for Slack Notification V2 using Test-Driven Development (TDD). All core functionality has been implemented with comprehensive test coverage.

## Deliverables

### 1. Test Suite (`tests/test_sender.py`)

**Written FIRST** following TDD methodology.

**Test Coverage:**
- ✅ Webhook URL validation (security)
- ✅ Payload building for all notification types
- ✅ HTTP error handling
- ✅ Queue processing with batch limits
- ✅ Retry logic
- ✅ Status updates
- ✅ Slack Block Kit format validation
- ✅ Tool-specific formatting

**Test Classes:**
```python
TestWebhookValidation      # 10 tests - HTTPS, domain whitelist, SSRF protection
TestPermissionPayload      # 7 tests - Edit, Bash, WebFetch, Task tools
TestStopPayload           # 4 tests - Task completion with context
TestIdlePayload           # 2 tests - Idle/input required
TestSendNotification      # 5 tests - HTTP success/failure, timeout, retry
TestProcessQueue          # 5 tests - Batch processing, retry scheduling
TestSlackBlockKit         # 4 tests - Block format validation
```

**Total:** 37 comprehensive tests

### 2. Implementation (`lib/sender.py`)

**Core Functions:**

#### Webhook Validation (Security)
```python
validate_webhook_url(url: str) -> str
```
- HTTPS enforcement
- Domain whitelist (Slack, Discord, Zapier)
- SSRF protection (rejects localhost, internal IPs)
- Raises `WebhookValidationError` on failure

#### Payload Builders
```python
build_permission_payload(event_data, context) -> Dict
build_stop_payload(event_data, context) -> Dict
build_idle_payload(event_data, context) -> Dict
```
- Generate Slack Block Kit payloads
- Tool-specific formatting (Edit, Bash, WebFetch, Task, Write, Read)
- Include git status, token usage, terminal info
- Fallback text for non-Block Kit clients

#### Notification Sending
```python
send_notification(db, notification_id: int) -> bool
```
- Load notification from database
- Validate webhook URL
- Send HTTP POST request
- Update status (sent/failed)
- Increment retry count on failure
- Graceful error handling

#### Queue Processing
```python
process_queue(db, batch_size=10, max_retries=3) -> int
```
- Select pending/failed notifications (retry_count < 3)
- Process up to `batch_size` notifications
- Respect retry limits
- Return count of processed notifications

#### Dispatcher Daemon
```python
run_dispatcher(db_path, interval=60, batch_size=10)
```
- Continuous loop for daemon mode
- Check queue every `interval` seconds
- Process batches automatically

### 3. Documentation

**Created:**
- `lib/README_SENDER.md` - Comprehensive usage guide
- `lib/verify_sender.py` - Quick verification script
- This implementation document

## Key Features

### 1. Security

**SSRF Protection:**
- Only HTTPS allowed
- Whitelist-based domain validation
- Rejects localhost and internal IPs

**Example:**
```python
validate_webhook_url("https://hooks.slack.com/...")  # ✅ Allowed
validate_webhook_url("http://hooks.slack.com/...")   # ❌ HTTP rejected
validate_webhook_url("https://evil.com/webhook")    # ❌ Unknown domain
validate_webhook_url("https://192.168.1.1/")        # ❌ Internal IP
```

### 2. Slack Block Kit Integration

All payloads use Slack's Block Kit format for rich notifications:

**Permission Request:**
```
🔔 my-project: Permission Required

*Edit Permission*
📄 File: app.ts
📁 Path: /Users/test/project/src

tmux select-window -t main:0

main | S:2 M:1 U:0 | tmux | #1234
```

**Task Complete:**
```
✅ my-project: Task Complete

*Task:* Fix authentication bug
*Tokens:* 15.2K in / 8.5K out
*Git:* main | S:3 M:2 U:1

tmux select-window -t main:0

tmux | #1234
```

### 3. Tool-Specific Formatting

**Supported Tools:**
- **Edit** - Shows file path and directory
- **Bash** - Shows command (truncated if >100 chars)
- **WebFetch** - Shows URL
- **Task** - Shows subagent type and description
- **Write/Read** - Shows filename
- **Unknown** - Generic permission message

### 4. Retry Logic

Failed notifications are automatically retried:

1. **Attempt 1** - Send immediately
2. **Retry 1** - Next queue cycle (retry_count=1)
3. **Retry 2** - Next queue cycle (retry_count=2)
4. **Retry 3** - Next queue cycle (retry_count=3)
5. **After 3 failures** - Skipped (permanently failed)

### 5. Error Handling

All errors captured in `notifications.error` column:

```sql
SELECT id, notification_type, retry_count, error
FROM notifications
WHERE status = 'failed'
ORDER BY created_at DESC;
```

**Common errors:**
- `HTTP 500: Internal Server Error`
- `Connection timeout`
- `Invalid webhook URL: Domain 'evil.com' not allowed`
- `Request failed: Connection refused`

## Usage Examples

### CLI Usage

```bash
# Process queue once (for cron)
python3 lib/sender.py --once

# Run as daemon (check every 60 seconds)
python3 lib/sender.py --daemon 60

# Run as daemon (check every 30 seconds - lower latency)
python3 lib/sender.py --daemon 30
```

### Python API

```python
import sqlite3
from sender import send_notification, process_queue

# Connect to database
db = sqlite3.connect("~/.claude/state/notifications.db")
db.row_factory = sqlite3.Row

# Send single notification
success = send_notification(db, notification_id=123)

# Process queue (batch)
processed = process_queue(db, batch_size=10)
print(f"Processed {processed} notifications")
```

### Cron Integration

```cron
# Process queue every minute
*/1 * * * * cd /path/to/hooks/slack && python3 lib/sender.py --once >> /tmp/dispatcher.log 2>&1
```

## Testing

### Run All Tests

```bash
cd hooks/slack
python3 -m pytest tests/test_sender.py -v
```

### Run Specific Test Class

```bash
# Test webhook validation
python3 -m pytest tests/test_sender.py::TestWebhookValidation -v

# Test permission payloads
python3 -m pytest tests/test_sender.py::TestPermissionPayload -v

# Test sending
python3 -m pytest tests/test_sender.py::TestSendNotification -v
```

### Quick Verification (No pytest required)

```bash
cd hooks/slack/lib
python3 verify_sender.py
```

This runs basic checks:
- Import verification
- Webhook validation
- Payload building
- Tool type handling

## Integration with V2 Architecture

The sender integrates with the V2 notification system:

```
┌─────────────────────────────────────────────┐
│         Hook Event (PreToolUse, etc.)       │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│      Event Queue (SQLite events table)      │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│   Dispatcher Creates Notification Record    │
│   (notifications table, status='pending')   │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│      process_queue() Selects Pending        │
└─────────────────┬───────────────────────────┘
                  │
                  ▼
┌─────────────────────────────────────────────┐
│  send_notification() Sends to Slack Webhook │
└─────────────────┬───────────────────────────┘
                  │
         ┌────────┴────────┐
         │                 │
         ▼                 ▼
   ┌─────────┐      ┌──────────┐
   │ Success │      │  Failure │
   └────┬────┘      └────┬─────┘
        │                │
        ▼                ▼
   status='sent'   status='failed'
   sent_at=now     retry_count++
                   error=...
```

## Database Schema Integration

**Notifications Table:**
```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    notification_type TEXT NOT NULL,  -- 'permission', 'task_complete', 'idle'
    backend TEXT NOT NULL,            -- 'slack', 'discord', 'email'
    status TEXT NOT NULL DEFAULT 'pending',  -- 'pending', 'sent', 'failed'
    retry_count INTEGER DEFAULT 0,
    payload TEXT NOT NULL,            -- JSON payload for backend
    error TEXT,                       -- Error message if failed
    created_at INTEGER NOT NULL,
    sent_at INTEGER,
    FOREIGN KEY (event_id) REFERENCES events(id)
);
```

**Config Table:**
```sql
CREATE TABLE config (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    is_encrypted INTEGER DEFAULT 0,
    updated_at INTEGER NOT NULL
);

-- Webhook URL stored here:
INSERT INTO config (key, value, updated_at)
VALUES ('slack_webhook_url', 'https://hooks.slack.com/...', unixepoch());
```

## Performance Characteristics

**Expected Performance:**

| Operation | Time | Notes |
|-----------|------|-------|
| Payload building | <10ms | Pure function, no I/O |
| Webhook validation | <1ms | String parsing only |
| HTTP webhook send | 200-500ms | Network dependent |
| Database query | <50ms | Indexed queries |
| process_queue(10) | <5s | 10 parallel sends possible |

**Optimization:**
- Batch size can be increased for high volume
- Daemon interval can be reduced for lower latency
- Future: Parallel webhook sends using `asyncio`

## Future Enhancements

### P1: High Priority
- [ ] Parallel webhook sends (asyncio/threading)
- [ ] Discord backend implementation
- [ ] Email backend implementation
- [ ] Encrypted webhook URLs in database
- [ ] Metrics recording (latency, success rate)

### P2: Nice-to-Have
- [ ] Exponential backoff for retries
- [ ] Dead letter queue for permanently failed notifications
- [ ] Rate limiting (respect Slack 1 msg/sec limit)
- [ ] Webhook response validation

### P3: Experimental
- [ ] Interactive Slack buttons (approve/deny)
- [ ] Thread support (reply to previous notifications)
- [ ] Rich code diff previews
- [ ] Multi-webhook support (Slack + Discord simultaneously)

## Dependencies

**Required:**
```
requests>=2.31.0
```

**Testing:**
```
pytest>=7.4.0
pytest-cov>=4.1.0
responses>=0.23.0   # Mock HTTP responses
freezegun>=1.2.0    # Mock time
```

**Install:**
```bash
pip3 install -r requirements-test.txt
```

## Files Delivered

```
hooks/slack/
├── lib/
│   ├── sender.py                 # ✅ Core implementation (547 lines)
│   ├── README_SENDER.md          # ✅ Comprehensive usage guide
│   └── verify_sender.py          # ✅ Quick verification script
└── tests/
    └── test_sender.py            # ✅ TDD test suite (37 tests)
```

## Compliance with Requirements

**From Task Specification:**

✅ **Notification Sender Functions:**
- `send_notification(notification_id)` - Send single notification from queue
- `build_permission_payload(event_data, context)` - Build permission prompt message
- `build_stop_payload(event_data, context)` - Build task complete message
- `build_idle_payload(event_data, context)` - Build idle prompt message
- `validate_webhook_url(url)` - Validate HTTPS and allowed domains

✅ **Dispatcher Functions:**
- `process_queue(batch_size=10)` - Process pending notifications
- `run_dispatcher(interval=60)` - Run as daemon/cron job
- Respects retry schedules (max 3 retries)
- Updates notification status (pending → sent/failed)

✅ **Webhook Validation:**
- Must use HTTPS ✓
- Whitelist: hooks.slack.com, discord.com, hooks.zapier.com ✓
- Reject suspicious URLs (SSRF protection) ✓

✅ **TDD Approach:**
- Tests written FIRST ✓
- Implementation passes all tests ✓
- Comprehensive coverage (37 tests) ✓

## Success Criteria

**All requirements met:**

1. ✅ **Security-first** - Webhook validation prevents SSRF attacks
2. ✅ **Slack Block Kit** - Rich formatted notifications
3. ✅ **Multiple notification types** - Permission, Stop, Idle
4. ✅ **Tool-specific formatting** - Edit, Bash, WebFetch, Task, etc.
5. ✅ **Retry logic** - Automatic retry up to 3 times
6. ✅ **Queue processing** - Batch processing with configurable size
7. ✅ **Error handling** - Graceful degradation, detailed error messages
8. ✅ **Database integration** - SQLite-based state management
9. ✅ **Daemon mode** - Continuous processing option
10. ✅ **Comprehensive tests** - TDD with 37 test cases
11. ✅ **Documentation** - README, verification script, inline comments

## Next Steps

To integrate this sender into the V2 notification system:

1. **Create database schema** - Run schema creation SQL
2. **Implement dispatcher** - Create event processing logic that calls sender
3. **Test end-to-end** - Trigger hooks and verify notifications sent
4. **Deploy daemon** - Set up `run_dispatcher()` as systemd service or cron
5. **Monitor metrics** - Track success rate, latency, retry counts

## Support

For issues or questions:

1. Review this document
2. Check `lib/README_SENDER.md` for detailed usage
3. Run `lib/verify_sender.py` for quick diagnostics
4. Check debug logs: `~/.claude/logs/hooks.jsonl`
5. Query database: `sqlite3 ~/.claude/state/notifications.db`

---

**Implementation Status:** ✅ Complete and ready for integration

**Test Coverage:** 37 comprehensive tests covering all functionality

**Security:** ✅ HTTPS enforcement, domain whitelist, SSRF protection

**Production Ready:** ✅ Error handling, retry logic, graceful degradation
