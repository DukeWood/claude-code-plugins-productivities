"""
Event Queue and Retry Logic for Slack Notification V2.

This module provides:
- Queue operations (enqueue, dequeue, mark_sent, mark_failed)
- Exponential backoff retry logic
- Dead letter queue for permanently failed notifications
- Thread-safe database operations
- Queue statistics and metrics
- Cleanup of old processed notifications

Thread Safety:
- All operations use database transactions
- WAL mode enabled for concurrent reads/writes
- Row-level locking for atomic status transitions
"""
import sqlite3
import json
import time
import threading
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from enum import Enum


# =============================================================================
# Constants
# =============================================================================

class NotificationStatus:
    """Notification status constants."""
    PENDING = "pending"
    PROCESSING = "processing"
    SENT = "sent"
    FAILED = "failed"
    DEAD_LETTER = "dead_letter"


# Retry delays in seconds: 1min, 5min, 15min, 1hr, 4hr
RETRY_DELAYS = [
    60,        # 1 minute
    300,       # 5 minutes
    900,       # 15 minutes
    3600,      # 1 hour
    14400      # 4 hours
]

MAX_RETRIES = 5


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QueueStats:
    """Queue statistics."""
    pending: int
    processing: int
    sent: int
    failed: int
    dead_letter: int
    total: int


# =============================================================================
# Notification Queue
# =============================================================================

