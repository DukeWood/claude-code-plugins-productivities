# Proposal 1: V1 Shell-Based File Counter

## 1. Description & Objectives

### Problem Statement

Users receiving Slack notifications from Claude Code have no visibility into their daily notification volume. When multiple notifications arrive throughout the day, there's no way to:
- Track how many notifications have been sent today
- Understand notification patterns
- Identify unusually high notification days

### Proposed Solution

Implement a file-based counter system using date-stamped text files that automatically reset daily. Each project maintains its own counter file using the naming pattern:

```
~/.claude/notification-counters/{PROJECT_NAME}_{MMDD}.count
```

The counter value is displayed in the Slack notification title:
```
⏳ Waiting for Input (#5)
```

### Goals & Success Metrics

| Goal | Success Metric |
|------|----------------|
| Daily tracking | Counter increments correctly on each notification |
| Auto-reset | Counter resets to 1 at midnight (via filename change) |
| Zero latency impact | Hook execution time remains <50ms |
| Reliability | Counter persists across hook invocations |

---

## 2. Detailed Implementation Plan

### Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Hook Execution                        │
├─────────────────────────────────────────────────────────┤
│  notify-permission.sh / notify-stop.sh                   │
│           │                                              │
│           ▼                                              │
│  ┌─────────────────────────────────────────────┐        │
│  │ lib/slack.sh                                 │        │
│  │  - increment_notification_counter()          │        │
│  │  - get_counter_file()                        │        │
│  │  - format_counter_display()                  │        │
│  └─────────────────────────────────────────────┘        │
│           │                                              │
│           ▼                                              │
│  ~/.claude/notification-counters/                        │
│    └── {project}_{MMDD}.count                           │
└─────────────────────────────────────────────────────────┘
```

### File Changes

#### 2.1 `hooks/slack/lib/slack.sh` - Add Counter Functions

**Location:** After line 50 (after existing helper functions)

```bash
# =============================================================================
# Daily Notification Counter
# =============================================================================

# Get counter file path for today
# Args: $1 = project_name
# Returns: Path to counter file
get_counter_file() {
    local project_name="$1"
    local today=$(date +%m%d)
    local counter_dir="$HOME/.claude/notification-counters"

    # Sanitize project name (replace spaces/special chars with underscore)
    local safe_name=$(echo "$project_name" | tr ' /:' '_')

    echo "${counter_dir}/${safe_name}_${today}.count"
}

# Increment and return daily notification counter
# Args: $1 = project_name
# Returns: New counter value (echoed)
# Side effects: Creates/updates counter file
increment_notification_counter() {
    local project_name="$1"
    local counter_file=$(get_counter_file "$project_name")
    local counter_dir="$HOME/.claude/notification-counters"

    # Create directory if missing (silent fail ok)
    mkdir -p "$counter_dir" 2>/dev/null || true

    # Read current count (default to 0 if file missing or invalid)
    local current=0
    if [ -f "$counter_file" ]; then
        current=$(cat "$counter_file" 2>/dev/null | grep -o '^[0-9]*' | head -1)
        current=${current:-0}
    fi

    # Increment
    local next=$((current + 1))

    # Write back (silent fail ok - notification still sends)
    echo "$next" > "$counter_file" 2>/dev/null || true

    echo "$next"
}

# Get current counter value without incrementing
# Args: $1 = project_name
# Returns: Current counter value (echoed)
get_notification_counter() {
    local project_name="$1"
    local counter_file=$(get_counter_file "$project_name")

    if [ -f "$counter_file" ]; then
        local count=$(cat "$counter_file" 2>/dev/null | grep -o '^[0-9]*' | head -1)
        echo "${count:-0}"
    else
        echo "0"
    fi
}

# Format counter for display in Slack message
# Args: $1 = count
# Returns: Formatted string like "(#5)" or empty if count is 0
format_counter_display() {
    local count="$1"

    if [ -z "$count" ] || [ "$count" = "0" ]; then
        echo ""
    else
        echo "(#${count})"
    fi
}
```

#### 2.2 `hooks/slack/notify-permission.sh` - Integrate Counter

**Location:** After line 45 (after PROJECT_NAME is set)

```bash
# Get project name
PROJECT_NAME=$(get_project_name "$CWD")

# === ADD THESE LINES ===
# Increment daily notification counter
DAILY_COUNT=$(increment_notification_counter "$PROJECT_NAME")
COUNTER_DISPLAY=$(format_counter_display "$DAILY_COUNT")
# === END ADDITION ===
```

**Location:** Line 79 (modify NOTIF_TITLE)

```bash
# Before:
NOTIF_TITLE="⏳ Waiting for Input"

# After:
NOTIF_TITLE="⏳ Waiting for Input ${COUNTER_DISPLAY}"
```

**Location:** Line 89 (modify header block in SLACK_PAYLOAD)

```bash
# Before:
"text": "⏳ Waiting for Input"

# After:
"text": "⏳ Waiting for Input ${COUNTER_DISPLAY}"
```

#### 2.3 `hooks/slack/notify-stop.sh` - Integrate Counter

**Location:** After line 35 (after PROJECT_NAME is set)

```bash
# Get project name
PROJECT_NAME=$(get_project_name "$CWD")

# === ADD THESE LINES ===
# Increment daily notification counter
DAILY_COUNT=$(increment_notification_counter "$PROJECT_NAME")
COUNTER_DISPLAY=$(format_counter_display "$DAILY_COUNT")
# === END ADDITION ===
```

**Location:** Line 82 (modify header in SLACK_PAYLOAD)

```bash
# Before:
"text": "✅ Task Complete"

