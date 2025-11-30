# Claude Code Plugins & Productivities

Personal productivity tools, hooks, agents, commands, and skills for Claude Code. Designed for solopreneurs and indie developers who want to extend Claude Code with useful customizations.

## Quick Install

```bash
git clone https://github.com/DukeWood/claude-code-plugins-productivities.git
cd claude-code-plugins-productivities
./install.sh
```

The installer lets you choose which components to install:
- Slack Notifications (hooks)
- Charlie - Thinking Partner (agent)
- DevJournal & DevReview (commands)

## What's Included

### 1. Slack Notification Hooks

Get Slack notifications when Claude Code:
- Requests tool permissions (PreToolUse)
- Completes tasks (Notification/Stop events)

**Features:**
- Terminal detection (iTerm2, VS Code, Terminal.app, tmux)
- Quick switch commands to jump back to your session
- tmux session:window.pane info for exact pane targeting
- Project context and serial numbers for tracking

### 2. Charlie - Socratic Thinking Partner

An AI agent that helps you think through complex problems via Socratic dialogue.

**Features:**
- Questions over answers - helps you think, doesn't solve for you
- Progressive note-taking throughout conversations
- Topic memory across sessions
- Framework integration (First Principles, Jobs-to-be-Done, etc.)

**Usage:**
```
/charlie                              # Open-ended thinking session
/charlie Should I take this job?      # Session with context
Charlie, help me think through...     # Direct invocation
```

### 3. DevJournal & DevReview

Track your development sessions and analyze patterns over time.

**DevJournal** - Log sessions with automatic git detection:
```
/devjournal my-project
```
- Detects commits, files changed, lines added/deleted
- Prompts for approaches tried, failures, insights
- Updates running statistics

**DevReview** - Analyze patterns from logged sessions:
```
/devreview my-project        # Last 30 days
/devreview my-project 7      # Last 7 days
```
- Identifies themes, blockers, effective strategies
- Shows velocity trends
- Generates actionable recommendations

## Structure

```
claude-code-plugins-productivities/
├── install.sh                      # Interactive installer
├── README.md
│
├── lib/
│   └── common.sh                   # Shared bash functions
│
├── hooks/
│   └── slack/
│       ├── lib.sh                  # Slack-specific functions
│       ├── notify.sh               # Notification/Stop hook
│       └── permission.sh           # PreToolUse hook
│
├── agents/
│   └── charlie/
│       ├── agent.md                # Agent definition
│       └── README.md               # Usage docs
│
├── commands/
│   ├── charlie/
│   │   ├── command.md              # /charlie command
│   │   └── README.md
│   ├── devjournal/
│   │   ├── command.md              # /devjournal command
│   │   └── README.md
│   └── devreview/
│       ├── command.md              # /devreview command
│       └── README.md
│
├── templates/
│   └── dev-journal.md              # Journal template
│
├── config/
│   └── templates/
│       ├── slack-config.template.json
│       └── devjournal-config.template.json
│
└── docs/
    ├── slack-notifications-cookbook.md
    ├── charlie-guide.md
    └── devjournal-guide.md
```

## How It Works

The installer creates symlinks from `~/.claude/` to this repo:

```
~/.claude/
├── agents/charlie.md      → repo/agents/charlie/agent.md
├── commands/charlie.md    → repo/commands/charlie/command.md
├── commands/devjournal.md → repo/commands/devjournal/command.md
├── commands/devreview.md  → repo/commands/devreview/command.md
└── hooks.json             # Points to repo scripts
```

This means `git pull` updates everything automatically.

## Configuration

### Slack Webhook

Stored in `~/.claude/config/slack-config.json` (not tracked in git):

```json
{
    "webhook_url": "https://hooks.slack.com/services/...",
    "enabled": true
}
```

### Charlie Notes

Default storage: `~/.claude/charlie-sessions/`

Configure in `~/.claude/charlie-config.md`:
```yaml
storage:
  default_path: "~/Documents/Charlie Thinking/"
behavior:
  memory_default: "ask"
```

### DevJournal Location

Journals stored in: `~/DevJournals/{project} - Dev Log.md`

## Updating

```bash
cd /path/to/claude-code-plugins-productivities
git pull
```

Symlinks mean updates take effect immediately.

## Notification Templates

### PreToolUse (Permission Prompts)

```
┌─────────────────────────────────────────────────────────────┐
│ 💻 *Bash Command* | `Bash` | Terminal.app+tmux             │
│ ⏳ *project* → `session:0.0 (window)` | 👉 `tmux attach...` │
├─────────────────────────────────────────────────────────────┤
│ `project-1130-001` | 09:15:23 | ```command preview```      │
└─────────────────────────────────────────────────────────────┘
```

### Notification/Stop (Task Events)

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

## Documentation

- [Slack Notifications Cookbook](docs/slack-notifications-cookbook.md) - Setup, customization, troubleshooting
- [Charlie Guide](docs/charlie-guide.md) - Socratic thinking partner usage
- [DevJournal Guide](docs/devjournal-guide.md) - Development logging workflow

## Supported Terminals

| Terminal | Detection | Switch Command |
|----------|-----------|----------------|
| tmux | `$TMUX` | `tmux attach -t session:window.pane` |
| iTerm2 | `$ITERM_SESSION_ID` | `open -a iTerm` |
| VS Code | `$TERM_PROGRAM=vscode` | `code {cwd}` |
| Terminal.app | `$TERM_PROGRAM=Apple_Terminal` | `open -a Terminal` |

## Requirements

- Claude Code installed (`~/.claude` directory exists)
- Python 3 (for JSON manipulation in installer)
- macOS (tested on Apple Silicon and Intel)

## License

MIT
