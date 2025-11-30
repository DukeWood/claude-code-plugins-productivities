---
description: Log a development session with auto-detected git activity
args:
  project_name:
    type: string
    description: The name of the project (e.g., "plugin-dev")
    required: true
---

I'll log a development session for "{{project_name}}" with automatic git activity detection and structured learning reflection.

## Step 1: Locate or Create Journal

Check if the journal exists at: `$HOME/DevJournals/{{project_name}} - Dev Log.md`

If the file doesn't exist:
- Use AskUserQuestion to prompt for:
  1. **Repository path** - Full path to the git repository
  2. **Project type** - Options: "plugin", "feature", "bugfix", "refactor", "experiment"
- Read the template: `$HOME/.claude/templates/dev-journal.md`
- Create the journal file with:
  - project: "{{project_name}}"
  - project_type: (from user input)
  - repo_path: (from user input)
  - first_session: Today (YYYY-MM-DD)
  - last_session: Today (YYYY-MM-DD)
  - total_sessions: 1
  - color: Based on project_type:
    - plugin -> "#bf5af2"
    - feature -> "#ff375f"
    - bugfix -> "#ff9500"
    - refactor -> "#5ac8fa"
    - experiment -> "#34c759"
- Replace `{{project}}` placeholder with {{project_name}}
- Replace `{{project_type}}` placeholder with actual type

## Step 2: Read Journal Frontmatter

Read the journal file and extract:
- `repo_path` - Git repository path
- `last_session` - Date of last logged session
- `project_type` - Type of project
- `total_sessions` - Number of sessions logged
- `primary_tools` - Array of tools used
- `learning_focus` - Array of learning areas

## Step 3: Detect Git Activity Since Last Session

Navigate to `repo_path` and run these git commands in parallel using Bash tool:

```bash
cd {{repo_path}}

# Commit log since last session
git log --since="{{last_session}}" --oneline --all --no-merges --max-count=50

# Summary stats
git diff --shortstat {{last_session}}..HEAD

# File changes with stats
git diff --stat {{last_session}}..HEAD | head -20

# Commit count
git rev-list --count {{last_session}}..HEAD

# Current branch
git rev-parse --abbrev-ref HEAD

# Uncommitted work
git status --short | head -20
```

Parse the results to extract:
- **commit_messages**: Array of commit messages
- **files_changed**: Number of files modified
- **lines_added**: Number of lines added
- **lines_deleted**: Number of lines deleted
- **commit_count**: Total commits since last session
- **current_branch**: Active git branch
- **uncommitted_changes**: List of uncommitted files

If git commands fail (repo not found/not a git repo):
- Warn user about git detection failure
- Continue without git stats
- Set commit_count = 0

## Step 4: Detect File Modifications (Non-Git Fallback)

If git detection succeeded, skip this step.

If git detection failed, run:
```bash
find {{repo_path}} -type f \
  \( -name "*.ts" -o -name "*.js" -o -name "*.py" -o -name "*.md" \) \
  -newermt "{{last_session}}" \
  ! -path "*/node_modules/*" ! -path "*/.git/*" \
  | head -20
```

This provides a list of recently modified files as fallback.

## Step 5: Gather Session Details (Interactive Prompts)

Use AskUserQuestion tool with these questions:

**Question 1: Duration**
- Options: "30min", "1-2hr", "3-4hr", "All day"

**Question 2: What did you work on?**
- Free text input
- Pre-fill with summary of commit messages if available

**Question 3: What approaches did you try?**
- Optional free text
- Examples: "Tried X library, tested Y pattern, experimented with Z approach"

**Question 4: What didn't work and why?**
- Optional free text
- Focus on failures, blockers, dead ends

**Question 5: Key learnings or insights?**
- Optional free text
- What did you learn? What would you do differently?

**Question 6: Next steps?**
- Free text
- Simple markdown checkbox format
- Example: "- [ ] Refactor authentication module\n- [ ] Add unit tests for X"

## Step 6: Analyze Tools Used

Parse the commit messages and user notes for mentions of tools:
- git, npm, pip, yarn, pnpm
- docker, kubernetes
- claude-code, cursor, vscode
- typescript, python, javascript
- bash, zsh
- Other tools mentioned

Add any new tools to the `primary_tools` array (avoid duplicates).

## Step 7: Format Timeline Entry

Create a new timeline entry in this format:

```markdown
## {{TODAY}} | Dev Session | {{duration}}
**Branch:** {{current_branch}} | **Commits:** {{commit_count}}

### What Was Done
{{user_input_what_done}}

**Files changed:** {{files_changed}} files (+{{lines_added}} -{{lines_deleted}})

<details>
<summary>Commit log ({{commit_count}} commits)</summary>

{{commit_messages}}

</details>

### Approaches Tried
{{user_input_approaches_tried}}

### What Didn't Work
{{user_input_what_didnt_work}}

### Key Insights
{{user_input_insights}}

### Next Steps
{{user_input_next_steps}}

---
```

If git detection failed, omit the commit log section and simplify to:
```markdown
## {{TODAY}} | Dev Session | {{duration}}

### What Was Done
{{user_input_what_done}}

### Approaches Tried
{{user_input_approaches_tried}}

### What Didn't Work
{{user_input_what_didnt_work}}

### Key Insights
{{user_input_insights}}

### Next Steps
{{user_input_next_steps}}

---
```

## Step 8: Insert Entry at Top of Timeline

Find the heading `# Development Timeline` in the journal file.

Insert the new entry immediately after this heading (before any existing entries).

This maintains reverse chronological order (newest first).

## Step 9: Update Journal Frontmatter

Update the following frontmatter properties:

1. **last_session**: Today's date (YYYY-MM-DD)
2. **total_sessions**: Increment by 1
3. **primary_tools**: Merge with newly detected tools (remove duplicates)
4. **learning_focus**: If user mentioned specific learning areas in insights, add them to array

If this is the very first session (total_sessions was 0):
- Also set **first_session**: Today's date

## Step 10: Update Development Stats Section

Find the `## Development Stats` section in the journal.

Recalculate and update:

```markdown
## Development Stats

- **Total sessions:** {{total_sessions}}
- **Frequency:** {{avg_days_between}} days/session
- **Primary tools:** {{comma_separated_tools}}
- **Learning focus:** {{comma_separated_learning_areas}}
- **Recent velocity:** {{commits_per_week}} commits/week
```

**Calculation formulas:**
- **avg_days_between**: (Today - first_session) / total_sessions
- **commits_per_week**: (Total commits in last 7 days) / 1 week
- If total_sessions = 1: Use "First session" for frequency

## Step 11: Confirm Success

Display a summary to the user:

```
Dev session logged ({{project_type}} - {{duration}})
Last session: Today ({{TODAY}})
Stats: {{commit_count}} commits, {{files_changed}} files
Learning: {{first_insight_sentence}}
```

Where:
- `{{TODAY}}`: Today's date (YYYY-MM-DD)
- `{{first_insight_sentence}}`: First sentence from user's insights (or "Session logged" if none)
