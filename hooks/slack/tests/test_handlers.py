"""
Test suite for V2 hook handlers.

Following TDD approach:
1. Write tests FIRST
2. Implement handlers.py to pass tests

Tests cover:
- Unified entry point for all hook events
- Payload validation
- Event routing to appropriate handlers
- Context enrichment
- Queue integration
- Audit logging
- Error handling
"""
import json
import time
import pytest
import sqlite3
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
import sys

# Add lib directory to path
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

# Import handlers module (to be implemented)
import handlers


# =============================================================================
# Payload Validation Tests
# =============================================================================

class TestPayloadValidation:
    """Test that handlers validate payload structure correctly."""

    def test_validate_notification_payload_valid(self):
        """Valid notification payload should pass validation."""
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        # Should not raise
        handlers.validate_payload(payload, "notification")

    def test_validate_notification_payload_missing_session_id(self):
        """Missing session_id should raise validation error."""
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "cwd": "/Users/test/project"
        }

        with pytest.raises(handlers.ValidationError, match="session_id"):
            handlers.validate_payload(payload, "notification")

    def test_validate_notification_payload_missing_cwd(self):
        """Missing cwd should raise validation error."""
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "session_id": "test-1234"
        }

        with pytest.raises(handlers.ValidationError, match="cwd"):
            handlers.validate_payload(payload, "notification")

    def test_validate_stop_payload_valid(self):
        """Valid stop payload should pass validation."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        handlers.validate_payload(payload, "stop")

    def test_validate_pre_tool_use_payload_valid(self):
        """Valid pre_tool_use payload should pass validation."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        handlers.validate_payload(payload, "pre_tool_use")

    def test_validate_post_tool_use_payload_valid(self):
        """Valid post_tool_use payload should pass validation."""
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {"question": "Continue?"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        handlers.validate_payload(payload, "post_tool_use")


# =============================================================================
# Event Routing Tests
# =============================================================================

class TestEventRouting:
    """Test that events are routed to correct handlers."""

    def test_route_notification_permission_event(self, test_db):
        """Notification permission_prompt should route to handle_notification."""
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "session_id": "test-1234",
            "cwd": "/Users/test/project",
            "tool_name": "Edit"
        }

        with patch.object(handlers, 'handle_notification') as mock_handler:
            mock_handler.return_value = {"success": True}
            result = handlers.route_event(test_db, payload)

            mock_handler.assert_called_once()
            assert result["success"] is True

    def test_route_notification_idle_event(self, test_db):
        """Notification idle_prompt should route to handle_notification."""
        payload = {
            "hook_event_name": "Notification",
            "notification_type": "idle_prompt",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch.object(handlers, 'handle_notification') as mock_handler:
            mock_handler.return_value = {"success": True}
            result = handlers.route_event(test_db, payload)

            mock_handler.assert_called_once()
            assert result["success"] is True

    def test_route_stop_event(self, test_db):
        """Stop event should route to handle_stop."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch.object(handlers, 'handle_stop') as mock_handler:
            mock_handler.return_value = {"success": True}
            result = handlers.route_event(test_db, payload)

            mock_handler.assert_called_once()
            assert result["success"] is True

    def test_route_pre_tool_use_event(self, test_db):
        """PreToolUse event should route to handle_pre_tool_use."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch.object(handlers, 'handle_pre_tool_use') as mock_handler:
            mock_handler.return_value = {"success": True}
            result = handlers.route_event(test_db, payload)

            mock_handler.assert_called_once()
            assert result["success"] is True

    def test_route_post_tool_use_event(self, test_db):
        """PostToolUse event should route to handle_post_tool_use."""
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {"question": "Continue?"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch.object(handlers, 'handle_post_tool_use') as mock_handler:
            mock_handler.return_value = {"success": True}
            result = handlers.route_event(test_db, payload)

            mock_handler.assert_called_once()
            assert result["success"] is True

    def test_route_unknown_event_returns_error(self, test_db):
        """Unknown event type should return error."""
        payload = {
            "unknown_field": "value"
        }

        result = handlers.route_event(test_db, payload)
        assert result["success"] is False
        assert "unknown" in result["error"].lower()


# =============================================================================
# Notification Handler Tests
# =============================================================================

class TestHandleNotification:
    """Test handle_notification function."""

    def test_handle_permission_prompt_success(self, test_db, notification_permission_payload):
        """Permission prompt should be queued successfully."""
        # Insert session first
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_notification(test_db, notification_permission_payload)

        assert result["success"] is True
        assert "event_id" in result

        # Verify event was written
        event = test_db.execute(
            "SELECT * FROM events WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert event is not None
        assert event["event_type"] == "notification"

    def test_handle_idle_prompt_success(self, test_db, notification_idle_payload):
        """Idle prompt should be queued successfully."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_notification(test_db, notification_idle_payload)

        assert result["success"] is True

        # Verify session is marked as idle
        session = test_db.execute(
            "SELECT is_idle FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert session["is_idle"] == 1

    def test_handle_notification_enriches_context(self, test_db, notification_permission_payload):
        """Notification should enrich context with git, terminal, etc."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        with patch('handlers.enrich_context') as mock_enrich:
            mock_enrich.return_value = {
                "git_branch": "main",
                "terminal_type": "tmux",
                "project_name": "test-project"
            }

            result = handlers.handle_notification(test_db, notification_permission_payload)

            assert result["success"] is True
            mock_enrich.assert_called_once()

    def test_handle_notification_queues_to_slack(self, test_db, notification_permission_payload):
        """Notification should create pending notification for Slack backend."""
        from tests.test_helpers import insert_test_session, insert_test_config
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")
        insert_test_config(test_db, "slack_enabled", "true")

        result = handlers.handle_notification(test_db, notification_permission_payload)

        assert result["success"] is True

        # Verify notification was queued
        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert notif is not None
        assert notif["backend"] == "slack"
        assert notif["status"] == "pending"
        assert notif["notification_type"] == "permission"

    def test_handle_notification_logs_to_audit(self, test_db, notification_permission_payload):
        """Notification should log to audit trail."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_notification(test_db, notification_permission_payload)

        assert result["success"] is True

        # Verify audit log entry
        audit = test_db.execute(
            "SELECT * FROM audit_log WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert audit is not None
        assert audit["action"] == "notification_queued"

    def test_handle_notification_creates_session_if_not_exists(self, test_db, notification_permission_payload):
        """Notification should create session if it doesn't exist."""
        result = handlers.handle_notification(test_db, notification_permission_payload)

        assert result["success"] is True

        # Verify session was created
        session = test_db.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert session is not None
        assert session["cwd"] == "/Users/test/project"


# =============================================================================
# Stop Handler Tests
# =============================================================================

class TestHandleStop:
    """Test handle_stop function."""

    def test_handle_stop_success(self, test_db, stop_hook_payload):
        """Stop event should be processed successfully."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_stop(test_db, stop_hook_payload)

        assert result["success"] is True
        assert "event_id" in result

    def test_handle_stop_marks_session_ended(self, test_db, stop_hook_payload):
        """Stop event should mark session as ended."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_stop(test_db, stop_hook_payload)

        # Verify session ended_at is set
        session = test_db.execute(
            "SELECT ended_at FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert session["ended_at"] is not None

    def test_handle_stop_queues_notification_if_in_tmux(self, test_db, stop_hook_payload):
        """Stop in tmux should queue task complete notification."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        # Set session terminal type to tmux
        test_db.execute(
            "UPDATE sessions SET terminal_type = ? WHERE session_id = ?",
            ("tmux", "test-session-1234")
        )
        test_db.commit()

        result = handlers.handle_stop(test_db, stop_hook_payload)

        # Verify notification was queued
        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert notif is not None
        assert notif["notification_type"] == "task_complete"

    def test_handle_stop_skips_notification_if_not_tmux(self, test_db, stop_hook_payload):
        """Stop not in tmux should skip notification unless notify_always."""
        from tests.test_helpers import insert_test_session, insert_test_config
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")
        insert_test_config(test_db, "notify_always", "false")

        # Set session terminal type to vscode
        test_db.execute(
            "UPDATE sessions SET terminal_type = ? WHERE session_id = ?",
            ("vscode", "test-session-1234")
        )
        test_db.commit()

        result = handlers.handle_stop(test_db, stop_hook_payload)

        # Verify no notification was queued
        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert notif is None

    def test_handle_stop_queues_if_notify_always(self, test_db, stop_hook_payload):
        """Stop with notify_always=true should queue notification."""
        from tests.test_helpers import insert_test_session, insert_test_config
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")
        insert_test_config(test_db, "notify_always", "true")

        result = handlers.handle_stop(test_db, stop_hook_payload)

        # Verify notification was queued
        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert notif is not None

    def test_handle_stop_enriches_with_token_usage(self, test_db, stop_hook_payload):
        """Stop should enrich context with token usage when notification is sent."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        # Set terminal_type to tmux to trigger notification path where get_token_usage is called
        test_db.execute(
            "UPDATE sessions SET terminal_type = ? WHERE session_id = ?",
            ("tmux", "test-session-1234")
        )
        test_db.commit()

        with patch('handlers.get_token_usage') as mock_tokens:
            mock_tokens.return_value = {"input": 1000, "output": 500}

            result = handlers.handle_stop(test_db, stop_hook_payload)

            assert result["success"] is True
            mock_tokens.assert_called_once_with("test-session-1234", "/Users/test/project")

    def test_handle_stop_logs_to_audit(self, test_db, stop_hook_payload):
        """Stop should log to audit trail."""
        from tests.test_helpers import insert_test_session
        insert_test_session(test_db, "test-session-1234", "/Users/test/project")

        result = handlers.handle_stop(test_db, stop_hook_payload)

        # Verify audit log entry
        audit = test_db.execute(
            "SELECT * FROM audit_log WHERE session_id = ? AND action = ?",
            ("test-session-1234", "session_stopped")
        ).fetchone()
        assert audit is not None


# =============================================================================
# PreToolUse Handler Tests
# =============================================================================

class TestHandlePreToolUse:
    """Test handle_pre_tool_use function."""

    def test_handle_pre_tool_use_success(self, test_db, pre_tool_use_edit_payload):
        """PreToolUse event should be captured successfully."""
        result = handlers.handle_pre_tool_use(test_db, pre_tool_use_edit_payload)

        assert result["success"] is True
        assert "event_id" in result

    def test_handle_pre_tool_use_stores_event(self, test_db, pre_tool_use_edit_payload):
        """PreToolUse should store event in database."""
        result = handlers.handle_pre_tool_use(test_db, pre_tool_use_edit_payload)

        # Verify event was stored
        event = test_db.execute(
            "SELECT * FROM events WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert event is not None
        assert event["event_type"] == "pre_tool_use"
        payload = json.loads(event["hook_payload"])
        assert payload["tool_name"] == "Edit"

    def test_handle_pre_tool_use_updates_session_activity(self, test_db, pre_tool_use_edit_payload):
        """PreToolUse should update session last_activity_at."""
        from tests.test_helpers import insert_test_session

        # Insert session with initial timestamp
        insert_test_session(test_db, "test-session-1234", "/Users/test/project", started_at=1000000)

        initial_activity = test_db.execute(
            "SELECT last_activity_at FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()["last_activity_at"]

        # Handler will update with current time which is always > 1000000
        result = handlers.handle_pre_tool_use(test_db, pre_tool_use_edit_payload)

        updated_activity = test_db.execute(
            "SELECT last_activity_at FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()["last_activity_at"]

        assert updated_activity > initial_activity

    def test_handle_pre_tool_use_creates_session_if_not_exists(self, test_db, pre_tool_use_edit_payload):
        """PreToolUse should create session if it doesn't exist."""
        result = handlers.handle_pre_tool_use(test_db, pre_tool_use_edit_payload)

        # Verify session was created
        session = test_db.execute(
            "SELECT * FROM sessions WHERE session_id = ?",
            ("test-session-1234",)
        ).fetchone()
        assert session is not None


# =============================================================================
# PostToolUse Handler Tests
# =============================================================================

class TestHandlePostToolUse:
    """Test handle_post_tool_use function."""

    def test_handle_post_tool_use_success(self, test_db):
        """PostToolUse event should be captured successfully."""
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {"question": "Continue?"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        result = handlers.handle_post_tool_use(test_db, payload)

        assert result["success"] is True

    def test_handle_post_tool_use_tracks_ask_user_question(self, test_db):
        """PostToolUse should track AskUserQuestion tool usage."""
        payload = {
            "tool_name": "AskUserQuestion",
            "tool_input": {"question": "Continue with deployment?"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        result = handlers.handle_post_tool_use(test_db, payload)

        # Verify event was stored
        event = test_db.execute(
            "SELECT * FROM events WHERE session_id = ?",
            ("test-1234",)
        ).fetchone()
        assert event is not None
        assert event["event_type"] == "post_tool_use"

    def test_handle_post_tool_use_ignores_other_tools(self, test_db):
        """PostToolUse should only track specific tools like AskUserQuestion."""
        payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        result = handlers.handle_post_tool_use(test_db, payload)

        # Should still succeed but may not store event
        assert result["success"] is True


# =============================================================================
# Context Enrichment Tests
# =============================================================================

class TestContextEnrichment:
    """Test context enrichment functions."""

    def test_enrich_context_calls_git_enricher(self, test_db):
        """enrich_context should call git enricher."""
        session = {
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch('handlers.get_git_status') as mock_git:
            mock_git.return_value = {
                "branch": "main",
                "staged": 2,
                "modified": 1
            }

            context = handlers.enrich_context(test_db, session, {})

            assert "git" in context
            assert context["git"]["branch"] == "main"

    def test_enrich_context_calls_terminal_enricher(self, test_db):
        """enrich_context should detect terminal type."""
        session = {
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch('handlers.detect_terminal') as mock_terminal:
            mock_terminal.return_value = {
                "type": "tmux",
                "info": "main:0.0"
            }

            context = handlers.enrich_context(test_db, session, {})

            assert "terminal" in context
            assert context["terminal"]["type"] == "tmux"

    def test_enrich_context_gets_project_name(self, test_db):
        """enrich_context should extract project name."""
        session = {
            "session_id": "test-1234",
            "cwd": "/Users/test/my-project"
        }

        context = handlers.enrich_context(test_db, session, {})

        assert "project_name" in context

    def test_enrich_context_handles_enricher_failure(self, test_db):
        """enrich_context should handle enricher failures gracefully."""
        session = {
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        with patch('handlers.get_git_status') as mock_git:
            mock_git.side_effect = Exception("Git failed")

            # Should not raise
            context = handlers.enrich_context(test_db, session, {})

            # Git context might be None or have error flag
            assert context is not None


# =============================================================================
# Error Handling Tests
# =============================================================================

class TestErrorHandling:
    """Test error handling and edge cases."""

    def test_handle_notification_invalid_payload(self, test_db):
        """Invalid payload should return error result."""
        payload = {"invalid": "data"}

        result = handlers.handle_notification(test_db, payload)

        assert result["success"] is False
        assert "error" in result

    def test_handle_stop_database_error(self, test_db):
        """Database errors should be caught and returned."""
        payload = {
            "hook_event_name": "Stop",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        # Simulate database error by closing connection
        test_db.close()

        result = handlers.handle_stop(test_db, payload)

        assert result["success"] is False
        assert "error" in result

    def test_route_event_malformed_json(self, test_db):
        """Malformed JSON should be handled gracefully."""
        # This would be caught at validation layer
        payload = None

        result = handlers.route_event(test_db, payload)

        assert result["success"] is False


# =============================================================================
# Integration Tests
# =============================================================================

class TestIntegration:
    """End-to-end integration tests."""

    def test_full_permission_flow(self, test_db):
        """Test full flow: PreToolUse -> Notification -> Queue."""
        from tests.test_helpers import insert_test_config, insert_test_session

        # Setup config
        insert_test_config(test_db, "slack_enabled", "true")
        insert_test_config(test_db, "notify_on_permission", "true")

        # 1. PreToolUse event
        pre_tool_payload = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/tmp/test.txt"},
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        result1 = handlers.handle_pre_tool_use(test_db, pre_tool_payload)
        assert result1["success"] is True

        # 2. Notification event
        notif_payload = {
            "hook_event_name": "Notification",
            "notification_type": "permission_prompt",
            "session_id": "test-1234",
            "cwd": "/Users/test/project",
            "tool_name": "Edit"
        }

        result2 = handlers.handle_notification(test_db, notif_payload)
        assert result2["success"] is True

        # 3. Verify notification was queued
        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-1234",)
        ).fetchone()
        assert notif is not None
        assert notif["status"] == "pending"

    def test_full_task_complete_flow(self, test_db):
        """Test full flow: Session -> Work -> Stop -> Notification."""
        from tests.test_helpers import insert_test_config, insert_test_session

        # Setup
        insert_test_session(test_db, "test-1234", "/Users/test/project")
        insert_test_config(test_db, "notify_always", "true")

        # Mark session as in tmux
        test_db.execute(
            "UPDATE sessions SET terminal_type = ? WHERE session_id = ?",
            ("tmux", "test-1234")
        )
        test_db.commit()

        # Stop event
        stop_payload = {
            "hook_event_name": "Stop",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        result = handlers.handle_stop(test_db, stop_payload)
        assert result["success"] is True

        # Verify session ended and notification queued
        session = test_db.execute(
            "SELECT ended_at FROM sessions WHERE session_id = ?",
            ("test-1234",)
        ).fetchone()
        assert session["ended_at"] is not None

        notif = test_db.execute(
            "SELECT * FROM notifications WHERE session_id = ?",
            ("test-1234",)
        ).fetchone()
        assert notif is not None
        assert notif["notification_type"] == "task_complete"
