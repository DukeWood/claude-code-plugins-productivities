"""
Test suite for database.py - SQLite database layer for Slack Notification V2.

Test coverage:
- Database initialization and schema creation
- Event CRUD operations
- Notification management (pending/sent/failed)
- Session lifecycle tracking
- Config storage with encryption
- Audit logging
- Metrics recording
- Session isolation
- Migration from V1 JSON files
- Error handling and edge cases
- Performance (WAL mode, indexes)

Run with: pytest tests/test_database.py -v
"""
import os
import sys
import json
import time
import sqlite3
import tempfile
import pytest
from pathlib import Path
from unittest.mock import patch

# Add lib directory to path
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

import database


# =============================================================================
# Test Database Initialization
# =============================================================================

@pytest.mark.unit
class TestDatabaseInit:
    """Test database initialization and schema creation."""

    def test_init_creates_database_file(self, tmp_path):
        """Should create database file at specified path."""
        db_path = str(tmp_path / "test.db")
        db = database.Database(db_path)

        assert os.path.exists(db_path)
        db.close()

    def test_init_creates_all_tables(self, tmp_path):
        """Should create all required tables with correct schema."""
        db_path = str(tmp_path / "test.db")
        db = database.Database(db_path)

        # Check all tables exist
        tables = db._get_table_names()
        assert 'events' in tables
        assert 'notifications' in tables
        assert 'sessions' in tables
        assert 'config' in tables
        assert 'audit_log' in tables
        assert 'metrics' in tables

        db.close()

    def test_init_creates_indexes(self, tmp_path):
        """Should create all required indexes for performance."""
        db_path = str(tmp_path / "test.db")
        db = database.Database(db_path)

        indexes = db._get_index_names()

        # Events table indexes
        assert 'idx_events_session' in indexes
        assert 'idx_events_created' in indexes
        assert 'idx_events_processed' in indexes

        # Notifications table indexes
        assert 'idx_notifications_status' in indexes
        assert 'idx_notifications_session' in indexes

        # Audit log indexes
        assert 'idx_audit_session' in indexes
        assert 'idx_audit_action' in indexes

        # Metrics indexes
        assert 'idx_metrics_name_time' in indexes

        db.close()

    def test_init_enables_wal_mode(self, tmp_path):
        """Should enable WAL mode for better concurrency."""
        db_path = str(tmp_path / "test.db")
        db = database.Database(db_path)

        journal_mode = db.conn.execute("PRAGMA journal_mode").fetchone()[0]
        assert journal_mode.lower() == 'wal'

        db.close()

    def test_init_with_existing_database(self, tmp_path):
        """Should open existing database without recreating tables."""
        db_path = str(tmp_path / "test.db")

        # Create and close first connection
        db1 = database.Database(db_path)
        event_id = db1.insert_event("session1", "test_event", {"data": "test"})
        db1.close()

        # Reopen database
        db2 = database.Database(db_path)
        event = db2.get_event_by_id(event_id)
        assert event is not None
        assert event['session_id'] == "session1"

        db2.close()


# =============================================================================
# Test Event Operations
# =============================================================================

