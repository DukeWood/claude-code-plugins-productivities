# /devjournal Command

Log development sessions with automatic git activity detection and structured reflection.

## Usage

```
/devjournal my-project
/devjournal plugin-dev
/devjournal torlyAI
```

## What It Does

1. **Locates or creates** a journal file at `~/DevJournals/{project} - Dev Log.md`
2. **Detects git activity** since your last logged session (commits, files changed, lines added/deleted)
3. **Prompts for reflection**:
   - What you worked on
   - Approaches you tried
   - What didn't work
   - Key insights
   - Next steps
4. **Adds a timestamped entry** to the development timeline
5. **Updates statistics** (total sessions, velocity, tools used)

## First-Time Setup

On first run for a project, you'll be asked:
- **Repository path**: Full path to the git repo
- **Project type**: plugin, feature, bugfix, refactor, or experiment

This creates the journal from the template with appropriate color coding.

## Journal Structure

```markdown
---
project: "my-project"
project_type: "feature"
repo_path: "/path/to/repo"
total_sessions: 5
first_session: 2024-01-15
last_session: 2024-01-20
primary_tools: ["typescript", "claude-code", "git"]
learning_focus: ["testing", "architecture"]
---

# my-project - Development Journal

## Development Stats
- Total sessions: 5
- Frequency: 1.2 days/session
- Primary tools: typescript, claude-code, git
- Recent velocity: 12 commits/week

# Development Timeline

## 2024-01-20 | Dev Session | 1-2hr
**Branch:** feature/auth | **Commits:** 4
...
```

## Example Session

```
> /devjournal torlyAI

Detecting git activity...
Found 8 commits, 12 files changed (+423 -156)

Duration: [1-2hr]
What did you work on: Added user authentication flow with JWT tokens
Approaches tried: Started with session-based auth, switched to JWT
What didn't work: Session storage was too complex for multi-device
Key insights: JWT with refresh tokens is cleaner for mobile apps
Next steps: - [ ] Add refresh token rotation
            - [ ] Implement logout on all devices

Dev session logged (feature - 1-2hr)
Stats: 8 commits, 12 files
Learning: JWT with refresh tokens is cleaner for mobile apps
```

## File Locations

| File | Location |
|------|----------|
| Journal files | `~/DevJournals/{project} - Dev Log.md` |
| Template | `~/.claude/templates/dev-journal.md` |

## Tips

- **Log at end of session**: Git activity detection works best when you log after commits
- **Be honest about failures**: The "What didn't work" section is valuable for learning
- **Keep insights actionable**: Write insights you can apply in future sessions
- **Review with /devreview**: Analyze patterns across multiple sessions

## Related

- `/devreview` - Analyze patterns from journal entries
- `templates/dev-journal.md` - The template used for new journals
