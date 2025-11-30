# DevJournal Guide - Development Session Logging

A comprehensive guide to using DevJournal and DevReview for tracking your development progress and learning patterns.

## Table of Contents

1. [What is DevJournal?](#what-is-devjournal)
2. [Getting Started](#getting-started)
3. [Logging Sessions](#logging-sessions)
4. [Reviewing Patterns](#reviewing-patterns)
5. [Journal Structure](#journal-structure)
6. [Git Integration](#git-integration)
7. [Tips for Effective Logging](#tips-for-effective-logging)
8. [FAQ](#faq)

---

## What is DevJournal?

DevJournal is a development session logging system that helps you:

- **Track Progress**: Record what you worked on, approaches tried, and outcomes
- **Identify Patterns**: See what strategies work and what blockers recur
- **Learn Systematically**: Document insights so you don't repeat mistakes
- **Measure Velocity**: Understand your development rhythm and productivity

**Philosophy**: Learning happens through reflection. Logging forces reflection.

---

## Getting Started

### Installation

```bash
git clone https://github.com/DukeWood/claude-code-plugins-productivities.git
cd claude-code-plugins-productivities
./install.sh
```

### First Journal

The first time you run `/devjournal` for a project, you'll be prompted:

```
No journal found for 'my-project'. Let's create one.

Repository path: /Users/you/Projects/my-project
Project type: [plugin, feature, bugfix, refactor, experiment]
```

This creates: `~/DevJournals/my-project - Dev Log.md`

---

## Logging Sessions

### Basic Usage

```
/devjournal my-project
```

### What Happens

1. **Git Detection**: Reads commits, files changed, lines added/deleted since last session
2. **Interactive Prompts**: Asks about duration, work done, approaches, failures, insights
3. **Entry Creation**: Adds timestamped entry to the timeline
4. **Stats Update**: Updates running statistics

### Session Prompts

| Prompt | Purpose | Example |
|--------|---------|---------|
| Duration | How long you worked | "1-2hr" |
| What you worked on | Summary of accomplishments | "Added JWT authentication" |
| Approaches tried | Methods you experimented with | "Tried session-based first" |
| What didn't work | Failures and blockers | "Session storage too complex" |
| Key insights | Learnings from this session | "JWT simpler for mobile" |
| Next steps | What to do next | "- [ ] Add refresh tokens" |

### Example Session

```
> /devjournal torlyAI

Detecting git activity since 2024-01-18...
Found 8 commits, 12 files changed (+423 -156)

Duration: 1-2hr

What did you work on:
Added user authentication flow with JWT tokens. Set up middleware
for protected routes. Created login/logout endpoints.

Approaches tried:
Started with session-based auth, switched to JWT when I realized
we need mobile support. Tried passport.js first, then switched
to jose for simpler JWT handling.

What didn't work:
Session storage with Redis was overkill for our scale. Also
passport.js had too much magic - hard to debug when things
went wrong.

Key insights:
JWT with refresh tokens is cleaner for multi-device apps. The
jose library is much simpler than jsonwebtoken for modern use cases.

Next steps:
- [ ] Add refresh token rotation
- [ ] Implement logout on all devices
- [ ] Add rate limiting to auth endpoints

---
✓ Dev session logged (feature - 1-2hr)
📊 Stats: 8 commits, 12 files
💡 Learning: JWT with refresh tokens is cleaner for multi-device apps
```

---

## Reviewing Patterns

### Basic Review

```
/devreview my-project        # Last 30 days
/devreview my-project 7      # Last 7 days
/devreview my-project 90     # Last 90 days
```

### What You Get

**Console Summary**:
```
Development Review: torlyAI (30 days)

ACTIVITY
   Sessions: 12 | Commits: 47 | Files: 89
   Active: 18/30 days | Velocity: Increasing

TOP THEMES
   1. Authentication system (40%)
   2. API integration (35%)
   3. UI polish (25%)

COMMON BLOCKERS
   1. OAuth token refresh complexity
   2. State management edge cases

EFFECTIVE STRATEGIES
   1. Test-driven development for auth flows
   2. Breaking large features into small PRs

TOP RECOMMENDATIONS
   1. Document OAuth flow for future reference
   2. Create state management patterns guide
   3. Schedule weekly architecture reviews
```

**Saved Report**: `~/DevJournals/torlyAI - Review 2024-01-20.md`

### Review Sections

| Section | What It Analyzes |
|---------|-----------------|
| Activity Metrics | Volume of work (sessions, commits, files) |
| Frequency | How often you work on this project |
| Velocity Trends | Is productivity increasing or decreasing? |
| Themes & Patterns | What topics come up repeatedly |
| Failure Modes | Common blockers and their root causes |
| Effective Strategies | What approaches led to success |
| Learning Observations | Skills developed, gaps identified |
| Recommendations | Actionable suggestions based on patterns |

---

## Journal Structure

### Frontmatter

```yaml
---
project: "torlyAI"
project_type: "feature"
repo_path: "/Users/you/Projects/torlyAI"
language: "typescript"
total_sessions: 12
first_session: 2024-01-01
last_session: 2024-01-20
primary_tools: ["typescript", "claude-code", "git", "jest"]
learning_focus: ["authentication", "state-management"]
color: "#ff375f"
---
```

### Timeline Entry

```markdown
## 2024-01-20 | Dev Session | 1-2hr
**Branch:** feature/auth | **Commits:** 8

### What Was Done
Added JWT authentication flow with refresh tokens...

**Files changed:** 12 files (+423 -156)

<details>
<summary>Commit log (8 commits)</summary>

abc1234 Add JWT middleware
def5678 Create auth endpoints
...

</details>

### Approaches Tried
Started with session-based, switched to JWT...

### What Didn't Work
Session storage complexity...

### Key Insights
JWT cleaner for mobile apps...

### Next Steps
- [ ] Add refresh token rotation
- [ ] Implement logout on all devices

---
```

---

## Git Integration

DevJournal automatically detects git activity:

### What's Detected

- Commits since last logged session
- Files changed with line counts
- Current branch
- Uncommitted changes (warning)

### When Git Fails

If the repo isn't found or git commands fail:
- Journal continues without git stats
- Entry uses simplified format
- Warning displayed to user

### Branch Tracking

Over time, reviews show:
- Which branches you work on most
- Commits per branch
- Primary development patterns

---

## Tips for Effective Logging

### 1. Log at Session End

Git detection works best after you've committed. Log right after pushing, not at the start of the next session.

### 2. Be Honest About Failures

The "What didn't work" section is the most valuable for learning. Don't skip it:

**Less useful**:
> "Nothing major"

**More useful**:
> "Spent 2 hours debugging state updates before realizing I was
> mutating objects directly. Need to review immutability patterns."

### 3. Make Insights Actionable

Write insights you can apply later:

**Less useful**:
> "TypeScript is helpful"

**More useful**:
> "Adding strict null checks caught 3 bugs immediately.
> Enable this on all new projects from the start."

### 4. Review Weekly

Use `/devreview project 7` at end of each week to:
- See what you accomplished
- Identify patterns while they're fresh
- Plan next week based on trends

### 5. Keep Next Steps Concrete

Use checkboxes for accountability:

```markdown
### Next Steps
- [ ] Refactor auth middleware to use dependency injection
- [ ] Add integration tests for token refresh flow
- [ ] Document OAuth flow in README
```

---

## FAQ

### Q: Where are journals stored?

**A:** `~/DevJournals/{project} - Dev Log.md`

Reviews are saved as: `~/DevJournals/{project} - Review {date}.md`

### Q: Can I edit journals manually?

**A:** Yes! They're just markdown files. The frontmatter YAML should stay intact for proper parsing.

### Q: What if I forget to log?

**A:** Git history is preserved. Your next log will detect all commits since the last recorded session - it might just be a larger chunk.

### Q: Can I use this for non-git projects?

**A:** Yes, but git integration won't work. Entries will be simplified without commit stats.

### Q: How does it handle multiple branches?

**A:** Git detection finds all commits since last session across all branches. Branch name is captured in entries.

### Q: Can I change the journal location?

**A:** Currently journals live in `~/DevJournals/`. Future versions may support custom paths via config.

---

## File Locations

| Purpose | Location |
|---------|----------|
| Journal files | `~/DevJournals/{project} - Dev Log.md` |
| Review files | `~/DevJournals/{project} - Review {date}.md` |
| Template | `~/.claude/templates/dev-journal.md` |
| Commands | `~/.claude/commands/devjournal.md`, `devreview.md` |

---

## Example Workflow

### Daily

1. Work on project as normal
2. Commit and push changes
3. Run `/devjournal project-name`
4. Answer prompts honestly
5. Review generated entry

### Weekly

1. Run `/devreview project-name 7`
2. Review themes and blockers
3. Check if recommended actions make sense
4. Plan next week based on patterns

### Monthly

1. Run `/devreview project-name 30`
2. Look for velocity trends
3. Identify skill gaps to address
4. Review whether process is working

---

## Support

- **Issues**: [GitHub Issues](https://github.com/DukeWood/claude-code-plugins-productivities/issues)
- **Updates**: `cd /path/to/repo && git pull`
