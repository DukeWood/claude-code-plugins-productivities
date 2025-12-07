# Proposal 2: V2 SQLite Database Counter

## 1. Description & Objectives

### Problem Statement

Users receiving Slack notifications from Claude Code have no visibility into their daily notification volume. The V2 system already stores all notifications in SQLite but doesn't expose this count in the messages.

### Proposed Solution

Query the existing `notifications` table to count today's sent notifications, then display this count in the Slack message title. No schema changes required - leverages existing data.

**Key insight:** The counter is determined at **send time** (not queue time), ensuring the most accurate count.

**Result:**
```
⏳ Waiting for Input (#5)
533b | claude-code-plugins-productivities | tmux 0:0.0 | main | 10:48 p.m.
```

### Goals & Success Metrics

| Goal | Success Metric |
|------|----------------|
| Accurate daily count | Counter matches actual DB records |
| Per-session tracking | Each session has independent count |
| Zero schema changes | No database migrations needed |
| Backward compatible | Existing tests pass (210+) |
| Real-time accuracy | Count reflects all sent notifications |

---

## 2. Detailed Implementation Plan

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                      Notification Flow                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  hook.py (entry point)                                           │
│       │                                                          │
│       ▼                                                          │
│  handlers.py                                                     │
│  ├── handle_pre_tool_use() ──► queue_notification()             │
│  └── handle_stop() ──────────► queue_notification()             │
│       │                                                          │
│       ▼                                                          │
│  notifications table (status='pending')                          │
│       │                                                          │
│       ▼                                                          │
│  sender.py                                                       │
│  ├── process_queue()                                             │
│  │     └── send_notification()                                   │
│  │           │                                                   │
│  │           ▼                                                   │
│  │     ┌─────────────────────────────────────────┐              │
│  │     │ NEW: get_daily_notification_count()     │              │
│  │     │      SELECT COUNT(*) FROM notifications │              │
│  │     │      WHERE session_id = ?               │              │
│  │     │        AND status = 'sent'              │              │
│  │     │        AND created_at >= midnight_utc   │              │
│  │     └─────────────────────────────────────────┘              │
│  │           │                                                   │
│  │           ▼                                                   │
│  │     build_permission_payload(daily_count=N)                   │
│  │     build_stop_payload(daily_count=N)                         │
│  │           │                                                   │
│  │           ▼                                                   │
│  │     Slack Webhook (with "#N" in title)                       │
│  │           │                                                   │
│  │           ▼                                                   │
│  └── mark_sent() ──► status='sent'                              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Database Schema (Existing - No Changes)

```sql
-- notifications table (already exists)
CREATE TABLE notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_id INTEGER,
    session_id TEXT NOT NULL,
    notification_type TEXT NOT NULL,
    backend TEXT DEFAULT 'slack',
    payload TEXT NOT NULL,
    status TEXT DEFAULT 'pending',
    created_at INTEGER NOT NULL,
    sent_at INTEGER,
    retry_count INTEGER DEFAULT 0,
    next_retry_at INTEGER,
    error_message TEXT
);

-- Existing index helps our query
CREATE INDEX idx_notifications_session ON notifications(session_id);
CREATE INDEX idx_notifications_status ON notifications(status);
```

### File Changes

#### 2.1 `hooks/slack/lib/sender.py` - Add Counter Function

**Location:** After line 100 (after imports and before payload builders)

```python
# =============================================================================
# Daily Notification Counter
# =============================================================================

def get_daily_notification_count(
    db: sqlite3.Connection,
    session_id: str,
    backend: str = 'slack'
) -> int:
    """
    Get count of successfully sent notifications for a session today.

    The count is determined at send time (not queue time) for accuracy.
    Uses UTC midnight as the day boundary for consistency.

    Args:
        db: SQLite database connection (row_factory should be sqlite3.Row)
        session_id: Session identifier
        backend: Notification backend (default: 'slack')

    Returns:
        Count of sent notifications since midnight UTC today.
        Returns 0 if no notifications found or on error.

    Example:
        >>> count = get_daily_notification_count(db, "abc-123")
        >>> print(f"Today's count: {count}")
        Today's count: 5
    """
    try:
        now = int(time.time())
        # Calculate Unix timestamp of today's midnight (UTC)
        # 86400 = seconds in a day
        today_start = (now // 86400) * 86400

        cursor = db.execute(
            """SELECT COUNT(*) as count
               FROM notifications
               WHERE session_id = ?
                 AND backend = ?
                 AND status = ?
                 AND created_at >= ?""",
            (session_id, backend, NotificationStatus.SENT, today_start)
        )

        row = cursor.fetchone()
        return row['count'] if row else 0

    except Exception:
        # Don't let counter query break notification sending
        return 0


def format_counter_for_title(count: int) -> str:
    """
    Format daily count for display in notification title.

    Args:
        count: Number of notifications sent today

    Returns:
        Formatted string like "(#5)" or empty string if count <= 0

    Examples:
        >>> format_counter_for_title(0)
        ''
        >>> format_counter_for_title(5)
        '(#5)'
        >>> format_counter_for_title(99)
        '(#99)'
    """
    if count <= 0:
        return ""
    return f"(#{count})"
```

