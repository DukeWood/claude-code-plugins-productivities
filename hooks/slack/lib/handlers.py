"""
V2 Hook Handlers for Slack Notifications.

This module provides unified event handling for all Claude Code hooks:
- Notification (permission_prompt, idle_prompt)
- Stop (task completion)
- PreToolUse (tool metadata capture)
- PostToolUse (AskUserQuestion tracking)

Key responsibilities:
- Validate payload structure
- Route events to appropriate handlers
- Enrich context (git, terminal, tokens)
- Queue notifications
- Log to audit trail
- Return success/error status
"""
import json
import time
import sqlite3
import subprocess
import os
from pathlib import Path
from typing import Dict, Any, Optional


# =============================================================================
# Exceptions
# =============================================================================

class ValidationError(Exception):
    """Raised when payload validation fails."""
    pass


# =============================================================================
# Payload Validation
# =============================================================================

def validate_payload(payload: Dict[str, Any], event_type: str) -> None:
    """
    Validate payload structure for given event type.

    Args:
        payload: Hook payload dictionary
        event_type: Type of event (notification, stop, pre_tool_use, post_tool_use)

    Raises:
        ValidationError: If required fields are missing
    """
    # Common required fields
    if "session_id" not in payload:
        raise ValidationError("Missing required field: session_id")

    if "cwd" not in payload:
        raise ValidationError("Missing required field: cwd")

    # Event-specific validation
    if event_type == "notification":
        if "hook_event_name" not in payload:
            raise ValidationError("Missing required field: hook_event_name")
        if "notification_type" not in payload:
            raise ValidationError("Missing required field: notification_type")

    elif event_type == "stop":
        if "hook_event_name" not in payload:
            raise ValidationError("Missing required field: hook_event_name")

    elif event_type in ["pre_tool_use", "post_tool_use"]:
        if "tool_name" not in payload:
            raise ValidationError("Missing required field: tool_name")


# =============================================================================
# Event Routing
# =============================================================================

