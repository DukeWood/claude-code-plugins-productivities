# Charlie Guide - Socratic Thinking Partner

A comprehensive guide to using Charlie, your AI thinking partner for exploring complex problems and decisions.

## Table of Contents

1. [What is Charlie?](#what-is-charlie)
2. [Getting Started](#getting-started)
3. [Invocation Patterns](#invocation-patterns)
4. [Session Examples](#session-examples)
5. [Note-Taking System](#note-taking-system)
6. [Memory & Context](#memory--context)
7. [Customization](#customization)
8. [Tips for Better Sessions](#tips-for-better-sessions)
9. [FAQ](#faq)

---

## What is Charlie?

Charlie is a Socratic thinking partner - an AI that helps you explore complex problems through dialogue rather than giving you answers.

**Philosophy**: The best insights come from your own thinking. Charlie's role is to ask the right questions, surface hidden assumptions, and help you see patterns you might miss.

**Core Principles**:
- Questions over answers
- Exploration over solutions
- Your thinking, not Charlie's opinions
- Progressive note-taking throughout

---

## Getting Started

### Installation

Charlie is installed as part of the claude-code-plugins-productivities package:

```bash
git clone https://github.com/DukeWood/claude-code-plugins-productivities.git
cd claude-code-plugins-productivities
./install.sh
```

### First Session

On your first invocation, Charlie will ask about note storage preferences:

```
Where should I keep your thinking notes by default?
1. Your Obsidian vault
2. A dedicated folder: ~/Documents/Charlie Thinking/
3. Project-specific: ./thinking-notes/
4. Custom path
```

Your choice becomes the default for future sessions.

---

## Invocation Patterns

Charlie **only** activates on explicit invocation. This prevents interference with normal Claude Code usage.

### Direct Address

```
Charlie, I'm thinking about...
Hey Charlie, let's explore...
@charlie what about...
Charlie?! help me with...
```

### Slash Command

```
/charlie
/charlie Should I pivot to enterprise?
/charlie pricing strategy decisions
```

### In Context

```
[After discussing a problem]
...so that's the situation. @charlie help me think through this.
```

---

## Session Examples

### Career Decision

```
You: Charlie, I'm considering leaving my stable job to start a company.

Charlie: That's a significant crossroads. Before we explore the options,
what's making this decision feel urgent right now?

You: I've been thinking about it for years, but now I have some savings
and a product idea.

Charlie: "Years" is interesting. What's been holding you back until now,
and what's changed?

You: Fear of failure mostly. But I realized I'm more afraid of regret.

Charlie: That's a powerful reframe - from fear of failure to fear of
regret. What does "failure" look like in each scenario for you?
```

### Product Strategy

```
You: /charlie We're debating adding a free tier to our SaaS

Charlie: A classic tension. What problem are you hoping the free tier
would solve?

You: More users in the funnel, hopefully converting to paid.

Charlie: "Hopefully" carries a lot of weight there. What would need to
be true for free users to convert? And what happens if they don't?

You: I guess... we'd have costs without revenue. And our paid users
might downgrade.

Charlie: Now we're getting somewhere. What's the real question here -
is it about growth strategy, or about confidence in your paid value
proposition?
```

### Technical Architecture

```
You: @charlie I'm stuck on whether to use microservices or a monolith

Charlie: Before we explore the architectures, what's driving this
decision now? Is this a new project or a refactor?

You: New project, but I've been burned by microservices complexity before.

Charlie: "Burned" suggests some specific pain. What specifically went
wrong, and what would have prevented it?
```

---

## Note-Taking System

Charlie doesn't just ask questions - it captures insights as they emerge.

### Progressive Notes

Every 5-7 exchanges, Charlie writes to a working session file:
`~/.claude/charlie-sessions/active-[timestamp].md`

This ensures insights aren't lost if you close the session unexpectedly.

### Note Structure

```markdown
# Career Crossroads - Thinking Session
*Date: 2024-03-15 | Duration: ~45min | Project: Personal*

## Key Breakthrough
> "I'm not afraid of failure - I'm afraid of regret. The stable job
> is actually the riskier choice for my long-term fulfillment."

## Insights Crystallized
- **Fear reframe**: Moving from "fear of failure" to "fear of regret"
  changes the risk calculation entirely
- **Timing clarity**: The "right time" is when costs of inaction
  exceed costs of action

## Questions Opened
- [ ] What's the minimum viable runway needed?
- [ ] Who are 3 people who've made this transition successfully?

## Decisions & Leanings
- **Leaning toward:** Starting the company, but with a safety net
- **Key trade-off:** Financial security vs. fulfillment

## Action Threads
- [ ] Calculate 18-month runway requirements
- [ ] Talk to Sarah about her startup transition
- [ ] Draft a 6-month "exploration period" plan

## Session Trajectory
Started with classic pro/con framing but quickly moved to the
underlying fear. The reframe from failure-fear to regret-fear
was the breakthrough. By end, the question shifted from "should I?"
to "how do I do this responsibly?"

---
*Captured by Charlie - Socratic Thinking Partner*
```

### End of Session

At conversation end, Charlie asks:
- "Should I merge this into an existing note or create a new file?"
- "I'll save this to [default location]. Sound good?"

You can override: "Save to ~/Projects/startup/thinking.md"

---

## Memory & Context

Charlie maintains a topic index to build on previous thinking sessions.

### How Memory Works

1. **Topic Index**: `~/.claude/charlie-index.md` maps topics to note files
2. **Session Start**: Charlie checks for related previous sessions
3. **Cross-Session**: "That reminds me of our [topic] discussion..."
4. **Session End**: Updates index with new/modified files

### Memory Phrases

| Say This | Charlie Does |
|----------|-------------|
| "Let's start fresh" | Ignores previous sessions |
| "Remind me what we discussed about X" | Reviews relevant notes |
| "Build on our last conversation" | Continues from previous session |

---

## Customization

### Configuration File

Edit `~/.claude/charlie-config.md`:

```yaml
---
storage:
  default_path: "~/Documents/Charlie Thinking/"
  project_overrides:
    torlyAI: "~/Projects/torly/thinking/"
behavior:
  memory_default: "ask"  # ask, always, never
  note_style: "structured"
  framework_frequency: "moderate"
---
```

### Storage Options

| Setting | Behavior |
|---------|----------|
| `ask` | Prompts before accessing previous notes |
| `always` | Auto-loads related sessions |
| `never` | Each session is independent |

---

## Tips for Better Sessions

### 1. Be Specific

**Less useful**:
> "Should I hire?"

**More useful**:
> "I'm considering hiring a junior developer to help with the backlog,
> but I'm worried about the time investment in training vs. the
> productivity gain. We have 3 months of runway."

### 2. Share Context

Charlie can't read your mind. Explain:
- What you've already tried
- What constraints exist
- Why this matters now

### 3. Think Out Loud

Don't wait for perfect thoughts. Messy thinking is productive:
> "I don't know if this makes sense, but..."
> "I might be overthinking this, but..."

### 4. Let Topics Evolve

Sessions often reveal deeper questions. If Charlie asks "is the real question X?", consider it - the surface problem may not be the core problem.

### 5. Review Notes Later

Charlie's notes are designed to restart your thinking. Come back to them when you have fresh perspective.

---

## FAQ

### Q: Will Charlie give me answers if I really need them?

**A:** No. Charlie will help you find your own answers. If you explicitly need information or solutions, use regular Claude Code instead.

### Q: Can I use Charlie for technical decisions?

**A:** Absolutely. Charlie is great for architecture decisions, technology choices, and system design - anything where there are tradeoffs to explore.

### Q: How long should a session be?

**A:** Most productive sessions are 15-45 minutes. Charlie will checkpoint at ~20 exchanges and offer to summarize.

### Q: What if I need to stop mid-session?

**A:** Charlie auto-saves to `~/.claude/charlie-sessions/`. Next time you invoke Charlie, it will offer to resume the abandoned session.

### Q: Can multiple people use the same Charlie setup?

**A:** The configuration and notes are per-user (`~/.claude/`). Share the repo, but each person has their own thinking history.

---

## File Locations

| Purpose | Location |
|---------|----------|
| Agent definition | `~/.claude/agents/charlie.md` (symlink) |
| Command | `~/.claude/commands/charlie.md` (symlink) |
| Configuration | `~/.claude/charlie-config.md` |
| Topic index | `~/.claude/charlie-index.md` |
| Session files | `~/.claude/charlie-sessions/` |

---

## Support

- **Issues**: [GitHub Issues](https://github.com/DukeWood/claude-code-plugins-productivities/issues)
- **Updates**: `cd /path/to/repo && git pull`
