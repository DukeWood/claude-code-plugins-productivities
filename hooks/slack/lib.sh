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

    $python << PYEOF
import json
import urllib.request

webhook = "${SLACK_WEBHOOK}"
try:
    payload = json.loads('''${payload}''')
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(webhook, data=data, headers={'Content-Type': 'application/json'})
    urllib.request.urlopen(req, timeout=5)
except Exception as e:
    pass  # Fail silently - don't block Claude
PYEOF
}

# ============================================
# Build Slack Payload - PreToolUse (Compact)
# ============================================
build_pretooluse_payload() {
    local tool_name="$1"
    local tool_input="$2"

    # Escape for JSON
    local python=$(find_python)
    local input_escaped=$($python -c "import json,sys; print(json.dumps(sys.stdin.read())[1:-1])" <<< "$tool_input")

    # Truncate for display
    local input_short="${tool_input:0:150}"
    [ ${#tool_input} -gt 150 ] && input_short="${input_short}..."
    input_short=$(echo "$input_short" | tr '\n' ' ')

    local session_display="${terminal_info:-$terminal_type}"
    local switch_display=""
    [ -n "$switch_command" ] && switch_display=" | :point_right: \`$switch_command\`"

    local python=$(find_python)

    # Escape single quotes for Python string embedding
    local input_escaped=$(echo "$input_short" | sed "s/'/\\\\'/g")
    local switch_escaped=$(echo "$switch_display" | sed "s/'/\\\\'/g")

    $python -c "
import json
payload = {
    'attachments': [{
        'color': '$color',
        'blocks': [
            {
                'type': 'section',
                'text': {
                    'type': 'mrkdwn',
                    'text': '$emoji *$ntype* | \`$tool_name\` | $terminal_type\n:hourglass: *$project* → \`$session_display\`$switch_escaped'
                }
            },
            {
                'type': 'context',
                'elements': [{
                    'type': 'mrkdwn',
                    'text': '\`$serial_number\` | $timestamp | \`\`\`$input_escaped\`\`\`'
                }]
            }
        ]
    }]
}
print(json.dumps(payload))
"
}

# ============================================
# Build Slack Payload - Notification/Stop (Full)
# ============================================
build_notification_payload() {
    local title="$1"
    local body="$2"
    local git_branch="${3:-}"
    local git_status="${4:-}"

    # Context line
    local context_text="\`$serial_number\` | *$project*"
    [ -n "$git_branch" ] && context_text="$context_text | \`$git_branch\` $git_status"
    context_text="$context_text | $timestamp"

    # Quick actions
    local actions=""
    [ -n "$switch_command" ] && actions="Terminal: \`$switch_command\`"

    local actions_block=""
    if [ -n "$actions" ]; then
        actions_block=',{"type":"context","elements":[{"type":"mrkdwn","text":"*Quick Actions:* '"$actions"'"}]}'
    fi

    local python=$(find_python)

    # Escape variables for Python string
    local title_escaped=$(echo "$title" | sed "s/'/\\\\'/g")
    local body_escaped=$(echo "$body" | sed "s/'/\\\\'/g")

    $python -c "
import json
payload = {
    'attachments': [{
        'color': '$color',
        'blocks': [
            {
                'type': 'header',
                'text': {'type': 'plain_text', 'text': '$emoji $ntype', 'emoji': True}
            },
            {
                'type': 'context',
                'elements': [{'type': 'mrkdwn', 'text': '$context_text'}]
            },
            {'type': 'divider'},
            {
                'type': 'section',
                'text': {'type': 'mrkdwn', 'text': '*$title_escaped*\n$body_escaped'}
            }
        ]
    }]
}
print(json.dumps(payload))
"
}
