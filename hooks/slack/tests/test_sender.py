"""
Test suite for notification sender and dispatcher (V2).

Tests cover:
- Webhook URL validation (security)
- Payload building for each notification type
- HTTP error handling
- Queue processing
- Retry logic
- Status updates
"""
import pytest
import json
import time
import responses
from unittest.mock import patch, MagicMock
import sys
from pathlib import Path

# Add lib directory to path
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

from sender import (
    validate_webhook_url,
    build_permission_payload,
    build_stop_payload,
    build_idle_payload,
    send_notification,
    process_queue,
    NotificationError,
    WebhookValidationError
)


# =============================================================================
# Webhook Validation Tests
# =============================================================================

class TestWebhookValidation:
    """Test webhook URL validation for security."""

    def test_valid_slack_webhook(self):
        """Valid Slack webhook URL should pass."""
        url = "https://hooks.slack.com/services/TTEST/BTEST/test"
        assert validate_webhook_url(url) == url

    def test_valid_discord_webhook(self):
        """Valid Discord webhook URL should pass."""
        url = "https://discord.com/api/webhooks/123456789/abcdefgh"
        assert validate_webhook_url(url) == url

    def test_valid_zapier_webhook(self):
        """Valid Zapier webhook URL should pass."""
        url = "https://hooks.zapier.com/hooks/catch/123456/abcdef/"
        assert validate_webhook_url(url) == url

    def test_reject_http_url(self):
        """HTTP URLs should be rejected (must use HTTPS)."""
        url = "http://hooks.slack.com/services/TTEST/BTEST/test"
        with pytest.raises(WebhookValidationError, match="must use HTTPS"):
            validate_webhook_url(url)

    def test_reject_unknown_domain(self):
        """Unknown domains should be rejected (SSRF protection)."""
        url = "https://evil.com/webhook"
        with pytest.raises(WebhookValidationError, match="not allowed"):
            validate_webhook_url(url)

    def test_reject_localhost(self):
        """Localhost URLs should be rejected."""
        url = "https://localhost:8000/webhook"
        with pytest.raises(WebhookValidationError, match="not allowed"):
            validate_webhook_url(url)

    def test_reject_internal_ip(self):
        """Internal IP addresses should be rejected."""
        url = "https://192.168.1.1/webhook"
        with pytest.raises(WebhookValidationError, match="not allowed"):
            validate_webhook_url(url)

    def test_reject_malformed_url(self):
        """Malformed URLs should be rejected."""
        with pytest.raises(WebhookValidationError):
            validate_webhook_url("not-a-url")

    def test_reject_empty_url(self):
        """Empty URLs should be rejected."""
        with pytest.raises(WebhookValidationError):
            validate_webhook_url("")


# =============================================================================
# Payload Building Tests
# =============================================================================

class TestPermissionPayload:
    """Test building permission request payloads."""

    def test_edit_tool_permission(self):
        """Edit tool should show file path."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {
                "file_path": "/Users/test/project/src/app.ts",
                "old_string": "const x = 1",
                "new_string": "const x = 2"
            },
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        context = {
            "project_name": "my-project",
            "git_branch": "main",
            "terminal_type": "tmux",
            "terminal_info": "main:0.0",
            "switch_command": "tmux select-window -t main:0"
        }

        payload = build_permission_payload(event_data, context)

        # Verify structure
        assert "text" in payload
        assert "blocks" in payload
        assert len(payload["blocks"]) > 0

        # Verify content
        text = json.dumps(payload).lower()
        assert "edit" in text
        assert "app.ts" in text
        assert "my-project" in text

    def test_bash_tool_permission(self):
        """Bash tool should show command."""
        event_data = {
            "tool_name": "Bash",
            "tool_input": {
                "command": "npm install express",
                "description": "Install express package"
            },
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        context = {
            "project_name": "my-project",
            "git_branch": "feature/auth",
            "terminal_type": "vscode"
        }

        payload = build_permission_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "bash" in text
        assert "npm install" in text

    def test_webfetch_tool_permission(self):
        """WebFetch tool should show URL."""
        event_data = {
            "tool_name": "WebFetch",
            "tool_input": {
                "url": "https://api.github.com/repos/user/repo"
            },
            "session_id": "test-1234"
        }

        context = {"project_name": "test"}

        payload = build_permission_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "web" in text or "fetch" in text
        assert "api.github.com" in text

    def test_task_tool_permission(self):
        """Task tool should show subagent type."""
        event_data = {
            "tool_name": "Task",
            "tool_input": {
                "subagent_type": "coder",
                "description": "Fix authentication bug"
            },
            "session_id": "test-1234"
        }

        context = {"project_name": "test"}

        payload = build_permission_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "agent" in text or "task" in text
        assert "coder" in text

    def test_unknown_tool_permission(self):
        """Unknown tools should have generic message."""
        event_data = {
            "tool_name": "UnknownTool",
            "tool_input": {},
            "session_id": "test-1234"
        }

        context = {"project_name": "test"}

        payload = build_permission_payload(event_data, context)

        assert "blocks" in payload
        assert payload["text"]  # Fallback text

    def test_permission_payload_with_git_context(self):
        """Permission payload should include git status."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/test/app.ts"},
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "git_branch": "feature/new-feature",
            "git_staged": 2,
            "git_modified": 3,
            "git_untracked": 1
        }

        payload = build_permission_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "feature/new-feature" in text or "feature" in text


