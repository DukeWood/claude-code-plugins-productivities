#!/usr/bin/env python3
"""
Quick verification script for sender.py implementation.

This script performs basic checks without requiring pytest:
- Import check
- Function signature verification
- Basic payload building
- Webhook validation

Run: python3 verify_sender.py
"""
import json
import sys

def test_imports():
    """Verify all imports work."""
    print("Testing imports...")
    try:
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
        print("✓ All imports successful")
        return True
    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def test_webhook_validation():
    """Verify webhook validation works."""
    print("\nTesting webhook validation...")
    from sender import validate_webhook_url, WebhookValidationError

    tests = [
        ("https://example.com/webhook/slack-test", True, "Valid Slack URL"),
        ("https://discord.com/api/webhooks/123/abc", True, "Valid Discord URL"),
        ("http://example.com/webhook/test", False, "HTTP rejected"),
        ("https://evil.com/webhook", False, "Unknown domain rejected"),
        ("https://localhost/webhook", False, "Localhost rejected"),
    ]

    passed = 0
    for url, should_pass, description in tests:
        try:
            result = validate_webhook_url(url)
            if should_pass:
                print(f"✓ {description}: {url[:50]}")
                passed += 1
            else:
                print(f"✗ {description}: Should have been rejected but passed")
        except WebhookValidationError as e:
            if not should_pass:
                print(f"✓ {description}: Correctly rejected")
                passed += 1
            else:
                print(f"✗ {description}: Should have passed but was rejected: {e}")

    print(f"Passed {passed}/{len(tests)} webhook validation tests")
    return passed == len(tests)


def test_permission_payload():
    """Verify permission payload building."""
    print("\nTesting permission payload building...")
    from sender import build_permission_payload

    event_data = {
        "tool_name": "Edit",
        "tool_input": {
            "file_path": "/Users/test/project/src/app.ts",
            "old_string": "const x = 1",
            "new_string": "const x = 2"
        },
        "session_id": "test-session-1234",
        "cwd": "/Users/test/project"
    }

    context = {
        "project_name": "my-project",
        "git_branch": "main",
        "terminal_type": "tmux",
        "terminal_info": "main:0.0",
        "switch_command": "tmux select-window -t main:0"
    }

    try:
        payload = build_permission_payload(event_data, context)

        # Verify structure
        assert "text" in payload, "Missing 'text' field"
        assert "blocks" in payload, "Missing 'blocks' field"
        assert isinstance(payload["blocks"], list), "'blocks' must be a list"
        assert len(payload["blocks"]) > 0, "'blocks' must not be empty"

        # Verify content
        payload_json = json.dumps(payload).lower()
        assert "edit" in payload_json, "Should mention 'Edit' tool"
        assert "app.ts" in payload_json, "Should mention filename"
        assert "my-project" in payload_json, "Should mention project name"

        print("✓ Permission payload structure correct")
        print(f"  - Text: {payload['text'][:60]}...")
        print(f"  - Blocks: {len(payload['blocks'])} blocks")
        return True

    except Exception as e:
        print(f"✗ Permission payload failed: {e}")
        return False


def test_stop_payload():
    """Verify stop payload building."""
    print("\nTesting stop payload building...")
    from sender import build_stop_payload

    event_data = {
        "hook_event_name": "Stop",
        "session_id": "test-1234",
        "cwd": "/Users/test/project"
    }

    context = {
        "project_name": "my-project",
        "task_description": "Fix authentication bug",
        "token_usage": "15.2K in / 8.5K out",
        "git_branch": "main",
        "git_staged": 3,
        "git_modified": 2,
        "git_untracked": 1
    }

    try:
        payload = build_stop_payload(event_data, context)

        # Verify structure
        assert "text" in payload, "Missing 'text' field"
        assert "blocks" in payload, "Missing 'blocks' field"
        assert isinstance(payload["blocks"], list), "'blocks' must be a list"

        payload_json = json.dumps(payload).lower()
        assert "complete" in payload_json or "done" in payload_json, "Should mention task completion"

        print("✓ Stop payload structure correct")
        print(f"  - Text: {payload['text'][:60]}...")
        print(f"  - Blocks: {len(payload['blocks'])} blocks")
        return True

    except Exception as e:
        print(f"✗ Stop payload failed: {e}")
        return False


def test_idle_payload():
    """Verify idle payload building."""
    print("\nTesting idle payload building...")
    from sender import build_idle_payload

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

    try:
        payload = build_idle_payload(event_data, context)

        # Verify structure
        assert "text" in payload, "Missing 'text' field"
        assert "blocks" in payload, "Missing 'blocks' field"

        payload_json = json.dumps(payload).lower()
        assert "waiting" in payload_json or "input" in payload_json or "idle" in payload_json, \
               "Should mention waiting/input/idle"

        print("✓ Idle payload structure correct")
        print(f"  - Text: {payload['text'][:60]}...")
        print(f"  - Blocks: {len(payload['blocks'])} blocks")
        return True

    except Exception as e:
        print(f"✗ Idle payload failed: {e}")
        return False


def test_all_tools():
    """Test payload building for all tool types."""
    print("\nTesting all tool types...")
    from sender import build_permission_payload

    tools = [
        ("Edit", {"file_path": "/test/app.ts"}),
        ("Bash", {"command": "npm install", "description": "Install packages"}),
        ("WebFetch", {"url": "https://api.github.com/repos/user/repo"}),
        ("Task", {"subagent_type": "coder", "description": "Fix bug"}),
        ("Write", {"file_path": "/test/config.json"}),
        ("Read", {"file_path": "/test/data.csv"}),
        ("UnknownTool", {})
    ]

    passed = 0
    for tool_name, tool_input in tools:
        event_data = {
            "tool_name": tool_name,
            "tool_input": tool_input,
            "session_id": "test-1234"
        }
        context = {"project_name": "test"}

        try:
            payload = build_permission_payload(event_data, context)
            assert "text" in payload and "blocks" in payload
            print(f"✓ {tool_name}: Payload built successfully")
            passed += 1
        except Exception as e:
            print(f"✗ {tool_name}: Failed - {e}")

    print(f"Passed {passed}/{len(tools)} tool type tests")
    return passed == len(tools)


def main():
    """Run all verification tests."""
    print("=" * 60)
    print("Sender.py Implementation Verification")
    print("=" * 60)

    results = []

    # Run tests
    results.append(("Imports", test_imports()))
    results.append(("Webhook Validation", test_webhook_validation()))
    results.append(("Permission Payload", test_permission_payload()))
    results.append(("Stop Payload", test_stop_payload()))
    results.append(("Idle Payload", test_idle_payload()))
    results.append(("All Tool Types", test_all_tools()))

    # Summary
    print("\n" + "=" * 60)
    print("Summary")
    print("=" * 60)

    passed = sum(1 for _, result in results if result)
    total = len(results)

    for name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {name}")

    print("\n" + "=" * 60)
    print(f"Overall: {passed}/{total} tests passed")
    print("=" * 60)

    if passed == total:
        print("\n🎉 All verification tests passed!")
        print("Ready to run: pytest tests/test_sender.py")
        return 0
    else:
        print("\n⚠️  Some tests failed. Please review the output above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
