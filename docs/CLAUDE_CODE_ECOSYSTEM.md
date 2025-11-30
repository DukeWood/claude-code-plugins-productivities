# Claude Code Ecosystem - Complete Reference Guide

This document provides a comprehensive map of your Claude Code setup, including all plugins, agents, commands, hooks, skills, and how to use them effectively.

---

## Quick Start

| I want to... | Do this |
|--------------|---------|
| Think through a decision | `Charlie, help me with...` or `/charlie` |
| Log my dev session | `/devjournal my-project` |
| Review my dev patterns | `/devreview my-project 30` |
| Commit my changes | `/commit` |
| Commit + Push + PR | `/commit-push-pr` |
| Review a PR | `/code-review:code-review` |
| Build a new feature | `/feature-dev` |
| Create frontend UI | Ask for UI work (frontend-design auto-activates) |
| Create a hook | `/hookify` |
| Build a new plugin | `/plugin-dev:create-plugin` |

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           CLAUDE CODE ECOSYSTEM                                 │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ~/.claude/ (Global Config)                                                     │
│  ├── CLAUDE.md              # Your global instructions                          │
│  ├── hooks.json             # Event hooks (Slack notifications)                 │
│  ├── agents/                # Custom agents (Charlie)                           │
│  ├── commands/              # Custom slash commands                             │
│  ├── templates/             # File templates                                    │
│  └── plugins/marketplaces/  # Installed plugins                                 │
│                                                                                 │
│  ~/AI/AI_Coding/Repositories/                                                   │
│  ├── claude-code-plugins-productivities/   # Your shareable tools               │
│  ├── compounding-integrated-github-projects-plugin/  # Your custom plugin       │
│  ├── Skill_Creators/                       # Skill creation tool (forked)       │
│  └── torlyAI/                              # Your project                       │
│                                                                                 │
└─────────────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Plugins

Plugins extend Claude Code with new capabilities, agents, commands, and hooks.

### Official Anthropic Plugins

These come from the `claude-code-plugins` marketplace maintained by Anthropic.

#### commit-commands
**Purpose**: Streamline git workflow

| Command | What it does |
|---------|--------------|
| `/commit` | Create a git commit with AI-generated message |
| `/commit-push-pr` | Commit, push, and open a pull request |
| `/clean_gone` | Clean up local branches deleted on remote |

**Example**:
```
/commit
# Claude analyzes changes, generates commit message, commits
```

---

#### feature-dev
**Purpose**: Comprehensive feature development workflow with specialized agents

| Command | What it does |
|---------|--------------|
| `/feature-dev [description]` | Guided feature development |

**Agents provided**:
- `code-explorer` - Analyzes existing codebase
- `code-architect` - Designs feature architecture
- `code-reviewer` - Reviews code quality

**Example**:
```
/feature-dev Add user authentication with JWT tokens
# Launches guided workflow: explore → design → implement → review
```

---

#### frontend-design
**Purpose**: Create distinctive, production-grade frontend interfaces

**How to use**: Simply ask for UI/UX work - the skill auto-activates.

**Example**:
```
Create a login page with a modern dark theme
# frontend-design skill provides design guidance
```

---

#### explanatory-output-style
**Purpose**: Adds educational insights about implementation choices

**How it works**: Auto-active. Adds `★ Insight` blocks explaining why code works.

**Example output**:
```
★ Insight ─────────────────────────────────────
- Using useCallback here prevents unnecessary re-renders
- The dependency array ensures the function updates when deps change
─────────────────────────────────────────────────
```

---

#### learning-output-style
**Purpose**: Interactive learning mode that requests your input at decision points

**How it works**: Auto-active. Instead of writing everything, Claude asks you to write 5-10 lines of meaningful code at key decision points.

---

#### security-guidance
**Purpose**: Warns about security issues when editing files

**How it works**: Auto-active hook. Checks for:
- Command injection
- XSS vulnerabilities
- Unsafe code patterns

---

#### hookify
**Purpose**: Create hooks to prevent unwanted behaviors

| Command | What it does |
|---------|--------------|
| `/hookify` | Analyze conversation for behaviors to prevent |
| `/hookify:list` | List all configured rules |
| `/hookify:configure` | Enable/disable rules |
| `/hookify:help` | Get help |

**Example**:
```
/hookify
# Claude analyzes recent conversation, suggests hooks for mistakes it made
```

---

#### plugin-dev
**Purpose**: Develop Claude Code plugins

| Command | What it does |
|---------|--------------|
| `/plugin-dev:create-plugin [description]` | Guided plugin creation |

**Skills provided**:
- `skill-development` - Create skills
- `command-development` - Create slash commands
- `hook-development` - Create hooks
- `agent-development` - Create agents

**Example**:
```
/plugin-dev:create-plugin A plugin that sends Discord notifications
```