class NotificationQueue:
    """
    Thread-safe notification queue with retry logic.

    Provides operations for:
    - Enqueueing notifications
    - Dequeueing batches for processing
    - Marking notifications as sent/failed
    - Tracking retry attempts with exponential backoff
    - Managing dead letter queue
    - Cleanup of old notifications
    """

    def __init__(self, db_path: str):
        """
        Initialize notification queue.

        Args:
            db_path: Path to SQLite database
        """
        self.db_path = db_path
        self._local = threading.local()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """
        Get thread-local database connection.

        Returns:
            Database connection with row factory configured
        """
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            conn = sqlite3.connect(self.db_path, timeout=30.0)
            conn.row_factory = sqlite3.Row
            # Enable WAL mode for better concurrency
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA busy_timeout=30000")  # 30 second timeout
            self._local.conn = conn
        return self._local.conn

    def _ensure_schema(self):
        """Ensure database schema exists."""
        conn = self._get_connection()

        # Check if notifications table exists
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='notifications'"
        )
        if cursor.fetchone() is None:
            # Schema doesn't exist, create it
            conn.executescript("""
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

                CREATE TABLE IF NOT EXISTS notifications (
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
                CREATE INDEX IF NOT EXISTS idx_notifications_status ON notifications(status);
                CREATE INDEX IF NOT EXISTS idx_notifications_session ON notifications(session_id);
                CREATE INDEX IF NOT EXISTS idx_notifications_retry ON notifications(next_retry_at)
                    WHERE status = 'failed';
            """)
            conn.commit()

    def enqueue(
        self,
        event_type: str,
        payload: Dict[str, Any],
        session_id: str,
        backend: str = "slack",
        event_id: Optional[int] = None
    ) -> int:
        """
        Add notification to queue.

        Args:
            event_type: Type of event (e.g., 'permission', 'task_complete')
            payload: Notification payload (will be JSON encoded)
            session_id: Session identifier
            backend: Backend to send notification (default: 'slack')
            event_id: Optional event ID to link to

        Returns:
            Notification ID
        """
        conn = self._get_connection()
        timestamp = int(time.time())

        # Use event_id = 0 if not provided (for backwards compatibility)
        if event_id is None:
            event_id = 0

        cursor = conn.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, retry_count)
               VALUES (?, ?, ?, ?, ?, ?, ?, 0)""",
            (
                event_id,
                session_id,
                event_type,
                backend,
                NotificationStatus.PENDING,
                json.dumps(payload),
                timestamp
            )
        )

        conn.commit()
        return cursor.lastrowid

    def dequeue(self, batch_size: int = 10) -> List[Dict[str, Any]]:
        """
        Get next batch of notifications for processing.

        Retrieves notifications that are:
        - Status = 'pending', OR
        - Status = 'failed' AND next_retry_at <= now

        Marks retrieved notifications as 'processing'.

        Args:
            batch_size: Maximum number of notifications to retrieve

        Returns:
            List of notification dictionaries
        """
        if batch_size <= 0:
            return []

        conn = self._get_connection()
        timestamp = int(time.time())

        # Use a transaction for atomicity
        conn.execute("BEGIN IMMEDIATE")

        try:
            # Find notifications ready for processing
            cursor = conn.execute(
                """SELECT id, event_id, session_id, notification_type, backend,
                          status, retry_count, payload, error, created_at,
                          sent_at, next_retry_at
                   FROM notifications
                   WHERE status = ? OR (status = ? AND next_retry_at <= ?)
                   ORDER BY created_at ASC
                   LIMIT ?""",
                (NotificationStatus.PENDING, NotificationStatus.FAILED, timestamp, batch_size)
            )

            rows = cursor.fetchall()

            if not rows:
                conn.commit()
                return []

            # Mark as processing
            notification_ids = [row["id"] for row in rows]
            placeholders = ",".join("?" * len(notification_ids))

            conn.execute(
                f"""UPDATE notifications
                    SET status = ?
                    WHERE id IN ({placeholders})""",
                [NotificationStatus.PROCESSING] + notification_ids
            )

            conn.commit()

            # Convert rows to dictionaries
            notifications = []
            for row in rows:
                notification = {
                    "id": row["id"],
                    "event_id": row["event_id"],
                    "session_id": row["session_id"],
                    "notification_type": row["notification_type"],
                    "backend": row["backend"],
                    "status": NotificationStatus.PROCESSING,  # Updated status
                    "retry_count": row["retry_count"],
                    "payload": json.loads(row["payload"]),
                    "error": row["error"],
                    "created_at": row["created_at"],
                    "sent_at": row["sent_at"],
                    "next_retry_at": row["next_retry_at"]
                }
                notifications.append(notification)

            return notifications

        except Exception as e:
            conn.rollback()
            raise

    def mark_sent(self, notification_id: int):
        """
        Mark notification as successfully sent.

        Args:
            notification_id: Notification ID
        """
        conn = self._get_connection()
        timestamp = int(time.time())

        conn.execute(
            """UPDATE notifications
               SET status = ?, sent_at = ?
               WHERE id = ?""",
            (NotificationStatus.SENT, timestamp, notification_id)
        )

        conn.commit()

    def mark_failed(self, notification_id: int, error: str):
        """
        Mark notification as failed and schedule retry.

        Implements exponential backoff:
        - Attempt 1: retry in 1 minute
        - Attempt 2: retry in 5 minutes
        - Attempt 3: retry in 15 minutes
        - Attempt 4: retry in 1 hour
        - Attempt 5: retry in 4 hours
        - Attempt 6+: move to dead letter queue

        Args:
            notification_id: Notification ID
            error: Error message
        """
        conn = self._get_connection()
        timestamp = int(time.time())

        # Get current retry count
        cursor = conn.execute(
            "SELECT retry_count FROM notifications WHERE id = ?",
            (notification_id,)
        )
        row = cursor.fetchone()

        if row is None:
            return

        current_retry_count = row["retry_count"]
        new_retry_count = current_retry_count + 1

        if new_retry_count > MAX_RETRIES:
            # Move to dead letter queue
            conn.execute(
                """UPDATE notifications
                   SET status = ?, retry_count = ?, error = ?
                   WHERE id = ?""",
                (NotificationStatus.DEAD_LETTER, new_retry_count, error, notification_id)
            )
        else:
            # Schedule retry with exponential backoff
            delay = RETRY_DELAYS[min(new_retry_count - 1, len(RETRY_DELAYS) - 1)]
            next_retry_at = timestamp + delay

            conn.execute(
                """UPDATE notifications
                   SET status = ?, retry_count = ?, error = ?, next_retry_at = ?
                   WHERE id = ?""",
                (NotificationStatus.FAILED, new_retry_count, error, next_retry_at, notification_id)
            )

        conn.commit()

    def get_pending_count(self, session_id: Optional[str] = None) -> int:
        """
        Get count of pending notifications.

        Includes both 'pending' and 'failed' (retry-able) notifications.

        Args:
            session_id: Optional session filter

        Returns:
            Count of pending notifications
        """
        conn = self._get_connection()
        timestamp = int(time.time())

        if session_id:
            cursor = conn.execute(
                """SELECT COUNT(*) as count
                   FROM notifications
                   WHERE session_id = ?
                     AND (status = ? OR (status = ? AND next_retry_at <= ?))""",
                (session_id, NotificationStatus.PENDING, NotificationStatus.FAILED, timestamp)
            )
        else:
            cursor = conn.execute(
                """SELECT COUNT(*) as count
                   FROM notifications
                   WHERE status = ? OR (status = ? AND next_retry_at <= ?)""",
                (NotificationStatus.PENDING, NotificationStatus.FAILED, timestamp)
            )

        row = cursor.fetchone()
        return row["count"]

    def get_stats(self, session_id: Optional[str] = None) -> QueueStats:
        """
        Get comprehensive queue statistics.

        Args:
            session_id: Optional session filter

        Returns:
            QueueStats object with counts by status
        """
        conn = self._get_connection()

        if session_id:
            cursor = conn.execute(
                """SELECT
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as pending,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as processing,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as sent,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as dead_letter,
                       COUNT(*) as total
                   FROM notifications
                   WHERE session_id = ?""",
                (
                    NotificationStatus.PENDING,
                    NotificationStatus.PROCESSING,
                    NotificationStatus.SENT,
                    NotificationStatus.FAILED,
                    NotificationStatus.DEAD_LETTER,
                    session_id
                )
            )
        else:
            cursor = conn.execute(
                """SELECT
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as pending,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as processing,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as sent,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as failed,
                       SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) as dead_letter,
                       COUNT(*) as total
                   FROM notifications""",
                (
                    NotificationStatus.PENDING,
                    NotificationStatus.PROCESSING,
                    NotificationStatus.SENT,
                    NotificationStatus.FAILED,
                    NotificationStatus.DEAD_LETTER
                )
            )

        row = cursor.fetchone()

        return QueueStats(
            pending=row["pending"] or 0,
            processing=row["processing"] or 0,
            sent=row["sent"] or 0,
            failed=row["failed"] or 0,
            dead_letter=row["dead_letter"] or 0,
            total=row["total"] or 0
        )

    def get_dead_letters(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """
        Get notifications in dead letter queue.

        Args:
            limit: Optional limit on number of results

        Returns:
            List of dead letter notification dictionaries
        """
        conn = self._get_connection()

        if limit:
            cursor = conn.execute(
                """SELECT id, event_id, session_id, notification_type, backend,
                          status, retry_count, payload, error, created_at,
                          sent_at, next_retry_at
                   FROM notifications
                   WHERE status = ?
                   ORDER BY created_at DESC
                   LIMIT ?""",
                (NotificationStatus.DEAD_LETTER, limit)
            )
        else:
            cursor = conn.execute(
                """SELECT id, event_id, session_id, notification_type, backend,
                          status, retry_count, payload, error, created_at,
                          sent_at, next_retry_at
                   FROM notifications
                   WHERE status = ?
                   ORDER BY created_at DESC""",
                (NotificationStatus.DEAD_LETTER,)
            )

        rows = cursor.fetchall()

        # Convert rows to dictionaries
        dead_letters = []
        for row in rows:
            notification = {
                "id": row["id"],
                "event_id": row["event_id"],
                "session_id": row["session_id"],
                "notification_type": row["notification_type"],
                "backend": row["backend"],
                "status": row["status"],
                "retry_count": row["retry_count"],
                "payload": json.loads(row["payload"]),
                "error": row["error"],
                "created_at": row["created_at"],
                "sent_at": row["sent_at"],
                "next_retry_at": row["next_retry_at"]
            }
            dead_letters.append(notification)

        return dead_letters

    def cleanup_old(self, days: int = 30) -> int:
        """
        Remove old processed notifications.

        Deletes notifications that are:
        - Status = 'sent' OR 'dead_letter'
        - Created more than N days ago

        Args:
            days: Age threshold in days

        Returns:
            Number of notifications deleted
        """
        conn = self._get_connection()
        cutoff_timestamp = int(time.time()) - (days * 24 * 60 * 60)

        cursor = conn.execute(
            """DELETE FROM notifications
               WHERE (status = ? OR status = ?)
                 AND created_at < ?""",
            (NotificationStatus.SENT, NotificationStatus.DEAD_LETTER, cutoff_timestamp)
        )

        conn.commit()
        return cursor.rowcount

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn is not None:
            self._local.conn.close()
            self._local.conn = None


# =============================================================================
# Helper Functions
# =============================================================================

def get_retry_delay(retry_count: int) -> int:
    """
    Get retry delay for given retry count.

    Args:
        retry_count: Current retry attempt (1-based)

    Returns:
        Delay in seconds
    """
    if retry_count < 1:
        return RETRY_DELAYS[0]

    index = min(retry_count - 1, len(RETRY_DELAYS) - 1)
    return RETRY_DELAYS[index]


def format_retry_time(next_retry_at: int) -> str:
    """
    Format next retry time as human-readable string.

    Args:
        next_retry_at: Unix timestamp

    Returns:
        Human-readable string (e.g., "in 5 minutes")
    """
    now = int(time.time())
    delta = next_retry_at - now

    if delta <= 0:
        return "now"

    if delta < 60:
        return f"in {delta} seconds"

    if delta < 3600:
        minutes = delta // 60
        return f"in {minutes} minute{'s' if minutes != 1 else ''}"

    if delta < 86400:
        hours = delta // 3600
        return f"in {hours} hour{'s' if hours != 1 else ''}"

    days = delta // 86400
    return f"in {days} day{'s' if days != 1 else ''}"
