#!/usr/bin/env python3
"""
Example usage of the database.py module.

This script demonstrates all major features of the database layer.
Run with: python3 database_example.py
"""
import os
import sys
import json
import time
import tempfile
from pathlib import Path

# Add lib directory to path
sys.path.insert(0, str(Path(__file__).parent))

from database import Database


def main():
    """Run database examples."""
    print("=" * 70)
    print("Database Layer Example - Slack Notification V2")
    print("=" * 70)

    # Use temporary database for demo
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "demo.db")
        print(f"\nCreating database at: {db_path}\n")

        # Use context manager for auto-cleanup
        with Database(db_path) as db:
            demo_events(db)
            demo_sessions(db)
            demo_notifications(db)
            demo_config(db)
            demo_audit_log(db)
            demo_metrics(db)
            demo_queries(db)

        print("\n" + "=" * 70)
        print("Demo complete! Database will be cleaned up.")
        print("=" * 70)


def demo_events(db):
    """Demonstrate event operations."""
    print("\n" + "-" * 70)
    print("1. EVENT OPERATIONS")
    print("-" * 70)

    # Insert events
    print("\n[+] Inserting events...")
    event1_id = db.insert_event(
        session_id="demo-session-1",
        event_type="pre_tool_use",
        payload={"tool_name": "Edit", "file": "/tmp/app.ts"}
    )
    print(f"    Event {event1_id} created")

    event2_id = db.insert_event(
        session_id="demo-session-1",
        event_type="notification",
        payload={"hook_event_name": "Notification", "type": "permission_prompt"}
    )
    print(f"    Event {event2_id} created")

    # Get unprocessed events
    print("\n[+] Getting unprocessed events...")
    unprocessed = db.get_unprocessed_events()
    print(f"    Found {len(unprocessed)} unprocessed events")
    for event in unprocessed:
        print(f"    - Event {event['id']}: {event['event_type']}")

    # Mark event as processed
    print(f"\n[+] Marking event {event1_id} as processed...")
    db.mark_event_processed(event1_id)

    unprocessed = db.get_unprocessed_events()
    print(f"    Now {len(unprocessed)} unprocessed events remain")

    # Get latest event by type
    print("\n[+] Getting latest pre_tool_use event...")
    latest = db.get_latest_event_by_type("demo-session-1", "pre_tool_use")
    if latest:
        payload = json.loads(latest['hook_payload'])
        print(f"    Latest: {payload}")


def demo_sessions(db):
    """Demonstrate session operations."""
    print("\n" + "-" * 70)
    print("2. SESSION OPERATIONS")
    print("-" * 70)

    # Create session
    print("\n[+] Creating session...")
    db.create_session(
        session_id="demo-session-1",
        cwd="/Users/demo/project",
        project_name="demo-project",
        git_branch="main",
        terminal_type="tmux",
        terminal_info='{"pane": "0:0.0", "session": "main"}'
    )
    print("    Session created")

    # Get session
    print("\n[+] Getting session info...")
    session = db.get_session("demo-session-1")
    print(f"    Session ID: {session['session_id']}")
    print(f"    Project: {session['project_name']}")
    print(f"    CWD: {session['cwd']}")
    print(f"    Git Branch: {session['git_branch']}")
    print(f"    Terminal: {session['terminal_type']}")

    # Update activity
    print("\n[+] Updating session activity...")
    time.sleep(0.1)
    db.update_session_activity("demo-session-1")
    print("    Activity timestamp updated")

    # Set idle
    print("\n[+] Marking session as idle...")
    db.set_session_idle("demo-session-1", is_idle=True)
    session = db.get_session("demo-session-1")
    print(f"    Is idle: {bool(session['is_idle'])}")

    # Get active sessions
    print("\n[+] Getting active sessions...")
    active = db.get_active_sessions()
    print(f"    Found {len(active)} active sessions")


def demo_notifications(db):
    """Demonstrate notification operations."""
    print("\n" + "-" * 70)
    print("3. NOTIFICATION OPERATIONS")
    print("-" * 70)

    # Insert notification
    print("\n[+] Creating notification...")
    event_id = db.insert_event("demo-session-1", "notification", {})
    notif_id = db.insert_notification(
        event_id=event_id,
        session_id="demo-session-1",
        notification_type="permission",
        backend="slack",
        payload={
            "text": "Claude wants to edit app.ts",
            "details": "Old: const x = 1\nNew: const x = 2"
        }
    )
    print(f"    Notification {notif_id} created")

    # Get pending notifications
    print("\n[+] Getting pending notifications...")
    pending = db.get_pending_notifications()
    print(f"    Found {len(pending)} pending notifications")
    for notif in pending:
        print(f"    - Notification {notif['id']}: {notif['notification_type']} via {notif['backend']}")

    # Simulate failure and retry
    print("\n[+] Simulating notification failure...")
    db.mark_notification_failed(notif_id, "Connection timeout")
    notif = db.get_notification_by_id(notif_id)
    print(f"    Status: {notif['status']}")
    print(f"    Retry count: {notif['retry_count']}")
    print(f"    Error: {notif['error']}")

    # Get retryable notifications
    print("\n[+] Getting notifications for retry...")
    retryable = db.get_failed_notifications_for_retry(max_retries=3)
    print(f"    Found {len(retryable)} retryable notifications")

    # Mark as sent
    print(f"\n[+] Marking notification {notif_id} as sent...")
    db.mark_notification_sent(notif_id)
    notif = db.get_notification_by_id(notif_id)
    print(f"    Status: {notif['status']}")
    print(f"    Sent at: {notif['sent_at']}")


