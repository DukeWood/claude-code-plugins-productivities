# Proposal 3: UI Placement Options for Daily Counter

## 1. Description & Objectives

### Problem Statement

Once a daily notification counter is implemented (via V1 Shell or V2 SQLite), it needs to be displayed in the Slack notification message. The placement significantly impacts:
- Visibility and scannability
- Visual hierarchy of the message
- User experience across different Slack clients (desktop, mobile, web)

### Proposed Solution

Three distinct placement options are presented, each with different trade-offs:

| Option | Placement | Example |
|--------|-----------|---------|
| **A** | In Title | `⏳ Waiting for Input (#5)` |
| **B** | In Info Line | `#5 | 533b | project | tmux...` |
| **C** | Separate Badge | `[Today: #5]` as own element |

### Goals & Success Metrics

| Goal | Success Metric |
|------|----------------|
| High visibility | Users notice counter within 1 second |
| Non-intrusive | Doesn't distract from core message |
| Consistent rendering | Works on desktop, mobile, web |
| Scannable | Easy to track in notification list |

---

## 2. Detailed Implementation Plan

### Current Message Structure (Slack Block Kit)

```
┌──────────────────────────────────────────────────────┐
│  HEADER BLOCK                                        │
│  "⏳ Waiting for Input"                              │
├──────────────────────────────────────────────────────┤
│  CONTEXT BLOCK (info line)                           │
│  `533b` | *project-name* | tmux 0:0.0 | main | 10:48│
├──────────────────────────────────────────────────────┤
│  DIVIDER BLOCK                                       │
│  ─────────────────────────────────────────────────   │
├──────────────────────────────────────────────────────┤
│  SECTION BLOCK (main content)                        │
│  **Claude is waiting for your response**             │
│  Please check the terminal to continue.              │
├──────────────────────────────────────────────────────┤
│  CONTEXT BLOCK (quick action)                        │
│  Quick Action: `tmux select-pane -t 1:0.0`          │
└──────────────────────────────────────────────────────┘
```

---

## Option A: Counter in Title (Recommended)

### Visual Design

```
┌──────────────────────────────────────────────────────┐
│  ⏳ Waiting for Input (#5)                           │  ← Counter here
├──────────────────────────────────────────────────────┤
│  533b | claude-code-plugins | tmux 0:0.0 | main     │
│  10:48 p.m.                                          │
├──────────────────────────────────────────────────────┤
│  ─────────────────────────────────────────────────   │
├──────────────────────────────────────────────────────┤
│  **Claude is waiting for your response**             │
│  Please check the terminal to continue.              │
├──────────────────────────────────────────────────────┤
│  Quick Action: `tmux select-pane -t 1:0.0`          │
└──────────────────────────────────────────────────────┘
```

### Implementation

#### V1 Shell (`notify-permission.sh`)

**Location:** Line ~79 (NOTIF_TITLE)

```bash
# Before:
NOTIF_TITLE="⏳ Waiting for Input"

# After:
COUNTER_DISPLAY=$(format_counter_display "$DAILY_COUNT")
NOTIF_TITLE="⏳ Waiting for Input ${COUNTER_DISPLAY}"
```

**Location:** Line ~89 (SLACK_PAYLOAD header block)

```bash
# Before:
{
  "type": "header",
  "text": {
    "type": "plain_text",
    "text": "⏳ Waiting for Input"
  }
}

# After:
{
  "type": "header",
  "text": {
    "type": "plain_text",
    "text": "⏳ Waiting for Input ${COUNTER_DISPLAY}"
  }
}
```

#### V2 Python (`sender.py`)

**Location:** `build_permission_payload()` line ~145

```python
# Before:
header_text = f"🔔 {project_name}: Permission Required"

# After:
counter_suffix = format_counter_for_title(daily_count) if daily_count else ""
header_text = f"🔔 {project_name}: Permission Required {counter_suffix}".strip()
```

### Pros & Cons

| Pros | Cons |
|------|------|
| Most visible position | May feel cluttered with emoji + counter |
| First thing user sees | Longer titles on mobile |
| Easy to scan in threads | No separation from notification type |
| Simplest implementation | |

### Rendering Examples

**Desktop Slack:**
```
⏳ Waiting for Input (#5)
```

**Mobile Slack:**
```
⏳ Waiting for Input (#5)
```

**Email notification:**
```
Subject: ⏳ Waiting for Input (#5) | project-name
```

---

## Option B: Counter in Info Line

### Visual Design

