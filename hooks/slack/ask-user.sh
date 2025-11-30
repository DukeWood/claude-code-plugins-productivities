#!/bin/bash
# ============================================
# Claude Code → Slack: PostToolUse Hook
# Notifies when AskUserQuestion is used
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

tool_name=$(json_get "$input_json" "tool_name" "Unknown")
cwd=$(json_get "$input_json" "cwd" "Unknown")

# Only handle AskUserQuestion
if [ "$tool_name" != "AskUserQuestion" ]; then
    exit 0
fi

# ============================================
# Load Config (exit if not configured)
# ============================================
if ! load_slack_config; then
    exit 0
fi

# ============================================
# Set idle state for Stop event
# ============================================
echo '{"was_idle": true}' > "$STATE_FILE"

# ============================================
# Extract question details
# ============================================
questions=$($python -c "
import json, sys
try:
    d = json.load(sys.stdin)
    tool_input = d.get('tool_input', {})
    questions = tool_input.get('questions', [])
    if questions:
        q = questions[0]
        print(q.get('question', 'Question pending'))
    else:
        print('Awaiting your response')
except:
    print('Awaiting your response')
" <<< "$input_json" 2>/dev/null)

title="Input Required"
body="${questions:-Awaiting your response}"

# ============================================
# Get Context
# ============================================
detect_terminal "$cwd"
get_project_info "$cwd"

# Set notification style
emoji="📝"
ntype="Input Required"
color="#ECB22E"  # Yellow
export emoji ntype color

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
