#!/bin/bash
# ============================================
# Claude Code → Slack: PreToolUse Hook
# Notifies on tool permission requests
# ============================================

# Load libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
setup_path

# Debug logging
DEBUG_LOG="$HOME/.claude/slack-hook-debug.log"
debug_log "PreToolUse hook triggered - PID=$$ TERM=$TERM_PROGRAM CWD=$PWD"

# ============================================
# PreToolUse MUST always output a decision
# ============================================
allow_and_exit() {
    echo '{"decision": "allow"}'
    exit 0
}

# Load Slack config (exit silently if not configured)
load_slack_config || allow_and_exit

# ============================================
# Parse Input JSON
# ============================================
python=$(find_python)
input_json=$(cat)

tool_name=$(json_get "$input_json" "tool_name" "Unknown")
tool_input=$(echo "$input_json" | $python -c "
import json, sys, textwrap
try:
    d = json.load(sys.stdin)
    inp = d.get('tool_input', {})
    s = str(inp) if isinstance(inp, dict) else str(inp)
    print(textwrap.shorten(s, width=200, placeholder='...'))
except:
    print('{}')
" 2>/dev/null)
cwd=$(json_get "$input_json" "cwd" "Unknown")

# ============================================
# Get Context
# ============================================
detect_terminal "$cwd"
get_project_info "$cwd"
get_tool_style "$tool_name"

# ============================================
# Output Decision FIRST (so Claude doesn't wait)
# ============================================
echo '{"decision": "allow"}'

# ============================================
# Send to Slack (after decision output)
# ============================================
payload=$(build_pretooluse_payload "$tool_name" "$tool_input")
send_to_slack "$payload"

exit 0
