"""
Comprehensive tests for Event Queue and Retry Logic (V2).

Tests cover:
- Queue operations (enqueue, dequeue, mark_sent, mark_failed)
- Retry logic with exponential backoff
- Dead letter queue
- Thread safety
- Queue statistics and metrics
- Cleanup operations
"""
import time
import sqlite3
import json
import pytest
from unittest.mock import patch
from pathlib import Path
import sys

# Add lib directory to path
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

# Import after path setup
from notification_queue import (
    NotificationQueue,
    QueueStats,
    NotificationStatus,
    RETRY_DELAYS,
    MAX_RETRIES
)


# =============================================================================
# Basic Queue Operations Tests
# =============================================================================

class TestEnqueue:
    """Test enqueueing notifications to the queue."""

    def test_enqueue_creates_notification(self, test_db_path):
        """Test that enqueue creates a notification record."""
        queue = NotificationQueue(test_db_path)

        payload = {
            "type": "permission",
            "text": "Claude wants to edit app.ts",
            "tool": "Edit"
        }

        notif_id = queue.enqueue(
            event_type="permission",
            payload=payload,
            session_id="test-session-123"
        )

        assert notif_id is not None
        assert isinstance(notif_id, int)
        assert notif_id > 0

    def test_enqueue_sets_pending_status(self, test_db_path):
        """Test that enqueued notifications start as 'pending'."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue(
            event_type="permission",
            payload={"text": "Test"},
            session_id="test-session-123"
        )

        # Verify status in database
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row is not None
        assert row["status"] == NotificationStatus.PENDING

    def test_enqueue_stores_payload(self, test_db_path):
        """Test that payload is correctly stored as JSON."""
        queue = NotificationQueue(test_db_path)

        payload = {
            "type": "permission",
            "text": "Test notification",
            "tool": "Edit",
            "file": "app.ts"
        }

        notif_id = queue.enqueue(
            event_type="permission",
            payload=payload,
            session_id="test-session-123"
        )

        # Verify payload in database
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        stored_payload = json.loads(row["payload"])
        assert stored_payload == payload

    def test_enqueue_multiple_notifications(self, test_db_path):
        """Test enqueueing multiple notifications."""
        queue = NotificationQueue(test_db_path)

        ids = []
        for i in range(5):
            notif_id = queue.enqueue(
                event_type="permission",
                payload={"text": f"Notification {i}"},
                session_id=f"session-{i}"
            )
            ids.append(notif_id)

        # All IDs should be unique
        assert len(ids) == len(set(ids))

        # All should be sequential
        assert ids == sorted(ids)


class TestDequeue:
    """Test dequeueing notifications for processing."""

    def test_dequeue_empty_queue(self, test_db_path):
        """Test dequeueing from empty queue returns empty list."""
        queue = NotificationQueue(test_db_path)

        batch = queue.dequeue(batch_size=10)

        assert batch == []

    def test_dequeue_single_notification(self, test_db_path):
        """Test dequeueing a single notification."""
        queue = NotificationQueue(test_db_path)

        # Enqueue a notification
        payload = {"text": "Test"}
        notif_id = queue.enqueue(
            event_type="permission",
            payload=payload,
            session_id="test-session-123"
        )

        # Dequeue
        batch = queue.dequeue(batch_size=1)

        assert len(batch) == 1
        assert batch[0]["id"] == notif_id
        assert batch[0]["payload"] == payload
        assert batch[0]["status"] == NotificationStatus.PROCESSING

    def test_dequeue_respects_batch_size(self, test_db_path):
        """Test that dequeue respects batch_size parameter."""
        queue = NotificationQueue(test_db_path)

        # Enqueue 10 notifications
        for i in range(10):
            queue.enqueue(
                event_type="permission",
                payload={"text": f"Test {i}"},
                session_id="test-session-123"
            )

        # Dequeue with batch_size=3
        batch = queue.dequeue(batch_size=3)

        assert len(batch) == 3

    def test_dequeue_only_pending_or_retry_ready(self, test_db_path):
        """Test that dequeue only returns pending or retry-ready notifications."""
        queue = NotificationQueue(test_db_path)

        # Enqueue 3 notifications
        id1 = queue.enqueue("permission", {"text": "Pending"}, "session-1")
        id2 = queue.enqueue("permission", {"text": "Processing"}, "session-2")
        id3 = queue.enqueue("permission", {"text": "Sent"}, "session-3")

        # Manually update statuses
        conn = sqlite3.connect(test_db_path)
        conn.execute(
            "UPDATE notifications SET status = ? WHERE id = ?",
            (NotificationStatus.PROCESSING, id2)
        )
        conn.execute(
            "UPDATE notifications SET status = ? WHERE id = ?",
            (NotificationStatus.SENT, id3)
        )
        conn.commit()
        conn.close()

        # Dequeue should only return the pending one
        batch = queue.dequeue(batch_size=10)

        assert len(batch) == 1
        assert batch[0]["id"] == id1

    def test_dequeue_marks_as_processing(self, test_db_path):
        """Test that dequeue marks notifications as processing."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # Dequeue
        batch = queue.dequeue(batch_size=1)

        # Verify status changed to processing
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["status"] == NotificationStatus.PROCESSING

    def test_dequeue_fifo_order(self, test_db_path):
        """Test that dequeue returns notifications in FIFO order."""
        queue = NotificationQueue(test_db_path)

        # Enqueue 5 notifications with slight delays
        ids = []
        for i in range(5):
            notif_id = queue.enqueue(
                "permission",
                {"text": f"Notification {i}"},
                "session-1"
            )
            ids.append(notif_id)
            time.sleep(0.01)  # Small delay to ensure different timestamps

        # Dequeue all
        batch = queue.dequeue(batch_size=10)

        # Should be in FIFO order
        batch_ids = [n["id"] for n in batch]
        assert batch_ids == ids


