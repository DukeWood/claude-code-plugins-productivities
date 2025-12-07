# Event Queue & Retry Logic

## Overview

The event queue system provides reliable, async notification delivery with automatic retry logic and dead letter queue handling for Slack Notification V2.

## Features

- **Queue Operations**: Enqueue, dequeue, mark_sent, mark_failed
- **Exponential Backoff**: 1min → 5min → 15min → 1hr → 4hr
- **Dead Letter Queue**: Permanently failed notifications after 5 retries
- **Thread Safety**: Atomic database operations with WAL mode
- **Queue Statistics**: Real-time metrics and monitoring
- **Auto Cleanup**: Remove old processed notifications

## Usage

### Basic Operations

```python
from queue import NotificationQueue

# Initialize queue
queue = NotificationQueue("/path/to/notifications.db")

# Enqueue a notification
notif_id = queue.enqueue(
    event_type="permission",
    payload={"text": "Claude wants to edit app.ts"},
    session_id="session-123"
)

# Dequeue batch for processing
batch = queue.dequeue(batch_size=10)

for notification in batch:
    try:
        # Send notification via backend
        send_to_slack(notification["payload"])

        # Mark as sent
        queue.mark_sent(notification["id"])
    except Exception as e:
        # Mark as failed (will retry)
        queue.mark_failed(notification["id"], str(e))
```

### Queue Statistics

```python
# Get overall stats
stats = queue.get_stats()
print(f"Pending: {stats.pending}")
print(f"Sent: {stats.sent}")
print(f"Failed: {stats.failed}")
print(f"Dead Letter: {stats.dead_letter}")

# Get stats for specific session
stats = queue.get_stats(session_id="session-123")

# Get pending count
count = queue.get_pending_count()
```

### Dead Letter Queue

```python
# Get all dead letters
dead_letters = queue.get_dead_letters()

for dl in dead_letters:
    print(f"ID: {dl['id']}")
    print(f"Error: {dl['error']}")
    print(f"Retry Count: {dl['retry_count']}")
    print(f"Payload: {dl['payload']}")
```

### Cleanup

```python
# Remove notifications older than 30 days
deleted_count = queue.cleanup_old(days=30)
print(f"Deleted {deleted_count} old notifications")
```

## Notification Lifecycle

```
┌─────────────┐
│   PENDING   │ ← Initial state
└──────┬──────┘
       │
       │ dequeue()
       ↓
┌─────────────┐
│ PROCESSING  │ ← Currently being sent
└──────┬──────┘
       │
       ├─→ SUCCESS → mark_sent() → ┌──────┐
       │                            │ SENT │
       │                            └──────┘
       │
       └─→ FAILURE → mark_failed() → ┌────────┐
                                       │ FAILED │
                                       └────┬───┘
                                            │
                     ┌──────────────────────┴──────────────────────┐
                     │                                             │
              retry_count <= 5                              retry_count > 5
                     │                                             │
                     ↓                                             ↓
              Wait for next_retry_at                    ┌──────────────┐
              (exponential backoff)                     │ DEAD_LETTER  │
                     │                                  └──────────────┘
                     │
                     └─→ dequeue() → PROCESSING → ...
```

## Retry Schedule

The queue implements exponential backoff for failed notifications:

| Attempt | Delay    | Total Time Since First Attempt |
|---------|----------|--------------------------------|
| 1       | 1 min    | 1 min                          |
| 2       | 5 min    | 6 min                          |
| 3       | 15 min   | 21 min                         |
| 4       | 1 hour   | 1 hr 21 min                    |
| 5       | 4 hours  | 5 hr 21 min                    |
| 6+      | Dead Letter | N/A                         |

## Database Schema

### Notifications Table

