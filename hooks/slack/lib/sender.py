"""
Notification sender and dispatcher for Slack Notification V2.

This module handles:
- Building Slack Block Kit payloads for different notification types
- Validating webhook URLs (security)
- Sending notifications via HTTP webhook
- Processing notification queue with retry logic
- Updating notification status in database

Architecture:
- Pure functions for payload building (easy to test)
- Database connection passed as parameter (no global state)
- Graceful error handling with detailed error messages
"""
import json
import time
import sqlite3
import requests
from urllib.parse import urlparse
from typing import Dict, Any, Optional, List


# =============================================================================
# Custom Exceptions
# =============================================================================

class NotificationError(Exception):
    """Base exception for notification errors."""
    pass


class WebhookValidationError(NotificationError):
    """Webhook URL failed security validation."""
    pass


# =============================================================================
# Webhook Validation (Security)
# =============================================================================

# Whitelist of allowed webhook domains (SSRF protection)
ALLOWED_WEBHOOK_DOMAINS = [
    'hooks.slack.com',
    'discord.com',
    'hooks.zapier.com'
]


def validate_webhook_url(url: str) -> str:
    """
    Validate webhook URL for security.

    Security checks:
    - Must use HTTPS (prevent credential leakage)
    - Must be on whitelist (prevent SSRF attacks)
    - Reject localhost/internal IPs

    Args:
        url: Webhook URL to validate

    Returns:
        Validated URL (same as input if valid)

    Raises:
        WebhookValidationError: If URL fails validation
    """
    if not url or not isinstance(url, str):
        raise WebhookValidationError("Webhook URL cannot be empty")

    try:
        parsed = urlparse(url)
    except Exception as e:
        raise WebhookValidationError(f"Malformed URL: {e}")

    # Must use HTTPS
    if parsed.scheme != 'https':
        raise WebhookValidationError(
            "Webhook URL must use HTTPS (got: {})".format(parsed.scheme)
        )

    # Check against whitelist
    domain = parsed.netloc.lower()

    # Handle port numbers (e.g., discord.com:443)
    if ':' in domain:
        domain = domain.split(':')[0]

    # Check if domain or any parent domain is allowed
    is_allowed = False
    for allowed_domain in ALLOWED_WEBHOOK_DOMAINS:
        if domain == allowed_domain or domain.endswith('.' + allowed_domain):
            is_allowed = True
            break

    if not is_allowed:
        raise WebhookValidationError(
            f"Domain '{domain}' not allowed. Allowed domains: {', '.join(ALLOWED_WEBHOOK_DOMAINS)}"
        )

    return url


# =============================================================================
# Payload Builders
# =============================================================================

def build_permission_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any],
    suppressed_count: int = 0
) -> Dict[str, Any]:
    """
    Build Slack Block Kit payload for permission request.

    Args:
        event_data: Event data from hook (tool_name, tool_input, etc.)
        context: Enriched context (project_name, git_branch, terminal_info, etc.)
        suppressed_count: Number of previously suppressed notifications

    Returns:
        Slack webhook payload with blocks
    """
    tool_name = event_data.get("tool_name", "Unknown")
    tool_input = event_data.get("tool_input", {})
    session_id = event_data.get("session_id", "unknown")
    project_name = context.get("project_name", "project")

    # Get session serial (last 4 chars)
    session_serial = session_id[-4:] if len(session_id) >= 4 else session_id

    # Build tool-specific details
    tool_details = _format_tool_details(tool_name, tool_input)

    # Build context footer
    context_parts = []
    if context.get("git_branch"):
        git_summary = _format_git_summary(context)
        context_parts.append(git_summary)
    if context.get("terminal_type"):
        context_parts.append(f"{context['terminal_type']}")
    context_parts.append(f"#{session_serial}")

    # Add suppressed count indicator if any
    if suppressed_count > 0:
        context_parts.append(f"+{suppressed_count} suppressed")

    # Build blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"🔔 {project_name}: Permission Required"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": tool_details
            }
        }
    ]

    # Add switch command if available
    if context.get("switch_command"):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{context['switch_command']}```"
            }
        })

    # Add context footer
    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": " | ".join(context_parts)
            }
        ]
    })

    # Build payload
    fallback_text = f"{project_name}: {tool_name} permission required"
    if suppressed_count > 0:
        fallback_text += f" (+{suppressed_count} suppressed)"

    return {
        "text": fallback_text,
        "blocks": blocks
    }


def build_stop_payload(event_data: Dict[str, Any], context: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build Slack Block Kit payload for task completion.

    Args:
        event_data: Event data from Stop hook
        context: Enriched context (task_description, token_usage, git_status, etc.)

    Returns:
        Slack webhook payload with blocks
    """
    session_id = event_data.get("session_id", "unknown")
    project_name = context.get("project_name", "project")
    task_description = context.get("task_description", "Task completed")

    # Get session serial
    session_serial = session_id[-4:] if len(session_id) >= 4 else session_id

    # Truncate task description if too long
    if len(task_description) > 150:
        task_description = task_description[:147] + "..."

    # Build summary section
    summary_parts = [f"*Task:* {task_description}"]

    if context.get("token_usage"):
        summary_parts.append(f"*Tokens:* {context['token_usage']}")

    if context.get("git_branch"):
        git_summary = _format_git_summary(context)
        summary_parts.append(f"*Git:* {git_summary}")

    # Build blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"✅ {project_name}: Task Complete"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "\n".join(summary_parts)
            }
        }
    ]

    # Add switch command if available
    if context.get("switch_command"):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{context['switch_command']}```"
            }
        })

    # Add context footer
    context_parts = []
    if context.get("terminal_type"):
        context_parts.append(f"{context['terminal_type']}")
    context_parts.append(f"#{session_serial}")

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": " | ".join(context_parts)
            }
        ]
    })

    # Build payload
    fallback_text = f"{project_name}: Task complete"

    return {
        "text": fallback_text,
        "blocks": blocks
    }


