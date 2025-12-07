"""
Test helper functions for V2 Slack notification tests.

These helpers are used across multiple test files for setting up test data.
"""
import json
import time


def insert_test_event(db, session_id, event_type, payload, created_at=None):
    """Helper to insert a test event."""
    created_at = created_at or int(time.time())
    cursor = db.execute(
        "INSERT INTO events (session_id, event_type, hook_payload, created_at) VALUES (?, ?, ?, ?)",
        (session_id, event_type, json.dumps(payload), created_at)
    )
    db.commit()
    return cursor.lastrowid


def insert_test_session(db, session_id, cwd, project_name=None, started_at=None):
    """Helper to insert a test session."""
    started_at = started_at or int(time.time())
    db.execute(
        """INSERT INTO sessions (session_id, cwd, project_name, started_at, last_activity_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, cwd, project_name or "test-project", started_at, started_at)
    )
    db.commit()


def insert_test_config(db, key, value, is_encrypted=0):
    """Helper to insert a test config value."""
    db.execute(
        "INSERT OR REPLACE INTO config (key, value, is_encrypted, updated_at) VALUES (?, ?, ?, ?)",
        (key, value, is_encrypted, int(time.time()))
    )
    db.commit()
