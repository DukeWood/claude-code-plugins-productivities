#!/usr/bin/env python3
"""
Simple test runner to verify queue implementation.
Run basic smoke tests to ensure core functionality works.
"""
import sys
import os
import tempfile
from pathlib import Path

# Add lib directory to path
SLACK_DIR = Path(__file__).parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

from queue import NotificationQueue, NotificationStatus, QueueStats

def test_basic_operations():
    """Test basic queue operations."""
    print("Testing basic queue operations...")

    # Create temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        queue = NotificationQueue(db_path)

        # Test enqueue
        print("  ✓ Testing enqueue...")
        notif_id = queue.enqueue(
            event_type="permission",
            payload={"text": "Test notification"},
            session_id="test-session-123"
        )
        assert notif_id > 0, "Enqueue should return positive ID"

        # Test dequeue
        print("  ✓ Testing dequeue...")
        batch = queue.dequeue(batch_size=1)
        assert len(batch) == 1, "Should dequeue 1 notification"
        assert batch[0]["id"] == notif_id, "Should dequeue correct notification"
        assert batch[0]["status"] == NotificationStatus.PROCESSING

        # Test mark_sent
        print("  ✓ Testing mark_sent...")
        queue.mark_sent(notif_id)

        # Test get_stats
        print("  ✓ Testing get_stats...")
        stats = queue.get_stats()
        assert isinstance(stats, QueueStats)
        assert stats.sent == 1, "Should have 1 sent notification"

        queue.close()
        print("✓ Basic operations test PASSED\n")
        return True

    finally:
        # Cleanup
        if os.path.exists(db_path):
            os.remove(db_path)
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        if os.path.exists(wal_path):
            os.remove(wal_path)
        if os.path.exists(shm_path):
            os.remove(shm_path)

def test_retry_logic():
    """Test retry logic with exponential backoff."""
    print("Testing retry logic...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        queue = NotificationQueue(db_path)

        # Enqueue and fail multiple times
        print("  ✓ Testing mark_failed with retries...")
        notif_id = queue.enqueue(
            event_type="permission",
            payload={"text": "Test"},
            session_id="test-session-123"
        )

        # First failure
        queue.mark_failed(notif_id, "Error 1")

        # Check stats
        stats = queue.get_stats()
        assert stats.failed == 1, "Should have 1 failed notification"

        # Fail multiple times
        for i in range(2, 6):
            queue.mark_failed(notif_id, f"Error {i}")

        # After 5 failures, should be in dead letter queue
        queue.mark_failed(notif_id, "Error 6")

        stats = queue.get_stats()
        assert stats.dead_letter == 1, "Should have 1 dead letter notification"

        # Test get_dead_letters
        print("  ✓ Testing get_dead_letters...")
        dead_letters = queue.get_dead_letters()
        assert len(dead_letters) == 1, "Should have 1 dead letter"
        assert dead_letters[0]["id"] == notif_id

        queue.close()
        print("✓ Retry logic test PASSED\n")
        return True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        if os.path.exists(wal_path):
            os.remove(wal_path)
        if os.path.exists(shm_path):
            os.remove(shm_path)

def test_cleanup():
    """Test cleanup of old notifications."""
    print("Testing cleanup...")

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    try:
        import time
        import sqlite3
        import json

        queue = NotificationQueue(db_path)

        # Create old notification (31 days ago)
        print("  ✓ Testing cleanup_old...")
        old_timestamp = int(time.time()) - (31 * 24 * 60 * 60)

        conn = sqlite3.connect(db_path)
        conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, sent_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (0, "old-session", "permission", "slack", NotificationStatus.SENT,
             json.dumps({"text": "Old"}), old_timestamp, old_timestamp)
        )
        conn.commit()
        conn.close()

        # Create recent notification
        notif_id = queue.enqueue("permission", {"text": "Recent"}, "recent-session")
        queue.mark_sent(notif_id)

        # Cleanup old notifications
        deleted = queue.cleanup_old(days=30)
        assert deleted >= 1, "Should delete at least 1 old notification"

        # Verify only recent remains
        stats = queue.get_stats()
        assert stats.total == 1, "Should have 1 notification remaining"

        queue.close()
        print("✓ Cleanup test PASSED\n")
        return True

    finally:
        if os.path.exists(db_path):
            os.remove(db_path)
        wal_path = db_path + "-wal"
        shm_path = db_path + "-shm"
        if os.path.exists(wal_path):
            os.remove(wal_path)
        if os.path.exists(shm_path):
            os.remove(shm_path)

def main():
    """Run all smoke tests."""
    print("=" * 60)
    print("Queue Implementation Smoke Tests")
    print("=" * 60 + "\n")

    tests = [
        test_basic_operations,
        test_retry_logic,
        test_cleanup
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"✗ {test.__name__} FAILED: {e}\n")
            failed += 1

    print("=" * 60)
    print(f"Results: {passed} passed, {failed} failed")
    print("=" * 60)

    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
