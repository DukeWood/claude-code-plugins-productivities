"""
SQLite database layer for Slack Notification V2.

This module provides:
- Event queue management (raw hook payloads)
- Notification tracking (pending/sent/failed with retry)
- Session lifecycle management
- Encrypted config storage
- Audit logging
- Performance metrics
- Session isolation
- Migration support from V1 JSON files

Usage:
    from database import Database

    # Initialize database
    db = Database("~/.claude/state/notifications.db")

    # Insert event
    event_id = db.insert_event("session1", "pre_tool_use", {"tool": "Edit"})

    # Create notification
    notif_id = db.insert_notification(event_id, "session1", "permission", "slack", payload)

    # Close connection
    db.close()

    # Or use context manager
    with Database("path/to/db.db") as db:
        db.insert_event(...)
"""
import os
import sys
import json
import time
import sqlite3
from pathlib import Path
from typing import Dict, List, Optional, Any, Union

# Import encryption module (will be created separately)
try:
    from . import encryption
except ImportError:
    # Allow import to work when running tests
    try:
        import encryption
    except ImportError:
        encryption = None


class Database:
    """SQLite database for Slack Notification V2."""

    def __init__(self, db_path: str):
        """
        Initialize database connection and create schema if needed.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = os.path.expanduser(db_path)

        # Ensure parent directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # Connect to database
        self.conn = sqlite3.connect(self.db_path)
        self.conn.row_factory = sqlite3.Row

        # Enable WAL mode for better concurrency
        self.conn.execute("PRAGMA journal_mode=WAL")

        # Create schema
        self._create_schema()

    def _create_schema(self):
        """Create database schema if it doesn't exist."""
        self.conn.executescript("""
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
        """)
        self.conn.commit()

    # =========================================================================
    # Event Operations
    # =========================================================================

    def insert_event(
        self,
        session_id: str,
        event_type: str,
        payload: Union[Dict, Any],
        created_at: Optional[int] = None
    ) -> int:
        """
        Insert a new event.

        Args:
            session_id: Session identifier
            event_type: Type of event (pre_tool_use, notification, post_tool_use, stop)
            payload: Event payload (will be JSON serialized)
            created_at: Optional timestamp (defaults to now)

        Returns:
            event_id: ID of inserted event
        """
        if created_at is None:
            created_at = int(time.time())

        cursor = self.conn.execute(
            """INSERT INTO events (session_id, event_type, hook_payload, created_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, event_type, json.dumps(payload), created_at)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_event_by_id(self, event_id: int) -> Optional[sqlite3.Row]:
        """Get event by ID."""
        row = self.conn.execute(
            "SELECT * FROM events WHERE id=?",
            (event_id,)
        ).fetchone()
        return row

    def get_unprocessed_events(self) -> List[sqlite3.Row]:
        """Get all events that haven't been processed yet."""
        rows = self.conn.execute(
            """SELECT * FROM events
               WHERE processed_at IS NULL
               ORDER BY created_at ASC"""
        ).fetchall()
        return rows

    def mark_event_processed(self, event_id: int):
        """Mark event as processed."""
        self.conn.execute(
            "UPDATE events SET processed_at=? WHERE id=?",
            (int(time.time()), event_id)
        )
        self.conn.commit()

    def get_events_by_session(self, session_id: str) -> List[sqlite3.Row]:
        """Get all events for a session."""
        rows = self.conn.execute(
            "SELECT * FROM events WHERE session_id=? ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
        return rows

    def get_latest_event_by_type(
        self,
        session_id: str,
        event_type: str
    ) -> Optional[sqlite3.Row]:
        """Get most recent event of specific type for session."""
        row = self.conn.execute(
            """SELECT * FROM events
               WHERE session_id=? AND event_type=?
               ORDER BY created_at DESC
               LIMIT 1""",
            (session_id, event_type)
        ).fetchone()
        return row

    # =========================================================================
    # Notification Operations
    # =========================================================================

    def insert_notification(
        self,
        event_id: int,
        session_id: str,
        notification_type: str,
        backend: str,
        payload: Union[Dict, Any],
        created_at: Optional[int] = None
    ) -> int:
        """
        Insert a new notification.

        Args:
            event_id: Associated event ID
            session_id: Session identifier
            notification_type: Type (permission, task_complete, input_required, error)
            backend: Backend name (slack, discord, email)
            payload: Backend-specific payload
            created_at: Optional timestamp (defaults to now)

        Returns:
            notification_id: ID of inserted notification
        """
        if created_at is None:
            created_at = int(time.time())

        cursor = self.conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, payload, created_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (event_id, session_id, notification_type, backend, json.dumps(payload), created_at)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_notification_by_id(self, notification_id: int) -> Optional[sqlite3.Row]:
        """Get notification by ID."""
        row = self.conn.execute(
            "SELECT * FROM notifications WHERE id=?",
            (notification_id,)
        ).fetchone()
        return row

    def get_pending_notifications(self) -> List[sqlite3.Row]:
        """Get all pending notifications."""
        rows = self.conn.execute(
            """SELECT * FROM notifications
               WHERE status='pending'
               ORDER BY created_at ASC"""
        ).fetchall()
        return rows

    def get_failed_notifications_for_retry(
        self,
        max_retries: int = 3
    ) -> List[sqlite3.Row]:
        """Get failed notifications that can be retried."""
        rows = self.conn.execute(
            """SELECT * FROM notifications
               WHERE status='failed' AND retry_count < ?
               ORDER BY created_at ASC""",
            (max_retries,)
        ).fetchall()
        return rows

    def mark_notification_sent(self, notification_id: int):
        """Mark notification as sent."""
        self.conn.execute(
            """UPDATE notifications
               SET status='sent', sent_at=?
               WHERE id=?""",
            (int(time.time()), notification_id)
        )
        self.conn.commit()

    def mark_notification_failed(self, notification_id: int, error: str):
        """Mark notification as failed and increment retry count."""
        self.conn.execute(
            """UPDATE notifications
               SET status='failed', retry_count=retry_count+1, error=?
               WHERE id=?""",
            (error, notification_id)
        )
        self.conn.commit()

    def get_notifications_by_session(self, session_id: str) -> List[sqlite3.Row]:
        """Get all notifications for a session."""
        rows = self.conn.execute(
            "SELECT * FROM notifications WHERE session_id=? ORDER BY created_at ASC",
            (session_id,)
        ).fetchall()
        return rows

    # =========================================================================
    # Session Operations
    # =========================================================================

    def create_session(
        self,
        session_id: str,
        cwd: str,
        project_name: Optional[str] = None,
        git_branch: Optional[str] = None,
        terminal_type: Optional[str] = None,
        terminal_info: Optional[str] = None,
        started_at: Optional[int] = None
    ):
        """
        Create a new session.

        Args:
            session_id: Session identifier
            cwd: Current working directory
            project_name: Optional project name
            git_branch: Optional git branch
            terminal_type: Optional terminal type (tmux, vscode, iterm, ssh)
            terminal_info: Optional terminal info JSON
            started_at: Optional start timestamp (defaults to now)
        """
        if started_at is None:
            started_at = int(time.time())

        self.conn.execute(
            """INSERT INTO sessions
               (session_id, cwd, project_name, git_branch, terminal_type, terminal_info,
                started_at, last_activity_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (session_id, cwd, project_name, git_branch, terminal_type, terminal_info,
             started_at, started_at)
        )
        self.conn.commit()

    def get_session(self, session_id: str) -> Optional[sqlite3.Row]:
        """Get session by ID."""
        row = self.conn.execute(
            "SELECT * FROM sessions WHERE session_id=?",
            (session_id,)
        ).fetchone()
        return row

    def update_session_activity(self, session_id: str):
        """Update last_activity_at timestamp."""
        self.conn.execute(
            "UPDATE sessions SET last_activity_at=? WHERE session_id=?",
            (int(time.time()), session_id)
        )
        self.conn.commit()

    def set_session_idle(self, session_id: str, is_idle: bool):
        """Set session idle flag."""
        self.conn.execute(
            "UPDATE sessions SET is_idle=? WHERE session_id=?",
            (1 if is_idle else 0, session_id)
        )
        self.conn.commit()

    def end_session(self, session_id: str):
        """Mark session as ended."""
        self.conn.execute(
            "UPDATE sessions SET ended_at=? WHERE session_id=?",
            (int(time.time()), session_id)
        )
        self.conn.commit()

    def get_active_sessions(self) -> List[sqlite3.Row]:
        """Get all active sessions (ended_at is NULL)."""
        rows = self.conn.execute(
            "SELECT * FROM sessions WHERE ended_at IS NULL ORDER BY started_at DESC"
        ).fetchall()
        return rows

    def upsert_session(
        self,
        session_id: str,
        cwd: str,
        project_name: Optional[str] = None,
        git_branch: Optional[str] = None,
        terminal_type: Optional[str] = None,
        terminal_info: Optional[str] = None
    ):
        """Create session or update if it exists."""
        now = int(time.time())
        self.conn.execute(
            """INSERT INTO sessions
               (session_id, cwd, project_name, git_branch, terminal_type, terminal_info,
                started_at, last_activity_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(session_id) DO UPDATE SET
                   cwd=excluded.cwd,
                   project_name=excluded.project_name,
                   git_branch=excluded.git_branch,
                   terminal_type=excluded.terminal_type,
                   terminal_info=excluded.terminal_info,
                   last_activity_at=excluded.last_activity_at""",
            (session_id, cwd, project_name, git_branch, terminal_type, terminal_info, now, now)
        )
        self.conn.commit()

    # =========================================================================
    # Config Operations
    # =========================================================================

    def set_config(self, key: str, value: str, encrypted: bool = False):
        """
        Set config value.

        Args:
            key: Config key
            value: Config value
            encrypted: If True, encrypt the value before storing
        """
        stored_value = value

        # Encrypt if requested and encryption module available
        if encrypted and encryption:
            stored_value = encryption.encrypt(value)

        self.conn.execute(
            """INSERT OR REPLACE INTO config (key, value, is_encrypted, updated_at)
               VALUES (?, ?, ?, ?)""",
            (key, stored_value, 1 if encrypted else 0, int(time.time()))
        )
        self.conn.commit()

    def get_config(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """
        Get config value.

        Args:
            key: Config key
            default: Default value if key doesn't exist

        Returns:
            Decrypted value if encrypted, raw value otherwise
        """
        row = self.conn.execute(
            "SELECT value, is_encrypted FROM config WHERE key=?",
            (key,)
        ).fetchone()

        if row is None:
            return default

        value = row['value']
        is_encrypted = row['is_encrypted']

        # Decrypt if necessary
        if is_encrypted and encryption:
            try:
                value = encryption.decrypt(value)
            except Exception:
                # If decryption fails, return raw value
                pass

        return value

    def get_all_config(self) -> Dict[str, str]:
        """Get all config values as dictionary (with decryption)."""
        rows = self.conn.execute("SELECT key, value, is_encrypted FROM config").fetchall()

        config = {}
        for row in rows:
            key = row['key']
            value = row['value']
            is_encrypted = row['is_encrypted']

            # Decrypt if necessary
            if is_encrypted and encryption:
                try:
                    value = encryption.decrypt(value)
                except Exception:
                    pass

            config[key] = value

        return config

    def delete_config(self, key: str):
        """Delete config key."""
        self.conn.execute("DELETE FROM config WHERE key=?", (key,))
        self.conn.commit()

    # =========================================================================
    # Audit Log Operations
    # =========================================================================

    def insert_audit_log(
        self,
        action: str,
        session_id: Optional[str] = None,
        details: Optional[Union[Dict, Any]] = None,
        created_at: Optional[int] = None
    ) -> int:
        """
        Insert audit log entry.

        Args:
            action: Action name
            session_id: Optional session identifier
            details: Optional details (will be JSON serialized)
            created_at: Optional timestamp (defaults to now)

        Returns:
            log_id: ID of inserted log entry
        """
        if created_at is None:
            created_at = int(time.time())

        details_json = json.dumps(details) if details is not None else None

        cursor = self.conn.execute(
            """INSERT INTO audit_log (session_id, action, details, created_at)
               VALUES (?, ?, ?, ?)""",
            (session_id, action, details_json, created_at)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_audit_logs_by_session(self, session_id: str) -> List[sqlite3.Row]:
        """Get audit logs for a session."""
        rows = self.conn.execute(
            "SELECT * FROM audit_log WHERE session_id=? ORDER BY created_at DESC",
            (session_id,)
        ).fetchall()
        return rows

    def get_audit_logs_by_action(self, action: str) -> List[sqlite3.Row]:
        """Get audit logs by action."""
        rows = self.conn.execute(
            "SELECT * FROM audit_log WHERE action=? ORDER BY created_at DESC",
            (action,)
        ).fetchall()
        return rows

    def get_recent_audit_logs(self, limit: int = 100) -> List[sqlite3.Row]:
        """Get recent audit logs."""
        rows = self.conn.execute(
            "SELECT * FROM audit_log ORDER BY created_at DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return rows

    # =========================================================================
    # Metrics Operations
    # =========================================================================

    def insert_metric(
        self,
        metric_name: str,
        metric_value: float,
        session_id: Optional[str] = None,
        created_at: Optional[int] = None
    ) -> int:
        """
        Insert metric.

        Args:
            metric_name: Metric name
            metric_value: Metric value
            session_id: Optional session identifier
            created_at: Optional timestamp (defaults to now)

        Returns:
            metric_id: ID of inserted metric
        """
        if created_at is None:
            created_at = int(time.time())

        cursor = self.conn.execute(
            """INSERT INTO metrics (metric_name, metric_value, session_id, created_at)
               VALUES (?, ?, ?, ?)""",
            (metric_name, metric_value, session_id, created_at)
        )
        self.conn.commit()
        return cursor.lastrowid

    def get_metrics_by_name(self, metric_name: str) -> List[sqlite3.Row]:
        """Get all metrics by name."""
        rows = self.conn.execute(
            "SELECT * FROM metrics WHERE metric_name=? ORDER BY created_at ASC",
            (metric_name,)
        ).fetchall()
        return rows

    def get_metric_stats(
        self,
        metric_name: str,
        since: Optional[int] = None
    ) -> Dict[str, float]:
        """
        Calculate statistics for a metric.

        Args:
            metric_name: Metric name
            since: Optional timestamp to filter from

        Returns:
            Dictionary with count, avg, min, max
        """
        if since is not None:
            row = self.conn.execute(
                """SELECT
                       COUNT(*) as count,
                       AVG(metric_value) as avg,
                       MIN(metric_value) as min,
                       MAX(metric_value) as max
                   FROM metrics
                   WHERE metric_name=? AND created_at >= ?""",
                (metric_name, since)
            ).fetchone()
        else:
            row = self.conn.execute(
                """SELECT
                       COUNT(*) as count,
                       AVG(metric_value) as avg,
                       MIN(metric_value) as min,
                       MAX(metric_value) as max
                   FROM metrics
                   WHERE metric_name=?""",
                (metric_name,)
            ).fetchone()

        return {
            'count': row['count'],
            'avg': row['avg'],
            'min': row['min'],
            'max': row['max']
        }

    # =========================================================================
    # Migration from V1
    # =========================================================================

    def import_v1_config(self, v1_config: Dict):
        """
        Import V1 slack-config.json into config table.

        Args:
            v1_config: V1 config dictionary
        """
        # Import webhook URL (encrypted)
        if 'webhook_url' in v1_config:
            self.set_config('slack_webhook_url', v1_config['webhook_url'], encrypted=True)

        # Import enabled flag
        if 'enabled' in v1_config:
            self.set_config('enabled', str(v1_config['enabled']).lower())

        # Import notify_on settings
        if 'notify_on' in v1_config:
            notify_on = v1_config['notify_on']
            if 'permission_required' in notify_on:
                self.set_config('notify_on_permission', str(notify_on['permission_required']).lower())
            if 'task_complete' in notify_on:
                self.set_config('notify_on_task_complete', str(notify_on['task_complete']).lower())
            if 'input_required' in notify_on:
                self.set_config('notify_on_input_required', str(notify_on['input_required']).lower())

        # Import notify_always
        if 'notify_always' in v1_config:
            self.set_config('notify_always', str(v1_config['notify_always']).lower())

    def import_v1_tool_request(
        self,
        session_id: str,
        tool_request: Dict,
        timestamp: int
    ) -> int:
        """
        Import V1 tool_requests/*.json into events table.

        Args:
            session_id: Session identifier
            tool_request: V1 tool request dictionary
            timestamp: Original timestamp

        Returns:
            event_id: ID of inserted event
        """
        # Insert as pre_tool_use event and mark as processed
        event_id = self.insert_event(
            session_id=session_id,
            event_type="pre_tool_use",
            payload=tool_request,
            created_at=timestamp
        )

        # Mark as processed since V1 events are historical
        self.mark_event_processed(event_id)

        return event_id

    def import_v1_notification_state(self, v1_state: Dict):
        """
        Import V1 notification_states.json into sessions table.

        Args:
            v1_state: V1 notification state dictionary
        """
        session_id = v1_state.get('session_id')
        if not session_id:
            return

        # Determine terminal info
        terminal_type = None
        terminal_info = None
        if v1_state.get('in_tmux'):
            terminal_type = 'tmux'
            terminal_info = v1_state.get('tmux_info')

        # Use last_notification_time as last_activity_at
        last_activity = v1_state.get('last_notification_time', int(time.time()))

        # Create or update session
        self.upsert_session(
            session_id=session_id,
            cwd=v1_state.get('cwd', '/unknown'),
            terminal_type=terminal_type,
            terminal_info=terminal_info
        )

        # Update last activity
        self.conn.execute(
            "UPDATE sessions SET last_activity_at=? WHERE session_id=?",
            (last_activity, session_id)
        )

        # Set idle flag if waiting for input
        if v1_state.get('is_waiting_for_input'):
            self.set_session_idle(session_id, True)

        self.conn.commit()

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _get_table_names(self) -> List[str]:
        """Get list of table names."""
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
        return [row['name'] for row in rows]

    def _get_index_names(self) -> List[str]:
        """Get list of index names."""
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index'"
        ).fetchall()
        return [row['name'] for row in rows]

    def execute_query(self, query: str, params: tuple = ()) -> List[sqlite3.Row]:
        """Execute raw SQL query and return results."""
        rows = self.conn.execute(query, params).fetchall()
        return rows

    # =========================================================================
    # Context Manager and Cleanup
    # =========================================================================

    def __enter__(self):
        """Context manager entry."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        if exc_type is None:
            # Commit if no exception
            self.conn.commit()
        else:
            # Rollback if exception
            self.conn.rollback()

        self.close()
        return False

    def close(self):
        """Close database connection."""
        if self.conn:
            self.conn.close()
