#!/bin/bash
# ============================================
# Claude Code Productivities - Shared Library
# Common functions used across all components
# ============================================

# Determine script's directory for relative sourcing
PRODUCTIVITIES_ROOT="${PRODUCTIVITIES_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"

# ============================================
# Path Setup (portable across Intel/Apple Silicon Macs)
# ============================================
setup_path() {
    export PATH="/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:$PATH"
}

# ============================================
# Find Python3 (portable)
# ============================================
find_python() {
    command -v python3 2>/dev/null || echo "/usr/bin/python3"
}

# ============================================
# JSON Parsing Helper
# ============================================
json_get() {
    local json="$1"
    local key="$2"
    local default="${3:-}"
    local python=$(find_python)

    local result=$($python -c "
import json, sys
try:
    d = json.loads(sys.stdin.read())
    print(d.get('$key', '$default'))
except:
    print('$default')
" <<< "$json" 2>/dev/null)

    echo "${result:-$default}"
}

# ============================================
# Terminal Detection
# Sets: terminal_type, terminal_info, switch_command
# ============================================
detect_terminal() {
    local cwd="${1:-$PWD}"

    terminal_type="Terminal"
    terminal_info=""
    switch_command=""
    local host_terminal=""

    # 1. Detect host terminal (most specific first)
    if [ -n "$ITERM_SESSION_ID" ]; then
        host_terminal="iTerm2"
        switch_command="open -a iTerm"
    elif [ "$TERM_PROGRAM" = "vscode" ] || [ -n "$VSCODE_INJECTION" ]; then
        host_terminal="VS Code"
        switch_command="code \"$cwd\""
    elif echo "$cwd" | grep -qi "obsidian"; then
        host_terminal="Obsidian"
        switch_command="open -a Obsidian"
    elif [ "$TERM_PROGRAM" = "Apple_Terminal" ]; then
        host_terminal="Terminal.app"
        switch_command="open -a Terminal"
    fi

    # 2. Check for tmux (can run inside any host terminal)
    local tmux_info=""
    local confirmed_tmux="false"

    if [ -n "$TMUX" ]; then
        # Running inside tmux - use display-message (confirmed tmux session)
        confirmed_tmux="true"
        local tmux_session=$(tmux display-message -p '#{session_name}' 2>/dev/null)
        local tmux_window_index=$(tmux display-message -p '#{window_index}' 2>/dev/null)
        local tmux_window_name=$(tmux display-message -p '#{window_name}' 2>/dev/null)
        local tmux_pane_index=$(tmux display-message -p '#{pane_index}' 2>/dev/null)
        if [ -n "$tmux_session" ]; then
            tmux_info="${tmux_session}:${tmux_window_index}.${tmux_pane_index}|${tmux_window_name}"
        fi
    elif command -v tmux &>/dev/null && [ -z "$host_terminal" ]; then
        # Running outside tmux AND no host terminal detected - likely a tmux hook subprocess
        # Find pane by cwd (only when we don't know the actual terminal)
        confirmed_tmux="true"
        tmux_info=$(tmux list-panes -a -F '#{session_name}:#{window_index}.#{pane_index}|#{window_name}|#{pane_current_path}|#{pane_active}' 2>/dev/null | \
            awk -F'|' -v cwd="$cwd" '$3 == cwd {print $1"|"$2; exit}')
    fi

    if [ -n "$tmux_info" ] && [ "$confirmed_tmux" = "true" ]; then
        local tmux_target=$(echo "$tmux_info" | cut -d'|' -f1)
        local tmux_window_name=$(echo "$tmux_info" | cut -d'|' -f2)

        if [ -n "$host_terminal" ]; then
            terminal_type="${host_terminal}+tmux"
        else
            terminal_type="tmux"
        fi
        # Format: session:window.pane (window_name)
        terminal_info="${tmux_target} (${tmux_window_name})"
        switch_command="tmux attach -t ${tmux_target}"
    elif [ -n "$host_terminal" ]; then
        terminal_type="$host_terminal"
    fi

    # 3. Claude Code indicator
    if [ "$CLAUDECODE" = "1" ] || [ -n "$CLAUDE_CODE_ENTRYPOINT" ]; then
        terminal_info="${terminal_info:+$terminal_info }(Claude)"
    fi

    # 4. Fallback for terminal_info (last 2 path components)
    if [ -z "$terminal_info" ]; then
        terminal_info=$(echo "$cwd" | awk -F/ '{if(NF>2) print $(NF-1)"/"$NF; else print $NF}')
    fi

    # 5. Fallback for switch_command
    if [ -z "$switch_command" ] && [ "$cwd" != "Unknown" ]; then
        switch_command="code \"$cwd\""
    fi

    # Export for use by caller
    export terminal_type terminal_info switch_command
}

# ============================================
# Project Info & Serial Number
# Sets: project, project_safe, timestamp, serial_number
# ============================================
get_project_info() {
    local cwd="${1:-$PWD}"
    local sn_dir="$HOME/.claude/notification-counters"

    mkdir -p "$sn_dir" 2>/dev/null

    project=$(basename "$cwd" 2>/dev/null || echo "Unknown")
    [ -z "$project" ] && project="Unknown"

    project_safe=$(echo "$project" | tr ' ' '_' | tr -cd '[:alnum:]_-')
    [ -z "$project_safe" ] && project_safe="Unknown"

    timestamp=$(date "+%H:%M:%S")
    local date_short=$(date "+%m%d")
    local sn_file="$sn_dir/${project_safe}_${date_short}.count"

    local counter=$(cat "$sn_file" 2>/dev/null || echo "0")
    counter=$((counter + 1))
    echo "$counter" > "$sn_file"

    serial_number="${project}-${date_short}-$(printf '%03d' $counter)"

    export project project_safe timestamp serial_number
}

# ============================================
# Debug Logging
# ============================================
debug_log() {
    local message="$1"
    local log_file="${DEBUG_LOG:-$HOME/.claude/productivities-debug.log}"

    if [ "${DEBUG:-0}" = "1" ]; then
        echo "$(date '+%Y-%m-%d %H:%M:%S'): $message" >> "$log_file"
    fi
}
