# Event Queue - Quick Start Guide

## Installation

No installation needed! The queue module uses only Python standard library + SQLite.

## Quick Usage

### 1. Initialize Queue

```python
from queue import NotificationQueue

queue = NotificationQueue("/path/to/notifications.db")
```

### 2. Enqueue Notification

```python
notif_id = queue.enqueue(
    event_type="permission",
    payload={"text": "Claude wants to edit app.ts"},
    session_id="session-123"
)
```

### 3. Process Notifications

```python
# Get batch of notifications
batch = queue.dequeue(batch_size=10)

for notif in batch:
    try:
        # Send notification
        send_to_slack(notif["payload"])

        # Mark as sent
        queue.mark_sent(notif["id"])
    except Exception as e:
        # Mark as failed (automatic retry)
        queue.mark_failed(notif["id"], str(e))
```

### 4. Monitor Queue

```python
# Get stats
stats = queue.get_stats()
print(f"Pending: {stats.pending}, Sent: {stats.sent}, Failed: {stats.failed}")

# Check dead letters
dead = queue.get_dead_letters()
if dead:
    print(f"⚠️  {len(dead)} notifications in dead letter queue!")
```

### 5. Cleanup

```python
# Remove old notifications (30 days)
deleted = queue.cleanup_old(days=30)
print(f"Cleaned up {deleted} old notifications")
```

## Retry Schedule

| Attempt | Delay    |
|---------|----------|
| 1       | 1 min    |
| 2       | 5 min    |
| 3       | 15 min   |
| 4       | 1 hour   |
| 5       | 4 hours  |
| 6+      | Dead Letter |

## Testing

### Run Full Test Suite

```bash
cd hooks/slack
python3 -m pytest tests/test_queue.py -v
```

### Run Smoke Tests

```bash
cd hooks/slack
python3 test_runner.py
```

## Files Delivered

1. **lib/queue.py** (591 lines)
   - NotificationQueue class
   - 9 public methods
   - Thread-safe operations

2. **tests/test_queue.py** (906 lines)
   - 38 comprehensive test cases
   - 10 test classes
   - Full coverage

3. **lib/QUEUE_README.md** (452 lines)
   - Complete documentation
   - API reference
   - Best practices

4. **test_runner.py** (209 lines)
   - Quick smoke tests
   - Easy validation

## Key Methods

```python
# Queue operations
enqueue(event_type, payload, session_id) → int
dequeue(batch_size=10) → List[Dict]
mark_sent(notification_id)
mark_failed(notification_id, error)

# Statistics
get_pending_count(session_id=None) → int
get_stats(session_id=None) → QueueStats
get_dead_letters(limit=None) → List[Dict]

# Maintenance
cleanup_old(days=30) → int
close()
```

## Status Flow

```
PENDING → PROCESSING → SENT ✓
             ↓
           FAILED → (retry) → PROCESSING
             ↓
        DEAD_LETTER (after 5 retries)
```

## Thread Safety

✓ Safe for concurrent use
✓ WAL mode enabled
✓ Atomic transactions
✓ Thread-local connections

## Next Steps

1. Review tests: `tests/test_queue.py`
2. Review implementation: `lib/queue.py`
3. Read full docs: `lib/QUEUE_README.md`
4. Run tests to verify
5. Integrate with dispatcher

## Support

See `QUEUE_README.md` for:
- Detailed API reference
- Performance tuning
- Troubleshooting guide
- Best practices