class TestMarkSent:
    """Test marking notifications as successfully sent."""

    def test_mark_sent_updates_status(self, test_db_path):
        """Test that mark_sent updates status to 'sent'."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        queue.mark_sent(notif_id)

        # Verify status
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, sent_at FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["status"] == NotificationStatus.SENT
        assert row["sent_at"] is not None

    def test_mark_sent_sets_timestamp(self, test_db_path):
        """Test that mark_sent sets sent_at timestamp."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        before = int(time.time())
        queue.mark_sent(notif_id)
        after = int(time.time())

        # Verify timestamp
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT sent_at FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["sent_at"] >= before
        assert row["sent_at"] <= after

    def test_mark_sent_nonexistent_notification(self, test_db_path):
        """Test marking a non-existent notification as sent."""
        queue = NotificationQueue(test_db_path)

        # Should not raise exception
        queue.mark_sent(99999)


class TestMarkFailed:
    """Test marking notifications as failed with retry logic."""

    def test_mark_failed_first_attempt(self, test_db_path):
        """Test marking notification as failed on first attempt."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        queue.mark_failed(notif_id, "Connection timeout")

        # Verify status and retry_count
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, retry_count, error, next_retry_at FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["status"] == NotificationStatus.FAILED
        assert row["retry_count"] == 1
        assert row["error"] == "Connection timeout"
        assert row["next_retry_at"] is not None

    def test_mark_failed_exponential_backoff(self, test_db_path):
        """Test that retry delays follow exponential backoff."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # First failure: 1 minute delay
        before = int(time.time())
        queue.mark_failed(notif_id, "Error 1")

        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT next_retry_at, retry_count FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        expected_delay = RETRY_DELAYS[0]  # 60 seconds
        assert row["retry_count"] == 1
        assert row["next_retry_at"] >= before + expected_delay - 2
        assert row["next_retry_at"] <= before + expected_delay + 2

    def test_mark_failed_max_retries_dead_letter(self, test_db_path):
        """Test that exceeding max retries moves to dead letter queue."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # Fail MAX_RETRIES + 1 times
        for i in range(MAX_RETRIES + 1):
            queue.mark_failed(notif_id, f"Error {i}")

        # Verify status is dead_letter
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, retry_count FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["status"] == NotificationStatus.DEAD_LETTER
        assert row["retry_count"] >= MAX_RETRIES

    def test_mark_failed_stores_error_message(self, test_db_path):
        """Test that error message is stored."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        error_msg = "Webhook returned 500: Internal Server Error"
        queue.mark_failed(notif_id, error_msg)

        # Verify error stored
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT error FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["error"] == error_msg


# =============================================================================
# Queue Statistics Tests
# =============================================================================

