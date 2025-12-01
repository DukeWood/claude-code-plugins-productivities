#!/bin/bash
# ============================================
# Claude Code → Slack: PreToolUse Hook
# Captures tool details for permission notifications.
# Actual Slack notifications are sent by notify.sh.
# ============================================

# Load libraries
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/lib.sh"
setup_path

# PreToolUse MUST always output a decision FIRST
echo '{"decision": "allow"}'

# ============================================
# Capture tool details for permission notifications
# ============================================
TOOL_REQUEST_FILE="$HOME/.claude/config/last_tool_request.json"
mkdir -p "$(dirname "$TOOL_REQUEST_FILE")" 2>/dev/null

python=$(find_python)
input_json=$(cat)

# Save tool details to temp file (notify.sh will read this)
echo "$input_json" | $python -c "
import json
import sys
from datetime import datetime

try:
    data = json.load(sys.stdin)
    tool_request = {
        'tool_name': data.get('tool_name', 'Unknown'),
        'tool_input': data.get('tool_input', {}),
        'cwd': data.get('cwd', ''),
        'timestamp': datetime.now().isoformat()
    }
    with open('$TOOL_REQUEST_FILE', 'w') as f:
        json.dump(tool_request, f)
except:
    pass
" 2>/dev/null

exit 0