def build_idle_payload(
    event_data: Dict[str, Any],
    context: Dict[str, Any],
    suppressed_count: int = 0
) -> Dict[str, Any]:
    """
    Build Slack Block Kit payload for idle/input required.

    Args:
        event_data: Event data from Notification hook
        context: Enriched context
        suppressed_count: Number of previously suppressed notifications

    Returns:
        Slack webhook payload with blocks
    """
    session_id = event_data.get("session_id", "unknown")
    project_name = context.get("project_name", "project")

    # Get session serial
    session_serial = session_id[-4:] if len(session_id) >= 4 else session_id

    # Build blocks
    blocks = [
        {
            "type": "header",
            "text": {
                "type": "plain_text",
                "text": f"⏸️ {project_name}: Waiting for Input"
            }
        },
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": "Claude is waiting for your response."
            }
        }
    ]

    # Add switch command if available
    if context.get("switch_command"):
        blocks.append({
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"```{context['switch_command']}```"
            }
        })

    # Add context footer
    context_parts = []
    if context.get("terminal_type"):
        context_parts.append(f"{context['terminal_type']}")
    context_parts.append(f"#{session_serial}")

    # Add suppressed count indicator if any
    if suppressed_count > 0:
        context_parts.append(f"+{suppressed_count} suppressed")

    blocks.append({
        "type": "context",
        "elements": [
            {
                "type": "mrkdwn",
                "text": " | ".join(context_parts)
            }
        ]
    })

    # Build payload
    fallback_text = f"{project_name}: Waiting for input"
    if suppressed_count > 0:
        fallback_text += f" (+{suppressed_count} suppressed)"

    return {
        "text": fallback_text,
        "blocks": blocks
    }


# =============================================================================
# Helper Functions for Payload Building
# =============================================================================

def _format_tool_details(tool_name: str, tool_input: Dict[str, Any]) -> str:
    """
    Format tool-specific details for display.

    Args:
        tool_name: Name of the tool
        tool_input: Tool input parameters

    Returns:
        Formatted markdown string
    """
    if tool_name == "Edit":
        file_path = tool_input.get("file_path", "")
        if file_path:
            import os
            filename = os.path.basename(file_path)
            dirname = os.path.dirname(file_path)
            # Shorten path if too long
            if len(dirname) > 50:
                dirname = "..." + dirname[-47:]
            return f"*Edit Permission*\n📄 File: `{filename}`\n📁 Path: `{dirname}`"
        return "*Edit Permission*\nWaiting for approval"

    elif tool_name == "Bash":
        command = tool_input.get("command", "")
        if command:
            # Truncate long commands
            if len(command) > 100:
                command = command[:97] + "..."
            return f"*Bash Permission*\n💻 Command: `{command}`"
        return "*Bash Permission*\nWaiting for approval"

    elif tool_name == "WebFetch":
        url = tool_input.get("url", "")
        if url:
            return f"*Web Access Permission*\n🌐 URL: {url}"
        return "*Web Access Permission*\nWaiting for approval"

    elif tool_name == "Task":
        subagent = tool_input.get("subagent_type", "")
        description = tool_input.get("description", "")
        if subagent:
            # Truncate description
            if len(description) > 100:
                description = description[:97] + "..."
            return f"*Agent Task Permission*\n🤖 Agent: {subagent}\n📋 Task: {description}"
        return "*Task Permission*\nWaiting for approval"

    elif tool_name == "Write":
        file_path = tool_input.get("file_path", "")
        if file_path:
            import os
            filename = os.path.basename(file_path)
            return f"*Write Permission*\n📄 File: `{filename}`"
        return "*Write Permission*\nWaiting for approval"

    elif tool_name == "Read":
        file_path = tool_input.get("file_path", "")
        if file_path:
            import os
            filename = os.path.basename(file_path)
            return f"*Read Permission*\n📄 File: `{filename}`"
        return "*Read Permission*\nWaiting for approval"

    else:
        return f"*{tool_name} Permission*\n⚠️ Waiting for approval"