class TestQueueStatistics:
    """Test queue statistics and metrics."""

    def test_get_pending_count_empty(self, test_db_path):
        """Test get_pending_count on empty queue."""
        queue = NotificationQueue(test_db_path)

        count = queue.get_pending_count()

        assert count == 0

    def test_get_pending_count_with_notifications(self, test_db_path):
        """Test get_pending_count with various statuses."""
        queue = NotificationQueue(test_db_path)

        # Enqueue 3 pending
        for i in range(3):
            queue.enqueue("permission", {"text": f"Test {i}"}, "session-1")

        # Enqueue 2 and mark as sent (shouldn't count)
        for i in range(2):
            notif_id = queue.enqueue("permission", {"text": f"Sent {i}"}, "session-2")
            queue.mark_sent(notif_id)

        # Enqueue 1 and mark as failed
        # Note: Failed notifications aren't counted until next_retry_at <= current time
        # Since mark_failed sets next_retry_at to 1 minute in the future, it won't count yet
        notif_id = queue.enqueue("permission", {"text": "Failed"}, "session-3")
        queue.mark_failed(notif_id, "Error")

        # Should only count pending (failed has next_retry_at in future)
        count = queue.get_pending_count()

        # Only 3 pending count (failed is scheduled for future retry)
        assert count == 3

    def test_get_stats(self, test_db_path):
        """Test getting comprehensive queue statistics."""
        queue = NotificationQueue(test_db_path)

        # Create notifications with various statuses
        # 3 pending
        for i in range(3):
            queue.enqueue("permission", {"text": f"Pending {i}"}, "session-1")

        # 2 sent
        for i in range(2):
            notif_id = queue.enqueue("permission", {"text": f"Sent {i}"}, "session-2")
            queue.mark_sent(notif_id)

        # 1 failed
        notif_id = queue.enqueue("permission", {"text": "Failed"}, "session-3")
        queue.mark_failed(notif_id, "Error")

        # 1 dead letter
        notif_id = queue.enqueue("permission", {"text": "Dead"}, "session-4")
        for _ in range(MAX_RETRIES + 1):
            queue.mark_failed(notif_id, "Error")

        stats = queue.get_stats()

        assert isinstance(stats, QueueStats)
        assert stats.pending == 3
        assert stats.processing == 0
        assert stats.sent == 2
        assert stats.failed == 1
        assert stats.dead_letter == 1
        assert stats.total == 7

    def test_get_stats_by_session(self, test_db_path):
        """Test getting statistics filtered by session."""
        queue = NotificationQueue(test_db_path)

        # Session 1: 3 notifications
        for i in range(3):
            queue.enqueue("permission", {"text": f"Test {i}"}, "session-1")

        # Session 2: 2 notifications
        for i in range(2):
            queue.enqueue("permission", {"text": f"Test {i}"}, "session-2")

        stats_all = queue.get_stats()
        stats_session1 = queue.get_stats(session_id="session-1")
        stats_session2 = queue.get_stats(session_id="session-2")

        assert stats_all.total == 5
        assert stats_session1.total == 3
        assert stats_session2.total == 2


class TestDeadLetterQueue:
    """Test dead letter queue functionality."""

    def test_get_dead_letters_empty(self, test_db_path):
        """Test getting dead letters from empty queue."""
        queue = NotificationQueue(test_db_path)

        dead_letters = queue.get_dead_letters()

        assert dead_letters == []

    def test_get_dead_letters(self, test_db_path):
        """Test getting all dead letter notifications."""
        queue = NotificationQueue(test_db_path)

        # Create 3 notifications that will become dead letters
        dead_ids = []
        for i in range(3):
            notif_id = queue.enqueue("permission", {"text": f"Test {i}"}, f"session-{i}")
            # Exceed max retries
            for _ in range(MAX_RETRIES + 1):
                queue.mark_failed(notif_id, f"Error {i}")
            dead_ids.append(notif_id)

        # Create 2 successful notifications
        for i in range(2):
            notif_id = queue.enqueue("permission", {"text": f"Success {i}"}, "session-ok")
            queue.mark_sent(notif_id)

        dead_letters = queue.get_dead_letters()

        assert len(dead_letters) == 3
        for dl in dead_letters:
            assert dl["id"] in dead_ids
            assert dl["status"] == NotificationStatus.DEAD_LETTER
            assert dl["retry_count"] >= MAX_RETRIES

    def test_get_dead_letters_with_limit(self, test_db_path):
        """Test getting dead letters with limit."""
        queue = NotificationQueue(test_db_path)

        # Create 5 dead letters
        for i in range(5):
            notif_id = queue.enqueue("permission", {"text": f"Test {i}"}, f"session-{i}")
            for _ in range(MAX_RETRIES + 1):
                queue.mark_failed(notif_id, "Error")

        dead_letters = queue.get_dead_letters(limit=2)

        assert len(dead_letters) == 2


# =============================================================================
# Cleanup Operations Tests
# =============================================================================

