#!/usr/bin/env python3
"""
V2 Unified Hook Entry Point for Slack Notifications.

This script replaces the V1 shell scripts (notify-permission.sh, notify-stop.sh)
with a unified Python entry point that uses:
- SQLite database for event storage
- Queue system with retry logic
- Rate limiting and deduplication (v2.1)
- Encrypted credential storage
- Structured logging

Usage:
    # As a hook command in ~/.claude/settings.json:
    echo '{"hook_event_name": "Stop", ...}' | python3 hook.py

    # Process queue (run as cron or daemon):
    python3 hook.py --process-queue

    # Run dispatcher daemon:
    python3 hook.py --daemon --interval 60

    # Show rate limiting stats:
    python3 hook.py --stats
"""
import sys
import os
import json
import argparse
import logging
from pathlib import Path
from datetime import datetime
from typing import Optional

# Add lib directory to path
SCRIPT_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(SCRIPT_DIR / "lib"))

from database import Database
from notification_queue import NotificationQueue
from handlers import (
    validate_payload,
    route_event,
    handle_notification,
    handle_stop,
    handle_pre_tool_use,
    handle_post_tool_use,
    enrich_context,
    ValidationError
)
from sender import (
    process_queue,
    run_dispatcher,
    send_notification,
    build_permission_payload,
    build_idle_payload,
    build_stop_payload
)
from encryption import get_or_create_key, decrypt
from rate_limiter import RateLimiter, RateLimitConfig

# Configuration
DEFAULT_DB_PATH = Path.home() / ".claude" / "state" / "notifications.db"
DEFAULT_CONFIG_PATH = Path.home() / ".claude" / "config" / "slack-config.json"
LOG_DIR = Path.home() / ".claude" / "logs"

# Setup logging
LOG_DIR.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(LOG_DIR / "hook-v2.log"),
        logging.StreamHandler(sys.stderr) if os.environ.get("DEBUG") else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)