#### 2.2 `hooks/slack/lib/sender.py` - Update `build_permission_payload()`

**Location:** Line ~108 (function signature)

```python
# Before:
def build_permission_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:

# After:
def build_permission_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any],
    daily_count: Optional[int] = None
) -> Dict[str, Any]:
```

**Location:** Line ~145 (header text generation)

```python
# Before:
project_name = context.get("project_name", "Unknown Project")
header_text = f"🔔 {project_name}: Permission Required"

# After:
project_name = context.get("project_name", "Unknown Project")
counter_suffix = format_counter_for_title(daily_count) if daily_count else ""
header_text = f"🔔 {project_name}: Permission Required {counter_suffix}".strip()
```

#### 2.3 `hooks/slack/lib/sender.py` - Update `build_stop_payload()`

**Location:** Line ~187 (function signature)

```python
# Before:
def build_stop_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:

# After:
def build_stop_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any],
    daily_count: Optional[int] = None
) -> Dict[str, Any]:
```

**Location:** Line ~225 (header text generation)

```python
# Before:
project_name = context.get("project_name", "Unknown Project")
header_text = f"✅ {project_name}: Task Complete"

# After:
project_name = context.get("project_name", "Unknown Project")
counter_suffix = format_counter_for_title(daily_count) if daily_count else ""
header_text = f"✅ {project_name}: Task Complete {counter_suffix}".strip()
```

#### 2.4 `hooks/slack/lib/sender.py` - Update `build_idle_payload()`

**Location:** Line ~272 (function signature and header)

```python
# Before:
def build_idle_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any]
) -> Dict[str, Any]:

# After:
def build_idle_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any],
    daily_count: Optional[int] = None
) -> Dict[str, Any]:
    # ... existing code ...
    counter_suffix = format_counter_for_title(daily_count) if daily_count else ""
    header_text = f"⏳ {project_name}: Waiting for Input {counter_suffix}".strip()
```

#### 2.5 `hooks/slack/lib/sender.py` - Update `send_notification()`

**Location:** Line ~440 (inside send_notification function, before payload building)

```python
def send_notification(db: sqlite3.Connection, notification_id: int) -> bool:
    """Send a single notification from the queue."""

    # Load notification from database
    cursor = db.execute(
        """SELECT * FROM notifications WHERE id = ?""",
        (notification_id,)
    )
    notif = cursor.fetchone()

    if notif is None:
        return False

    # === ADD THIS SECTION ===
    # Get daily notification count for this session
    daily_count = get_daily_notification_count(
        db,
        notif['session_id'],
        notif['backend']
    )
    # Increment by 1 since this notification will be sent
    daily_count += 1
    # === END ADDITION ===

    # Parse stored payload
    payload_data = json.loads(notif['payload'])

    # Build final Slack payload based on notification type
    notification_type = notif['notification_type']

    if notification_type == 'permission':
        # === MODIFY THIS LINE ===
        slack_payload = build_permission_payload(
            payload_data.get('event_data', {}),
            payload_data.get('context', {}),
            daily_count=daily_count  # ADD THIS PARAMETER
        )
    elif notification_type == 'task_complete':
        # === MODIFY THIS LINE ===
        slack_payload = build_stop_payload(
            payload_data.get('event_data', {}),
            payload_data.get('context', {}),
            daily_count=daily_count  # ADD THIS PARAMETER
        )
    elif notification_type == 'idle':
        # === MODIFY THIS LINE ===
        slack_payload = build_idle_payload(
            payload_data.get('event_data', {}),
            payload_data.get('context', {}),
            daily_count=daily_count  # ADD THIS PARAMETER
        )
    else:
        # Generic payload for unknown types
        slack_payload = payload_data

    # ... rest of existing send logic ...
```

### Import Updates

**Location:** Top of `sender.py` (add Optional to imports)

