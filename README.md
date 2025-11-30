# Claude Code Plugins & Productivities

Personal productivity tools, hooks, commands, and skills for Claude Code.

## Quick Install

```bash
# Clone to your preferred location
git clone https://github.com/DukeWood/claude-code-plugins-productivities.git
cd claude-code-plugins-productivities
./install.sh
```

## What's Included

### Slack Notification Hooks

Get Slack notifications when Claude Code:
- Requests tool permissions (PreToolUse)
- Completes tasks (Notification/Stop events)

**Features:**
- Terminal detection (iTerm2, VS Code, Terminal.app, tmux)
- Quick switch commands to jump back to your session
- tmux session:window.pane info for exact pane targeting
- Project context and serial numbers for tracking

## Structure

```
claude-code-plugins-productivities/
├── install.sh                      # One-command installer
├── lib/
│   └── common.sh                   # Shared functions
├── hooks/
│   └── slack/
│       ├── lib.sh                  # Slack-specific functions
│       ├── notify.sh               # Notification/Stop hook
│       └── permission.sh           # PreToolUse hook
├── commands/                       # (Future) Slash commands
├── skills/                         # (Future) Skills
└── config/
    └── templates/
        └── slack-config.template.json
```

## Configuration

### Slack Webhook

1. Go to [Slack API](https://api.slack.com/apps)
2. Create or select an app
3. Enable "Incoming Webhooks"
4. Create a webhook for your notification channel
5. Run the installer - it will prompt for the URL

Config is stored in `~/.claude/config/slack-config.json` (not tracked in git).

## Updating

```bash
cd /path/to/claude-code-plugins-productivities
git pull
```

## Notification Templates

### PreToolUse (Permission Prompts) - Compact

```
┌─────────────────────────────────────────────────────────────┐
│ 💻 *Bash Command* | `Bash` | Terminal.app+tmux             │
│ ⏳ *project* → `session:0.0 (window)` | 👉 `tmux attach...` │
├─────────────────────────────────────────────────────────────┤
│ `project-1130-001` | 09:15:23 | ```command preview```      │
└─────────────────────────────────────────────────────────────┘
```

### Notification/Stop (Task Events) - Full

```
┌─────────────────────────────────────────────────────┐
│ ✅ Task Complete                                    │
├─────────────────────────────────────────────────────┤
│ `serial` | *project* | `branch` clean | 09:15:23   │
├─────────────────────────────────────────────────────┤
│ *Title*                                             │
│ Message body                                        │
├─────────────────────────────────────────────────────┤
│ *Quick Actions:* Terminal: `tmux attach -t ...`    │
└─────────────────────────────────────────────────────┘
```

### Emoji & Color Legend

| Type | Emoji | Color |
|------|-------|-------|
| Bash Command | 💻 | Red |
| File Write/Edit | ✏️ | Yellow |
| Web Access | 🌐 | Blue |
| File Read | 📖 | Green |
| Agent Task | 🤖 | Purple |
| Task Complete | ✅ | Green |
| Permission Required | 🔐 | Red |
| Awaiting Input | ⏳ | Yellow |
| Error | ❌ | Red |

## Supported Terminals

| Terminal | Detection | Switch Command |
|----------|-----------|----------------|
| tmux | `$TMUX` | `tmux attach -t session:window.pane` |
| iTerm2 | `$ITERM_SESSION_ID` | `open -a iTerm` |
| VS Code | `$TERM_PROGRAM=vscode` | `code {cwd}` |
| Terminal.app | `$TERM_PROGRAM=Apple_Terminal` | `open -a Terminal` |
| Obsidian | path contains "obsidian" | `open -a Obsidian` |

## Documentation

- [Slack Notifications Cookbook](docs/slack-notifications-cookbook.md) - Complete guide with customization, troubleshooting, and advanced usage

## License

MIT