```
┌──────────────────────────────────────────────────────┐
│  ⏳ Waiting for Input                                │
├──────────────────────────────────────────────────────┤
│  #5 | 533b | claude-code-plugins | tmux 0:0.0       │  ← Counter here
│  main | 10:48 p.m.                                   │
├──────────────────────────────────────────────────────┤
│  ─────────────────────────────────────────────────   │
├──────────────────────────────────────────────────────┤
│  **Claude is waiting for your response**             │
│  Please check the terminal to continue.              │
├──────────────────────────────────────────────────────┤
│  Quick Action: `tmux select-pane -t 1:0.0`          │
└──────────────────────────────────────────────────────┘
```

### Implementation

#### V1 Shell (`notify-permission.sh`)

**Location:** Line ~120 (context block text)

```bash
# Before:
"text": "\`$SERIAL\` | *$PROJECT_NAME* | $TERMINAL_INFO | \`$GIT_BRANCH\` | $TIMESTAMP"

# After:
"text": "#$DAILY_COUNT | \`$SERIAL\` | *$PROJECT_NAME* | $TERMINAL_INFO | \`$GIT_BRANCH\` | $TIMESTAMP"
```

#### V2 Python (`sender.py`)

**Location:** `build_permission_payload()` context_parts array (~line 173)

```python
# Before:
context_parts = [
    f"`{session_short}`",
    f"*{project_name}*",
    terminal_info,
    f"`{git_branch}`" if git_branch else None,
    timestamp
]

# After:
counter_prefix = f"#{daily_count}" if daily_count and daily_count > 0 else None
context_parts = [
    counter_prefix,  # NEW: Counter first
    f"`{session_short}`",
    f"*{project_name}*",
    terminal_info,
    f"`{git_branch}`" if git_branch else None,
    timestamp
]
context_parts = [p for p in context_parts if p]  # Filter None
```

### Pros & Cons

| Pros | Cons |
|------|------|
| Natural metadata grouping | Less prominent |
| Doesn't clutter title | Can be missed when scrolling |
| Professional appearance | Adds to already-long info line |
| Consistent with serial ID | May wrap on mobile |

### Rendering Examples

**Desktop Slack:**
```
#5 | 533b | claude-code-plugins | tmux 0:0.0 | main | 10:48 p.m.
```

**Mobile Slack (may wrap):**
```
#5 | 533b | claude-code-
plugins | tmux 0:0.0 | main
| 10:48 p.m.
```

---

## Option C: Separate Badge/Field

### Visual Design

```
┌──────────────────────────────────────────────────────┐
│  ⏳ Waiting for Input                                │
├──────────────────────────────────────────────────────┤
│  [Today: #5]                                         │  ← Counter here
├──────────────────────────────────────────────────────┤
│  533b | claude-code-plugins | tmux 0:0.0 | main     │
│  10:48 p.m.                                          │
├──────────────────────────────────────────────────────┤
│  ─────────────────────────────────────────────────   │
├──────────────────────────────────────────────────────┤
│  **Claude is waiting for your response**             │
│  Please check the terminal to continue.              │
├──────────────────────────────────────────────────────┤
│  Quick Action: `tmux select-pane -t 1:0.0`          │
└──────────────────────────────────────────────────────┘
```

### Implementation

#### V1 Shell (`notify-permission.sh`)

**Location:** After header block, before context block (~line 95)

```bash
# Add new context block for counter
COUNTER_BLOCK=""
if [ -n "$DAILY_COUNT" ] && [ "$DAILY_COUNT" != "0" ]; then
  COUNTER_BLOCK=',{
    "type": "context",
    "elements": [{
      "type": "mrkdwn",
      "text": "📊 *Today:* #'"$DAILY_COUNT"'"
    }]
  }'
fi

# Insert in SLACK_PAYLOAD between header and info line
```

#### V2 Python (`sender.py`)

**Location:** `build_permission_payload()` blocks array (~line 180)

```python
# Build blocks array
blocks = [
    {
        "type": "header",
        "text": {"type": "plain_text", "text": header_text}
    }
]

# NEW: Add counter badge if present
if daily_count and daily_count > 0:
    blocks.append({
        "type": "context",
        "elements": [{
            "type": "mrkdwn",
            "text": f"📊 *Today:* #{daily_count}"
        }]
    })

# Continue with existing blocks
blocks.extend([
    {
        "type": "context",
        "elements": [{"type": "mrkdwn", "text": context_text}]
    },
    {"type": "divider"},
    # ... rest of blocks
])
```

### Alternative: Right-Aligned Badge

```python
# Using section with accessory
{
    "type": "section",
    "text": {
        "type": "mrkdwn",
        "text": "*⏳ Waiting for Input*"
    },
    "accessory": {
        "type": "button",
        "text": {"type": "plain_text", "text": "#5 today"},
        "style": "primary",
        "action_id": "counter_badge"  # Non-functional, just display
    }
}
```

**Note:** Button accessory requires Slack app with interactivity enabled.

### Pros & Cons

