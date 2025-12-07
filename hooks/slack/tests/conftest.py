"""
Shared pytest fixtures for Slack Notification V2 tests.

This module provides:
- Temporary test database with schema
- Sample hook payloads
- Mock Slack webhook server
- Test configuration helpers
"""
import os
import sys
import json
import sqlite3
import tempfile
import pytest
from pathlib import Path

# Add lib directory to path for imports
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))


# =============================================================================
# Database Fixtures
# =============================================================================

@pytest.fixture
def test_db_path(tmp_path):
    """Provide a temporary database path."""
    return str(tmp_path / "test_notifications.db")


@pytest.fixture
def test_db(test_db_path):
    """Create a temporary test database with V2 schema."""
    conn = sqlite3.connect(test_db_path)
    conn.row_factory = sqlite3.Row

    # Create schema
    conn.executescript("""
        -- Events table: raw hook events
        CREATE TABLE IF NOT EXISTS events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT NOT NULL,
            event_type TEXT NOT NULL,
            hook_payload TEXT NOT NULL,
            created_at INTEGER NOT NULL,
            processed_at INTEGER
        );
        CREATE INDEX IF NOT EXISTS idx_events_session ON events(session_id);
        CREATE INDEX IF NOT EXISTS idx_events_created ON events(created_at);
        CREATE INDEX IF NOT EXISTS idx_events_processed ON events(processed_at);

        -- Notifications table: pending/sent/failed
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id INTEGER NOT NULL,
            session_id TEXT NOT NULL,
            notification_type TEXT NOT NULL,
            backend TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            retry_count INTEGER DEFAULT 0,
            payload TEXT NOT NULL,
            error TEXT,
            created_at INTEGER NOT NULL,
            sent_at INTEGER,
            FOREIGN KEY (event_id) REFERENCES events(id)
        );
        CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
        CREATE INDEX IF NOT EXISTS idx_notifications_session ON notifications(session_id);

        -- Sessions table: active session metadata
        CREATE TABLE IF NOT EXISTS sessions (
            session_id TEXT PRIMARY KEY,
            project_name TEXT,
            cwd TEXT NOT NULL,
            git_branch TEXT,
            terminal_type TEXT,
            terminal_info TEXT,
            started_at INTEGER NOT NULL,
            last_activity_at INTEGER NOT NULL,
            ended_at INTEGER,
            is_idle INTEGER DEFAULT 0
        );

        -- Config table: encrypted settings
        CREATE TABLE IF NOT EXISTS config (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            is_encrypted INTEGER DEFAULT 0,
            updated_at INTEGER NOT NULL
        );

        -- Audit log table
        CREATE TABLE IF NOT EXISTS audit_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id TEXT,
            action TEXT NOT NULL,
            details TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_audit_session ON audit_log(session_id);
        CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_log(action);

        -- Metrics table
        CREATE TABLE IF NOT EXISTS metrics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            metric_name TEXT NOT NULL,
            metric_value REAL NOT NULL,
            session_id TEXT,
            created_at INTEGER NOT NULL
        );
        CREATE INDEX IF NOT EXISTS idx_metrics_name_time ON metrics(metric_name, created_at);

        -- Enable WAL mode for better concurrency
        PRAGMA journal_mode=WAL;
    """)

    conn.commit()
    yield conn
    conn.close()

    # Cleanup
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    wal_path = test_db_path + "-wal"
    shm_path = test_db_path + "-shm"
    if os.path.exists(wal_path):
        os.remove(wal_path)
    if os.path.exists(shm_path):
        os.remove(shm_path)


# =============================================================================
# Hook Payload Fixtures
# =============================================================================

@pytest.fixture
def pre_tool_use_edit_payload():
    """Sample PreToolUse payload for Edit tool."""
    return {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/Users/test/project/src/app.ts",
            "old_string": "const x = 1",
            "new_string": "const x = 2"
        },
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project"
    }


@pytest.fixture
def pre_tool_use_bash_payload():
    """Sample PreToolUse payload for Bash tool."""
    return {
        "tool_name": "Bash",
        "tool_input": {
            "command": "npm install express",
            "description": "Install express package"
        },
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project"
    }


@pytest.fixture
def notification_permission_payload():
    """Sample Notification hook payload for permission_prompt."""
    return {
        "hook_event_name": "Notification",
        "notification_type": "permission_prompt",
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project",
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/Users/test/project/src/app.ts"
        }
    }


@pytest.fixture
def notification_idle_payload():
    """Sample Notification hook payload for idle_prompt."""
    return {
        "hook_event_name": "Notification",
        "notification_type": "idle_prompt",
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project"
    }


@pytest.fixture
def stop_hook_payload():
    """Sample Stop hook payload."""
    return {
        "hook_event_name": "Stop",
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project",
        "stop_reason": "user_request"
    }


# =============================================================================
# Config Fixtures
# =============================================================================

@pytest.fixture
def test_config():
    """Sample V1-style config for testing."""
    return {
        "webhook_url": "https://example.com/webhook/test-placeholder",
        "enabled": True,
        "notify_on": {
            "permission_required": True,
            "task_complete": True,
            "input_required": True
        },
        "notify_always": False
    }


@pytest.fixture
def test_config_file(tmp_path, test_config):
    """Create a temporary config file."""
    config_path = tmp_path / "slack-config.json"
    config_path.write_text(json.dumps(test_config, indent=2))
    return str(config_path)


# =============================================================================
# Environment Fixtures
# =============================================================================

@pytest.fixture
def mock_tmux_env(monkeypatch):
    """Mock tmux environment variables."""
    monkeypatch.setenv("TMUX", "/tmp/tmux-501/default,12345,0")
    return "main:0.0"


@pytest.fixture
def mock_vscode_env(monkeypatch):
    """Mock VSCode terminal environment."""
    monkeypatch.setenv("TERM_PROGRAM", "vscode")
    monkeypatch.delenv("TMUX", raising=False)


@pytest.fixture
def mock_iterm_env(monkeypatch):
    """Mock iTerm2 environment."""
    monkeypatch.setenv("TERM_PROGRAM", "iTerm.app")
    monkeypatch.delenv("TMUX", raising=False)


# =============================================================================
# Encryption Fixtures
# =============================================================================

@pytest.fixture
def test_encryption_key_path(tmp_path):
    """Provide a temporary encryption key path."""
    return str(tmp_path / "encryption.key")


# =============================================================================
# Helper Functions
# =============================================================================

def insert_test_event(db, session_id, event_type, payload, created_at=None):
    """Helper to insert a test event."""
    import time
    created_at = created_at or int(time.time())
    cursor = db.execute(
        "INSERT INTO events (session_id, event_type, hook_payload, created_at) VALUES (?, ?, ?, ?)",
        (session_id, event_type, json.dumps(payload), created_at)
    )
    db.commit()
    return cursor.lastrowid


def insert_test_session(db, session_id, cwd, project_name=None, started_at=None):
    """Helper to insert a test session."""
    import time
    started_at = started_at or int(time.time())
    db.execute(
        """INSERT INTO sessions (session_id, cwd, project_name, started_at, last_activity_at)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, cwd, project_name or "test-project", started_at, started_at)
    )
    db.commit()


def insert_test_config(db, key, value, is_encrypted=0):
    """Helper to insert a test config value."""
    import time
    db.execute(
        "INSERT OR REPLACE INTO config (key, value, is_encrypted, updated_at) VALUES (?, ?, ?, ?)",
        (key, value, is_encrypted, int(time.time()))
    )
    db.commit()
