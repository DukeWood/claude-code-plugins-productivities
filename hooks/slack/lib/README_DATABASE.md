# Database Layer - Slack Notification V2

## Overview

The database layer (`database.py`) provides a SQLite-based storage system for the Slack Notification V2 architecture. It replaces V1's scattered JSON files with a centralized, transactional database.

## Features

- **Event Queue**: Store raw hook payloads for async processing
- **Notification Tracking**: Track pending/sent/failed notifications with retry logic
- **Session Management**: Track active Claude Code sessions with metadata
- **Encrypted Config**: Store sensitive settings (webhook URLs) with encryption
- **Audit Logging**: Record all actions for debugging and compliance
- **Metrics**: Collect performance metrics for monitoring
- **Session Isolation**: Ensure sessions can't access each other's data
- **V1 Migration**: Import existing V1 JSON files

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                    database.py                          │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Events   │  │Notifications│ │Sessions  │            │
│  │ Queue    │  │  Tracker  │  │ Manager  │            │
│  └──────────┘  └──────────┘  └──────────┘            │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐            │
│  │ Config   │  │ Audit    │  │ Metrics  │            │
│  │ Storage  │  │ Log      │  │ Recorder │            │
│  └──────────┘  └──────────┘  └──────────┘            │
└─────────────────────────────────────────────────────────┘
                         │
                         ▼
              ┌──────────────────┐
              │   SQLite DB      │
              │ (WAL mode)       │
              └──────────────────┘
```

## Database Schema

### Tables

#### events
Stores raw hook event payloads for async processing.

```sql
CREATE TABLE events (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT NOT NULL,
  event_type TEXT NOT NULL,          -- 'pre_tool_use', 'notification', 'stop'
  hook_payload TEXT NOT NULL,        -- JSON payload
  created_at INTEGER NOT NULL,       -- Unix timestamp
  processed_at INTEGER               -- NULL until processed
);
```

#### notifications
Tracks notification delivery status with retry logic.

```sql
CREATE TABLE notifications (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  event_id INTEGER NOT NULL,
  session_id TEXT NOT NULL,
  notification_type TEXT NOT NULL,   -- 'permission', 'task_complete', etc.
  backend TEXT NOT NULL,             -- 'slack', 'discord', 'email'
  status TEXT NOT NULL DEFAULT 'pending', -- 'pending', 'sent', 'failed'
  retry_count INTEGER DEFAULT 0,
  payload TEXT NOT NULL,             -- Backend-specific JSON
  error TEXT,                        -- Error message if failed
  created_at INTEGER NOT NULL,
  sent_at INTEGER,
  FOREIGN KEY (event_id) REFERENCES events(id)
);
```

#### sessions
Tracks active Claude Code sessions with context.

```sql
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  project_name TEXT,
  cwd TEXT NOT NULL,
  git_branch TEXT,
  terminal_type TEXT,               -- 'tmux', 'vscode', 'iterm'
  terminal_info TEXT,               -- JSON metadata
  started_at INTEGER NOT NULL,
  last_activity_at INTEGER NOT NULL,
  ended_at INTEGER,                 -- NULL for active sessions
  is_idle INTEGER DEFAULT 0         -- Boolean: waiting for input?
);
```

#### config
Stores configuration with optional encryption.

```sql
CREATE TABLE config (
  key TEXT PRIMARY KEY,
  value TEXT NOT NULL,              -- Encrypted if is_encrypted=1
  is_encrypted INTEGER DEFAULT 0,
  updated_at INTEGER NOT NULL
);
```

#### audit_log
Records all significant actions.

```sql
CREATE TABLE audit_log (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  session_id TEXT,
  action TEXT NOT NULL,             -- 'notification_sent', 'config_updated', etc.
  details TEXT,                     -- JSON details
  created_at INTEGER NOT NULL
);
```

#### metrics
Stores performance metrics.

```sql
CREATE TABLE metrics (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  metric_name TEXT NOT NULL,        -- 'notification_latency_ms', etc.
  metric_value REAL NOT NULL,
  session_id TEXT,
  created_at INTEGER NOT NULL
);
```

## Usage Examples

### Basic Usage

```python
from database import Database

# Initialize database
db = Database("~/.claude/state/notifications.db")

# Insert event
event_id = db.insert_event(
    session_id="abc123",
    event_type="pre_tool_use",
    payload={"tool_name": "Edit", "file": "app.ts"}
)

