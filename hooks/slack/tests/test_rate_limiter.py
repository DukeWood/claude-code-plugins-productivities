"""
Unit tests for rate_limiter.py

Tests cover:
- Rate limiting with cooldowns
- Deduplication logic
- Suppressed count tracking
- Configuration parsing
- State persistence
- Cleanup operations
"""
import os
import sys
import time
import tempfile
import pytest

# Add lib directory to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'lib'))

from rate_limiter import RateLimiter, RateLimitConfig, RateLimitResult


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def temp_db():
    """Create temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    # Cleanup
    try:
        os.unlink(path)
    except:
        pass


@pytest.fixture
def default_config():
    """Default rate limit configuration."""
    return RateLimitConfig(
        enabled=True,
        cooldowns={"permission": 2, "idle": 3, "complete": 0},  # Short for testing
        dedup_enabled=True,
        dedup_window_seconds=60
    )


@pytest.fixture
def limiter(temp_db, default_config):
    """Create rate limiter with test database."""
    rl = RateLimiter(temp_db, default_config)
    yield rl
    rl.close()


# =============================================================================
# Configuration Tests
# =============================================================================

class TestRateLimitConfig:
    """Tests for RateLimitConfig."""

    def test_default_config(self):
        """Test default configuration values."""
        config = RateLimitConfig()
        assert config.enabled is True
        assert config.cooldowns["permission"] == 30
        assert config.cooldowns["idle"] == 60
        assert config.cooldowns["complete"] == 0
        assert config.dedup_enabled is True
        assert config.dedup_window_seconds == 300

    def test_from_dict_full(self):
        """Test creating config from full dictionary."""
        data = {
            "rate_limiting": {
                "enabled": True,
                "cooldowns": {
                    "permission": 45,
                    "idle": 90,
                    "complete": 10
                }
            },
            "deduplication": {
                "enabled": False,
                "window_seconds": 600
            }
        }
        config = RateLimitConfig.from_dict(data)
        assert config.enabled is True
        assert config.cooldowns["permission"] == 45
        assert config.cooldowns["idle"] == 90
        assert config.cooldowns["complete"] == 10
        assert config.dedup_enabled is False
        assert config.dedup_window_seconds == 600

    def test_from_dict_partial(self):
        """Test creating config from partial dictionary."""
        data = {
            "rate_limiting": {
                "enabled": True
            }
        }
        config = RateLimitConfig.from_dict(data)
        assert config.enabled is True
        # Should use defaults for missing values
        assert "permission" in config.cooldowns

    def test_from_dict_empty(self):
        """Test creating config from empty dictionary."""
        config = RateLimitConfig.from_dict({})
        assert config.enabled is True  # Default
        assert config.dedup_enabled is True  # Default

    def test_get_cooldown_direct(self):
        """Test getting cooldown for direct type names."""
        config = RateLimitConfig(cooldowns={"permission": 30, "idle": 60})
        assert config.get_cooldown("permission") == 30
        assert config.get_cooldown("idle") == 60

    def test_get_cooldown_aliased(self):
        """Test getting cooldown for aliased type names."""
        config = RateLimitConfig(cooldowns={"permission": 30, "idle": 60, "complete": 0})
        # These are aliased to normalized names
        assert config.get_cooldown("permission_prompt") == 30
        assert config.get_cooldown("idle_prompt") == 60
        assert config.get_cooldown("task_complete") == 0
        assert config.get_cooldown("stop") == 0

    def test_get_cooldown_unknown(self):
        """Test getting cooldown for unknown type."""
        config = RateLimitConfig()
        assert config.get_cooldown("unknown_type") == 0


# =============================================================================
# Rate Limiting Tests
# =============================================================================

class TestRateLimiting:
    """Tests for rate limiting functionality."""

    def test_first_notification_allowed(self, limiter):
        """First notification should always be allowed."""
        result = limiter.should_send("session1", "permission")
        assert result.allowed is True
        assert result.reason == "first_notification"

    def test_cooldown_blocks_second_notification(self, limiter):
        """Second notification within cooldown should be blocked."""
        session_id = "session1"

        # First notification
        result1 = limiter.should_send(session_id, "permission")
        assert result1.allowed is True
        limiter.record_sent(session_id, "permission")

        # Second notification immediately after
        result2 = limiter.should_send(session_id, "permission")
        assert result2.allowed is False
        assert result2.reason == "cooldown_active"
        assert result2.cooldown_remaining > 0

    def test_cooldown_expires(self, limiter):
        """Notification should be allowed after cooldown expires."""
        session_id = "session2"

        # First notification
        limiter.should_send(session_id, "permission")
        limiter.record_sent(session_id, "permission")

        # Wait for cooldown (2 seconds in test config)
        time.sleep(2.5)

        # Should be allowed now
        result = limiter.should_send(session_id, "permission")
        assert result.allowed is True

    def test_no_cooldown_type_always_allowed(self, limiter):
        """Types with no cooldown should always be allowed."""
        session_id = "session3"

        # Record first
        limiter.record_sent(session_id, "complete")

        # Second should still be allowed (no cooldown for complete)
        result = limiter.should_send(session_id, "complete")
        assert result.allowed is True
        assert result.reason == "no_cooldown"

    def test_different_sessions_independent(self, limiter):
        """Different sessions should have independent rate limits."""
        # Session 1
        limiter.should_send("session_a", "permission")
        limiter.record_sent("session_a", "permission")

        # Session 2 should still be allowed
        result = limiter.should_send("session_b", "permission")
        assert result.allowed is True

    def test_different_types_independent(self, limiter):
        """Different notification types should have independent rate limits."""
        session_id = "session4"

        # Record permission
        limiter.record_sent(session_id, "permission")

        # Idle should still be allowed
        result = limiter.should_send(session_id, "idle")
        assert result.allowed is True

    def test_rate_limiting_disabled(self, temp_db):
        """When disabled, all notifications should be allowed."""
        config = RateLimitConfig(enabled=False)
        limiter = RateLimiter(temp_db, config)

        limiter.record_sent("session", "permission")
        result = limiter.should_send("session", "permission")

        assert result.allowed is True
        assert result.reason == "rate_limiting_disabled"

        limiter.close()


# =============================================================================
# Suppressed Count Tests
# =============================================================================

class TestSuppressedCount:
    """Tests for suppressed notification counting."""

    def test_suppressed_count_increments(self, limiter):
        """Suppressed count should increment for blocked notifications."""
        session_id = "session5"

        # First notification
        limiter.should_send(session_id, "permission")
        limiter.record_sent(session_id, "permission")

        # Block several more
        for i in range(3):
            result = limiter.should_send(session_id, "permission")
            assert result.allowed is False
            # Each blocked notification increases suppressed count
            assert result.suppressed_count == i + 1

    def test_suppressed_count_resets_after_send(self, limiter):
        """Suppressed count should reset after successful send."""
        session_id = "session6"

        # First send
        limiter.record_sent(session_id, "permission")

        # Block a few
        limiter.should_send(session_id, "permission")
        limiter.should_send(session_id, "permission")

        # Wait for cooldown
        time.sleep(2.5)

        # Record sent again - should reset count
        suppressed = limiter.record_sent(session_id, "permission")
        assert suppressed == 2  # Returns count before reset

        # New count should be 0
        count = limiter.get_suppressed_count(session_id, "permission")
        assert count == 0

    def test_get_suppressed_count(self, limiter):
        """Test getting suppressed count for session/type."""
        session_id = "session7"

        # Initial count should be 0
        count = limiter.get_suppressed_count(session_id, "permission")
        assert count == 0

        # After sends and blocks
        limiter.record_sent(session_id, "permission")
        limiter.should_send(session_id, "permission")  # Blocked

        count = limiter.get_suppressed_count(session_id, "permission")
        assert count == 1


# =============================================================================
# Deduplication Tests
# =============================================================================

class TestDeduplication:
    """Tests for payload deduplication."""

    def test_duplicate_payload_blocked(self, limiter):
        """Duplicate payloads within window should be blocked."""
        session_id = "session8"
        payload = {"tool_name": "Edit", "tool_input": {"file_path": "/test.py"}}

        # First send
        limiter.record_sent(session_id, "permission", payload)

        # Wait for cooldown
        time.sleep(2.5)

        # Same payload should be blocked as duplicate
        result = limiter.should_send(session_id, "permission", payload)
        assert result.allowed is False
        assert result.reason == "duplicate_suppressed"

    def test_different_payload_allowed(self, limiter):
        """Different payloads should be allowed."""
        session_id = "session9"
        payload1 = {"tool_name": "Edit", "tool_input": {"file_path": "/test1.py"}}
        payload2 = {"tool_name": "Edit", "tool_input": {"file_path": "/test2.py"}}

        # First send
        limiter.record_sent(session_id, "permission", payload1)

        # Wait for cooldown
        time.sleep(2.5)

        # Different payload should be allowed
        result = limiter.should_send(session_id, "permission", payload2)
        assert result.allowed is True

    def test_deduplication_disabled(self, temp_db):
        """When dedup disabled, same payloads should be allowed after cooldown."""
        config = RateLimitConfig(
            enabled=True,
            cooldowns={"permission": 1},
            dedup_enabled=False
        )
        limiter = RateLimiter(temp_db, config)

        session_id = "session10"
        payload = {"tool_name": "Edit"}

        limiter.record_sent(session_id, "permission", payload)
        time.sleep(1.5)

        result = limiter.should_send(session_id, "permission", payload)
        assert result.allowed is True

        limiter.close()


# =============================================================================
# Statistics Tests
# =============================================================================

class TestStatistics:
    """Tests for statistics functionality."""

    def test_get_stats_empty(self, limiter):
        """Stats should handle empty state."""
        stats = limiter.get_stats()
        assert stats["total_sessions"] == 0
        assert stats["total_suppressed"] == 0

    def test_get_stats_with_data(self, limiter):
        """Stats should reflect recorded data."""
        # Create some activity
        limiter.record_sent("session_a", "permission")
        limiter.record_sent("session_b", "idle")
        limiter.should_send("session_a", "permission")  # Blocked

        stats = limiter.get_stats()
        assert stats["total_sessions"] == 2
        assert stats["total_suppressed"] == 1
        assert "permission" in stats["by_type"]

    def test_get_stats_for_session(self, limiter):
        """Stats should filter by session."""
        limiter.record_sent("session_x", "permission")
        limiter.record_sent("session_y", "idle")

        stats = limiter.get_stats(session_id="session_x")
        assert stats["total_sessions"] == 1


# =============================================================================
# Cleanup Tests
# =============================================================================

class TestCleanup:
    """Tests for cleanup operations."""

    def test_cleanup_old_state(self, limiter):
        """Cleanup should remove old entries."""
        # Create some state
        limiter.record_sent("session_old", "permission")

        # Cleanup with 0 hour TTL (remove everything)
        limiter.cleanup_old_state(max_age_hours=0)

        # State should be gone
        count = limiter.get_suppressed_count("session_old", "permission")
        # After cleanup, the state is removed, so count will be 0
        # (get_suppressed_count returns 0 for non-existent entries)

    def test_reset_session(self, limiter):
        """Reset should clear all state for a session."""
        session_id = "session_reset"

        # Create state
        limiter.record_sent(session_id, "permission")
        limiter.record_sent(session_id, "idle")

        # Reset
        limiter.reset_session(session_id)

        # State should be gone
        result = limiter.should_send(session_id, "permission")
        assert result.allowed is True
        assert result.reason == "first_notification"


# =============================================================================
# Thread Safety Tests
# =============================================================================

class TestThreadSafety:
    """Tests for thread safety."""

    def test_concurrent_access(self, temp_db, default_config):
        """Test concurrent access from multiple threads."""
        import threading

        limiter = RateLimiter(temp_db, default_config)
        results = []
        errors = []

        def worker(session_id):
            try:
                for _ in range(10):
                    result = limiter.should_send(session_id, "permission")
                    if result.allowed:
                        limiter.record_sent(session_id, "permission")
                    results.append(result.allowed)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=worker, args=(f"thread_{i}",))
            for i in range(5)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join()

        limiter.close()

        # Should complete without errors
        assert len(errors) == 0
        # Should have some results
        assert len(results) > 0


# =============================================================================
# RateLimitResult Tests
# =============================================================================

class TestRateLimitResult:
    """Tests for RateLimitResult dataclass."""

    def test_should_send_alias(self):
        """Test should_send is alias for allowed."""
        result = RateLimitResult(allowed=True)
        assert result.should_send is True

        result = RateLimitResult(allowed=False)
        assert result.should_send is False

    def test_default_values(self):
        """Test default values."""
        result = RateLimitResult(allowed=True)
        assert result.reason == ""
        assert result.suppressed_count == 0
        assert result.last_sent_at is None
        assert result.cooldown_remaining == 0
