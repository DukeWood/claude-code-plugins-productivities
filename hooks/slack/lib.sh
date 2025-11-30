#!/bin/bash
# ============================================
# Slack Hook Library
# Shared functions for Slack notification hooks
# ============================================

# Get script directory and source common lib
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../../lib/common.sh"

# ============================================
# Slack Configuration
# ============================================
SLACK_CONFIG_FILE="${SLACK_CONFIG_FILE:-$HOME/.claude/config/slack-config.json}"

load_slack_config() {
    if [ ! -f "$SLACK_CONFIG_FILE" ]; then
        debug_log "Config file not found: $SLACK_CONFIG_FILE"
        return 1
    fi

    local python=$(find_python)
    SLACK_WEBHOOK=$($python -c "import json; print(json.load(open('$SLACK_CONFIG_FILE')).get('webhook_url',''))" 2>/dev/null)

    if [ -z "$SLACK_WEBHOOK" ]; then
        debug_log "webhook_url not found in config"
        return 1
    fi

    export SLACK_WEBHOOK
    return 0
}

# ============================================
# Tool Type Detection (for PreToolUse)
# Sets: emoji, ntype, color
# ============================================
get_tool_style() {
    local tool_name="$1"

    case "$tool_name" in
        Bash|bash)
            emoji="💻"
            ntype="Bash Command"
            color="#E01E5A"  # Red
            ;;
        Write|Edit|NotebookEdit)
            emoji="✏️"
            ntype="File Write"
            color="#ECB22E"  # Yellow
            ;;
        WebFetch|WebSearch)
            emoji="🌐"
            ntype="Web Access"
            color="#36C5F0"  # Blue
            ;;
        Read|Glob|Grep|LS)
            emoji="📖"
            ntype="File Read"
            color="#2EB67D"  # Green
            ;;
        Task)
            emoji="🤖"
            ntype="Agent Task"
            color="#9B59B6"  # Purple
            ;;
        *)
            emoji="🔧"
            ntype="Tool: $tool_name"
            color="#2EB67D"  # Green
            ;;
    esac

    export emoji ntype color
}

# ============================================
# Notification Type Detection (for Notification/Stop)
# Sets: emoji, ntype, color
# ============================================
get_notification_style() {
    local notification_type="$1"
    local title="$2"
    local body="$3"

    # Default
    emoji="🔔"
    ntype="Notification"
    color="#36C5F0"  # Blue

    # Try notification_type field first
    case "$notification_type" in
        permission_prompt)
            emoji="🔐"
            ntype="Permission Required"
            color="#E01E5A"
            ;;
        idle_prompt)
            emoji="⏳"
            ntype="Awaiting Input"
            color="#ECB22E"
            ;;
        auth_success|auth_required)
            emoji="🔑"
            ntype="Authentication"
            color="#36C5F0"
            ;;
        elicitation_dialog)
            emoji="📝"
            ntype="Input Required"
            color="#ECB22E"
            ;;
        *)
            # Fall back to keyword matching
            local combined="$title $body"

            if echo "$combined" | grep -qi "permission\|approve\|allow"; then
                emoji="🔐"
                ntype="Permission Required"
                color="#E01E5A"
            elif echo "$combined" | grep -qi "idle\|waiting\|awaiting.*input"; then
                emoji="⏳"
                ntype="Awaiting Input"
                color="#ECB22E"
            elif echo "$combined" | grep -qi "complete\|finished\|done\|success"; then
                emoji="✅"
                ntype="Task Complete"
                color="#2EB67D"
            elif echo "$combined" | grep -qi "error\|fail\|exception"; then
                emoji="❌"
                ntype="Error"
                color="#E01E5A"
            fi
            ;;
    esac

    export emoji ntype color
}

# ============================================
# Send to Slack
# ============================================
send_to_slack() {
    local payload="$1"
    local python=$(find_python)

    # Pass payload via stdin to avoid heredoc escaping issues
    echo "$payload" | $python -c "
import json
import urllib.request
import sys

webhook = '${SLACK_WEBHOOK}'

try:
    payload_str = sys.stdin.read()
    payload = json.loads(payload_str)
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(webhook, data=data, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=5)
except:
    pass  # Fail silently - don't block Claude
"
}

