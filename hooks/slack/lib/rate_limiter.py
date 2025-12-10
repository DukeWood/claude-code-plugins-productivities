"""
Rate Limiter and Deduplication for Slack Notifications.

This module provides:
- Rate limiting with configurable cooldown periods per notification type
- Deduplication to suppress consecutive identical notifications
- SQLite-based state storage for persistence across restarts
- Thread-safe operations for concurrent access
- Suppressed notification counting for user feedback

Usage:
    from rate_limiter import RateLimiter, RateLimitConfig

    # Initialize with config
    config = RateLimitConfig(
        enabled=True,
        cooldowns={"permission": 30, "idle": 60, "complete": 0}
    )
    limiter = RateLimiter(db_path, config)

    # Check if notification should be sent
    result = limiter.should_send("session123", "permission", {"tool": "Edit"})
    if result.allowed:
        # Send notification
        send_notification(...)
        limiter.record_sent("session123", "permission")
    else:
        # Notification suppressed
        print(f"Suppressed ({result.suppressed_count} in window)")
"""
import sqlite3
import json
import time
import hashlib
import threading
from dataclasses import dataclass, field
from typing import Dict, Optional, Any
from pathlib import Path


# =============================================================================
# Configuration
# =============================================================================

@dataclass
class RateLimitConfig:
    """Configuration for rate limiting and deduplication."""

    # Rate limiting
    enabled: bool = True
    cooldowns: Dict[str, int] = field(default_factory=lambda: {
        "permission": 30,   # 30 seconds for permission prompts
        "idle": 60,         # 60 seconds for idle prompts
        "complete": 0,      # No cooldown for task complete (always send)
        "stop": 0           # Alias for complete
    })

    # Deduplication
    dedup_enabled: bool = True
    dedup_window_seconds: int = 300  # 5 minutes

    # State cleanup
    state_ttl_hours: int = 24  # Clean up state older than 24 hours

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RateLimitConfig':
        """Create config from dictionary (e.g., from JSON config file)."""
        rate_limiting = data.get("rate_limiting", {})
        deduplication = data.get("deduplication", {})

        return cls(
            enabled=rate_limiting.get("enabled", True),
            cooldowns=rate_limiting.get("cooldowns", {
                "permission": 30,
                "idle": 60,
                "complete": 0,
                "stop": 0
            }),
            dedup_enabled=deduplication.get("enabled", True),
            dedup_window_seconds=deduplication.get("window_seconds", 300)
        )

    def get_cooldown(self, notification_type: str) -> int:
        """Get cooldown period for notification type."""
        # Normalize type names
        type_map = {
            "permission_prompt": "permission",
            "idle_prompt": "idle",
            "task_complete": "complete",
            "stop": "complete"
        }
        normalized = type_map.get(notification_type, notification_type)
        return self.cooldowns.get(normalized, 0)


# =============================================================================
# Result Types
# =============================================================================

@dataclass
class RateLimitResult:
    """Result of a rate limit check."""
    allowed: bool
    reason: str = ""
    suppressed_count: int = 0
    last_sent_at: Optional[int] = None
    cooldown_remaining: int = 0

    @property
    def should_send(self) -> bool:
        """Alias for allowed."""
        return self.allowed


# =============================================================================
# Rate Limiter
# =============================================================================