class TestStopPayload:
    """Test building task completion payloads."""

    def test_basic_stop_payload(self):
        """Basic stop payload with minimal context."""
        event_data = {
            "hook_event_name": "Stop",
            "session_id": "test-1234",
            "cwd": "/Users/test/project"
        }

        context = {
            "project_name": "my-project",
            "task_description": "Fix authentication bug"
        }

        payload = build_stop_payload(event_data, context)

        assert "text" in payload
        assert "blocks" in payload
        text = json.dumps(payload).lower()
        assert "complete" in text or "done" in text or "finished" in text

    def test_stop_payload_with_tokens(self):
        """Stop payload should include token usage."""
        event_data = {
            "hook_event_name": "Stop",
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "task_description": "Implement feature",
            "token_usage": "15.2K in / 8.5K out"
        }

        payload = build_stop_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "15.2k" in text or "token" in text

    def test_stop_payload_with_git_status(self):
        """Stop payload should include git changes."""
        event_data = {
            "hook_event_name": "Stop",
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "task_description": "Refactor code",
            "git_branch": "main",
            "git_staged": 3,
            "git_modified": 2,
            "git_untracked": 1
        }

        payload = build_stop_payload(event_data, context)

        text = json.dumps(payload).lower()
        # Should mention files changed
        assert "3" in text or "staged" in text or "modified" in text

    def test_stop_payload_with_terminal_switch(self):
        """Stop payload should include terminal switch command."""
        event_data = {
            "hook_event_name": "Stop",
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "task_description": "Task completed",
            "terminal_type": "tmux",
            "switch_command": "tmux select-window -t main:0"
        }

        payload = build_stop_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "tmux" in text


class TestIdlePayload:
    """Test building idle prompt payloads."""

    def test_basic_idle_payload(self):
        """Basic idle payload for input required."""
        event_data = {
            "hook_event_name": "Notification",
            "notification_type": "idle_prompt",
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "terminal_type": "tmux"
        }

        payload = build_idle_payload(event_data, context)

        assert "text" in payload
        assert "blocks" in payload
        text = json.dumps(payload).lower()
        assert "waiting" in text or "input" in text or "idle" in text

    def test_idle_payload_with_switch_command(self):
        """Idle payload should include switch command."""
        event_data = {
            "hook_event_name": "Notification",
            "notification_type": "idle_prompt",
            "session_id": "test-1234"
        }

        context = {
            "project_name": "my-project",
            "terminal_type": "tmux",
            "switch_command": "tmux select-window -t dev:2"
        }

        payload = build_idle_payload(event_data, context)

        text = json.dumps(payload).lower()
        assert "tmux" in text


# =============================================================================
# Notification Sending Tests
# =============================================================================