def _format_git_summary(context: Dict[str, Any]) -> str:
    """
    Format git status summary.

    Args:
        context: Context dict with git_branch, git_staged, etc.

    Returns:
        Formatted git summary string
    """
    branch = context.get("git_branch", "")
    staged = context.get("git_staged", 0)
    modified = context.get("git_modified", 0)
    untracked = context.get("git_untracked", 0)

    parts = [branch]
    if staged or modified or untracked:
        parts.append(f"S:{staged} M:{modified} U:{untracked}")

    return " | ".join(parts)


# =============================================================================
# Notification Sending
# =============================================================================

def _build_slack_payload(stored_payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Build Slack Block Kit payload from stored notification data.

    Args:
        stored_payload: Notification payload stored in database

    Returns:
        Slack-formatted payload ready to send to webhook
    """
    notification_type = stored_payload.get("type", "")
    event_data = stored_payload.get("event_data", {})
    context = stored_payload.get("context", {})
    suppressed_count = stored_payload.get("suppressed_count", 0)

    # If payload already has "blocks", it's already in Slack format
    if "blocks" in stored_payload:
        return stored_payload

    # Build appropriate payload based on type
    if notification_type == "permission":
        return build_permission_payload(event_data, context, suppressed_count)
    elif notification_type == "idle":
        return build_idle_payload(event_data, context, suppressed_count)
    elif notification_type == "stop":
        return build_stop_payload(event_data, context)
    else:
        # Fallback: return as-is for unknown types
        return stored_payload


def send_notification(db: sqlite3.Connection, notification_id: int) -> bool:
    """
    Send a single notification via webhook.

    This function:
    1. Loads notification from database
    2. Gets webhook URL from config or payload
    3. Builds Slack Block Kit payload
    4. Sends HTTP POST to webhook
    5. Updates notification status (sent/failed)
    6. Increments retry count on failure

    Args:
        db: SQLite database connection
        notification_id: ID of notification to send

    Returns:
        True if sent successfully, False if failed

    Raises:
        NotificationError: If notification not found
    """
    # Load notification
    notif = db.execute(
        """SELECT id, backend, payload, retry_count
           FROM notifications
           WHERE id = ?""",
        (notification_id,)
    ).fetchone()

    if not notif:
        raise NotificationError(f"Notification {notification_id} not found")

    # Parse stored payload
    try:
        stored_payload = json.loads(notif["payload"])
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON payload: {e}"
        _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
        return False

    # Get webhook URL from payload or config
    webhook_url = stored_payload.get("webhook_url", "")

    if not webhook_url:
        webhook_config = db.execute(
            "SELECT value FROM config WHERE key = 'slack_webhook_url'"
        ).fetchone()

        if not webhook_config:
            error_msg = "Slack webhook URL not configured"
            _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
            return False

        webhook_url = webhook_config["value"]

    # Validate webhook URL
    try:
        validate_webhook_url(webhook_url)
    except WebhookValidationError as e:
        error_msg = f"Invalid webhook URL: {e}"
        _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
        return False

    # Build Slack payload from stored data
    slack_payload = _build_slack_payload(stored_payload)

    # Send webhook
    try:
        response = requests.post(
            webhook_url,
            json=slack_payload,
            timeout=10,
            headers={"Content-Type": "application/json"}
        )

        # Check response
        if response.status_code == 200:
            _update_notification_sent(db, notification_id)
            return True
        else:
            error_msg = f"HTTP {response.status_code}: {response.text[:200]}"
            _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
            return False

    except requests.exceptions.Timeout:
        error_msg = "Connection timeout"
        _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
        return False

    except requests.exceptions.RequestException as e:
        error_msg = f"Request failed: {str(e)[:200]}"
        _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
        return False

    except Exception as e:
        error_msg = f"Unexpected error: {str(e)[:200]}"
        _update_notification_failed(db, notification_id, notif["retry_count"], error_msg)
        return False


def _update_notification_sent(db: sqlite3.Connection, notification_id: int):
    """Update notification status to 'sent'."""
    db.execute(
        """UPDATE notifications
           SET status = 'sent', sent_at = ?
           WHERE id = ?""",
        (int(time.time()), notification_id)
    )
    db.commit()


def _update_notification_failed(db: sqlite3.Connection, notification_id: int, current_retry_count: int, error: str):
    """Update notification status to 'failed' and increment retry count."""
    db.execute(
        """UPDATE notifications
           SET status = 'failed', retry_count = ?, error = ?
           WHERE id = ?""",
        (current_retry_count + 1, error, notification_id)
    )
    db.commit()


# =============================================================================
# Queue Processing (Dispatcher)
# =============================================================================

def process_queue(db: sqlite3.Connection, batch_size: int = 10, max_retries: int = 3) -> int:
    """
    Process pending notifications from queue.

    This function:
    1. Selects pending or failed (with retry_count < max_retries) notifications
    2. Processes up to batch_size notifications
    3. Calls send_notification() for each
    4. Returns count of processed notifications

    Args:
        db: SQLite database connection
        batch_size: Maximum number of notifications to process (default: 10)
        max_retries: Maximum retry attempts (default: 3)

    Returns:
        Number of notifications processed
    """
    # Select notifications to process
    notifications = db.execute(
        """SELECT id
           FROM notifications
           WHERE (status = 'pending' OR (status = 'failed' AND retry_count < ?))
           ORDER BY created_at ASC
           LIMIT ?""",
        (max_retries, batch_size)
    ).fetchall()

    processed_count = 0

    for notif in notifications:
        notif_id = notif["id"]
        try:
            send_notification(db, notif_id)
            processed_count += 1
        except NotificationError as e:
            # Log error but continue processing other notifications
            print(f"Error processing notification {notif_id}: {e}")
            continue

    return processed_count


def run_dispatcher(db_path: str, interval: int = 60, batch_size: int = 10):
    """
    Run dispatcher as daemon (continuous loop).

    This is a simple implementation for daemon mode. In production, you might use:
    - systemd service
    - supervisord
    - pm2
    - Docker container with restart policy

    Args:
        db_path: Path to SQLite database
        interval: Seconds between queue checks (default: 60)
        batch_size: Max notifications per batch (default: 10)
    """
    print(f"Dispatcher started: checking queue every {interval}s")

    while True:
        try:
            db = sqlite3.connect(db_path)
            db.row_factory = sqlite3.Row

            processed = process_queue(db, batch_size=batch_size)

            if processed > 0:
                print(f"Processed {processed} notifications")

            db.close()

        except Exception as e:
            print(f"Dispatcher error: {e}")

        time.sleep(interval)


# =============================================================================
# CLI Entry Point (for testing and cron jobs)
# =============================================================================

if __name__ == "__main__":
    import sys
    import os

    # Default database path
    DB_PATH = os.path.expanduser("~/.claude/state/notifications.db")

    # Parse command-line arguments
    if len(sys.argv) > 1:
        if sys.argv[1] == "--once":
            # Run once (for cron mode)
            db = sqlite3.connect(DB_PATH)
            db.row_factory = sqlite3.Row
            processed = process_queue(db)
            print(f"Processed {processed} notifications")
            db.close()

        elif sys.argv[1] == "--daemon":
            # Run as daemon
            interval = int(sys.argv[2]) if len(sys.argv) > 2 else 60
            run_dispatcher(DB_PATH, interval=interval)

        else:
            print("Usage:")
            print("  python3 sender.py --once          # Process queue once (for cron)")
            print("  python3 sender.py --daemon [60]   # Run as daemon (check every 60s)")
            sys.exit(1)
    else:
        # Default: run once
        db = sqlite3.connect(DB_PATH)
        db.row_factory = sqlite3.Row
        processed = process_queue(db)
        print(f"Processed {processed} notifications")
        db.close()