```python
# Before:
from typing import Dict, List, Any, Union

# After:
from typing import Dict, List, Any, Union, Optional
```

---

## 3. Acceptance Criteria

### Functional Requirements

| ID | Requirement | Verification |
|----|-------------|--------------|
| FR-1 | Counter queries sent notifications only | Pending/failed not counted |
| FR-2 | Counter scoped to session | Different sessions have different counts |
| FR-3 | Counter scoped to backend | Only 'slack' notifications counted |
| FR-4 | Counter resets at UTC midnight | Count = 1 after midnight |
| FR-5 | Counter displayed in title | All notification types show "(#N)" |
| FR-6 | Counter hidden when 0 | First notification shows "(#1)" |
| FR-7 | Backward compatible | Existing tests pass |

### Non-Functional Requirements

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Query performance | < 10ms for COUNT query |
| NFR-2 | Error isolation | Counter failure doesn't block send |
| NFR-3 | Thread safety | SQLite handles concurrency |
| NFR-4 | Memory | No additional memory allocation |

### Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| No sent notifications | Count = 0, display "(#1)" after send |
| DB connection error | Return 0, notification sends without counter |
| Invalid session_id | Return 0 (no matching rows) |
| Cross-midnight query | Uses UTC, not local time |
| High volume (1000+) | Query still fast due to indexes |
| Concurrent sends | Each gets incremented count |

---

## 4. Testing Requirements

### Unit Tests (`test_sender.py`)

```python
# =============================================================================
# Daily Counter Tests
# =============================================================================

class TestDailyNotificationCounter:
    """Tests for daily notification counter functionality."""

    def test_get_daily_count_empty_db(self, test_db):
        """Should return 0 when no notifications exist."""
        count = sender.get_daily_notification_count(test_db, "session-1")
        assert count == 0

    def test_get_daily_count_with_sent_notifications(self, test_db):
        """Should count only sent notifications."""
        # Insert 3 sent notifications for today
        now = int(time.time())
        for i in range(3):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "sent", now)
            )
        test_db.commit()

        count = sender.get_daily_notification_count(test_db, "session-1")
        assert count == 3

    def test_get_daily_count_excludes_pending(self, test_db):
        """Should not count pending notifications."""
        now = int(time.time())
        # 2 sent
        for i in range(2):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "sent", now)
            )
        # 3 pending (should not count)
        for i in range(3):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "pending", now)
            )
        test_db.commit()

        count = sender.get_daily_notification_count(test_db, "session-1")
        assert count == 2

    def test_get_daily_count_excludes_yesterday(self, test_db):
        """Should not count notifications from yesterday."""
        now = int(time.time())
        yesterday = now - 86400  # 24 hours ago

        # 2 from today
        for i in range(2):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "sent", now)
            )
        # 5 from yesterday (should not count)
        for i in range(5):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "sent", yesterday)
            )
        test_db.commit()

        count = sender.get_daily_notification_count(test_db, "session-1")
        assert count == 2

    def test_get_daily_count_session_isolation(self, test_db):
        """Should only count notifications for specified session."""
        now = int(time.time())

        # 3 for session-1
        for i in range(3):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-1", "permission", "slack", "{}", "sent", now)
            )
        # 5 for session-2
        for i in range(5):
            test_db.execute(
                """INSERT INTO notifications
                   (session_id, notification_type, backend, payload, status, created_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                ("session-2", "permission", "slack", "{}", "sent", now)
            )
        test_db.commit()

        count_1 = sender.get_daily_notification_count(test_db, "session-1")
        count_2 = sender.get_daily_notification_count(test_db, "session-2")

        assert count_1 == 3
        assert count_2 == 5


class TestFormatCounterForTitle:
    """Tests for counter formatting."""

    def test_format_zero(self):
        """Zero should return empty string."""
        assert sender.format_counter_for_title(0) == ""

    def test_format_negative(self):
        """Negative should return empty string."""
        assert sender.format_counter_for_title(-1) == ""

    def test_format_positive(self):
        """Positive should return (#N) format."""
        assert sender.format_counter_for_title(1) == "(#1)"
        assert sender.format_counter_for_title(5) == "(#5)"
        assert sender.format_counter_for_title(99) == "(#99)"
        assert sender.format_counter_for_title(1000) == "(#1000)"


class TestPayloadWithCounter:
    """Tests for payload building with counter."""

    def test_permission_payload_includes_counter(self):
        """Permission payload should include counter in header."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/test/file.py"}
        }
        context = {"project_name": "test-project"}

        payload = sender.build_permission_payload(event_data, context, daily_count=5)

        # Find header block
        header_block = next(
            (b for b in payload['blocks'] if b.get('type') == 'header'),
            None
        )
        assert header_block is not None
        assert "(#5)" in header_block['text']['text']

    def test_stop_payload_includes_counter(self):
        """Stop payload should include counter in header."""
        event_data = {"session_id": "test-123"}
        context = {"project_name": "test-project"}

        payload = sender.build_stop_payload(event_data, context, daily_count=7)

        header_block = next(
            (b for b in payload['blocks'] if b.get('type') == 'header'),
            None
        )
        assert header_block is not None
        assert "(#7)" in header_block['text']['text']

    def test_payload_without_counter(self):
        """Payload should work without counter (backward compat)."""
        event_data = {"tool_name": "Edit", "tool_input": {}}
        context = {"project_name": "test-project"}

        # No daily_count parameter
        payload = sender.build_permission_payload(event_data, context)

        header_block = next(
            (b for b in payload['blocks'] if b.get('type') == 'header'),
            None
        )
        assert header_block is not None
        # Should not contain counter
        assert "(#" not in header_block['text']['text']
```