# After:
"text": "✅ Task Complete ${COUNTER_DISPLAY}"
```

### Counter File Format

**Location:** `~/.claude/notification-counters/`

**Naming:** `{PROJECT_NAME}_{MMDD}.count`

**Content:** Single integer value (no newline required)

**Examples:**
```
~/.claude/notification-counters/
├── claude-code-plugins_1207.count  → "5"
├── torlyAI_1207.count              → "12"
├── claude-code-plugins_1206.count  → "23"  (yesterday, not used)
└── myproject_1207.count            → "1"
```

---

## 3. Acceptance Criteria

### Functional Requirements

| ID | Requirement | Verification |
|----|-------------|--------------|
| FR-1 | Counter increments on each notification | Send 3 notifications, verify count shows #1, #2, #3 |
| FR-2 | Counter resets at midnight | Check counter after midnight shows #1 |
| FR-3 | Counter displays in notification title | Slack message shows "⏳ Waiting for Input (#5)" |
| FR-4 | Each project has separate counter | Two projects show independent counts |
| FR-5 | Counter hidden when 0 | First notification shows "(#1)" not "(#0)" |

### Non-Functional Requirements

| ID | Requirement | Threshold |
|----|-------------|-----------|
| NFR-1 | Hook execution time | < 50ms added latency |
| NFR-2 | File operations | No blocking on disk I/O failure |
| NFR-3 | Error handling | Notification sends even if counter fails |
| NFR-4 | Concurrent safety | Sequential access (shell single-threaded) |

### Edge Cases

| Case | Expected Behavior |
|------|-------------------|
| Counter file missing | Create file, start at 1 |
| Counter directory missing | Create directory, then file |
| Disk full | Counter fails silently, notification sends |
| Invalid file content | Reset to 1 |
| Permission denied | Continue without counter |
| Project name with spaces | Converted to underscores |
| Very long project name | Truncated or hashed (future) |

---

## 4. Testing Requirements

### Unit Tests (Manual - Shell)

```bash
# Test 1: Counter increments
source hooks/slack/lib/slack.sh
increment_notification_counter "test-project"  # Should echo "1"
increment_notification_counter "test-project"  # Should echo "2"
increment_notification_counter "test-project"  # Should echo "3"

# Test 2: Format display
format_counter_display "0"   # Should echo "" (empty)
format_counter_display "1"   # Should echo "(#1)"
format_counter_display "99"  # Should echo "(#99)"

# Test 3: Separate projects
increment_notification_counter "project-a"  # Should echo "1"
increment_notification_counter "project-b"  # Should echo "1"
increment_notification_counter "project-a"  # Should echo "2"

# Test 4: Counter file location
get_counter_file "my-project"  # Should echo ~/.claude/notification-counters/my-project_1207.count
```

### Integration Tests

```bash
# Test 1: End-to-end permission notification
echo '{"hook_event_name":"Notification","notification_type":"permission_prompt","tool_name":"Edit","session_id":"test","cwd":"'$PWD'"}' | ./notify-permission.sh

# Verify in Slack: Title shows "(#1)"

# Test 2: End-to-end stop notification
echo '{"hook_event_name":"Stop","session_id":"test","cwd":"'$PWD'"}' | ./notify-stop.sh

# Verify in Slack: Title shows "(#2)"

# Test 3: Minimal environment (as Claude Code runs it)
env -i HOME=$HOME PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" \
  ./notify-permission.sh <<< '{"hook_event_name":"Notification","notification_type":"permission_prompt","tool_name":"Bash","session_id":"test","cwd":"'$PWD'"}'
```

### Manual Test Scenarios

1. **Fresh start:** Delete all counter files, send notification → Shows (#1)
2. **Multiple notifications:** Send 5 notifications quickly → Shows (#1) through (#5)
3. **Cross-midnight:** Send notification at 11:59 PM, another at 12:01 AM → Second shows (#1)
4. **Multiple projects:** Switch projects between notifications → Each has own counter
5. **Error recovery:** Make counter file read-only → Notification still sends

---

## 5. Performance Considerations

### Expected Latency Impact

| Operation | Time | Notes |
|-----------|------|-------|
| Read counter file | ~1ms | Single file read |
| Write counter file | ~2ms | Write + fsync |
| mkdir (if needed) | ~1ms | Only first time |
| Total overhead | ~3-5ms | Well within budget |

### Resource Usage

- **Disk space:** ~10 bytes per project per day
- **File handles:** 1 open/close per notification
- **Memory:** Negligible (shell variables only)

### Scalability Notes

**Counter file cleanup (optional):**
```bash
# Clean up counter files older than 7 days
find ~/.claude/notification-counters -name "*.count" -mtime +7 -delete
```

**High volume considerations:**
- 100 notifications/day = 100 file writes = negligible
- 1000 notifications/day = still fine, but consider V2 SQLite

### Comparison to V2 SQLite

| Aspect | V1 Shell | V2 SQLite |
|--------|----------|-----------|
| Latency | ~3-5ms | ~5-10ms |
| Accuracy | Per-project | Per-session |
| Persistence | Files | Database |
| Query flexibility | Limited | Full SQL |
| Dependencies | None | Python |

---

## Summary

**Recommended for:** Immediate deployment with V1 shell hooks.

**Implementation effort:** ~40 lines of code, 30 minutes.

**Risk level:** Low - file-based, no external dependencies.