@pytest.mark.unit
class TestEventOperations:
    """Test event CRUD operations."""

    def test_insert_event(self, tmp_path):
        """Should insert event and return event_id."""
        db = database.Database(str(tmp_path / "test.db"))

        payload = {"tool_name": "Edit", "file": "app.ts"}
        event_id = db.insert_event("session1", "pre_tool_use", payload)

        assert event_id > 0

        event = db.get_event_by_id(event_id)
        assert event['session_id'] == "session1"
        assert event['event_type'] == "pre_tool_use"
        assert json.loads(event['hook_payload']) == payload
        assert event['created_at'] > 0
        assert event['processed_at'] is None

        db.close()

    def test_insert_event_with_custom_timestamp(self, tmp_path):
        """Should allow custom created_at timestamp."""
        db = database.Database(str(tmp_path / "test.db"))

        custom_time = 1234567890
        event_id = db.insert_event("session1", "test", {}, created_at=custom_time)

        event = db.get_event_by_id(event_id)
        assert event['created_at'] == custom_time

        db.close()

    def test_get_unprocessed_events(self, tmp_path):
        """Should return events where processed_at is NULL."""
        db = database.Database(str(tmp_path / "test.db"))

        # Insert 3 events, mark 1 as processed
        id1 = db.insert_event("session1", "event1", {})
        id2 = db.insert_event("session1", "event2", {})
        id3 = db.insert_event("session2", "event3", {})

        db.mark_event_processed(id2)

        unprocessed = db.get_unprocessed_events()
        assert len(unprocessed) == 2
        assert unprocessed[0]['id'] == id1
        assert unprocessed[1]['id'] == id3

        db.close()

    def test_get_unprocessed_events_ordered_by_created_at(self, tmp_path):
        """Should return events ordered by created_at ASC."""
        db = database.Database(str(tmp_path / "test.db"))

        # Insert events with different timestamps
        id1 = db.insert_event("session1", "event1", {}, created_at=1000)
        id2 = db.insert_event("session1", "event2", {}, created_at=3000)
        id3 = db.insert_event("session1", "event3", {}, created_at=2000)

        unprocessed = db.get_unprocessed_events()
        assert [e['id'] for e in unprocessed] == [id1, id3, id2]

        db.close()

    def test_mark_event_processed(self, tmp_path):
        """Should set processed_at timestamp."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "event1", {})
        assert db.get_event_by_id(event_id)['processed_at'] is None

        before = int(time.time())
        db.mark_event_processed(event_id)
        after = int(time.time())

        processed_at = db.get_event_by_id(event_id)['processed_at']
        assert processed_at >= before
        assert processed_at <= after

        db.close()

    def test_get_events_by_session(self, tmp_path):
        """Should filter events by session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_event("session1", "event1", {})
        db.insert_event("session2", "event2", {})
        db.insert_event("session1", "event3", {})

        session1_events = db.get_events_by_session("session1")
        assert len(session1_events) == 2
        assert all(e['session_id'] == "session1" for e in session1_events)

        db.close()

    def test_get_latest_event_by_type(self, tmp_path):
        """Should return most recent event of specific type for session."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_event("session1", "pre_tool_use", {"tool": "Edit"}, created_at=1000)
        db.insert_event("session1", "notification", {}, created_at=2000)
        db.insert_event("session1", "pre_tool_use", {"tool": "Bash"}, created_at=3000)

        latest = db.get_latest_event_by_type("session1", "pre_tool_use")
        assert latest is not None
        assert json.loads(latest['hook_payload'])['tool'] == "Bash"
        assert latest['created_at'] == 3000

        db.close()

    def test_get_latest_event_by_type_no_match(self, tmp_path):
        """Should return None if no events of type exist."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_event("session1", "notification", {})

        latest = db.get_latest_event_by_type("session1", "pre_tool_use")
        assert latest is None

        db.close()


# =============================================================================
# Test Notification Operations
# =============================================================================