def route_event(db: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Route event to appropriate handler based on payload structure.

    Args:
        db: SQLite database connection
        payload: Hook payload dictionary

    Returns:
        Result dictionary with success status and optional error
    """
    if payload is None:
        return {"success": False, "error": "Null payload"}

    try:
        # Detect event type from payload structure
        if "hook_event_name" in payload:
            hook_name = payload["hook_event_name"]

            if hook_name == "Notification":
                return handle_notification(db, payload)
            elif hook_name == "Stop":
                return handle_stop(db, payload)
            else:
                return {"success": False, "error": f"Unknown hook event: {hook_name}"}

        elif "tool_name" in payload:
            # Determine if PreToolUse or PostToolUse based on context
            # For now, we'll use a heuristic: if it's AskUserQuestion, it's likely PostToolUse
            if payload["tool_name"] == "AskUserQuestion":
                return handle_post_tool_use(db, payload)
            else:
                return handle_pre_tool_use(db, payload)

        else:
            return {"success": False, "error": "Unknown event type (no hook_event_name or tool_name)"}

    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


# =============================================================================
# Session Management
# =============================================================================

def ensure_session(db: sqlite3.Connection, session_id: str, cwd: str) -> None:
    """
    Ensure session exists in database, create if not.

    Args:
        db: SQLite database connection
        session_id: Session ID
        cwd: Current working directory
    """
    cursor = db.execute(
        "SELECT session_id FROM sessions WHERE session_id = ?",
        (session_id,)
    )

    if cursor.fetchone() is None:
        # Create new session
        now = int(time.time())
        project_name = get_project_name(cwd)

        db.execute(
            """INSERT INTO sessions (session_id, cwd, project_name, started_at, last_activity_at)
               VALUES (?, ?, ?, ?, ?)""",
            (session_id, cwd, project_name, now, now)
        )
        db.commit()


def update_session_activity(db: sqlite3.Connection, session_id: str) -> None:
    """
    Update session's last_activity_at timestamp.

    Args:
        db: SQLite database connection
        session_id: Session ID
    """
    now = int(time.time())
    db.execute(
        "UPDATE sessions SET last_activity_at = ? WHERE session_id = ?",
        (now, session_id)
    )
    db.commit()


def mark_session_ended(db: sqlite3.Connection, session_id: str) -> None:
    """
    Mark session as ended.

    Args:
        db: SQLite database connection
        session_id: Session ID
    """
    now = int(time.time())
    db.execute(
        "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
        (now, session_id)
    )
    db.commit()


def mark_session_idle(db: sqlite3.Connection, session_id: str, is_idle: bool = True) -> None:
    """
    Mark session as idle or active.

    Args:
        db: SQLite database connection
        session_id: Session ID
        is_idle: Whether session is idle
    """
    db.execute(
        "UPDATE sessions SET is_idle = ? WHERE session_id = ?",
        (1 if is_idle else 0, session_id)
    )
    db.commit()


def get_session(db: sqlite3.Connection, session_id: str) -> Optional[Dict[str, Any]]:
    """
    Get session metadata.

    Args:
        db: SQLite database connection
        session_id: Session ID

    Returns:
        Session dictionary or None if not found
    """
    cursor = db.execute(
        "SELECT * FROM sessions WHERE session_id = ?",
        (session_id,)
    )

    row = cursor.fetchone()
    if row is None:
        return None

    return dict(row)


# =============================================================================
# Event Storage
# =============================================================================

def store_event(
    db: sqlite3.Connection,
    session_id: str,
    event_type: str,
    payload: Dict[str, Any]
) -> int:
    """
    Store event in database.

    Args:
        db: SQLite database connection
        session_id: Session ID
        event_type: Type of event
        payload: Full event payload

    Returns:
        Event ID
    """
    now = int(time.time())
    cursor = db.execute(
        """INSERT INTO events (session_id, event_type, hook_payload, created_at)
           VALUES (?, ?, ?, ?)""",
        (session_id, event_type, json.dumps(payload), now)
    )
    db.commit()
    return cursor.lastrowid


# =============================================================================
# Notification Queueing
# =============================================================================

def queue_notification(
    db: sqlite3.Connection,
    event_id: int,
    session_id: str,
    notification_type: str,
    backend: str,
    payload: Dict[str, Any]
) -> int:
    """
    Queue notification for delivery.

    Args:
        db: SQLite database connection
        event_id: Associated event ID
        session_id: Session ID
        notification_type: Type of notification
        backend: Backend to use (slack, discord, etc)
        payload: Notification payload

    Returns:
        Notification ID
    """
    now = int(time.time())
    cursor = db.execute(
        """INSERT INTO notifications
           (event_id, session_id, notification_type, backend, status, payload, created_at)
           VALUES (?, ?, ?, ?, 'pending', ?, ?)""",
        (event_id, session_id, notification_type, backend, json.dumps(payload), now)
    )
    db.commit()
    return cursor.lastrowid


# =============================================================================
# Audit Logging
# =============================================================================

def log_audit(
    db: sqlite3.Connection,
    session_id: str,
    action: str,
    details: Optional[Dict[str, Any]] = None
) -> None:
    """
    Log action to audit trail.

    Args:
        db: SQLite database connection
        session_id: Session ID
        action: Action name
        details: Optional details dictionary
    """
    now = int(time.time())
    db.execute(
        """INSERT INTO audit_log (session_id, action, details, created_at)
           VALUES (?, ?, ?, ?)""",
        (session_id, action, json.dumps(details) if details else None, now)
    )
    db.commit()


# =============================================================================
# Configuration
# =============================================================================

def get_config(db: sqlite3.Connection, key: str, default: Any = None) -> Any:
    """
    Get configuration value.

    Args:
        db: SQLite database connection
        key: Config key
        default: Default value if not found

    Returns:
        Config value or default
    """
    cursor = db.execute(
        "SELECT value FROM config WHERE key = ?",
        (key,)
    )

    row = cursor.fetchone()
    if row is None:
        return default

    value = row[0]

    # Convert string booleans to bool
    if value == "true":
        return True
    elif value == "false":
        return False

    return value


def is_notifications_enabled(db: sqlite3.Connection, notification_type: str) -> bool:
    """
    Check if notifications are enabled for given type.

    Args:
        db: SQLite database connection
        notification_type: Type of notification

    Returns:
        True if enabled
    """
    # Check global enabled flag
    if not get_config(db, "slack_enabled", True):
        return False

    # Check specific notification type
    config_key = f"notify_on_{notification_type}"
    return get_config(db, config_key, True)


# =============================================================================
# Context Enrichment
# =============================================================================

def get_project_name(cwd: str) -> str:
    """
    Extract project name from working directory.

    Args:
        cwd: Current working directory

    Returns:
        Project name
    """
    # Try git repo name first
    try:
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            timeout=2
        )
        if result.returncode == 0:
            return Path(result.stdout.strip()).name
    except:
        pass

    # Fallback to directory name
    return Path(cwd).name


def get_git_status(cwd: str) -> Optional[Dict[str, Any]]:
    """
    Get git status for working directory.

    Args:
        cwd: Current working directory

    Returns:
        Git status dictionary or None if not a git repo
    """
    try:
        # Check if in git repo
        result = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--git-dir"],
            capture_output=True,
            timeout=2
        )
        if result.returncode != 0:
            return None

        # Get branch
        branch_result = subprocess.run(
            ["git", "-C", cwd, "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=2
        )
        branch = branch_result.stdout.strip() or "detached"

        # Get status
        status_result = subprocess.run(
            ["git", "-C", cwd, "status", "--porcelain"],
            capture_output=True,
            text=True,
            timeout=2
        )
        status_lines = status_result.stdout.strip().split("\n")

        staged = sum(1 for line in status_lines if line.startswith(("M ", "A ", "D ")))
        modified = sum(1 for line in status_lines if line.startswith(" M"))
        untracked = sum(1 for line in status_lines if line.startswith("??"))

        return {
            "branch": branch,
            "staged": staged,
            "modified": modified,
            "untracked": untracked,
            "summary": f"{branch} | S:{staged} M:{modified} U:{untracked}"
        }
    except:
        return None


def detect_terminal(cwd: str) -> Dict[str, Any]:
    """
    Detect terminal type and info.

    Args:
        cwd: Current working directory

    Returns:
        Terminal info dictionary
    """
    # Check for tmux
    if "TMUX" in os.environ:
        try:
            result = subprocess.run(
                ["tmux", "display-message", "-p", "#S:#I.#P"],
                capture_output=True,
                text=True,
                timeout=2
            )
            if result.returncode == 0:
                return {
                    "type": "tmux",
                    "info": result.stdout.strip()
                }
        except:
            pass

        return {"type": "tmux", "info": ""}

    # Check for VS Code
    if os.environ.get("TERM_PROGRAM") == "vscode":
        return {"type": "vscode", "info": ""}

    # Check for iTerm
    if os.environ.get("TERM_PROGRAM") == "iTerm.app":
        return {"type": "iterm", "info": ""}

    # Default
    return {"type": "terminal", "info": ""}


def get_token_usage(session_id: str, cwd: str) -> Optional[Dict[str, Any]]:
    """
    Get token usage from session transcript.

    Args:
        session_id: Session ID
        cwd: Current working directory

    Returns:
        Token usage dictionary or None if not available
    """
    # Find transcript file
    try:
        claude_dir = Path.home() / ".claude" / "projects"
        transcript_files = list(claude_dir.rglob(f"{session_id}.jsonl"))

        if not transcript_files:
            return None

        transcript_file = transcript_files[0]

        total_input = 0
        total_output = 0
        total_cache_read = 0

        with open(transcript_file) as f:
            for line in f:
                try:
                    data = json.loads(line)
                    if "message" in data and "usage" in data["message"]:
                        usage = data["message"]["usage"]
                        total_input += usage.get("input_tokens", 0)
                        total_output += usage.get("output_tokens", 0)
                        total_cache_read += usage.get("cache_read_input_tokens", 0)
                except:
                    continue

        # Include cache reads in input
        total_input += total_cache_read

        return {
            "input": total_input,
            "output": total_output,
            "cache_read": total_cache_read
        }
    except:
        return None


def enrich_context(
    db: sqlite3.Connection,
    session: Dict[str, Any],
    payload: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Enrich context with git, terminal, project info.

    Args:
        db: SQLite database connection
        session: Session dictionary
        payload: Event payload

    Returns:
        Enriched context dictionary
    """
    context = {}

    cwd = session.get("cwd", "")

    # Project name
    try:
        context["project_name"] = get_project_name(cwd)
    except:
        context["project_name"] = "unknown"

    # Git status
    try:
        git_status = get_git_status(cwd)
        if git_status:
            context["git"] = git_status
    except:
        pass

    # Terminal info
    try:
        terminal = detect_terminal(cwd)
        context["terminal"] = terminal
    except:
        pass

    return context


# =============================================================================
# Notification Handler
# =============================================================================

def handle_notification(db: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Notification hook events (permission_prompt, idle_prompt).

    Args:
        db: SQLite database connection
        payload: Notification hook payload

    Returns:
        Result dictionary with success status
    """
    try:
        # Validate payload
        validate_payload(payload, "notification")

        session_id = payload["session_id"]
        cwd = payload["cwd"]
        notification_type = payload["notification_type"]

        # Ensure session exists
        ensure_session(db, session_id, cwd)

        # Get session
        session = get_session(db, session_id)

        # Update session activity
        update_session_activity(db, session_id)

        # Handle idle_prompt specifically
        if notification_type == "idle_prompt":
            mark_session_idle(db, session_id, True)

        # Store event
        event_id = store_event(db, session_id, "notification", payload)

        # Check if notifications are enabled
        if is_notifications_enabled(db, "permission"):
            # Enrich context
            context = enrich_context(db, session, payload)

            # Build notification payload
            notif_payload = {
                "notification_type": notification_type,
                "context": context,
                "tool_name": payload.get("tool_name", "Unknown"),
                "tool_input": payload.get("tool_input", {}),
                "timestamp": int(time.time())
            }

            # Queue notification
            queue_notification(
                db, event_id, session_id,
                "permission",  # notification_type for database
                "slack",  # backend
                notif_payload
            )

            # Log to audit
            log_audit(db, session_id, "notification_queued", {
                "type": notification_type,
                "event_id": event_id
            })

        return {"success": True, "event_id": event_id}

    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Handler error: {str(e)}"}


# =============================================================================
# Stop Handler
# =============================================================================

def handle_stop(db: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle Stop hook events (task completion).

    Args:
        db: SQLite database connection
        payload: Stop hook payload

    Returns:
        Result dictionary with success status
    """
    try:
        # Validate payload
        validate_payload(payload, "stop")

        session_id = payload["session_id"]
        cwd = payload["cwd"]

        # Ensure session exists
        ensure_session(db, session_id, cwd)

        # Get session
        session = get_session(db, session_id)

        # Store event
        event_id = store_event(db, session_id, "stop", payload)

        # Mark session as ended
        mark_session_ended(db, session_id)

        # Log to audit
        log_audit(db, session_id, "session_stopped", {
            "event_id": event_id,
            "cwd": cwd
        })

        # Check if should notify
        should_notify = False

        # Get terminal type from session
        terminal_type = session.get("terminal_type", "")

        # Notify if in tmux
        if terminal_type == "tmux":
            should_notify = True

        # Or if notify_always is enabled
        if get_config(db, "notify_always", False):
            should_notify = True

        if should_notify and is_notifications_enabled(db, "task_complete"):
            # Enrich context
            context = enrich_context(db, session, payload)

            # Get token usage
            token_usage = get_token_usage(session_id, cwd)
            if token_usage:
                context["token_usage"] = token_usage

            # Build notification payload
            notif_payload = {
                "notification_type": "task_complete",
                "context": context,
                "timestamp": int(time.time())
            }

            # Queue notification
            queue_notification(
                db, event_id, session_id,
                "task_complete",
                "slack",
                notif_payload
            )

            # Log to audit
            log_audit(db, session_id, "task_complete_notification_queued", {
                "event_id": event_id
            })

        return {"success": True, "event_id": event_id}

    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Handler error: {str(e)}"}


# =============================================================================
# PreToolUse Handler
# =============================================================================

def handle_pre_tool_use(db: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle PreToolUse hook events (capture tool metadata).

    Args:
        db: SQLite database connection
        payload: PreToolUse payload

    Returns:
        Result dictionary with success status
    """
    try:
        # Validate payload
        validate_payload(payload, "pre_tool_use")

        session_id = payload["session_id"]
        cwd = payload["cwd"]

        # Ensure session exists
        ensure_session(db, session_id, cwd)

        # Store event
        event_id = store_event(db, session_id, "pre_tool_use", payload)

        # Update session activity
        update_session_activity(db, session_id)

        return {"success": True, "event_id": event_id}

    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Handler error: {str(e)}"}


# =============================================================================
# PostToolUse Handler
# =============================================================================

def handle_post_tool_use(db: sqlite3.Connection, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Handle PostToolUse hook events (track AskUserQuestion).

    Args:
        db: SQLite database connection
        payload: PostToolUse payload

    Returns:
        Result dictionary with success status
    """
    try:
        # Validate payload
        validate_payload(payload, "post_tool_use")

        session_id = payload["session_id"]
        cwd = payload["cwd"]
        tool_name = payload["tool_name"]

        # Only track specific tools (like AskUserQuestion)
        if tool_name == "AskUserQuestion":
            # Ensure session exists
            ensure_session(db, session_id, cwd)

            # Store event
            event_id = store_event(db, session_id, "post_tool_use", payload)

            return {"success": True, "event_id": event_id}

        # For other tools, just return success without storing
        return {"success": True}

    except ValidationError as e:
        return {"success": False, "error": str(e)}
    except Exception as e:
        return {"success": False, "error": f"Handler error: {str(e)}"}