class TestCleanup:
    """Test cleanup of old notifications."""

    def test_cleanup_old_empty_queue(self, test_db_path):
        """Test cleanup on empty queue."""
        queue = NotificationQueue(test_db_path)

        deleted_count = queue.cleanup_old(days=30)

        assert deleted_count == 0

    def test_cleanup_old_notifications(self, test_db_path):
        """Test cleaning up old processed notifications."""
        queue = NotificationQueue(test_db_path)

        # Create old notifications (31 days ago)
        old_timestamp = int(time.time()) - (31 * 24 * 60 * 60)
        conn = sqlite3.connect(test_db_path)

        for i in range(3):
            conn.execute(
                """INSERT INTO notifications
                   (event_id, session_id, notification_type, backend, status, payload, created_at, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (1, f"old-session-{i}", "permission", "slack", NotificationStatus.SENT,
                 json.dumps({"text": f"Old {i}"}), old_timestamp, old_timestamp)
            )

        # Create recent notifications
        recent_timestamp = int(time.time())
        for i in range(2):
            conn.execute(
                """INSERT INTO notifications
                   (event_id, session_id, notification_type, backend, status, payload, created_at, sent_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (1, f"recent-session-{i}", "permission", "slack", NotificationStatus.SENT,
                 json.dumps({"text": f"Recent {i}"}), recent_timestamp, recent_timestamp)
            )

        conn.commit()
        conn.close()

        # Cleanup notifications older than 30 days
        deleted_count = queue.cleanup_old(days=30)

        assert deleted_count == 3

        # Verify only recent notifications remain
        stats = queue.get_stats()
        assert stats.total == 2

    def test_cleanup_only_sent_notifications(self, test_db_path):
        """Test that cleanup only removes sent/dead_letter notifications."""
        queue = NotificationQueue(test_db_path)

        # Create old notifications with different statuses
        old_timestamp = int(time.time()) - (31 * 24 * 60 * 60)
        conn = sqlite3.connect(test_db_path)

        # Old sent (should be deleted)
        conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, "session-1", "permission", "slack", NotificationStatus.SENT,
             json.dumps({"text": "Sent"}), old_timestamp, old_timestamp)
        )

        # Old pending (should NOT be deleted)
        conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (1, "session-2", "permission", "slack", NotificationStatus.PENDING,
             json.dumps({"text": "Pending"}), old_timestamp)
        )

        # Old failed (should NOT be deleted - might retry)
        conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, "session-3", "permission", "slack", NotificationStatus.FAILED,
             json.dumps({"text": "Failed"}), old_timestamp, 1)
        )

        conn.commit()
        conn.close()

        deleted_count = queue.cleanup_old(days=30)

        # Should only delete the sent notification
        assert deleted_count == 1


# =============================================================================
# Retry Logic Tests
# =============================================================================

