#!/bin/bash
# ============================================
# Claude Code → Slack: Notification/Stop Hook
# Notifies on task completion and notifications
# ============================================

# Load libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
setup_path

# ============================================
# State file for idle detection
# ============================================
STATE_FILE="$HOME/.claude/config/notification_states.json"
mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null

# ============================================
# Parse Input JSON
# ============================================
python=$(find_python)
input_json=$(cat)

hook_event=$(json_get "$input_json" "hook_event_name" "Notification")
cwd=$(json_get "$input_json" "cwd" "Unknown")

# ============================================
# Load Config (exit if not configured)
# ============================================
if ! load_slack_config; then
    exit 0
fi

# ============================================
# Check config for notification preferences
# ============================================
notify_task_complete=$($python -c "import json; c=json.load(open('$SLACK_CONFIG_FILE')); print(str(c.get('notify_on',{}).get('task_complete', True)).lower())" 2>/dev/null)

# ============================================
# Handle Stop Event
# ============================================
if [ "$hook_event" = "Stop" ]; then
    # Check if task_complete notifications are enabled
    if [ "$notify_task_complete" != "true" ]; then
        exit 0
    fi

    # Check if we were waiting for input (idle state)
    was_idle="false"
    if [ -f "$STATE_FILE" ]; then
        was_idle=$($python -c "import json; print(str(json.load(open('$STATE_FILE')).get('was_idle', False)).lower())" 2>/dev/null)
    fi

    if [ "$was_idle" != "true" ]; then
        # Not idle - skip notification
        exit 0
    fi

    # Reset idle state
    echo '{"was_idle": false}' > "$STATE_FILE"

    # Set Stop event message
    title="Task Complete"
    body="Claude Code has finished responding"
    notification_type="task_complete"
else
    # ============================================
    # Handle Notification Event
    # ============================================

    # Parse notification fields
    message=$(json_get "$input_json" "message" "")
    notification_type=$(json_get "$input_json" "notification_type" "")
    title=$(json_get "$input_json" "title" "Claude Code")
    body=$(json_get "$input_json" "body" "")

    # Use message field if available
    if [ -n "$message" ]; then
        title="Claude Code"
        body="$message"
    fi

    # ============================================
    # Filter notifications - only send actionable ones
    # ============================================
    combined="$title $body $message"

    # Check if this is a permission request (ACTION REQUIRED)
    if echo "$combined" | grep -qi "permission\|needs your permission"; then
        # This IS actionable - set type and continue
        notification_type="permission_prompt"

        # ============================================
        # Enrich permission notification with tool details
        # ============================================
        TOOL_REQUEST_FILE="$HOME/.claude/config/last_tool_request.json"
        if [ -f "$TOOL_REQUEST_FILE" ]; then
            tool_details=$($python -c "
import json
import os

try:
    with open('$TOOL_REQUEST_FILE') as f:
        data = json.load(f)

    tool_name = data.get('tool_name', 'Unknown')
    tool_input = data.get('tool_input', {})

    # Format based on tool type
    if tool_name in ['Edit', 'Write', 'Read']:
        file_path = tool_input.get('file_path', '')
        if file_path:
            filename = os.path.basename(file_path)
            dirname = os.path.dirname(file_path)
            # Shorten path if too long
            if len(dirname) > 50:
                dirname = '.../' + '/'.join(dirname.split('/')[-3:])
            print(f'{tool_name} Permission')
            print(f':page_facing_up: File: {filename}')
            print(f':file_folder: Path: {dirname}')
        else:
            print(f'{tool_name} Permission')
    elif tool_name == 'Bash':
        cmd = tool_input.get('command', '')
        if len(cmd) > 80:
            cmd = cmd[:77] + '...'
        print('Bash Permission')
        print(f':computer: Command: \`{cmd}\`')
    elif tool_name == 'WebFetch':
        url = tool_input.get('url', '')
        if len(url) > 60:
            url = url[:57] + '...'
        print('Web Access Permission')
        print(f':globe_with_meridians: URL: {url}')
    elif tool_name == 'Task':
        agent_type = tool_input.get('subagent_type', 'general')
        desc = tool_input.get('description', '')[:50]
        print('Agent Task Permission')
        print(f':robot_face: Agent: {agent_type}')
        if desc:
            print(f':clipboard: Task: {desc}')
    else:
        print(f'{tool_name} Permission')
        # Show first key-value from input
        for k, v in list(tool_input.items())[:1]:
            v_str = str(v)[:50]
            print(f':wrench: {k}: {v_str}')
except Exception as e:
    print('Permission Request')
" 2>/dev/null)

            if [ -n "$tool_details" ]; then
                # Use tool details for title and body
                title=$(echo "$tool_details" | head -1)
                body=$(echo "$tool_details" | tail -n +2)
            fi
        fi
    elif echo "$combined" | grep -qi "waiting for your input\|waiting for input"; then
        # Already handled by ask-user.sh (PostToolUse hook)
        exit 0
    fi

    # Defaults
    [ -z "$title" ] && title="Claude Code"
    [ -z "$body" ] && body="Notification"

    # Set idle state for next Stop event
    echo '{"was_idle": true}' > "$STATE_FILE"
fi

# ============================================
# Get Context
# ============================================
detect_terminal "$cwd"
get_project_info "$cwd"
get_notification_style "$notification_type" "$title" "$body"

# ============================================
# Get Git Info (optional)
# ============================================
git_branch=""
git_status=""

if cd "$cwd" 2>/dev/null && git rev-parse --git-dir &>/dev/null; then
    git_branch=$(git symbolic-ref --short HEAD 2>/dev/null || echo "")

    if [ -n "$git_branch" ]; then
        staged=$(git diff --cached --numstat 2>/dev/null | wc -l | tr -d ' ')
        unstaged=$(git diff --numstat 2>/dev/null | wc -l | tr -d ' ')
        untracked=$(git ls-files --others --exclude-standard 2>/dev/null | wc -l | tr -d ' ')

        [ "$staged" -gt 0 ] 2>/dev/null && git_status="${git_status}S:${staged} "
        [ "$unstaged" -gt 0 ] 2>/dev/null && git_status="${git_status}M:${unstaged} "
        [ "$untracked" -gt 0 ] 2>/dev/null && git_status="${git_status}U:${untracked}"
        [ -z "$git_status" ] && git_status="clean"
    fi
fi

# ============================================
# Build and Send Payload
# ============================================
payload=$(build_notification_payload "$title" "$body" "$git_branch" "$git_status")
send_to_slack "$payload"

exit 0