---

#### pr-review-toolkit
**Purpose**: Comprehensive PR review with specialized agents

| Command | What it does |
|---------|--------------|
| `/pr-review-toolkit:review-pr [aspects]` | Review PR with multiple agents |

**Agents provided**:
- `code-reviewer` - Code quality and conventions
- `silent-failure-hunter` - Error handling issues
- `code-simplifier` - Simplification opportunities
- `comment-analyzer` - Comment accuracy
- `pr-test-analyzer` - Test coverage
- `type-design-analyzer` - Type design quality

**Example**:
```
/pr-review-toolkit:review-pr
# Runs specialized agents to review your PR
```

---

#### code-review
**Purpose**: Automated code review for pull requests

| Command | What it does |
|---------|--------------|
| `/code-review:code-review` | Review a PR |

---

#### ralph-wiggum
**Purpose**: Continuous self-referential AI loops for iterative development

| Command | What it does |
|---------|--------------|
| `/ralph-wiggum:ralph-loop PROMPT` | Start a loop with given prompt |
| `/ralph-wiggum:cancel-ralph` | Cancel active loop |
| `/ralph-wiggum:help` | Explain the technique |

**Example**:
```
/ralph-wiggum:ralph-loop "Keep improving the test coverage until it reaches 80%"
```

---

#### agent-sdk-dev
**Purpose**: Claude Agent SDK development

**Agents provided**:
- `agent-sdk-verifier-ts` - Verify TypeScript SDK apps
- `agent-sdk-verifier-py` - Verify Python SDK apps

---

### Your Custom Plugin

#### compounding-skill-seekers
**Purpose**: Compounding engineering approach + GitHub Projects integration

**Location**: `~/AI/AI_Coding/Repositories/compounding-integrated-github-projects-plugin/`

**How it works**: Installed via symlink to `~/.claude/plugins/marketplaces/skill-seekers-plugins/`

---

## 2. Agents

Agents are autonomous assistants that can be triggered for specific tasks.

### Charlie - Socratic Thinking Partner

**Purpose**: Help you think through complex problems via dialogue, not answers.

**How to invoke** (explicit invocation only):
```
Charlie, I'm trying to decide...
Hey Charlie, let's explore...
@charlie help me think through...
/charlie [topic]
```

**What Charlie does**:
- Asks questions instead of giving answers
- Takes progressive notes throughout conversation
- Remembers topics across sessions
- Uses frameworks (First Principles, Jobs-to-be-Done, etc.)

**What Charlie doesn't do**:
- Give direct answers
- Make decisions for you
- Create formal reports

**Example session**:
```
You: Charlie, I'm considering leaving my job to start a company.

Charlie: That's a significant crossroads. Before we explore the options,
what's making this decision feel urgent right now?

You: I've been thinking about it for years, but now I have savings and an idea.

Charlie: "Years" is interesting. What's been holding you back until now,
and what's changed?
```

**Notes location**: `~/.claude/charlie-sessions/`

---

## 3. Commands

Custom slash commands for specific workflows.

### /charlie

**Purpose**: Start a thinking session with Charlie

**Usage**:
```
/charlie                              # Open-ended session
/charlie Should I take this job?      # With context
/charlie pricing strategy             # Topic-focused
```

---

### /devjournal

**Purpose**: Log development sessions with automatic git detection

**Usage**:
```
/devjournal my-project
```

**What it does**:
1. Detects git activity since last session (commits, files, lines)
2. Prompts for: duration, work done, approaches tried, failures, insights
3. Adds timestamped entry to journal
4. Updates statistics

**Journal location**: `~/DevJournals/{project} - Dev Log.md`

**Example**:
```
/devjournal torlyAI

# Claude detects: 8 commits, 12 files changed (+423 -156)
# Prompts for your reflections
# Saves structured entry to journal
```

---

### /devreview

**Purpose**: Analyze development patterns from journal entries

**Usage**:
```
/devreview my-project        # Last 30 days (default)
/devreview my-project 7      # Last 7 days
/devreview my-project 90     # Last 90 days
```

**What it does**:
1. Parses all journal entries in time period
2. Calculates metrics (sessions, commits, velocity)
3. Identifies themes, blockers, effective strategies
4. Generates actionable recommendations
5. Saves report file

**Example output**:
```
Development Review: torlyAI (30 days)

ACTIVITY
   Sessions: 12 | Commits: 47 | Files: 89
   Active: 18/30 days | Velocity: Increasing

TOP THEMES
   1. Authentication system (40%)
   2. API integration (35%)

COMMON BLOCKERS
   1. OAuth token refresh complexity

EFFECTIVE STRATEGIES
   1. Test-driven development for auth flows
```

---

## 4. Hooks

Hooks run automatically on specific events.

### Slack Notifications

**Events covered**:

