# Database API Quick Reference

## Initialization

```python
from database import Database

# Create connection
db = Database("~/.claude/state/notifications.db")

# Use context manager (recommended)
with Database("path/to/db.db") as db:
    db.insert_event(...)
```

## Events

| Method | Description | Returns |
|--------|-------------|---------|
| `insert_event(session_id, event_type, payload, created_at=None)` | Insert event | `event_id (int)` |
| `get_event_by_id(event_id)` | Get event by ID | `Row or None` |
| `get_unprocessed_events()` | Get events where processed_at IS NULL | `List[Row]` |
| `mark_event_processed(event_id)` | Mark event as processed | `None` |
| `get_events_by_session(session_id)` | Get all events for session | `List[Row]` |
| `get_latest_event_by_type(session_id, event_type)` | Get most recent event of type | `Row or None` |

## Notifications

| Method | Description | Returns |
|--------|-------------|---------|
| `insert_notification(event_id, session_id, notification_type, backend, payload, created_at=None)` | Create notification | `notification_id (int)` |
| `get_notification_by_id(notification_id)` | Get notification by ID | `Row or None` |
| `get_pending_notifications()` | Get notifications with status='pending' | `List[Row]` |
| `get_failed_notifications_for_retry(max_retries=3)` | Get retryable failed notifications | `List[Row]` |
| `mark_notification_sent(notification_id)` | Mark as sent | `None` |
| `mark_notification_failed(notification_id, error)` | Mark as failed, increment retry_count | `None` |
| `get_notifications_by_session(session_id)` | Get all notifications for session | `List[Row]` |

## Sessions

| Method | Description | Returns |
|--------|-------------|---------|
| `create_session(session_id, cwd, project_name=None, git_branch=None, terminal_type=None, terminal_info=None, started_at=None)` | Create session | `None` |
| `get_session(session_id)` | Get session by ID | `Row or None` |
| `update_session_activity(session_id)` | Update last_activity_at | `None` |
| `set_session_idle(session_id, is_idle)` | Set idle flag | `None` |
| `end_session(session_id)` | Set ended_at timestamp | `None` |
| `get_active_sessions()` | Get sessions where ended_at IS NULL | `List[Row]` |
| `upsert_session(session_id, cwd, project_name=None, git_branch=None, terminal_type=None, terminal_info=None)` | Create or update session | `None` |

## Config

| Method | Description | Returns |
|--------|-------------|---------|
| `set_config(key, value, encrypted=False)` | Set config value | `None` |
| `get_config(key, default=None)` | Get config value (auto-decrypts) | `str or None` |
| `get_all_config()` | Get all config as dict (auto-decrypts) | `Dict[str, str]` |
| `delete_config(key)` | Delete config key | `None` |

## Audit Log

| Method | Description | Returns |
|--------|-------------|---------|
| `insert_audit_log(action, session_id=None, details=None, created_at=None)` | Insert audit log entry | `log_id (int)` |
| `get_audit_logs_by_session(session_id)` | Get logs for session | `List[Row]` |
| `get_audit_logs_by_action(action)` | Get logs by action | `List[Row]` |
| `get_recent_audit_logs(limit=100)` | Get recent logs | `List[Row]` |

## Metrics

| Method | Description | Returns |
|--------|-------------|---------|
| `insert_metric(metric_name, metric_value, session_id=None, created_at=None)` | Insert metric | `metric_id (int)` |
| `get_metrics_by_name(metric_name)` | Get all metrics by name | `List[Row]` |
| `get_metric_stats(metric_name, since=None)` | Calculate count/avg/min/max | `Dict` |

## Migration

| Method | Description | Returns |
|--------|-------------|---------|
| `import_v1_config(v1_config)` | Import V1 slack-config.json | `None` |
| `import_v1_tool_request(session_id, tool_request, timestamp)` | Import V1 tool request | `event_id (int)` |
| `import_v1_notification_state(v1_state)` | Import V1 notification state | `None` |

## Utilities