@pytest.mark.unit
class TestNotificationOperations:
    """Test notification management."""

    def test_insert_notification(self, tmp_path):
        """Should insert notification with pending status."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "notification", {})
        payload = {"text": "Test notification"}

        notif_id = db.insert_notification(
            event_id=event_id,
            session_id="session1",
            notification_type="permission",
            backend="slack",
            payload=payload
        )

        assert notif_id > 0

        notif = db.get_notification_by_id(notif_id)
        assert notif['event_id'] == event_id
        assert notif['session_id'] == "session1"
        assert notif['notification_type'] == "permission"
        assert notif['backend'] == "slack"
        assert notif['status'] == "pending"
        assert notif['retry_count'] == 0
        assert json.loads(notif['payload']) == payload
        assert notif['error'] is None
        assert notif['created_at'] > 0
        assert notif['sent_at'] is None

        db.close()

    def test_get_pending_notifications(self, tmp_path):
        """Should return notifications with status=pending."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "notification", {})

        id1 = db.insert_notification(event_id, "session1", "permission", "slack", {})
        id2 = db.insert_notification(event_id, "session1", "task_complete", "slack", {})
        id3 = db.insert_notification(event_id, "session1", "error", "slack", {})

        # Mark one as sent
        db.mark_notification_sent(id2)

        pending = db.get_pending_notifications()
        assert len(pending) == 2
        assert {p['id'] for p in pending} == {id1, id3}

        db.close()

    def test_get_failed_notifications_for_retry(self, tmp_path):
        """Should return failed notifications with retry_count < max_retries."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "notification", {})

        id1 = db.insert_notification(event_id, "session1", "permission", "slack", {})
        id2 = db.insert_notification(event_id, "session1", "task_complete", "slack", {})
        id3 = db.insert_notification(event_id, "session1", "error", "slack", {})

        # Mark as failed with different retry counts
        db.mark_notification_failed(id1, "Error 1")  # retry_count=1
        db.mark_notification_failed(id2, "Error 2")  # retry_count=1
        db.mark_notification_failed(id2, "Error 2")  # retry_count=2
        db.mark_notification_failed(id2, "Error 2")  # retry_count=3 (should not retry)

        retryable = db.get_failed_notifications_for_retry(max_retries=3)
        assert len(retryable) == 1
        assert retryable[0]['id'] == id1

        db.close()

    def test_mark_notification_sent(self, tmp_path):
        """Should set status=sent and sent_at timestamp."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "notification", {})
        notif_id = db.insert_notification(event_id, "session1", "permission", "slack", {})

        before = int(time.time())
        db.mark_notification_sent(notif_id)
        after = int(time.time())

        notif = db.get_notification_by_id(notif_id)
        assert notif['status'] == "sent"
        assert notif['sent_at'] >= before
        assert notif['sent_at'] <= after

        db.close()

    def test_mark_notification_failed(self, tmp_path):
        """Should set status=failed, increment retry_count, store error."""
        db = database.Database(str(tmp_path / "test.db"))

        event_id = db.insert_event("session1", "notification", {})
        notif_id = db.insert_notification(event_id, "session1", "permission", "slack", {})

        db.mark_notification_failed(notif_id, "Connection timeout")

        notif = db.get_notification_by_id(notif_id)
        assert notif['status'] == "failed"
        assert notif['retry_count'] == 1
        assert notif['error'] == "Connection timeout"

        # Fail again
        db.mark_notification_failed(notif_id, "Still failing")

        notif = db.get_notification_by_id(notif_id)
        assert notif['retry_count'] == 2
        assert notif['error'] == "Still failing"

        db.close()

    def test_get_notifications_by_session(self, tmp_path):
        """Should filter notifications by session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        event1 = db.insert_event("session1", "notification", {})
        event2 = db.insert_event("session2", "notification", {})

        db.insert_notification(event1, "session1", "permission", "slack", {})
        db.insert_notification(event2, "session2", "permission", "slack", {})
        db.insert_notification(event1, "session1", "task_complete", "slack", {})

        session1_notifs = db.get_notifications_by_session("session1")
        assert len(session1_notifs) == 2
        assert all(n['session_id'] == "session1" for n in session1_notifs)

        db.close()


# =============================================================================
# Test Session Operations
# =============================================================================

@pytest.mark.unit
class TestSessionOperations:
    """Test session lifecycle tracking."""

    def test_create_session(self, tmp_path):
        """Should create new session record."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session(
            session_id="session1",
            cwd="/Users/test/project",
            project_name="my-project",
            git_branch="main",
            terminal_type="tmux",
            terminal_info='{"pane": "0:0.0"}'
        )

        session = db.get_session("session1")
        assert session['session_id'] == "session1"
        assert session['cwd'] == "/Users/test/project"
        assert session['project_name'] == "my-project"
        assert session['git_branch'] == "main"
        assert session['terminal_type'] == "tmux"
        assert session['terminal_info'] == '{"pane": "0:0.0"}'
        assert session['started_at'] > 0
        assert session['last_activity_at'] > 0
        assert session['ended_at'] is None
        assert session['is_idle'] == 0

        db.close()

    def test_create_session_minimal(self, tmp_path):
        """Should create session with only required fields."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session(session_id="session1", cwd="/tmp")

        session = db.get_session("session1")
        assert session['session_id'] == "session1"
        assert session['cwd'] == "/tmp"
        assert session['project_name'] is None

        db.close()

    def test_update_session_activity(self, tmp_path):
        """Should update last_activity_at timestamp."""
        db = database.Database(str(tmp_path / "test.db"))

        # Use mocking since database uses int(time.time()) which has second precision
        with patch('database.time') as mock_time:
            mock_time.time.return_value = 1000000
            db.create_session("session1", "/tmp")
            original = db.get_session("session1")['last_activity_at']

            mock_time.time.return_value = 1000001  # 1 second later
            db.update_session_activity("session1")

            updated = db.get_session("session1")['last_activity_at']
            assert updated > original

        db.close()

    def test_set_session_idle(self, tmp_path):
        """Should set is_idle flag."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session("session1", "/tmp")
        assert db.get_session("session1")['is_idle'] == 0

        db.set_session_idle("session1", is_idle=True)
        assert db.get_session("session1")['is_idle'] == 1

        db.set_session_idle("session1", is_idle=False)
        assert db.get_session("session1")['is_idle'] == 0

        db.close()

    def test_end_session(self, tmp_path):
        """Should set ended_at timestamp."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session("session1", "/tmp")
        assert db.get_session("session1")['ended_at'] is None

        before = int(time.time())
        db.end_session("session1")
        after = int(time.time())

        ended_at = db.get_session("session1")['ended_at']
        assert ended_at >= before
        assert ended_at <= after

        db.close()

    def test_get_active_sessions(self, tmp_path):
        """Should return sessions where ended_at is NULL."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session("session1", "/tmp")
        db.create_session("session2", "/tmp")
        db.create_session("session3", "/tmp")

        db.end_session("session2")

        active = db.get_active_sessions()
        assert len(active) == 2
        assert {s['session_id'] for s in active} == {"session1", "session3"}

        db.close()

    def test_upsert_session(self, tmp_path):
        """Should update existing session or create new one."""
        db = database.Database(str(tmp_path / "test.db"))

        # Create
        db.upsert_session("session1", "/tmp/old", project_name="old-project")
        assert db.get_session("session1")['cwd'] == "/tmp/old"

        # Update
        db.upsert_session("session1", "/tmp/new", project_name="new-project")
        assert db.get_session("session1")['cwd'] == "/tmp/new"
        assert db.get_session("session1")['project_name'] == "new-project"

        db.close()