# ============================================
# Build Slack Payload - PreToolUse (Compact)
# ============================================
build_pretooluse_payload() {
    local tool_name="$1"
    local tool_input="$2"
    local python=$(find_python)

    # Truncate first, then escape
    local input_short="${tool_input:0:150}"
    [ ${#tool_input} -gt 150 ] && input_short="${input_short}..."
    input_short=$(echo "$input_short" | tr '\n' ' ')

    local session_display="${terminal_info:-$terminal_type}"
    local switch_display=""
    [ -n "$switch_command" ] && switch_display=" | :point_right: \`$switch_command\`"

    # Use Slack emoji codes instead of Unicode emojis (more reliable)
    local slack_emoji
    case "$ntype" in
        "Bash Command") slack_emoji=":computer:" ;;
        "File Write") slack_emoji=":pencil2:" ;;
        "Web Access") slack_emoji=":globe_with_meridians:" ;;
        "File Read") slack_emoji=":book:" ;;
        "Agent Task") slack_emoji=":robot_face:" ;;
        *) slack_emoji=":wrench:" ;;
    esac

    # Use Python to safely build the entire payload with proper escaping
    $python << PYEOF
import json

# Safe values passed as Python strings
tool_name = """$tool_name"""
input_short = """$input_short"""
color = """$color"""
slack_emoji = """$slack_emoji"""
ntype = """$ntype"""
terminal_type = """$terminal_type"""
project = """$project"""
session_display = """$session_display"""
switch_display = """$switch_display"""
serial_number = """$serial_number"""
timestamp = """$timestamp"""

# Build header line
header = f"{slack_emoji} *{ntype}* | \`{tool_name}\` | {terminal_type}"
subheader = f":hourglass: *{project}* -> \`{session_display}\`{switch_display}"
context = f"\`{serial_number}\` | {timestamp} | \`\`\`{input_short}\`\`\`"

# Use chr(10) to safely represent newline in the output JSON
newline = chr(10)
full_text = header + newline + subheader

# Notification preview text (shows in macOS notification banner)
preview_text = f"{ntype} | {project} | {input_short[:50]}"

payload = {
    'text': preview_text,  # For macOS/mobile notification previews
    'attachments': [{
        'color': color,
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': full_text
                }
            },
            {
                'type': 'context',
                'elements': [{
                    'type': 'mrkdwn',
                    'text': context
                }]
            }
        ]
    }]
}
# json.dumps will properly escape the newline as \n
print(json.dumps(payload))
PYEOF
}

# ============================================
# Build Slack Payload - Notification/Stop (Full)
# ============================================
build_notification_payload() {
    local title="$1"
    local body="$2"
    local git_branch="${3:-}"
    local git_status="${4:-}"
    local python=$(find_python)

    # Use Slack emoji codes instead of Unicode emojis (more reliable)
    local slack_emoji
    case "$ntype" in
        "Permission Required") slack_emoji=":lock:" ;;
        "Awaiting Input") slack_emoji=":hourglass_flowing_sand:" ;;
        "Authentication") slack_emoji=":key:" ;;
        "Input Required") slack_emoji=":memo:" ;;
        "Task Complete") slack_emoji=":white_check_mark:" ;;
        "Error") slack_emoji=":x:" ;;
        *) slack_emoji=":bell:" ;;
    esac

    # Use Python to safely build the entire payload with proper escaping
    $python << PYEOF
import json

# Safe values passed as Python strings
title = """$title"""
body = """$body"""
git_branch = """$git_branch"""
git_status = """$git_status"""
color = """$color"""
slack_emoji = """$slack_emoji"""
ntype = """$ntype"""
project = """$project"""
serial_number = """$serial_number"""
timestamp = """$timestamp"""
switch_command = """$switch_command"""

# Build context line
context_text = f"\`{serial_number}\` | *{project}*"
if git_branch:
    context_text += f" | \`{git_branch}\` {git_status}"
context_text += f" | {timestamp}"

# Build blocks
blocks = [
    {
        'type': 'header',
        'text': {'type': 'plain_text', 'text': f"{slack_emoji} {ntype}", 'emoji': True}
    },
    {
        'type': 'context',
        'elements': [{'type': 'mrkdwn', 'text': context_text}]
    },
    {'type': 'divider'},
    {
        'type': 'section',
        'text': {'type': 'mrkdwn', 'text': "*" + title + "*" + chr(10) + body}
    }
]

# Add quick actions if switch_command exists
if switch_command:
    blocks.append({
        'type': 'context',
        'elements': [{'type': 'mrkdwn', 'text': f"*Quick Actions:* Terminal: \`{switch_command}\`"}]
    })

# Notification preview text (shows in macOS notification banner)
preview_text = f"{ntype} | {project} | {body[:50]}"

payload = {
    'text': preview_text,  # For macOS/mobile notification previews
    'attachments': [{
        'color': color,
        'blocks': blocks
    }]
}
print(json.dumps(payload))
PYEOF
}