| Method | Description | Returns |
|--------|-------------|---------|
| `execute_query(query, params=())` | Execute raw SQL | `List[Row]` |
| `_get_table_names()` | Get table names | `List[str]` |
| `_get_index_names()` | Get index names | `List[str]` |
| `close()` | Close connection | `None` |

## Row Access

All query methods return `sqlite3.Row` objects that support both index and key access:

```python
event = db.get_event_by_id(1)

# Dictionary-style access (recommended)
session_id = event['session_id']
event_type = event['event_type']

# Index access
session_id = event[1]

# Convert to dict
event_dict = dict(event)
```

## Common Patterns

### Process Event Queue

```python
for event in db.get_unprocessed_events():
    # Process event
    handle_event(event)
    # Mark as processed
    db.mark_event_processed(event['id'])
```

### Send Notifications with Retry

```python
pending = db.get_pending_notifications()
failed = db.get_failed_notifications_for_retry(max_retries=3)

for notif in pending + failed:
    try:
        send_to_slack(json.loads(notif['payload']))
        db.mark_notification_sent(notif['id'])
    except Exception as e:
        db.mark_notification_failed(notif['id'], str(e))
```

### Track Session Lifecycle

```python
# Start session
db.create_session("abc123", "/Users/dev/project", project_name="my-app")

# Update activity on each event
db.update_session_activity("abc123")

# Mark as idle when waiting for input
db.set_session_idle("abc123", is_idle=True)

# End session on completion
db.end_session("abc123")
```

### Store Encrypted Webhook URL

```python
# Store
db.set_config("slack_webhook_url", "https://hooks.slack.com/...", encrypted=True)

# Retrieve (auto-decrypts)
webhook_url = db.get_config("slack_webhook_url")
```

### Calculate Metrics

```python
# Record latency
db.insert_metric("notification_latency_ms", 123.45, session_id="abc123")

# Get statistics
stats = db.get_metric_stats("notification_latency_ms")
print(f"Average latency: {stats['avg']:.2f} ms")
```

## Event Types

- `pre_tool_use` - Claude wants to use a tool
- `notification` - Permission prompt or input required
- `post_tool_use` - Tool execution completed
- `stop` - Session ended

## Notification Types

- `permission` - Permission prompt
- `task_complete` - Task finished
- `input_required` - Waiting for user input
- `error` - Error occurred

## Notification Status

- `pending` - Waiting to be sent
- `sent` - Successfully delivered
- `failed` - Failed (will retry if retry_count < max_retries)

## Terminal Types

- `tmux` - tmux session
- `vscode` - VSCode terminal
- `iterm` - iTerm2
- `ssh` - SSH session

## Example: Complete Event Flow

```python
from database import Database
import json
import time

db = Database("~/.claude/state/notifications.db")

# 1. Create session
db.create_session(
    session_id="abc123",
    cwd="/Users/dev/my-project",
    project_name="my-project",
    git_branch="main",
    terminal_type="tmux",
    terminal_info='{"pane": "0:0.0"}'
)

# 2. Insert pre_tool_use event
event_id = db.insert_event(
    session_id="abc123",
    event_type="pre_tool_use",
    payload={"tool_name": "Edit", "file": "app.ts"}
)

# 3. Update session activity
db.update_session_activity("abc123")

# 4. Insert notification event
notif_event_id = db.insert_event(
    session_id="abc123",
    event_type="notification",
    payload={"hook_event_name": "Notification", "type": "permission_prompt"}
)

# 5. Create notification
notif_id = db.insert_notification(
    event_id=notif_event_id,
    session_id="abc123",
    notification_type="permission",
    backend="slack",
    payload={"text": "Claude wants to edit app.ts"}
)

# 6. Send notification
try:
    send_to_slack(db.get_notification_by_id(notif_id))
    db.mark_notification_sent(notif_id)
    db.insert_audit_log("abc123", "notification_sent", {"notification_id": notif_id})
    db.insert_metric("notification_latency_ms", 123, "abc123")
except Exception as e:
    db.mark_notification_failed(notif_id, str(e))

# 7. Mark events as processed
db.mark_event_processed(event_id)
db.mark_event_processed(notif_event_id)

# 8. End session
db.end_session("abc123")

db.close()
```