def demo_config(db):
    """Demonstrate config operations."""
    print("\n" + "-" * 70)
    print("4. CONFIG OPERATIONS")
    print("-" * 70)

    # Set plaintext config
    print("\n[+] Setting plaintext config...")
    db.set_config("enabled", "true")
    db.set_config("notify_always", "false")
    print("    Config values set")

    # Set encrypted config
    print("\n[+] Setting encrypted config (webhook URL)...")
    webhook_url = "https://example.com/webhook/your-secret-token"
    db.set_config("slack_webhook_url", webhook_url, encrypted=True)
    print("    Webhook URL encrypted and stored")

    # Get config values
    print("\n[+] Getting config values...")
    enabled = db.get_config("enabled")
    notify_always = db.get_config("notify_always")
    webhook = db.get_config("slack_webhook_url")  # Auto-decrypted
    print(f"    enabled: {enabled}")
    print(f"    notify_always: {notify_always}")
    print(f"    webhook_url: {webhook[:30]}... (decrypted)")

    # Get all config
    print("\n[+] Getting all config...")
    all_config = db.get_all_config()
    print(f"    Total config keys: {len(all_config)}")
    for key in sorted(all_config.keys()):
        value = all_config[key]
        if 'webhook' in key.lower():
            value = value[:30] + "..."
        print(f"    - {key}: {value}")


def demo_audit_log(db):
    """Demonstrate audit log operations."""
    print("\n" + "-" * 70)
    print("5. AUDIT LOG OPERATIONS")
    print("-" * 70)

    # Insert audit logs
    print("\n[+] Recording audit logs...")
    db.insert_audit_log(
        session_id="demo-session-1",
        action="notification_sent",
        details={"notification_id": 1, "backend": "slack", "latency_ms": 123}
    )
    db.insert_audit_log(
        session_id="demo-session-1",
        action="permission_granted",
        details={"tool": "Edit", "file": "/tmp/app.ts"}
    )
    db.insert_audit_log(
        action="config_updated",
        details={"key": "enabled", "value": "true"}
    )
    print("    Audit logs recorded")

    # Get audit logs by session
    print("\n[+] Getting audit logs for session...")
    logs = db.get_audit_logs_by_session("demo-session-1")
    print(f"    Found {len(logs)} logs for demo-session-1")
    for log in logs:
        print(f"    - {log['action']}: {log['details'][:50]}...")

    # Get audit logs by action
    print("\n[+] Getting audit logs by action...")
    sent_logs = db.get_audit_logs_by_action("notification_sent")
    print(f"    Found {len(sent_logs)} 'notification_sent' logs")

    # Get recent audit logs
    print("\n[+] Getting recent audit logs...")
    recent = db.get_recent_audit_logs(limit=5)
    print(f"    Found {len(recent)} recent logs")


def demo_metrics(db):
    """Demonstrate metrics operations."""
    print("\n" + "-" * 70)
    print("6. METRICS OPERATIONS")
    print("-" * 70)

    # Insert metrics
    print("\n[+] Recording metrics...")
    latencies = [100, 150, 200, 125, 175, 300, 50]
    for latency in latencies:
        db.insert_metric(
            metric_name="notification_latency_ms",
            metric_value=latency,
            session_id="demo-session-1"
        )
    print(f"    Recorded {len(latencies)} latency measurements")

    db.insert_metric("notification_success", 1)
    db.insert_metric("notification_success", 1)
    db.insert_metric("notification_failure", 1)
    print("    Recorded success/failure metrics")

    # Get metrics by name
    print("\n[+] Getting latency metrics...")
    metrics = db.get_metrics_by_name("notification_latency_ms")
    print(f"    Found {len(metrics)} latency metrics")

    # Get metric statistics
    print("\n[+] Calculating latency statistics...")
    stats = db.get_metric_stats("notification_latency_ms")
    print(f"    Count: {stats['count']}")
    print(f"    Average: {stats['avg']:.2f} ms")
    print(f"    Min: {stats['min']} ms")
    print(f"    Max: {stats['max']} ms")


def demo_queries(db):
    """Demonstrate advanced queries."""
    print("\n" + "-" * 70)
    print("7. ADVANCED QUERIES")
    print("-" * 70)

    # Session isolation
    print("\n[+] Demonstrating session isolation...")
    db.insert_event("session-A", "event1", {"data": "A"})
    db.insert_event("session-B", "event2", {"data": "B"})
    db.insert_event("session-A", "event3", {"data": "A"})

    session_a_events = db.get_events_by_session("session-A")
    print(f"    Session A has {len(session_a_events)} events")

    session_b_events = db.get_events_by_session("session-B")
    print(f"    Session B has {len(session_b_events)} events")

    # Raw SQL query
    print("\n[+] Running custom SQL query...")
    results = db.execute_query("""
        SELECT event_type, COUNT(*) as count
        FROM events
        GROUP BY event_type
        ORDER BY count DESC
    """)
    print("    Event type distribution:")
    for row in results:
        print(f"    - {row['event_type']}: {row['count']}")

    # Schema inspection
    print("\n[+] Inspecting database schema...")
    tables = db._get_table_names()
    print(f"    Tables: {', '.join(tables)}")

    indexes = db._get_index_names()
    print(f"    Indexes: {len(indexes)} total")


if __name__ == "__main__":
    main()
