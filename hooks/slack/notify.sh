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
# Debug logging
# ============================================
DEBUG_LOG="/tmp/slack-notify-debug.log"

# ============================================
# Parse Input JSON
# ============================================
python=$(find_python)
input_json=$(cat)

# Always log hook invocation for debugging (helps trace tmux issues)
{
    echo -n "$(date '+%Y-%m-%d %H:%M:%S') | HOOK INVOKED | "
    echo "$input_json" | $python -c "
import json, sys
try:
    d = json.load(sys.stdin)
    event = d.get('hook_event_name', '?')
    ntype = d.get('notification_type', '?')
    title = str(d.get('title', '?'))[:40]
    body = str(d.get('body', '?'))[:40]
    print('event=' + event + ' type=' + ntype + ' title=' + title)
except Exception as e:
    print('parse_error: ' + str(e))
" 2>/dev/null
} >> "$DEBUG_LOG"

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

    # Check if running in tmux - always notify for tmux sessions
    # Note: $TMUX env var may not be available in hook subprocess, so we also
    # check if any tmux session has a pane in our cwd
    in_tmux="false"
    if [ -n "$TMUX" ]; then
        in_tmux="true"
    elif command -v tmux &>/dev/null && tmux list-panes -a -F '#{pane_current_path}' 2>/dev/null | grep -q "^${cwd}$"; then
        in_tmux="true"
    fi

    # Check if we were waiting for input (idle state)
    was_idle="false"
    if [ -f "$STATE_FILE" ]; then
        was_idle=$($python -c "import json; print(str(json.load(open('$STATE_FILE')).get('was_idle', False)).lower())" 2>/dev/null)
    fi

    # Log the decision for debugging
    echo "$(date '+%Y-%m-%d %H:%M:%S') | STOP | in_tmux=$in_tmux was_idle=$was_idle cwd=$cwd" >> "$DEBUG_LOG"

    # Skip notification only if NOT in tmux AND NOT idle
    if [ "$in_tmux" != "true" ] && [ "$was_idle" != "true" ]; then
        # Not in tmux and not idle - skip notification
        echo "$(date '+%Y-%m-%d %H:%M:%S') | STOP | SKIPPED (not tmux, not idle)" >> "$DEBUG_LOG"
        exit 0
    fi

    # Reset idle state
    echo '{"was_idle": false}' > "$STATE_FILE"

    # ============================================
    # Categorize based on git changes
    # ============================================
    category="Task"
    file_summary=""

    if cd "$cwd" 2>/dev/null && git rev-parse --git-dir &>/dev/null; then
        # Get changed files
        changed_files=$(git diff --name-only 2>/dev/null)
        new_files=$(git ls-files --others --exclude-standard 2>/dev/null)
        all_changes=$(echo -e "$changed_files\n$new_files" | grep -v '^$')

        # Count changes
        change_count=$(echo "$all_changes" | grep -c . 2>/dev/null || echo "0")

        # Categorize based on file paths
        if echo "$all_changes" | grep -qE "Journals/|Memory/"; then
            category="CRM Update"
        elif echo "$all_changes" | grep -qE "\.sh$|hooks/"; then
            category="Automation"
        elif echo "$all_changes" | grep -qE "\.(js|ts|py|json)$"; then
            category="Code Edit"
        elif echo "$all_changes" | grep -qE "\.md$"; then
            category="Documentation"
        elif [ "$change_count" -eq 0 ]; then
            category="Research"
        fi

        # Build summary
        if [ "$change_count" -gt 0 ]; then
            # Get first changed file's basename for context
            first_file=$(echo "$all_changes" | head -1 | xargs basename 2>/dev/null)
            if [ "$change_count" -eq 1 ]; then
                file_summary="$first_file"
            else
                file_summary="$first_file +$((change_count - 1)) more"
            fi
        else
            file_summary="No file changes"
        fi
    fi

    # Set Stop event message
    title="$category Complete"
    body="$file_summary"
    notification_type="task_complete"
else
    # ============================================
    # Handle Notification Event
    # ============================================
    echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | Starting notification handler" >> "$DEBUG_LOG"

    # Parse notification fields
    message=$(json_get "$input_json" "message" "")
    notification_type=$(json_get "$input_json" "notification_type" "")
    title=$(json_get "$input_json" "title" "Claude Code")
    body=$(json_get "$input_json" "body" "")

    echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | parsed: type=$notification_type title='${title:0:30}' body='${body:0:30}'" >> "$DEBUG_LOG"

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
    # Method 1: notification_type is already permission_prompt (from Claude Code)
    # Method 2: Text contains permission-related keywords
    if [ "$notification_type" = "permission_prompt" ] || echo "$combined" | grep -qi "permission\|needs your permission\|needs your attention"; then
        # This IS actionable - set type and continue
        echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | PERMISSION detected, proceeding" >> "$DEBUG_LOG"
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
        echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | SKIPPED - waiting for input (handled by ask-user.sh)" >> "$DEBUG_LOG"
        exit 0
    elif [ "$notification_type" = "idle_prompt" ]; then
        # Idle prompt - also actionable, user should be notified
        echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | IDLE_PROMPT detected, proceeding" >> "$DEBUG_LOG"
        title="Claude Code"
        body="Waiting for your input"
    else
        # Not actionable - skip unknown notification types
        echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | SKIPPED - not actionable (type=$notification_type)" >> "$DEBUG_LOG"
        exit 0
    fi

    # Defaults
    [ -z "$title" ] && title="Claude Code"
    [ -z "$body" ] && body="Notification"

    echo "$(date '+%Y-%m-%d %H:%M:%S') | NOTIFY | Final: title='${title:0:40}' body='${body:0:40}'" >> "$DEBUG_LOG"

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