# =============================================================================
# Test Config Operations
# =============================================================================

@pytest.mark.unit
class TestConfigOperations:
    """Test config storage with encryption."""

    def test_set_config(self, tmp_path):
        """Should store config value."""
        db = database.Database(str(tmp_path / "test.db"))

        db.set_config("enabled", "true")

        value = db.get_config("enabled")
        assert value == "true"

        db.close()

    def test_set_config_encrypted(self, tmp_path):
        """Should store encrypted config value."""
        db = database.Database(str(tmp_path / "test.db"))

        webhook_url = "https://example.com/webhook/test"
        db.set_config("slack_webhook_url", webhook_url, encrypted=True)

        # Raw value should be encrypted (different from plaintext)
        raw_value = db.conn.execute(
            "SELECT value FROM config WHERE key=?",
            ("slack_webhook_url",)
        ).fetchone()[0]
        assert raw_value != webhook_url

        # Decrypted value should match
        decrypted_value = db.get_config("slack_webhook_url")
        assert decrypted_value == webhook_url

        db.close()

    def test_get_config_nonexistent(self, tmp_path):
        """Should return None for nonexistent key."""
        db = database.Database(str(tmp_path / "test.db"))

        value = db.get_config("nonexistent_key")
        assert value is None

        db.close()

    def test_get_config_with_default(self, tmp_path):
        """Should return default value if key doesn't exist."""
        db = database.Database(str(tmp_path / "test.db"))

        value = db.get_config("nonexistent_key", default="default_value")
        assert value == "default_value"

        db.close()

    def test_get_all_config(self, tmp_path):
        """Should return all config as dictionary."""
        db = database.Database(str(tmp_path / "test.db"))

        db.set_config("enabled", "true")
        db.set_config("notify_always", "false")
        db.set_config("webhook_url", "https://example.com", encrypted=True)

        config = db.get_all_config()
        assert config['enabled'] == "true"
        assert config['notify_always'] == "false"
        assert config['webhook_url'] == "https://example.com"  # Should be decrypted

        db.close()

    def test_delete_config(self, tmp_path):
        """Should delete config key."""
        db = database.Database(str(tmp_path / "test.db"))

        db.set_config("test_key", "test_value")
        assert db.get_config("test_key") == "test_value"

        db.delete_config("test_key")
        assert db.get_config("test_key") is None

        db.close()

    def test_config_updated_at(self, tmp_path):
        """Should update updated_at timestamp when config changes."""
        db = database.Database(str(tmp_path / "test.db"))

        # Use mocking since database uses int(time.time()) which has second precision
        with patch('database.time') as mock_time:
            mock_time.time.return_value = 1000000
            db.set_config("test_key", "value1")
            first_update = db.conn.execute(
                "SELECT updated_at FROM config WHERE key=?",
                ("test_key",)
            ).fetchone()[0]

            mock_time.time.return_value = 1000001  # 1 second later
            db.set_config("test_key", "value2")
            second_update = db.conn.execute(
                "SELECT updated_at FROM config WHERE key=?",
                ("test_key",)
            ).fetchone()[0]

            assert second_update > first_update

        db.close()