def load_config() -> dict:
    """Load Slack configuration from JSON file."""
    config_path = DEFAULT_CONFIG_PATH
    if not config_path.exists():
        return {"enabled": False}

    try:
        with open(config_path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Failed to load config: {e}")
        return {"enabled": False}


def is_enabled(config: dict, notification_type: str) -> bool:
    """Check if notifications are enabled for given type."""
    if not config.get("enabled", True):
        return False

    notify_on = config.get("notify_on", {})
    return notify_on.get(notification_type, True)


def should_notify_stop(config: dict) -> bool:
    """
    Determine if Stop notification should be sent.

    Logic:
    - Always notify if in tmux (detected from CWD matching a tmux pane)
    - Otherwise, only notify if notify_always=true
    """
    # Check tmux using shell enricher (reuse existing logic)
    import subprocess
    try:
        result = subprocess.run(
            ["bash", "-c", f"source {SCRIPT_DIR}/lib/enrichers.sh && detect_tmux"],
            capture_output=True,
            text=True,
            timeout=5,
            env={**os.environ, "PATH": "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin"}
        )
        in_tmux = result.stdout.strip() == "true"
    except Exception:
        in_tmux = False

    notify_always = config.get("notify_always", False)
    return in_tmux or notify_always


def handle_hook_event(
    payload: dict,
    config: dict,
    db: Database,
    queue: NotificationQueue,
    rate_limiter: Optional[RateLimiter] = None
) -> dict:
    """
    Handle a hook event from Claude Code.

    Args:
        payload: Hook event payload from stdin
        config: Slack configuration
        db: Database connection
        queue: Notification queue
        rate_limiter: Optional rate limiter for spam prevention

    Returns:
        Status dict with success/error info
    """
    event_name = payload.get("hook_event_name", "")
    session_id = payload.get("session_id", "unknown")
    cwd = payload.get("cwd", os.getcwd())

    logger.info(f"Processing {event_name} event for session {session_id[-4:]}")

    try:
        # Route based on event type
        if event_name == "Notification":
            notification_type = payload.get("notification_type", "")

            if notification_type == "permission_prompt":
                if not is_enabled(config, "permission_required"):
                    return {"status": "skipped", "reason": "permission_required disabled"}

                # Check rate limiting
                if rate_limiter:
                    result = rate_limiter.should_send(session_id, "permission", payload)
                    if not result.allowed:
                        logger.info(f"Rate limited: {result.reason} (suppressed: {result.suppressed_count})")
                        return {
                            "status": "rate_limited",
                            "reason": result.reason,
                            "suppressed_count": result.suppressed_count
                        }

                # Store event and queue notification
                event_id = db.insert_event(session_id, "notification", payload)
                context = enrich_context(cwd, session_id)

                # Get suppressed count for display
                suppressed_count = 0
                if rate_limiter:
                    suppressed_count = rate_limiter.get_suppressed_count(session_id, "permission")

                notification_payload = {
                    "type": "permission",
                    "event_data": payload,
                    "context": context,
                    "webhook_url": config.get("webhook_url", ""),
                    "suppressed_count": suppressed_count
                }

                notif_id = queue.enqueue("permission", notification_payload, session_id)
                db.insert_audit_log(session_id, "notification_queued", {"notification_id": notif_id, "type": "permission"})

                # Record sent for rate limiting
                if rate_limiter:
                    rate_limiter.record_sent(session_id, "permission", payload)

                return {"status": "queued", "notification_id": notif_id, "suppressed_count": suppressed_count}

            elif notification_type == "idle_prompt":
                if not is_enabled(config, "permission_required"):
                    return {"status": "skipped", "reason": "permission_required disabled"}

                # Check rate limiting
                if rate_limiter:
                    result = rate_limiter.should_send(session_id, "idle", payload)
                    if not result.allowed:
                        logger.info(f"Rate limited: {result.reason} (suppressed: {result.suppressed_count})")
                        return {
                            "status": "rate_limited",
                            "reason": result.reason,
                            "suppressed_count": result.suppressed_count
                        }

                event_id = db.insert_event(session_id, "notification", payload)
                context = enrich_context(cwd, session_id)

                # Get suppressed count for display
                suppressed_count = 0
                if rate_limiter:
                    suppressed_count = rate_limiter.get_suppressed_count(session_id, "idle")

                notification_payload = {
                    "type": "idle",
                    "event_data": payload,
                    "context": context,
                    "webhook_url": config.get("webhook_url", ""),
                    "suppressed_count": suppressed_count
                }

                notif_id = queue.enqueue("idle", notification_payload, session_id)
                db.insert_audit_log(session_id, "notification_queued", {"notification_id": notif_id, "type": "idle"})

                # Record sent for rate limiting
                if rate_limiter:
                    rate_limiter.record_sent(session_id, "idle", payload)

                return {"status": "queued", "notification_id": notif_id, "suppressed_count": suppressed_count}

        elif event_name == "Stop":
            if not is_enabled(config, "task_complete"):
                return {"status": "skipped", "reason": "task_complete disabled"}

            if not should_notify_stop(config):
                return {"status": "skipped", "reason": "not in tmux and notify_always=false"}

            # Check rate limiting (usually no cooldown for stop, but check anyway)
            if rate_limiter:
                result = rate_limiter.should_send(session_id, "stop", payload)
                if not result.allowed:
                    logger.info(f"Rate limited: {result.reason}")
                    return {"status": "rate_limited", "reason": result.reason}

            event_id = db.insert_event(session_id, "stop", payload)
            context = enrich_context(cwd, session_id)

            notification_payload = {
                "type": "stop",
                "event_data": payload,
                "context": context,
                "webhook_url": config.get("webhook_url", "")
            }

            notif_id = queue.enqueue("stop", notification_payload, session_id)
            db.insert_audit_log(session_id, "notification_queued", {"notification_id": notif_id, "type": "stop"})

            # Record sent for rate limiting
            if rate_limiter:
                rate_limiter.record_sent(session_id, "stop", payload)

            return {"status": "queued", "notification_id": notif_id}

        elif event_name == "PreToolUse":
            # Store tool metadata for later use
            event_id = db.insert_event(session_id, "pre_tool_use", payload)
            return {"status": "stored", "event_id": event_id}

        elif event_name == "PostToolUse":
            # Track AskUserQuestion for idle state
            tool_name = payload.get("tool_name", "")
            if tool_name == "AskUserQuestion":
                db.set_config(f"idle_state_{session_id}", "true")
            return {"status": "processed"}

        else:
            return {"status": "ignored", "reason": f"unknown event: {event_name}"}

    except Exception as e:
        logger.exception(f"Error handling {event_name} event")
        return {"status": "error", "error": str(e)}


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="V2 Slack Notification Hook")
    parser.add_argument("--process-queue", action="store_true", help="Process notification queue once")
    parser.add_argument("--daemon", action="store_true", help="Run as queue processor daemon")
    parser.add_argument("--interval", type=int, default=60, help="Daemon check interval in seconds")
    parser.add_argument("--batch-size", type=int, default=10, help="Queue batch size")
    parser.add_argument("--db", type=str, default=str(DEFAULT_DB_PATH), help="Database path")
    parser.add_argument("--stats", action="store_true", help="Show rate limiting statistics")
    parser.add_argument("--cleanup", action="store_true", help="Clean up old rate limit state")
    args = parser.parse_args()

    # Ensure state directory exists
    Path(args.db).parent.mkdir(parents=True, exist_ok=True)

    # Load configuration
    config = load_config()

    if not config.get("enabled", True) and not args.stats:
        logger.info("Slack notifications disabled")
        sys.exit(0)

    # Initialize database and queue
    db = Database(args.db)
    queue = NotificationQueue(args.db)

    # Initialize rate limiter
    rate_config = RateLimitConfig.from_dict(config)
    rate_limiter = RateLimiter(args.db, rate_config)

    try:
        if args.stats:
            # Show rate limiting statistics
            stats = rate_limiter.get_stats()
            print(json.dumps(stats, indent=2))
            return

        if args.cleanup:
            # Clean up old state
            rate_limiter.cleanup_old_state()
            print("Cleaned up old rate limit state")
            return

        if args.daemon:
            # Run as daemon - continuously process queue
            logger.info(f"Starting dispatcher daemon (interval={args.interval}s)")
            run_dispatcher(args.db, interval=args.interval, batch_size=args.batch_size)

        elif args.process_queue:
            # Process queue once
            processed = process_queue(db, batch_size=args.batch_size)
            logger.info(f"Processed {processed} notifications")
            print(json.dumps({"processed": processed}))

        else:
            # Handle hook event from stdin
            try:
                payload = json.load(sys.stdin)
            except json.JSONDecodeError as e:
                logger.error(f"Invalid JSON on stdin: {e}")
                sys.exit(1)

            result = handle_hook_event(payload, config, db, queue, rate_limiter)

            # Process queue immediately (sync mode for quick delivery)
            if result.get("status") == "queued":
                try:
                    process_queue(db, batch_size=1, max_retries=1)
                except Exception as e:
                    logger.warning(f"Immediate queue processing failed: {e}")

            # Log result
            logger.info(f"Result: {result}")

    finally:
        db.close()
        rate_limiter.close()


if __name__ == "__main__":
    main()
