#!/bin/bash
# PATH must be set BEFORE any commands (hooks run in minimal environment)
export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"

# Get the hooks/slack directory
ENRICHERS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Source the shared library for robust terminal detection
# This provides detect_terminal() which handles tmux, iTerm2, VS Code, etc.
source "$ENRICHERS_DIR/../../../lib/common.sh"

# Get project name from git or directory
get_project_name() {
  local cwd="${1:-$PWD}"

  # Try git repo name
  if git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    basename "$(git -C "$cwd" rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null || basename "$cwd"
  else
    # Fallback to directory name
    basename "$cwd"
  fi
}

# Get git branch only
get_git_branch() {
  local cwd="${1:-$PWD}"

  if ! git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo ""
    return
  fi

  git -C "$cwd" branch --show-current 2>/dev/null || echo "detached"
}

# Get git status summary
get_git_status() {
  local cwd="${1:-$PWD}"

  if ! git -C "$cwd" rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo ""
    return
  fi

  local branch=$(git -C "$cwd" branch --show-current 2>/dev/null || echo "detached")
  local status=$(git -C "$cwd" status --porcelain 2>/dev/null)

  local staged=$(echo "$status" | grep -c '^[MADRC]' 2>/dev/null || echo 0)
  local modified=$(echo "$status" | grep -c '^ M' 2>/dev/null || echo 0)
  local untracked=$(echo "$status" | grep -c '^??' 2>/dev/null || echo 0)

  echo "$branch | S:$staged M:$modified U:$untracked"
}

# Get terminal info (uses detect_terminal from lib/common.sh)
get_terminal_info() {
  local cwd="${1:-$PWD}"

  # Use the robust detect_terminal() from lib/common.sh
  detect_terminal "$cwd"

  # Format the output for Slack display
  if [ -n "$terminal_info" ]; then
    echo "$terminal_type \`$terminal_info\`"
  else
    echo "$terminal_type"
  fi
}

# Get terminal switch command (uses detect_terminal from lib/common.sh)
get_switch_command() {
  local cwd="${1:-$PWD}"

  # Use the robust detect_terminal() from lib/common.sh
  # This sets: terminal_type, terminal_info, switch_command
  detect_terminal "$cwd"

  echo "$switch_command"
}

# Get token usage from session transcript
get_token_usage() {
  local session_id="$1"
  local cwd="${2:-$PWD}"

  # Find transcript file
  local cwd_escaped=$(echo "$cwd" | sed 's/\//_/g' | sed 's/^_//')
  local transcript_file=$(find "$HOME/.claude/projects" -name "${session_id}.jsonl" 2>/dev/null | head -n 1)

  if [ ! -f "$transcript_file" ]; then
    echo "N/A"
    return
  fi

  # Parse token usage with Python
  python3 -c "
import json
import sys

total_input = 0
total_output = 0
total_cache_read = 0

try:
    with open('$transcript_file') as f:
        for line in f:
            try:
                data = json.loads(line)
                if 'message' in data and 'usage' in data['message']:
                    u = data['message']['usage']
                    total_input += u.get('input_tokens', 0)
                    total_output += u.get('output_tokens', 0)
                    total_cache_read += u.get('cache_read_input_tokens', 0)
            except:
                pass

    # Include cache reads in input
    total_input += total_cache_read

    # Format with K suffix
    def format_tokens(n):
        if n >= 1000:
            return f'{n/1000:.1f}K'
        return str(n)

    print(f'{format_tokens(total_input)} in / {format_tokens(total_output)} out')
except:
    print('N/A')
" 2>/dev/null || echo "N/A"
}

# Get task description from last user message
get_task_description() {
  local session_id="$1"
  local cwd="${2:-$PWD}"

  # Find transcript file
  local transcript_file=$(find "$HOME/.claude/projects" -name "${session_id}.jsonl" 2>/dev/null | head -n 1)

  if [ ! -f "$transcript_file" ]; then
    echo "Task completed"
    return
  fi

  # Get last user message
  python3 -c "
import json

try:
    with open('$transcript_file') as f:
        lines = f.readlines()

    # Find last user message
    for line in reversed(lines):
        try:
            data = json.loads(line)
            if 'message' in data and data['message']['role'] == 'user':
                content = data['message']['content']
                if isinstance(content, list):
                    text = ' '.join(block.get('text', '') for block in content if block.get('type') == 'text')
                else:
                    text = content

                # Truncate if too long
                if len(text) > 150:
                    text = text[:147] + '...'

                print(text)
                break
        except:
            pass
    else:
        print('Task completed')
except:
    print('Task completed')
" 2>/dev/null || echo "Task completed"
}

# Format tool-specific details for Slack
format_tool_details() {
  local tool_name="$1"
  local tool_input="$2"

  case "$tool_name" in
    Edit|Write|Read)
      local file_path=$(echo "$tool_input" | jq -r '.file_path // empty' 2>/dev/null)
      if [ -n "$file_path" ]; then
        local filename=$(basename "$file_path")
        local dir=$(dirname "$file_path")
        # Shorten path if too long
        if [ ${#dir} -gt 50 ]; then
          dir="...${dir:(-47)}"
        fi
        echo "**${tool_name} Permission**\n📄 File: $filename\n📁 Path: $dir"
      else
        echo "**${tool_name} Permission**\nWaiting for approval"
      fi
      ;;
    Bash)
      local command=$(echo "$tool_input" | jq -r '.command // empty' 2>/dev/null | head -c 100)
      if [ -n "$command" ]; then
        echo "**Bash Permission**\n💻 Command: \`$command\`"
      else
        echo "**Bash Permission**\nWaiting for approval"
      fi
      ;;
    WebFetch)
      local url=$(echo "$tool_input" | jq -r '.url // empty' 2>/dev/null)
      if [ -n "$url" ]; then
        echo "**Web Access Permission**\n🌐 URL: $url"
      else
        echo "**Web Access Permission**\nWaiting for approval"
      fi
      ;;
    Task)
      local subagent=$(echo "$tool_input" | jq -r '.subagent_type // empty' 2>/dev/null)
      local desc=$(echo "$tool_input" | jq -r '.description // empty' 2>/dev/null | head -c 100)
      if [ -n "$subagent" ]; then
        echo "**Agent Task Permission**\n🤖 Agent: $subagent\n📋 Task: $desc"
      else
        echo "**Task Permission**\nWaiting for approval"
      fi
      ;;
    *)
      echo "**${tool_name} Permission**\n⚠️ Waiting for approval"
      ;;
  esac
}

# Get session ID last 4 characters for serial number
get_session_serial() {
  local session_id="$1"
  echo "${session_id:(-4)}"
}

# Get current timestamp in readable format
get_timestamp() {
  date "+%I:%M %p"
}

# Detect if running in tmux (returns "true" or "false")
detect_tmux() {
  local cwd="${1:-$PWD}"

  # Use detect_terminal from lib/common.sh
  detect_terminal "$cwd"

  # Check if terminal_type contains "tmux"
  if [[ "$terminal_type" == *"tmux"* ]]; then
    echo "true"
  else
    echo "false"
  fi
}