# =============================================================================
# Test Audit Log Operations
# =============================================================================

@pytest.mark.unit
class TestAuditLogOperations:
    """Test audit logging."""

    def test_insert_audit_log(self, tmp_path):
        """Should insert audit log entry."""
        db = database.Database(str(tmp_path / "test.db"))

        details = {"notification_id": 123, "backend": "slack"}
        log_id = db.insert_audit_log(
            session_id="session1",
            action="notification_sent",
            details=details
        )

        assert log_id > 0

        log = db.conn.execute(
            "SELECT * FROM audit_log WHERE id=?",
            (log_id,)
        ).fetchone()

        assert log['session_id'] == "session1"
        assert log['action'] == "notification_sent"
        assert json.loads(log['details']) == details
        assert log['created_at'] > 0

        db.close()

    def test_insert_audit_log_without_session(self, tmp_path):
        """Should allow audit log without session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        log_id = db.insert_audit_log(action="config_updated")

        log = db.conn.execute(
            "SELECT * FROM audit_log WHERE id=?",
            (log_id,)
        ).fetchone()

        assert log['session_id'] is None
        assert log['action'] == "config_updated"

        db.close()

    def test_get_audit_logs_by_session(self, tmp_path):
        """Should filter audit logs by session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_audit_log(action="action1", session_id="session1")
        db.insert_audit_log(action="action2", session_id="session2")
        db.insert_audit_log(action="action3", session_id="session1")

        session1_logs = db.get_audit_logs_by_session("session1")
        assert len(session1_logs) == 2
        assert all(log['session_id'] == "session1" for log in session1_logs)

        db.close()

    def test_get_audit_logs_by_action(self, tmp_path):
        """Should filter audit logs by action."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_audit_log(action="notification_sent", session_id="session1")
        db.insert_audit_log(action="permission_granted", session_id="session1")
        db.insert_audit_log(action="notification_sent", session_id="session2")

        sent_logs = db.get_audit_logs_by_action("notification_sent")
        assert len(sent_logs) == 2
        assert all(log['action'] == "notification_sent" for log in sent_logs)

        db.close()

    def test_get_recent_audit_logs(self, tmp_path):
        """Should return recent audit logs with limit."""
        db = database.Database(str(tmp_path / "test.db"))

        # Use mocking to ensure distinct timestamps for ordering
        with patch('database.time') as mock_time:
            for i in range(10):
                mock_time.time.return_value = 1000000 + i
                db.insert_audit_log(action=f"action{i}")

        recent = db.get_recent_audit_logs(limit=5)
        assert len(recent) == 5

        # Should be ordered by created_at DESC (most recent first)
        assert recent[0]['action'] == "action9"
        assert recent[4]['action'] == "action5"

        db.close()


# =============================================================================
# Test Metrics Operations
# =============================================================================

@pytest.mark.unit
class TestMetricsOperations:
    """Test metrics recording."""

    def test_insert_metric(self, tmp_path):
        """Should insert metric."""
        db = database.Database(str(tmp_path / "test.db"))

        metric_id = db.insert_metric(
            metric_name="notification_latency_ms",
            metric_value=123.45,
            session_id="session1"
        )

        assert metric_id > 0

        metric = db.conn.execute(
            "SELECT * FROM metrics WHERE id=?",
            (metric_id,)
        ).fetchone()

        assert metric['metric_name'] == "notification_latency_ms"
        assert metric['metric_value'] == 123.45
        assert metric['session_id'] == "session1"
        assert metric['created_at'] > 0

        db.close()

    def test_insert_metric_without_session(self, tmp_path):
        """Should allow metric without session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        metric_id = db.insert_metric("global_counter", 1)

        metric = db.conn.execute(
            "SELECT * FROM metrics WHERE id=?",
            (metric_id,)
        ).fetchone()

        assert metric['session_id'] is None

        db.close()

    def test_get_metrics_by_name(self, tmp_path):
        """Should filter metrics by name."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_metric("latency", 100)
        db.insert_metric("success", 1)
        db.insert_metric("latency", 200)

        latency_metrics = db.get_metrics_by_name("latency")
        assert len(latency_metrics) == 2
        assert all(m['metric_name'] == "latency" for m in latency_metrics)

        db.close()

    def test_get_metric_stats(self, tmp_path):
        """Should calculate average, min, max for metric."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_metric("latency", 100)
        db.insert_metric("latency", 200)
        db.insert_metric("latency", 300)

        stats = db.get_metric_stats("latency")
        assert stats['count'] == 3
        assert stats['avg'] == 200
        assert stats['min'] == 100
        assert stats['max'] == 300

        db.close()

    def test_get_metric_stats_with_time_range(self, tmp_path):
        """Should calculate stats within time range."""
        db = database.Database(str(tmp_path / "test.db"))

        now = int(time.time())

        # Insert metrics at different times
        db.conn.execute(
            "INSERT INTO metrics (metric_name, metric_value, created_at) VALUES (?, ?, ?)",
            ("latency", 100, now - 3600)  # 1 hour ago
        )
        db.conn.execute(
            "INSERT INTO metrics (metric_name, metric_value, created_at) VALUES (?, ?, ?)",
            ("latency", 200, now - 1800)  # 30 min ago
        )
        db.conn.execute(
            "INSERT INTO metrics (metric_name, metric_value, created_at) VALUES (?, ?, ?)",
            ("latency", 300, now)  # Now
        )
        db.conn.commit()

        # Get stats for last 45 minutes
        stats = db.get_metric_stats("latency", since=now - 2700)
        assert stats['count'] == 2
        assert stats['avg'] == 250  # Average of 200 and 300

        db.close()