| Pros | Cons |
|------|------|
| Highly visible and intentional | Adds vertical space |
| Room for expansion (week count) | More complex implementation |
| Clear separation from metadata | Inconsistent with minimal design |
| Can add icon/emoji | Requires extra block in payload |

### Rendering Examples

**Desktop Slack:**
```
⏳ Waiting for Input
📊 Today: #5
533b | project | tmux 0:0.0 | main | 10:48 p.m.
```

**Mobile Slack:**
```
⏳ Waiting for Input
📊 Today: #5
533b | project | tmux
0:0.0 | main | 10:48 p.m.
```

---

## 3. Acceptance Criteria

### Common Criteria (All Options)

| ID | Requirement | Verification |
|----|-------------|--------------|
| AC-1 | Counter visible on desktop | Visual inspection |
| AC-2 | Counter visible on mobile | Test on iOS/Android Slack |
| AC-3 | Counter visible in web app | Test on slack.com |
| AC-4 | Counter doesn't break layout | No text overflow |
| AC-5 | Counter hidden when 0 | First notification shows #1 |

### Option-Specific Criteria

| Option | Additional Criteria |
|--------|---------------------|
| A | Title stays single line on desktop |
| A | Title wraps gracefully on mobile |
| B | Info line fits on single line (80 chars) |
| B | Counter is first element in line |
| C | Badge block appears after header |
| C | Badge has consistent styling |

---

## 4. Testing Requirements

### Visual Testing Matrix

| Client | Option A | Option B | Option C |
|--------|----------|----------|----------|
| Slack Desktop (Mac) | Test | Test | Test |
| Slack Desktop (Windows) | Test | Test | Test |
| Slack Mobile (iOS) | Test | Test | Test |
| Slack Mobile (Android) | Test | Test | Test |
| Slack Web | Test | Test | Test |
| Email notification | Test | Test | Test |

### Test Scenarios

```gherkin
Feature: Daily Counter Display

  Scenario: Counter shows in title (Option A)
    Given a notification with daily_count = 5
    When the Slack message is rendered
    Then the header shows "⏳ Waiting for Input (#5)"

  Scenario: Counter shows in info line (Option B)
    Given a notification with daily_count = 5
    When the Slack message is rendered
    Then the context line starts with "#5 |"

  Scenario: Counter shows as badge (Option C)
    Given a notification with daily_count = 5
    When the Slack message is rendered
    Then a context block shows "📊 Today: #5"

  Scenario: Counter hidden for zero
    Given a notification with daily_count = 0
    When the Slack message is rendered
    Then no counter is displayed

  Scenario: Long project name + counter (Option A)
    Given project_name = "claude-code-plugins-productivities"
    And daily_count = 99
    When the Slack message is rendered
    Then the title doesn't overflow
```

### Manual Test Commands

```bash
# Test Option A: Title
echo '{"header": "⏳ Waiting for Input (#5)"}' | \
  jq '.blocks[0].text.text'

# Test Option B: Info Line
echo '{"context": "#5 | 533b | project | tmux"}' | \
  jq '.blocks[1].elements[0].text'

# Test Option C: Badge
echo '{"badge": "📊 Today: #5"}' | \
  jq '.blocks[1].elements[0].text'
```

---

## 5. Performance Considerations

### Payload Size Impact

| Option | Additional Bytes | Impact |
|--------|------------------|--------|
| A | ~10 bytes | Negligible |
| B | ~5 bytes | Negligible |
| C | ~80 bytes | Negligible |

**Note:** All options add < 100 bytes to payload. Slack's limit is 4KB for blocks.

### Rendering Performance

All options render in < 10ms on any client. No performance difference.

### Implementation Complexity

| Option | Lines of Code | Complexity |
|--------|---------------|------------|
| A | 5-10 | Low |
| B | 10-15 | Low |
| C | 20-30 | Medium |

---

## Recommendation Matrix

| Criteria | Option A | Option B | Option C |
|----------|----------|----------|----------|
| Visibility | ⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Simplicity | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Mobile UX | ⭐⭐ | ⭐⭐ | ⭐⭐⭐ |
| Professional | ⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| Implementation | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐ |
| **Total** | **13** | **13** | **12** |

### Final Recommendation

**Option A (In Title)** is recommended because:
1. Highest visibility - users immediately see the counter
2. Simplest implementation - just append to existing string
3. Consistent across all Slack clients
4. No additional blocks or layout changes
5. Matches user's goal: "know how many notifications per day"

**Option B** is a good alternative if title feels cluttered.

**Option C** is best for future expansion (week/month counters, analytics).

---

## Summary

| Option | Best For | Avoid When |
|--------|----------|------------|
| A (Title) | Quick scanning, simple tracking | Title already long |
| B (Info Line) | Clean design, metadata grouping | Counter visibility critical |
| C (Badge) | Analytics focus, room for expansion | Minimal design preferred |