```sql
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER NOT NULL,
    session_id TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    backend TEXT NOT NULL DEFAULT 'slack',
    status TEXT NOT NULL DEFAULT 'pending',
    retry_count INTEGER DEFAULT 0,
    payload TEXT NOT NULL,
    error TEXT,
    created_at INTEGER NOT NULL,
    sent_at INTEGER,
    next_retry_at INTEGER,
    FOREIGN KEY (event_id) REFERENCES events(id)
);
```

### Indexes

- `idx_notifications_status`: Fast queries by status
- `idx_notifications_session`: Fast queries by session
- `idx_notifications_retry`: Fast queries for retry-ready notifications

## Thread Safety

The queue is fully thread-safe:

- **WAL Mode**: Enabled for concurrent reads/writes
- **Row-Level Locking**: Atomic status transitions
- **Transaction Isolation**: IMMEDIATE transactions for dequeue
- **Thread-Local Connections**: Each thread gets its own connection

### Concurrent Usage Example

```python
import threading

queue = NotificationQueue("/path/to/db")

def worker():
    batch = queue.dequeue(batch_size=5)
    for notif in batch:
        # Process notification
        pass

# Safe to run multiple workers
threads = [threading.Thread(target=worker) for _ in range(5)]
for t in threads:
    t.start()
for t in threads:
    t.join()
```

## Error Handling

### Automatic Retry

Failed notifications are automatically retried with exponential backoff:

```python
try:
    send_notification(notif)
    queue.mark_sent(notif["id"])
except Exception as e:
    # Automatic retry scheduling
    queue.mark_failed(notif["id"], str(e))
```

### Dead Letter Queue

After 5 failed attempts, notifications move to the dead letter queue for manual review:

```python
# Review failed notifications
dead_letters = queue.get_dead_letters()

for dl in dead_letters:
    # Investigate issue
    print(f"Error: {dl['error']}")

    # Optionally re-enqueue after fixing issue
    queue.enqueue(
        event_type=dl["notification_type"],
        payload=dl["payload"],
        session_id=dl["session_id"]
    )
```

## Performance

### Benchmarks (Expected)

- **Enqueue**: < 5ms
- **Dequeue (batch=10)**: < 10ms
- **Mark Sent**: < 3ms
- **Mark Failed**: < 5ms
- **Throughput**: > 1000 ops/sec

### Optimization Tips

1. **Batch Dequeue**: Use larger batch sizes for better throughput
2. **Connection Reuse**: Queue maintains thread-local connections
3. **Periodic Cleanup**: Run `cleanup_old()` regularly to maintain DB size
4. **Monitor Dead Letters**: Set up alerts for dead letter queue growth

## Monitoring

### Key Metrics to Track

```python
# Pending notification count (should stay low)
pending = queue.get_pending_count()

# Dead letter count (should stay near zero)
stats = queue.get_stats()
if stats.dead_letter > 0:
    alert("Dead letters detected!")

# Success rate
success_rate = stats.sent / stats.total if stats.total > 0 else 1.0
if success_rate < 0.95:
    alert("Low success rate!")
```

### Debugging Queries

```sql
-- Find stuck notifications
SELECT * FROM notifications
WHERE status = 'processing'
  AND created_at < unixepoch('now', '-5 minutes');

-- Find notifications with most retries
SELECT id, retry_count, error, payload
FROM notifications
WHERE retry_count > 3
ORDER BY retry_count DESC;

-- Average retry count for failed notifications
SELECT AVG(retry_count) as avg_retries
FROM notifications
WHERE status = 'failed';
```

## Testing

### Run Unit Tests

```bash
cd hooks/slack
python3 -m pytest tests/test_queue.py -v
```

### Run Smoke Tests

```bash
cd hooks/slack
python3 test_runner.py
```

### Test Coverage

The test suite covers:

- ✓ Basic queue operations (enqueue, dequeue, mark_sent, mark_failed)
- ✓ Retry logic with exponential backoff
- ✓ Dead letter queue handling
- ✓ Queue statistics and metrics
- ✓ Cleanup operations
- ✓ Thread safety (concurrent operations)
- ✓ Edge cases (empty payloads, long errors, zero batch size)
- ✓ FIFO ordering
- ✓ Session filtering