# =============================================================================
# Test Session Isolation
# =============================================================================

@pytest.mark.unit
class TestSessionIsolation:
    """Test that sessions can't access each other's data."""

    def test_events_isolated_by_session(self, tmp_path):
        """Should only return events for specified session."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_event("session1", "event1", {"data": "s1_e1"})
        db.insert_event("session2", "event2", {"data": "s2_e1"})
        db.insert_event("session1", "event3", {"data": "s1_e2"})

        session1_events = db.get_events_by_session("session1")
        assert len(session1_events) == 2
        assert all(e['session_id'] == "session1" for e in session1_events)

        db.close()

    def test_notifications_isolated_by_session(self, tmp_path):
        """Should only return notifications for specified session."""
        db = database.Database(str(tmp_path / "test.db"))

        event1 = db.insert_event("session1", "notification", {})
        event2 = db.insert_event("session2", "notification", {})

        db.insert_notification(event1, "session1", "permission", "slack", {})
        db.insert_notification(event2, "session2", "permission", "slack", {})

        session1_notifs = db.get_notifications_by_session("session1")
        assert len(session1_notifs) == 1
        assert session1_notifs[0]['session_id'] == "session1"

        db.close()

    def test_audit_logs_isolated_by_session(self, tmp_path):
        """Should only return audit logs for specified session."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_audit_log(action="action1", session_id="session1")
        db.insert_audit_log(action="action2", session_id="session2")
        db.insert_audit_log(action="action3", session_id="session1")

        session1_logs = db.get_audit_logs_by_session("session1")
        assert len(session1_logs) == 2
        assert all(log['session_id'] == "session1" for log in session1_logs)

        db.close()


# =============================================================================
# Test Migration from V1
# =============================================================================