class RateLimiter:
    """
    Thread-safe rate limiter with deduplication support.

    Uses SQLite for persistent state storage across process restarts.
    Supports per-session, per-type rate limiting with configurable cooldowns.
    """

    def __init__(self, db_path: str, config: Optional[RateLimitConfig] = None):
        """
        Initialize rate limiter.

        Args:
            db_path: Path to SQLite database
            config: Rate limit configuration (uses defaults if None)
        """
        self.db_path = str(Path(db_path).expanduser())
        self.config = config or RateLimitConfig()
        self._local = threading.local()
        self._ensure_schema()

    def _get_connection(self) -> sqlite3.Connection:
        """Get thread-local database connection."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            # Ensure directory exists
            Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

            self._local.conn = sqlite3.connect(self.db_path)
            self._local.conn.row_factory = sqlite3.Row
            self._local.conn.execute("PRAGMA journal_mode=WAL")
        return self._local.conn

    def _ensure_schema(self):
        """Create database schema if it doesn't exist."""
        conn = self._get_connection()
        conn.executescript("""
            -- Rate limit state table
            CREATE TABLE IF NOT EXISTS rate_limit_state (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                last_sent_at INTEGER NOT NULL,
                suppressed_count INTEGER DEFAULT 0,
                last_payload_hash TEXT,
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                UNIQUE(session_id, notification_type)
            );

            CREATE INDEX IF NOT EXISTS idx_rate_limit_session
                ON rate_limit_state(session_id);
            CREATE INDEX IF NOT EXISTS idx_rate_limit_type
                ON rate_limit_state(notification_type);
            CREATE INDEX IF NOT EXISTS idx_rate_limit_updated
                ON rate_limit_state(updated_at);

            -- Deduplication history for tracking identical payloads
            CREATE TABLE IF NOT EXISTS dedup_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                notification_type TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                sent_at INTEGER NOT NULL,
                UNIQUE(session_id, notification_type, payload_hash)
            );

            CREATE INDEX IF NOT EXISTS idx_dedup_session
                ON dedup_history(session_id);
            CREATE INDEX IF NOT EXISTS idx_dedup_sent
                ON dedup_history(sent_at);
        """)
        conn.commit()

    def _hash_payload(self, payload: Dict[str, Any]) -> str:
        """
        Create a hash of the payload for deduplication.

        Only hashes relevant fields to detect true duplicates.
        """
        # Extract relevant fields for deduplication
        relevant = {
            "tool_name": payload.get("tool_name"),
            "tool_input": payload.get("tool_input"),
            "notification_type": payload.get("notification_type"),
        }

        # Remove None values
        relevant = {k: v for k, v in relevant.items() if v is not None}

        # Create hash
        payload_str = json.dumps(relevant, sort_keys=True)
        return hashlib.sha256(payload_str.encode()).hexdigest()[:16]

    def should_send(
        self,
        session_id: str,
        notification_type: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> RateLimitResult:
        """
        Check if a notification should be sent.

        Args:
            session_id: Session identifier
            notification_type: Type of notification (permission, idle, complete)
            payload: Optional payload for deduplication check

        Returns:
            RateLimitResult with allowed status and metadata
        """
        # If rate limiting is disabled, always allow
        if not self.config.enabled:
            return RateLimitResult(allowed=True, reason="rate_limiting_disabled")

        now = int(time.time())
        cooldown = self.config.get_cooldown(notification_type)

        # If no cooldown for this type, always allow
        if cooldown == 0:
            return RateLimitResult(allowed=True, reason="no_cooldown")

        conn = self._get_connection()

        # Get current state
        cursor = conn.execute(
            """SELECT last_sent_at, suppressed_count, last_payload_hash
               FROM rate_limit_state
               WHERE session_id = ? AND notification_type = ?""",
            (session_id, notification_type)
        )
        row = cursor.fetchone()

        if row is None:
            # No previous state - allow
            return RateLimitResult(allowed=True, reason="first_notification")

        last_sent_at = row["last_sent_at"]
        suppressed_count = row["suppressed_count"]
        last_payload_hash = row["last_payload_hash"]

        # Check cooldown
        elapsed = now - last_sent_at
        if elapsed < cooldown:
            # Still in cooldown period
            remaining = cooldown - elapsed

            # Increment suppressed count
            self._increment_suppressed(session_id, notification_type)

            return RateLimitResult(
                allowed=False,
                reason="cooldown_active",
                suppressed_count=suppressed_count + 1,
                last_sent_at=last_sent_at,
                cooldown_remaining=remaining
            )

        # Cooldown expired - check deduplication if enabled
        if self.config.dedup_enabled and payload:
            payload_hash = self._hash_payload(payload)

            # Check if this exact payload was sent recently
            if self._is_duplicate(session_id, notification_type, payload_hash):
                self._increment_suppressed(session_id, notification_type)
                return RateLimitResult(
                    allowed=False,
                    reason="duplicate_suppressed",
                    suppressed_count=suppressed_count + 1,
                    last_sent_at=last_sent_at
                )

        # Allow with suppressed count info
        return RateLimitResult(
            allowed=True,
            reason="cooldown_expired",
            suppressed_count=suppressed_count,
            last_sent_at=last_sent_at
        )

    def _is_duplicate(
        self,
        session_id: str,
        notification_type: str,
        payload_hash: str
    ) -> bool:
        """Check if payload is a duplicate within dedup window."""
        conn = self._get_connection()
        now = int(time.time())
        window_start = now - self.config.dedup_window_seconds

        cursor = conn.execute(
            """SELECT 1 FROM dedup_history
               WHERE session_id = ? AND notification_type = ?
               AND payload_hash = ? AND sent_at > ?""",
            (session_id, notification_type, payload_hash, window_start)
        )

        return cursor.fetchone() is not None

    def _increment_suppressed(self, session_id: str, notification_type: str):
        """Increment suppressed count for a session/type."""
        conn = self._get_connection()
        now = int(time.time())

        conn.execute(
            """UPDATE rate_limit_state
               SET suppressed_count = suppressed_count + 1, updated_at = ?
               WHERE session_id = ? AND notification_type = ?""",
            (now, session_id, notification_type)
        )
        conn.commit()

    def record_sent(
        self,
        session_id: str,
        notification_type: str,
        payload: Optional[Dict[str, Any]] = None
    ) -> int:
        """
        Record that a notification was sent.

        Args:
            session_id: Session identifier
            notification_type: Type of notification
            payload: Optional payload for dedup tracking

        Returns:
            Number of previously suppressed notifications (before reset)
        """
        conn = self._get_connection()
        now = int(time.time())

        # Get current suppressed count before reset
        cursor = conn.execute(
            """SELECT suppressed_count FROM rate_limit_state
               WHERE session_id = ? AND notification_type = ?""",
            (session_id, notification_type)
        )
        row = cursor.fetchone()
        suppressed_count = row["suppressed_count"] if row else 0

        # Calculate payload hash
        payload_hash = self._hash_payload(payload) if payload else None

        # Upsert rate limit state
        conn.execute(
            """INSERT INTO rate_limit_state
               (session_id, notification_type, last_sent_at, suppressed_count,
                last_payload_hash, created_at, updated_at)
               VALUES (?, ?, ?, 0, ?, ?, ?)
               ON CONFLICT(session_id, notification_type)
               DO UPDATE SET
                   last_sent_at = excluded.last_sent_at,
                   suppressed_count = 0,
                   last_payload_hash = excluded.last_payload_hash,
                   updated_at = excluded.updated_at""",
            (session_id, notification_type, now, payload_hash, now, now)
        )

        # Record in dedup history if payload provided
        if payload_hash:
            conn.execute(
                """INSERT OR REPLACE INTO dedup_history
                   (session_id, notification_type, payload_hash, sent_at)
                   VALUES (?, ?, ?, ?)""",
                (session_id, notification_type, payload_hash, now)
            )

        conn.commit()
        return suppressed_count

    def get_suppressed_count(
        self,
        session_id: str,
        notification_type: str
    ) -> int:
        """Get current suppressed count for a session/type."""
        conn = self._get_connection()

        cursor = conn.execute(
            """SELECT suppressed_count FROM rate_limit_state
               WHERE session_id = ? AND notification_type = ?""",
            (session_id, notification_type)
        )
        row = cursor.fetchone()
        return row["suppressed_count"] if row else 0

    def get_stats(self, session_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Get rate limiting statistics.

        Args:
            session_id: Optional session to filter by

        Returns:
            Dictionary with statistics
        """
        conn = self._get_connection()

        if session_id:
            cursor = conn.execute(
                """SELECT notification_type, last_sent_at, suppressed_count
                   FROM rate_limit_state WHERE session_id = ?""",
                (session_id,)
            )
        else:
            cursor = conn.execute(
                """SELECT session_id, notification_type, last_sent_at, suppressed_count
                   FROM rate_limit_state ORDER BY updated_at DESC LIMIT 100"""
            )

        rows = cursor.fetchall()

        total_suppressed = sum(row["suppressed_count"] for row in rows)
        by_type = {}
        for row in rows:
            ntype = row["notification_type"]
            if ntype not in by_type:
                by_type[ntype] = {"count": 0, "suppressed": 0}
            by_type[ntype]["count"] += 1
            by_type[ntype]["suppressed"] += row["suppressed_count"]

        # Get unique sessions - handle sqlite3.Row objects
        unique_sessions = set()
        for row in rows:
            if session_id:
                unique_sessions.add(session_id)
            else:
                unique_sessions.add(row["session_id"])

        return {
            "total_sessions": len(unique_sessions),
            "total_suppressed": total_suppressed,
            "by_type": by_type
        }

    def cleanup_old_state(self, max_age_hours: Optional[int] = None):
        """
        Remove old rate limit state entries.

        Args:
            max_age_hours: Maximum age in hours (uses config default if None)
        """
        conn = self._get_connection()
        max_age = max_age_hours or self.config.state_ttl_hours
        cutoff = int(time.time()) - (max_age * 3600)

        conn.execute(
            "DELETE FROM rate_limit_state WHERE updated_at < ?",
            (cutoff,)
        )
        conn.execute(
            "DELETE FROM dedup_history WHERE sent_at < ?",
            (cutoff,)
        )
        conn.commit()

    def reset_session(self, session_id: str):
        """Reset all rate limit state for a session."""
        conn = self._get_connection()
        conn.execute(
            "DELETE FROM rate_limit_state WHERE session_id = ?",
            (session_id,)
        )
        conn.execute(
            "DELETE FROM dedup_history WHERE session_id = ?",
            (session_id,)
        )
        conn.commit()

    def close(self):
        """Close database connection."""
        if hasattr(self._local, 'conn') and self._local.conn:
            self._local.conn.close()
            self._local.conn = None


# =============================================================================
# Convenience Functions
# =============================================================================

def create_limiter_from_config(config_path: str, db_path: str) -> RateLimiter:
    """
    Create a rate limiter from a JSON config file.

    Args:
        config_path: Path to slack-config.json
        db_path: Path to SQLite database

    Returns:
        Configured RateLimiter instance
    """
    config_path = Path(config_path).expanduser()

    if config_path.exists():
        with open(config_path) as f:
            data = json.load(f)
        rate_config = RateLimitConfig.from_dict(data)
    else:
        rate_config = RateLimitConfig()

    return RateLimiter(db_path, rate_config)