class TestRetryLogic:
    """Test retry logic and exponential backoff."""

    def test_dequeue_includes_retry_ready(self, test_db_path):
        """Test that dequeue includes notifications ready for retry."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # Mark as failed with next_retry_at in the past
        conn = sqlite3.connect(test_db_path)
        past_time = int(time.time()) - 10  # 10 seconds ago
        conn.execute(
            """UPDATE notifications
               SET status = ?, retry_count = 1, next_retry_at = ?
               WHERE id = ?""",
            (NotificationStatus.FAILED, past_time, notif_id)
        )
        conn.commit()
        conn.close()

        # Dequeue should include this notification
        batch = queue.dequeue(batch_size=10)

        assert len(batch) == 1
        assert batch[0]["id"] == notif_id

    def test_dequeue_excludes_not_ready_retry(self, test_db_path):
        """Test that dequeue excludes notifications not ready for retry."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # Mark as failed with next_retry_at in the future
        conn = sqlite3.connect(test_db_path)
        future_time = int(time.time()) + 300  # 5 minutes from now
        conn.execute(
            """UPDATE notifications
               SET status = ?, retry_count = 1, next_retry_at = ?
               WHERE id = ?""",
            (NotificationStatus.FAILED, future_time, notif_id)
        )
        conn.commit()
        conn.close()

        # Dequeue should NOT include this notification
        batch = queue.dequeue(batch_size=10)

        assert len(batch) == 0

    def test_retry_delays_progression(self, test_db_path):
        """Test that retry delays follow the correct progression."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        for attempt, expected_delay in enumerate(RETRY_DELAYS, start=1):
            before = int(time.time())
            queue.mark_failed(notif_id, f"Error {attempt}")

            conn = sqlite3.connect(test_db_path)
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT next_retry_at, retry_count FROM notifications WHERE id = ?",
                (notif_id,)
            ).fetchone()
            conn.close()

            assert row["retry_count"] == attempt

            # Allow 2 second tolerance for test execution time
            assert row["next_retry_at"] >= before + expected_delay - 2
            assert row["next_retry_at"] <= before + expected_delay + 2


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestThreadSafety:
    """Test thread-safe operations."""

    def test_concurrent_enqueue(self, test_db_path):
        """Test concurrent enqueue operations."""
        import threading

        queue = NotificationQueue(test_db_path)
        results = []
        errors = []

        def enqueue_worker(worker_id):
            try:
                for i in range(10):
                    notif_id = queue.enqueue(
                        "permission",
                        {"text": f"Worker {worker_id} - Notification {i}"},
                        f"session-{worker_id}"
                    )
                    results.append(notif_id)
            except Exception as e:
                errors.append(e)

        # Create 5 threads, each enqueueing 10 notifications
        threads = []
        for i in range(5):
            thread = threading.Thread(target=enqueue_worker, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors
        assert len(errors) == 0

        # Verify all 50 notifications were created
        assert len(results) == 50
        assert len(set(results)) == 50  # All unique IDs

        # Verify in database
        stats = queue.get_stats()
        assert stats.total == 50

    def test_concurrent_dequeue(self, test_db_path):
        """Test concurrent dequeue operations."""
        import threading

        queue = NotificationQueue(test_db_path)

        # Enqueue 20 notifications
        for i in range(20):
            queue.enqueue("permission", {"text": f"Test {i}"}, "session-1")

        results = []
        errors = []

        def dequeue_worker():
            try:
                batch = queue.dequeue(batch_size=5)
                results.extend(batch)
            except Exception as e:
                errors.append(e)

        # Create 5 threads, each dequeueing 5 notifications
        threads = []
        for i in range(5):
            thread = threading.Thread(target=dequeue_worker)
            threads.append(thread)
            thread.start()

        # Wait for all threads to complete
        for thread in threads:
            thread.join()

        # Verify no errors
        assert len(errors) == 0

        # Verify all notifications were dequeued exactly once
        dequeued_ids = [n["id"] for n in results]
        assert len(dequeued_ids) == 20
        assert len(set(dequeued_ids)) == 20  # No duplicates


# =============================================================================
# Edge Cases Tests
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_enqueue_with_empty_payload(self, test_db_path):
        """Test enqueueing with empty payload."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue(
            event_type="permission",
            payload={},
            session_id="test-session-123"
        )

        assert notif_id is not None

    def test_enqueue_with_complex_payload(self, test_db_path):
        """Test enqueueing with complex nested payload."""
        queue = NotificationQueue(test_db_path)

        payload = {
            "type": "permission",
            "text": "Complex notification",
            "metadata": {
                "tool": "Edit",
                "file": "app.ts",
                "changes": [
                    {"line": 10, "old": "const x = 1", "new": "const x = 2"},
                    {"line": 20, "old": "const y = 1", "new": "const y = 2"}
                ]
            },
            "timestamp": time.time()
        }

        notif_id = queue.enqueue(
            event_type="permission",
            payload=payload,
            session_id="test-session-123"
        )

        # Verify payload integrity
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT payload FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        stored_payload = json.loads(row["payload"])
        assert stored_payload == payload

    def test_mark_failed_with_long_error_message(self, test_db_path):
        """Test marking failed with very long error message."""
        queue = NotificationQueue(test_db_path)

        notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")

        # Create a very long error message
        long_error = "Error: " + ("x" * 10000)

        queue.mark_failed(notif_id, long_error)

        # Verify error is stored (may be truncated by implementation)
        conn = sqlite3.connect(test_db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT error FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()
        conn.close()

        assert row["error"] is not None
        assert len(row["error"]) > 0

    def test_dequeue_with_zero_batch_size(self, test_db_path):
        """Test dequeue with batch_size=0."""
        queue = NotificationQueue(test_db_path)

        queue.enqueue("permission", {"text": "Test"}, "session-1")

        batch = queue.dequeue(batch_size=0)

        # Should return empty list
        assert batch == []

    def test_cleanup_with_zero_days(self, test_db_path):
        """Test cleanup with days=0 deletes old notifications."""
        queue = NotificationQueue(test_db_path)

        # Create notification in the past using time mocking
        past_time = int(time.time()) - 100  # 100 seconds ago
        with patch('notification_queue.time') as mock_time:
            mock_time.time.return_value = past_time
            notif_id = queue.enqueue("permission", {"text": "Test"}, "session-1")
            queue.mark_sent(notif_id)

        # Cleanup with 0 days should delete notifications created before now
        deleted_count = queue.cleanup_old(days=0)

        assert deleted_count >= 1