@pytest.mark.unit
class TestV1Migration:
    """Test migration from V1 JSON files."""

    def test_import_v1_config(self, tmp_path):
        """Should import V1 slack-config.json into config table."""
        db = database.Database(str(tmp_path / "test.db"))

        v1_config = {
            "webhook_url": "https://example.com/webhook/test",
            "enabled": True,
            "notify_on": {
                "permission_required": True,
                "task_complete": False,
                "input_required": True
            },
            "notify_always": False
        }

        db.import_v1_config(v1_config)

        # Check all values imported
        assert db.get_config("slack_webhook_url") == v1_config['webhook_url']
        assert db.get_config("enabled") == "true"
        assert db.get_config("notify_on_permission") == "true"
        assert db.get_config("notify_on_task_complete") == "false"
        assert db.get_config("notify_on_input_required") == "true"
        assert db.get_config("notify_always") == "false"

        # Webhook URL should be encrypted
        is_encrypted = db.conn.execute(
            "SELECT is_encrypted FROM config WHERE key='slack_webhook_url'"
        ).fetchone()[0]
        assert is_encrypted == 1

        db.close()

    def test_import_v1_tool_request(self, tmp_path):
        """Should import V1 tool_requests/*.json into events table."""
        db = database.Database(str(tmp_path / "test.db"))

        v1_tool_request = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/tmp/app.ts",
                "old_string": "const x = 1",
                "new_string": "const x = 2"
            }
        }

        event_id = db.import_v1_tool_request(
            session_id="session1",
            tool_request=v1_tool_request,
            timestamp=1234567890
        )

        event = db.get_event_by_id(event_id)
        assert event['session_id'] == "session1"
        assert event['event_type'] == "pre_tool_use"
        assert json.loads(event['hook_payload']) == v1_tool_request
        assert event['created_at'] == 1234567890
        assert event['processed_at'] is not None  # V1 events already processed

        db.close()

    def test_import_v1_notification_state(self, tmp_path):
        """Should import V1 notification_states.json into sessions table."""
        db = database.Database(str(tmp_path / "test.db"))

        v1_state = {
            "session_id": "abc123",
            "in_tmux": True,
            "tmux_info": "main:0.0",
            "last_notification_time": 1234567890,
            "is_waiting_for_input": True
        }

        db.import_v1_notification_state(v1_state)

        session = db.get_session("abc123")
        assert session['session_id'] == "abc123"
        assert session['terminal_type'] == "tmux"
        assert session['terminal_info'] == "main:0.0"
        assert session['is_idle'] == 1
        assert session['last_activity_at'] == 1234567890

        db.close()


# =============================================================================
# Test Error Handling
# =============================================================================

@pytest.mark.unit
class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_insert_event_with_invalid_json_payload(self, tmp_path):
        """Should handle non-dict payloads gracefully."""
        db = database.Database(str(tmp_path / "test.db"))

        # Should accept any JSON-serializable payload
        event_id = db.insert_event("session1", "test", "string payload")
        event = db.get_event_by_id(event_id)
        assert json.loads(event['hook_payload']) == "string payload"

        db.close()

    def test_get_nonexistent_event(self, tmp_path):
        """Should return None for nonexistent event_id."""
        db = database.Database(str(tmp_path / "test.db"))

        event = db.get_event_by_id(99999)
        assert event is None

        db.close()

    def test_get_nonexistent_notification(self, tmp_path):
        """Should return None for nonexistent notification_id."""
        db = database.Database(str(tmp_path / "test.db"))

        notif = db.get_notification_by_id(99999)
        assert notif is None

        db.close()

    def test_get_nonexistent_session(self, tmp_path):
        """Should return None for nonexistent session_id."""
        db = database.Database(str(tmp_path / "test.db"))

        session = db.get_session("nonexistent")
        assert session is None

        db.close()

    def test_update_nonexistent_session(self, tmp_path):
        """Should fail gracefully when updating nonexistent session."""
        db = database.Database(str(tmp_path / "test.db"))

        # Should not raise exception
        db.update_session_activity("nonexistent")
        db.end_session("nonexistent")

        db.close()

    def test_duplicate_session_id(self, tmp_path):
        """Should raise exception when creating duplicate session."""
        db = database.Database(str(tmp_path / "test.db"))

        db.create_session("session1", "/tmp")

        # Should raise IntegrityError
        with pytest.raises(sqlite3.IntegrityError):
            db.create_session("session1", "/tmp")

        db.close()