class TestSendNotification:
    """Test sending notifications via webhook."""

    @responses.activate
    def test_successful_send(self, test_db, test_config):
        """Successful webhook call should update status to 'sent'."""
        # Setup: Insert notification in database
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        payload = {"text": "Test notification", "blocks": []}
        cursor = test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at)
               VALUES (1, 'test-1234', 'permission', 'slack', 'pending', ?, ?)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()
        notif_id = cursor.lastrowid

        # Mock webhook response
        responses.add(
            responses.POST,
            webhook_url,
            status=200,
            body="ok"
        )

        # Execute
        result = send_notification(test_db, notif_id)

        # Verify
        assert result is True

        notif = test_db.execute(
            "SELECT status, sent_at, error FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        assert notif["status"] == "sent"
        assert notif["sent_at"] is not None
        assert notif["error"] is None

    @responses.activate
    def test_failed_send_http_error(self, test_db, test_config):
        """HTTP error should update status to 'failed'."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        payload = {"text": "Test notification"}
        cursor = test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at)
               VALUES (1, 'test-1234', 'permission', 'slack', 'pending', ?, ?)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()
        notif_id = cursor.lastrowid

        # Mock webhook failure
        responses.add(
            responses.POST,
            webhook_url,
            status=500,
            body="Internal Server Error"
        )

        # Execute
        result = send_notification(test_db, notif_id)

        # Verify
        assert result is False

        notif = test_db.execute(
            "SELECT status, retry_count, error FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        assert notif["status"] == "failed"
        assert notif["retry_count"] == 1
        assert notif["error"] is not None
        assert "500" in notif["error"]

    @responses.activate
    def test_failed_send_timeout(self, test_db, test_config):
        """Timeout should be handled gracefully."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        payload = {"text": "Test notification"}
        cursor = test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at)
               VALUES (1, 'test-1234', 'permission', 'slack', 'pending', ?, ?)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()
        notif_id = cursor.lastrowid

        # Mock timeout
        import requests
        responses.add(
            responses.POST,
            webhook_url,
            body=requests.exceptions.Timeout("Connection timeout")
        )

        # Execute
        result = send_notification(test_db, notif_id)

        # Verify
        assert result is False

        notif = test_db.execute(
            "SELECT status, error FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        assert notif["status"] == "failed"
        assert "timeout" in notif["error"].lower()

    def test_send_notification_not_found(self, test_db):
        """Non-existent notification ID should raise error."""
        with pytest.raises(NotificationError, match="not found"):
            send_notification(test_db, 999999)

    @responses.activate
    def test_retry_increments_count(self, test_db, test_config):
        """Each retry should increment retry_count."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        payload = {"text": "Test notification"}
        cursor = test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, retry_count)
               VALUES (1, 'test-1234', 'permission', 'slack', 'failed', ?, ?, 2)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()
        notif_id = cursor.lastrowid

        # Mock failure
        responses.add(responses.POST, webhook_url, status=500)

        # Execute
        send_notification(test_db, notif_id)

        # Verify retry count incremented
        notif = test_db.execute(
            "SELECT retry_count FROM notifications WHERE id = ?",
            (notif_id,)
        ).fetchone()

        assert notif["retry_count"] == 3


# =============================================================================
# Queue Processing Tests
# =============================================================================

class TestProcessQueue:
    """Test batch queue processing."""

    @responses.activate
    def test_process_pending_notifications(self, test_db, test_config):
        """Process all pending notifications."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        # Insert 3 pending notifications
        payload = {"text": "Test"}
        for i in range(3):
            test_db.execute(
                """INSERT INTO notifications
                   (event_id, session_id, notification_type, backend, status, payload, created_at)
                   VALUES (?, 'test-1234', 'permission', 'slack', 'pending', ?, ?)""",
                (i + 1, json.dumps(payload), int(time.time()))
            )
        test_db.commit()

        # Mock webhook success
        responses.add(responses.POST, webhook_url, status=200, body="ok")

        # Process queue
        processed = process_queue(test_db, batch_size=10)

        # Verify all 3 sent
        assert processed == 3

        sent_count = test_db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE status = 'sent'"
        ).fetchone()["cnt"]

        assert sent_count == 3

    @responses.activate
    def test_process_queue_respects_batch_size(self, test_db, test_config):
        """Process only batch_size notifications at a time."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        # Insert 5 pending notifications
        payload = {"text": "Test"}
        for i in range(5):
            test_db.execute(
                """INSERT INTO notifications
                   (event_id, session_id, notification_type, backend, status, payload, created_at)
                   VALUES (?, 'test-1234', 'permission', 'slack', 'pending', ?, ?)""",
                (i + 1, json.dumps(payload), int(time.time()))
            )
        test_db.commit()

        # Mock webhook success
        responses.add(responses.POST, webhook_url, status=200, body="ok")

        # Process with batch_size=3
        processed = process_queue(test_db, batch_size=3)

        # Verify only 3 processed
        assert processed == 3

        pending_count = test_db.execute(
            "SELECT COUNT(*) as cnt FROM notifications WHERE status = 'pending'"
        ).fetchone()["cnt"]

        assert pending_count == 2

    @responses.activate
    def test_process_queue_retries_failed(self, test_db, test_config):
        """Failed notifications with retry_count < 3 should be retried."""
        webhook_url = test_config["webhook_url"]
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", webhook_url)
        insert_test_session(test_db, "test-1234", "/test")

        # Insert failed notification with retry_count=1
        payload = {"text": "Test"}
        test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, retry_count)
               VALUES (1, 'test-1234', 'permission', 'slack', 'failed', ?, ?, 1)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()

        # Mock success on retry
        responses.add(responses.POST, webhook_url, status=200, body="ok")

        # Process queue
        processed = process_queue(test_db)

        # Verify it was retried and succeeded
        assert processed == 1

        notif = test_db.execute(
            "SELECT status FROM notifications WHERE event_id = 1"
        ).fetchone()

        assert notif["status"] == "sent"

    def test_process_queue_skips_max_retries(self, test_db, test_config):
        """Failed notifications with retry_count >= 3 should be skipped."""
        from tests.test_helpers import insert_test_config, insert_test_session
        insert_test_config(test_db, "slack_webhook_url", test_config["webhook_url"])
        insert_test_session(test_db, "test-1234", "/test")

        # Insert failed notification with retry_count=3
        payload = {"text": "Test"}
        test_db.execute(
            """INSERT INTO notifications
               (event_id, session_id, notification_type, backend, status, payload, created_at, retry_count)
               VALUES (1, 'test-1234', 'permission', 'slack', 'failed', ?, ?, 3)""",
            (json.dumps(payload), int(time.time()))
        )
        test_db.commit()

        # Process queue
        processed = process_queue(test_db)

        # Verify nothing processed (max retries reached)
        assert processed == 0

    def test_process_empty_queue(self, test_db, test_config):
        """Empty queue should return 0."""
        from tests.test_helpers import insert_test_config
        insert_test_config(test_db, "slack_webhook_url", test_config["webhook_url"])

        processed = process_queue(test_db)
        assert processed == 0


# =============================================================================
# Slack Block Kit Format Tests
# =============================================================================

class TestSlackBlockKit:
    """Test that payloads use valid Slack Block Kit format."""

    def test_permission_payload_has_blocks(self):
        """Permission payload should have blocks array."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/test/app.ts"},
            "session_id": "test-1234"
        }
        context = {"project_name": "test"}

        payload = build_permission_payload(event_data, context)

        assert isinstance(payload["blocks"], list)
        assert len(payload["blocks"]) > 0

    def test_stop_payload_has_blocks(self):
        """Stop payload should have blocks array."""
        event_data = {"hook_event_name": "Stop", "session_id": "test-1234"}
        context = {"project_name": "test", "task_description": "Done"}

        payload = build_stop_payload(event_data, context)

        assert isinstance(payload["blocks"], list)
        assert len(payload["blocks"]) > 0

    def test_idle_payload_has_blocks(self):
        """Idle payload should have blocks array."""
        event_data = {
            "hook_event_name": "Notification",
            "notification_type": "idle_prompt",
            "session_id": "test-1234"
        }
        context = {"project_name": "test"}

        payload = build_idle_payload(event_data, context)

        assert isinstance(payload["blocks"], list)
        assert len(payload["blocks"]) > 0

    def test_payload_has_text_fallback(self):
        """All payloads should have text for fallback."""
        event_data = {
            "tool_name": "Edit",
            "tool_input": {"file_path": "/test/app.ts"},
            "session_id": "test-1234"
        }
        context = {"project_name": "test"}

        payload = build_permission_payload(event_data, context)

        assert "text" in payload
        assert isinstance(payload["text"], str)
        assert len(payload["text"]) > 0


# =============================================================================
# Helper Function Tests
# =============================================================================

def test_build_bash_tool_permission():
    """Test Bash-specific permission builder."""
    event_data = {
        "tool_name": "Bash",
        "tool_input": {
            "command": "git commit -m 'test'",
            "description": "Commit changes"
        },
        "session_id": "test-1234"
    }
    context = {"project_name": "test-project"}

    payload = build_permission_payload(event_data, context)

    text = json.dumps(payload).lower()
    assert "bash" in text or "command" in text
    assert "git commit" in text