| Event | When | Notification |
|-------|------|--------------|
| PreToolUse | Before any tool use | Permission prompt with command preview |
| Notification | Claude sends a message | Task notification |
| Stop | Task completes | Completion notification |

**Features**:
- Terminal detection (iTerm2, VS Code, Terminal.app, tmux)
- Quick switch commands to jump back to session
- tmux session:window.pane info
- Project context and serial numbers

**Configuration**: `~/.claude/config/slack-config.json`

**To temporarily disable**: Set `"enabled": false` in config

---

## 5. Skills (Your Created Skills)

Skills are uploadable knowledge packages for Claude.ai Projects.

### obsidian-clipper-linkedin-crm

**Purpose**: Generate Obsidian Web Clipper templates for LinkedIn CRM

**How to use**: Upload `obsidian-clipper-linkedin-crm.zip` to Claude.ai Project

**Location**: `Skill_Creators/output/obsidian-clipper-linkedin-crm/`

---

### uk-innovator-founder-visa-complete

**Purpose**: Complete UK Innovator Founder Visa toolkit (7 modes)

**Modes**:
1. Assessment & Scoring
2. Business Plan Writing
3. Financial Model Building (Excel)
4. Compliance Checking
5. Pitch Deck Creation (PowerPoint)
6. Document Organization
7. Knowledge Base

**How to use**: Upload `uk-innovator-founder-visa-complete.zip` to Claude.ai Project

**Location**: `Skill_Creators/output/uk-innovator-founder-visa-complete/`

---

## 6. Templates

### dev-journal.md

**Purpose**: Template for new DevJournal files

**Location**: `~/.claude/templates/dev-journal.md`

**Used by**: `/devjournal` command when creating new project journals

---

## 7. Global Configuration

### ~/.claude/CLAUDE.md

Your global instructions that apply to all Claude Code sessions.

**Current contents**:
- GitHub Projects configuration (Project #4)
- Issue naming conventions ([REPO-type] emoji Description)
- TorlyAI design system rules

---

## File Locations Reference

```
~/.claude/
├── CLAUDE.md                    # Global instructions
├── hooks.json                   # Hook configuration
├── settings.json                # Claude Code settings
├── settings.local.json          # Local settings (not synced)
├── agents/
│   └── charlie.md               # → symlink to repo
├── commands/
│   ├── charlie.md               # → symlink to repo
│   ├── devjournal.md            # → symlink to repo
│   └── devreview.md             # → symlink to repo
├── templates/
│   └── dev-journal.md           # Journal template
├── config/
│   └── slack-config.json        # Slack webhook (secret)
├── charlie-sessions/            # Charlie's session notes
├── plugins/
│   ├── installed_plugins.json   # Plugin registry
│   └── marketplaces/
│       ├── claude-code-plugins/ # Official plugins
│       └── skill-seekers-plugins/
│           └── plugins/
│               └── compounding-skill-seekers  # → symlink

~/AI/AI_Coding/Repositories/
├── claude-code-plugins-productivities/
│   ├── hooks/slack/             # Slack notification scripts
│   ├── agents/charlie/          # Charlie agent source
│   ├── commands/                # Command sources
│   ├── templates/               # Template sources
│   └── docs/                    # Documentation
├── compounding-integrated-github-projects-plugin/
│   └── plugins/compounding-engineering/  # Your customized plugin
├── Skill_Creators/
│   └── output/                  # Your created skills
└── torlyAI/                     # Your project

~/DevJournals/                   # Development journals
```

---

## Updating

### Update Your Custom Tools
```bash
cd ~/AI/AI_Coding/Repositories/claude-code-plugins-productivities
git pull
# Symlinks mean changes take effect immediately
```

### Update Skill_Creators (External)
```bash
cd ~/AI/AI_Coding/Repositories/Skill_Creators
git fetch upstream  # If upstream remote set
git merge upstream/development
```

### Update Official Plugins
```bash
# In Claude Code
claude plugin update
```

---

## Troubleshooting

### Slack notifications not working
1. Check webhook URL: `cat ~/.claude/config/slack-config.json`
2. Test manually: `~/.../hooks/slack/permission.sh < test.json`
3. Check debug log: `cat ~/.claude/productivities-debug.log`

### Command not found
1. Check symlink exists: `ls -la ~/.claude/commands/`
2. Run installer: `cd claude-code-plugins-productivities && ./install.sh`

### Plugin not loading
1. Check installed: `cat ~/.claude/plugins/installed_plugins.json`
2. Check symlink: `ls -la ~/.claude/plugins/marketplaces/*/plugins/`

---

## Support

- **Your tools issues**: Edit source in `claude-code-plugins-productivities/`
- **Official plugins**: https://github.com/anthropics/claude-code/issues
- **Claude Code docs**: https://docs.anthropic.com/claude-code