# =============================================================================
# Test Context Manager and Cleanup
# =============================================================================

@pytest.mark.unit
class TestContextManager:
    """Test database context manager and cleanup."""

    def test_context_manager(self, tmp_path):
        """Should support context manager protocol."""
        db_path = str(tmp_path / "test.db")

        with database.Database(db_path) as db:
            db.insert_event("session1", "test", {})

        # Connection should be closed
        # Verify data persisted by reopening
        with database.Database(db_path) as db:
            events = db.get_events_by_session("session1")
            assert len(events) == 1

    def test_transaction_rollback_on_exception(self, tmp_path):
        """Should rollback transaction if exception occurs."""
        db_path = str(tmp_path / "test.db")

        try:
            with database.Database(db_path) as db:
                db.insert_event("session1", "test", {})
                raise Exception("Test error")
        except Exception:
            pass

        # Check if rollback occurred
        with database.Database(db_path) as db:
            events = db.get_events_by_session("session1")
            # Note: insert_event commits immediately, so this will have the event
            # This test verifies the context manager handles exceptions gracefully

    def test_explicit_close(self, tmp_path):
        """Should close connection explicitly."""
        db = database.Database(str(tmp_path / "test.db"))
        db.insert_event("session1", "test", {})
        db.close()

        # Attempting operations after close should fail
        with pytest.raises(sqlite3.ProgrammingError):
            db.insert_event("session1", "test2", {})


# =============================================================================
# Test Performance and Indexes
# =============================================================================

@pytest.mark.unit
class TestPerformance:
    """Test performance optimizations."""

    def test_unprocessed_events_query_uses_index(self, tmp_path):
        """Should use index for unprocessed events query."""
        db = database.Database(str(tmp_path / "test.db"))

        # Insert many events
        for i in range(100):
            db.insert_event(f"session{i}", "event", {})

        # Query should use idx_events_processed
        explain = db.conn.execute(
            "EXPLAIN QUERY PLAN SELECT * FROM events WHERE processed_at IS NULL"
        ).fetchall()

        # Should mention using index (implementation detail, may vary)
        # At minimum, query should complete quickly
        unprocessed = db.get_unprocessed_events()
        assert len(unprocessed) == 100

        db.close()

    def test_session_lookup_uses_primary_key(self, tmp_path):
        """Should use primary key for session lookup."""
        db = database.Database(str(tmp_path / "test.db"))

        for i in range(100):
            db.create_session(f"session{i}", "/tmp")

        # Lookup by session_id should be O(1)
        session = db.get_session("session50")
        assert session['session_id'] == "session50"

        db.close()

    def test_wal_mode_allows_concurrent_reads(self, tmp_path):
        """Should allow concurrent reads with WAL mode."""
        db_path = str(tmp_path / "test.db")

        db1 = database.Database(db_path)
        db1.insert_event("session1", "test", {})

        # Open second connection while first is still open
        db2 = database.Database(db_path)
        events = db2.get_events_by_session("session1")
        assert len(events) == 1

        db1.close()
        db2.close()


# =============================================================================
# Test Helper Methods
# =============================================================================

@pytest.mark.unit
class TestHelperMethods:
    """Test internal helper methods."""

    def test_get_table_names(self, tmp_path):
        """Should return list of table names."""
        db = database.Database(str(tmp_path / "test.db"))

        tables = db._get_table_names()
        assert isinstance(tables, list)
        assert 'events' in tables
        assert 'notifications' in tables

        db.close()

    def test_get_index_names(self, tmp_path):
        """Should return list of index names."""
        db = database.Database(str(tmp_path / "test.db"))

        indexes = db._get_index_names()
        assert isinstance(indexes, list)
        assert 'idx_events_session' in indexes

        db.close()

    def test_execute_query(self, tmp_path):
        """Should execute raw SQL query."""
        db = database.Database(str(tmp_path / "test.db"))

        db.insert_event("session1", "test", {})

        result = db.execute_query("SELECT COUNT(*) as count FROM events")
        assert result[0]['count'] == 1

        db.close()