## Integration with V2 Architecture

The queue integrates with the V2 dispatcher:

```python
# dispatcher.py
from queue import NotificationQueue

queue = NotificationQueue("~/.claude/state/notifications.db")

def process_events():
    # Get pending notifications
    batch = queue.dequeue(batch_size=10)

    for notif in batch:
        backend = notif["backend"]
        payload = notif["payload"]

        try:
            if backend == "slack":
                slack.send(payload)
            elif backend == "discord":
                discord.send(payload)

            queue.mark_sent(notif["id"])
        except Exception as e:
            queue.mark_failed(notif["id"], str(e))
```

## API Reference

### NotificationQueue

#### `__init__(db_path: str)`

Initialize queue with database path.

#### `enqueue(event_type: str, payload: Dict, session_id: str, backend: str = "slack", event_id: Optional[int] = None) -> int`

Add notification to queue. Returns notification ID.

#### `dequeue(batch_size: int = 10) -> List[Dict]`

Get next batch of notifications for processing. Marks them as PROCESSING.

#### `mark_sent(notification_id: int)`

Mark notification as successfully sent.

#### `mark_failed(notification_id: int, error: str)`

Mark notification as failed and schedule retry with exponential backoff.

#### `get_pending_count(session_id: Optional[str] = None) -> int`

Get count of pending notifications.

#### `get_stats(session_id: Optional[str] = None) -> QueueStats`

Get comprehensive queue statistics.

#### `get_dead_letters(limit: Optional[int] = None) -> List[Dict]`

Get notifications in dead letter queue.

#### `cleanup_old(days: int = 30) -> int`

Remove old processed notifications. Returns count deleted.

#### `close()`

Close database connection.

### QueueStats

Dataclass containing queue statistics:

- `pending`: Count of pending notifications
- `processing`: Count of currently processing
- `sent`: Count of successfully sent
- `failed`: Count of failed (retry-able)
- `dead_letter`: Count in dead letter queue
- `total`: Total count of all notifications

### NotificationStatus

Status constants:

- `PENDING`: "pending"
- `PROCESSING`: "processing"
- `SENT`: "sent"
- `FAILED`: "failed"
- `DEAD_LETTER`: "dead_letter"

### Constants

- `RETRY_DELAYS`: [60, 300, 900, 3600, 14400] (seconds)
- `MAX_RETRIES`: 5

## Best Practices

1. **Always close connections**: Call `queue.close()` when done
2. **Handle exceptions**: Wrap send operations in try/except
3. **Monitor dead letters**: Set up alerts for growing dead letter queue
4. **Regular cleanup**: Run `cleanup_old()` daily via cron
5. **Batch processing**: Use appropriate batch sizes for your workload
6. **Session isolation**: Filter stats by session for debugging
7. **Error logging**: Include detailed error messages in `mark_failed()`
8. **Retry logic**: Trust the exponential backoff, don't retry manually

## Troubleshooting

### Notifications not being sent

1. Check pending count: `queue.get_pending_count()`
2. Check for stuck processing: Query notifications with status='processing' and old timestamps
3. Check dead letter queue: `queue.get_dead_letters()`

### High dead letter count

1. Review error messages in dead letters
2. Check webhook URL validity
3. Verify network connectivity
4. Check Slack webhook rate limits

### Database growing too large

1. Run cleanup: `queue.cleanup_old(days=30)`
2. Check for stuck notifications in 'processing' state
3. Vacuum database: `PRAGMA vacuum;`

## Migration from V1

V1 had no queue system. To migrate:

1. No data migration needed (V1 notifications were ephemeral)
2. Simply start using the queue for all new notifications
3. Old V1 code can be safely removed

## License

Part of claude-code-plugins-productivities project.