# Create notification
notif_id = db.insert_notification(
    event_id=event_id,
    session_id="abc123",
    notification_type="permission",
    backend="slack",
    payload={"text": "Claude wants to edit app.ts"}
)

# Mark as sent
db.mark_notification_sent(notif_id)

# Close connection
db.close()
```

### Context Manager

```python
with Database("~/.claude/state/notifications.db") as db:
    # Auto-commits on success, rolls back on exception
    db.insert_event("session1", "test", {})
    # Connection auto-closed
```

### Event Processing

```python
# Get unprocessed events
db = Database("~/.claude/state/notifications.db")
events = db.get_unprocessed_events()

for event in events:
    # Process event
    process_event(event)

    # Mark as processed
    db.mark_event_processed(event['id'])

db.close()
```

### Session Tracking

```python
# Create session
db.create_session(
    session_id="abc123",
    cwd="/Users/dev/project",
    project_name="my-project",
    git_branch="main",
    terminal_type="tmux",
    terminal_info='{"pane": "0:0.0"}'
)

# Update activity
db.update_session_activity("abc123")

# Set idle
db.set_session_idle("abc123", is_idle=True)

# End session
db.end_session("abc123")

# Get active sessions
active = db.get_active_sessions()
```

### Config Storage

```python
# Store plaintext config
db.set_config("enabled", "true")

# Store encrypted config
db.set_config("slack_webhook_url",
              "https://hooks.slack.com/services/...",
              encrypted=True)

# Retrieve (auto-decrypts)
webhook_url = db.get_config("slack_webhook_url")
enabled = db.get_config("enabled", default="false")

# Get all config
config = db.get_all_config()
```

### Audit Logging

```python
# Log action
db.insert_audit_log(
    session_id="abc123",
    action="notification_sent",
    details={"notification_id": 123, "backend": "slack"}
)

# Query logs
logs = db.get_audit_logs_by_session("abc123")
sent_logs = db.get_audit_logs_by_action("notification_sent")
recent = db.get_recent_audit_logs(limit=50)
```

### Metrics

```python
# Record metric
db.insert_metric(
    metric_name="notification_latency_ms",
    metric_value=123.45,
    session_id="abc123"
)

# Get statistics
stats = db.get_metric_stats("notification_latency_ms")
# Returns: {'count': 100, 'avg': 150.5, 'min': 50, 'max': 500}

# Time-filtered stats
import time
since = int(time.time()) - 3600  # Last hour
stats = db.get_metric_stats("notification_latency_ms", since=since)
```

### Notification Retry

```python
# Get pending notifications
pending = db.get_pending_notifications()

# Get failed notifications that can retry (retry_count < 3)
failed = db.get_failed_notifications_for_retry(max_retries=3)

for notif in pending + failed:
    try:
        send_notification(notif)
        db.mark_notification_sent(notif['id'])
    except Exception as e:
        db.mark_notification_failed(notif['id'], str(e))
```

### V1 Migration

```python
import json

# Import V1 config
with open("~/.claude/config/slack-config.json") as f:
    v1_config = json.load(f)
db.import_v1_config(v1_config)

# Import V1 tool request
with open("tool_requests/abc123_1234567890.json") as f:
    tool_request = json.load(f)
db.import_v1_tool_request(
    session_id="abc123",
    tool_request=tool_request,
    timestamp=1234567890
)

# Import V1 notification state
with open("notification_states.json") as f:
    states = json.load(f)
for state in states:
    db.import_v1_notification_state(state)
```

## Performance

### WAL Mode

The database uses Write-Ahead Logging (WAL) mode for better concurrency:
- Multiple readers can access DB while writer is writing
- Faster than default rollback journal
- Better for high-frequency writes

### Indexes

All queries are optimized with appropriate indexes:
- `events.session_id` - Session filtering
- `events.created_at` - Time-ordered queries
- `events.processed_at` - Unprocessed event queries
- `notifications.status` - Pending/failed queries
- `notifications.session_id` - Session filtering
- `audit_log.session_id`, `audit_log.action` - Log queries
- `metrics.metric_name`, `metrics.created_at` - Metric queries

### Benchmarks

Expected performance (on modern hardware):
- Insert event: ~1ms
- Get unprocessed events (1000 events): ~5ms
- Mark event processed: ~1ms
- Query with indexes: ~1-5ms
- WAL checkpoint: ~10-50ms (periodic, automatic)

## Session Isolation

All queries filter by `session_id` to ensure data isolation:

```python
# Only returns events for session1
events = db.get_events_by_session("session1")