### Integration Tests

```python
def test_send_notification_includes_daily_count(test_db):
    """Full send flow should include counter in final payload."""
    # Setup: Insert a sent notification from earlier today
    now = int(time.time())
    test_db.execute(
        """INSERT INTO notifications
           (session_id, notification_type, backend, payload, status, created_at, sent_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("test-session", "permission", "slack", "{}", "sent", now - 3600, now - 3600)
    )
    test_db.commit()

    # Insert pending notification to send
    payload = json.dumps({
        "event_data": {"tool_name": "Edit", "tool_input": {}},
        "context": {"project_name": "test"}
    })
    test_db.execute(
        """INSERT INTO notifications
           (session_id, notification_type, backend, payload, status, created_at)
           VALUES (?, ?, ?, ?, ?, ?)""",
        ("test-session", "permission", "slack", payload, "pending", now)
    )
    test_db.commit()

    # Mock webhook and send
    with responses.RequestsMock() as rsps:
        rsps.add(responses.POST, "https://hooks.slack.com/services/test", status=200)

        # This should query count (1) + increment (2) and include (#2) in message
        sender.send_notification(test_db, 2)  # notification_id = 2

        # Verify webhook was called with counter in payload
        assert len(rsps.calls) == 1
        sent_payload = json.loads(rsps.calls[0].request.body)
        assert "(#2)" in json.dumps(sent_payload)
```

---

## 5. Performance Considerations

### Query Performance

**Expected execution time:** < 5ms

The COUNT query is efficient because:
1. Uses existing `idx_notifications_session` index
2. Status filter uses `idx_notifications_status` index
3. `created_at` comparison uses integer arithmetic

**Query plan analysis:**
```sql
EXPLAIN QUERY PLAN
SELECT COUNT(*) FROM notifications
WHERE session_id = 'test-123'
  AND backend = 'slack'
  AND status = 'sent'
  AND created_at >= 1733529600;

-- Expected: SEARCH notifications USING INDEX idx_notifications_session
```

### Optional Index Optimization

If query becomes slow with high volume, add a covering index:

```sql
CREATE INDEX idx_notifications_daily_count
ON notifications(session_id, backend, status, created_at)
WHERE status = 'sent';
```

### Resource Usage

| Resource | Impact | Notes |
|----------|--------|-------|
| CPU | Negligible | One COUNT query |
| Memory | ~100 bytes | Query result buffer |
| Disk I/O | 1 page read | Index lookup |
| Network | None | Local SQLite |

### Scalability

| Daily Volume | Query Time | Notes |
|--------------|------------|-------|
| 10 | < 1ms | Index lookup |
| 100 | < 2ms | Small result set |
| 1,000 | < 5ms | Index still effective |
| 10,000 | < 10ms | Consider archiving old data |

### Comparison to V1 Shell

| Aspect | V1 Shell | V2 SQLite |
|--------|----------|-----------|
| Query time | 1-3ms (file read) | 2-5ms (SQL) |
| Accuracy | Per-project | Per-session |
| Data source | Separate files | Existing DB |
| Concurrent safety | Limited | SQLite WAL |
| Query flexibility | None | Full SQL |

---

## Summary

**Recommended for:** V2 Python hook deployment.

**Implementation effort:** ~100 lines of code, 45 minutes.

**Risk level:** Low - no schema changes, backward compatible.

**Dependencies:** V2 hooks must be active in `~/.claude/settings.json`.