# Only returns notifications for session1
notifs = db.get_notifications_by_session("session1")

# Only returns audit logs for session1
logs = db.get_audit_logs_by_session("session1")
```

This prevents sessions from accessing each other's data.

## Error Handling

```python
# Handle missing events
event = db.get_event_by_id(99999)
if event is None:
    print("Event not found")

# Handle missing config
value = db.get_config("nonexistent_key", default="fallback")

# Handle duplicate session
import sqlite3
try:
    db.create_session("session1", "/tmp")
    db.create_session("session1", "/tmp")  # Raises IntegrityError
except sqlite3.IntegrityError:
    # Use upsert instead
    db.upsert_session("session1", "/tmp")
```

## Testing

Run the comprehensive test suite:

```bash
# Run all tests
cd hooks/slack
python3 -m pytest tests/test_database.py -v

# Run specific test class
python3 -m pytest tests/test_database.py::TestEventOperations -v

# Run with coverage
python3 -m pytest tests/test_database.py --cov=lib/database --cov-report=html

# Use helper script
./run_database_tests.sh
```

Test coverage includes:
- Database initialization and schema
- Event CRUD operations
- Notification tracking (pending/sent/failed)
- Session lifecycle management
- Config storage with encryption
- Audit logging
- Metrics recording
- Session isolation
- V1 migration
- Error handling
- Performance optimizations

## Debugging

### View Database Contents

```bash
# Open database
sqlite3 ~/.claude/state/notifications.db

# List tables
.tables

# Describe schema
.schema events

# Query data
SELECT * FROM events ORDER BY created_at DESC LIMIT 10;
SELECT * FROM notifications WHERE status='pending';
SELECT * FROM sessions WHERE ended_at IS NULL;
```

### Query Helper

```python
# Execute raw SQL
results = db.execute_query(
    "SELECT event_type, COUNT(*) as count FROM events GROUP BY event_type"
)
for row in results:
    print(f"{row['event_type']}: {row['count']}")
```

### Inspect Schema

```python
# Get table names
tables = db._get_table_names()
print(f"Tables: {tables}")

# Get index names
indexes = db._get_index_names()
print(f"Indexes: {indexes}")
```

## Security

### Encrypted Config

Sensitive config values (webhook URLs) are encrypted using Fernet symmetric encryption:

```python
# Set encrypted config
db.set_config("slack_webhook_url", "https://hooks.slack.com/...", encrypted=True)

# Get config (auto-decrypts)
webhook_url = db.get_config("slack_webhook_url")
```

The encryption key is stored at `~/.claude/state/encryption.key` with `0o600` permissions.

### Session Isolation

All session-specific queries filter by `session_id` to prevent cross-session data access.

## Migration from V1

Complete migration example:

```python
from database import Database
import json
import os
from pathlib import Path

db = Database("~/.claude/state/notifications.db")

# 1. Import config
config_path = Path.home() / ".claude/config/slack-config.json"
if config_path.exists():
    with open(config_path) as f:
        v1_config = json.load(f)
    db.import_v1_config(v1_config)
    print("✓ Imported config")

# 2. Import tool requests
tool_requests_dir = Path.home() / ".claude/state/tool_requests"
if tool_requests_dir.exists():
    for file_path in tool_requests_dir.glob("*.json"):
        # Parse filename: {session_id}_{timestamp}.json
        parts = file_path.stem.split("_")
        if len(parts) >= 2:
            session_id = parts[0]
            timestamp = int(parts[1])

            with open(file_path) as f:
                tool_request = json.load(f)

            db.import_v1_tool_request(session_id, tool_request, timestamp)
    print(f"✓ Imported {len(list(tool_requests_dir.glob('*.json')))} tool requests")

# 3. Import notification states
states_path = Path.home() / ".claude/state/notification_states.json"
if states_path.exists():
    with open(states_path) as f:
        states = json.load(f)

    for state in states:
        db.import_v1_notification_state(state)
    print(f"✓ Imported {len(states)} notification states")

db.close()
print("Migration complete!")
```

## References

- [PRD: Slack Notifications V2](../../../docs/PRD_SLACK_NOTIFICATIONS_V2_OPTIMIZED.md)
- [Encryption Module](./ENCRYPTION_README.md)
- [Test Suite](../tests/test_database.py)
- [SQLite WAL Mode](https://www.sqlite.org/wal.html)
