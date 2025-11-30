---
description: Analyze development patterns from recent journal entries
args:
  project_name:
    type: string
    description: The name of the project (e.g., "plugin-dev")
    required: true
  days:
    type: string
    description: Number of days to review (default 30)
    required: false
---

I'll analyze development patterns for "{{project_name}}" over the last {{days}} days to identify themes, blockers, effective strategies, and learning opportunities.

## Step 1: Locate Journal

Read the journal file: `$HOME/DevJournals/{{project_name}} - Dev Log.md`

If the file doesn't exist:
- Display error message: "No dev journal found for '{{project_name}}'. Run `/devjournal "{{project_name}}"` first to create it."
- Stop execution

## Step 2: Set Review Window

Determine the review period:
- If `{{days}}` argument provided: Use that value
- Otherwise: Default to 30 days

Calculate:
- **review_days**: The number of days to analyze
- **cutoff_date**: Today minus review_days (YYYY-MM-DD format)
- **today**: Today's date (YYYY-MM-DD)

## Step 3: Parse Timeline Entries

Scan the journal file for all entries in the `# Development Timeline` section.

For each entry with a date >= cutoff_date, extract:
- **Date**: Entry date
- **Duration**: Session duration (30min, 1-2hr, etc.)
- **Branch**: Git branch (if available)
- **Commit count**: Number of commits
- **What was done**: Content from "What Was Done" section
- **Approaches tried**: Content from "Approaches Tried" section
- **What didn't work**: Content from "What Didn't Work" section
- **Key insights**: Content from "Key Insights" section
- **Next steps**: Content from "Next Steps" section

Store all extracted entries in an array for analysis.

If fewer than 3 entries found:
- Add warning note: "Low sample size (< 3 sessions) - patterns may not be statistically significant"

## Step 4: Calculate Aggregate Metrics

From the parsed entries, calculate:

**Activity Volume:**
- Total sessions in period
- Total commits (sum of all commit counts)
- Total files modified (parse from entries)
- Total lines changed (parse from entries)

**Frequency:**
- Sessions per week: total_sessions / (review_days / 7)
- Active days: Count of unique dates with sessions
- Inactive days: review_days - active_days
- Average session duration

**Velocity Trends:**
- Commits per week (grouped by week)
- Trend: Compare first half vs. second half of review period
  - If second half > first half: "Increasing"
  - If second half < first half: "Decreasing"
  - If similar: "Stable"

**Branch Analysis:**
- All branches worked on (unique list)
- Commits per branch
- Primary development branch (most commits)

**Streak Analysis:**
- Longest gap between sessions
- Current streak (days since last session)

## Step 5: AI-Powered Pattern Analysis

Analyze the content from all entries to identify:

**1. Themes & Patterns:**
- Recurring focus areas (what topics appear most often?)
- Work distribution (features vs. bugs vs. refactoring - estimate percentages)
- Technical topics (libraries, frameworks, languages mentioned)
- Common workflows or approaches

**2. Common Failure Modes:**
- Blockers that appeared multiple times
- Approaches that didn't work (from "What Didn't Work" sections)
- Root causes if identifiable
- Environmental issues (tooling, setup problems)

**3. Effective Strategies:**
- Approaches that led to progress
- Patterns in successful sessions
- Tools or workflows that worked well
- What accelerated velocity

**4. Learning Observations:**
- Skills developed or improved
- Knowledge gaps identified
- Insights gained
- Areas of growth

Generate 3-5 bullet points for each category.

## Step 6: Generate Review Report

Create a comprehensive markdown report with this structure:

```markdown
# Development Review: {{project_name}}

**Review Period:** {{cutoff_date}} to {{today}} ({{review_days}} days)
**Generated:** {{today}} at {{current_time}}

---

## Activity Metrics

### Volume
- **Sessions:** {{total_sessions}}
- **Commits:** {{total_commits}}
- **Files modified:** {{total_files}}
- **Lines changed:** {{total_lines}}

### Frequency
- **Sessions per week:** {{sessions_per_week}}
- **Active days:** {{active_days}}/{{review_days}} days ({{active_percentage}}%)
- **Average session:** {{avg_duration}}

### Velocity
- **Commits/week:** {{commits_per_week}}
- **Trend:** {{trend}} (first half: {{first_half_commits}}, second half: {{second_half_commits}})

### Branches
- **Primary branch:** {{primary_branch}} ({{primary_commits}} commits)
- **Feature branches:** {{feature_branches}}

### Streaks
- **Longest gap:** {{longest_gap}} days
- **Days since last session:** {{days_since_last}}

---

## Themes & Patterns

{{themes_list}}

**Work Distribution:**
{{work_distribution}}

---

## Common Failure Modes

{{failure_modes_list}}

**Root Causes:**
{{root_causes}}

---

## Effective Strategies

{{effective_strategies_list}}

**Velocity Accelerators:**
{{accelerators}}

---

## Learning Observations

### Skills Developed
{{skills_list}}

### Insights Gained
{{insights_list}}

### Knowledge Gaps
{{gaps_list}}

---

## Recommendations

### Immediate Actions
1. {{action_1}}
2. {{action_2}}
3. {{action_3}}

### Process Improvements
{{process_improvements}}

### Learning Focus
{{learning_focus_areas}}

---

## Technical Workflow Checklist

Based on effective patterns observed:

- [ ] {{checklist_item_1}}
- [ ] {{checklist_item_2}}
- [ ] {{checklist_item_3}}
- [ ] {{checklist_item_4}}
- [ ] {{checklist_item_5}}

---

**Next Review:** {{next_review_date}} (in {{days_until}} days)
```

## Step 7: Save Review File

Write the generated report to:
`$HOME/DevJournals/{{project_name}} - Review {{today}}.md`

This keeps reviews dated and separate from the main log.

## Step 8: Display Console Summary

Show a concise summary in the console:

```
Development Review: {{project_name}} ({{review_days}} days)

ACTIVITY
   Sessions: {{total_sessions}} | Commits: {{total_commits}} | Files: {{total_files}}
   Active: {{active_days}}/{{review_days}} days | Velocity: {{trend}}

TOP THEMES
   1. {{theme_1}}
   2. {{theme_2}}
   3. {{theme_3}}

COMMON BLOCKERS
   1. {{blocker_1}}
   2. {{blocker_2}}

EFFECTIVE STRATEGIES
   1. {{strategy_1}}
   2. {{strategy_2}}

KEY INSIGHTS
   1. {{insight_1}}
   2. {{insight_2}}

TOP RECOMMENDATIONS
   1. {{rec_1}}
   2. {{rec_2}}
   3. {{rec_3}}

Full report: ~/DevJournals/{{project_name}} - Review {{today}}.md
```

## Step 9: Update Journal Frontmatter

Read the main journal file and update frontmatter:

Add or update these properties:
- **last_review**: {{today}} (YYYY-MM-DD)
- **last_review_file**: "[[~/DevJournals/{{project_name}} - Review {{today}}]]"

This creates a link to the review file from the main journal.

## Step 10: Provide Summary

Display final confirmation:

```
Review generated for {{project_name}}
Period: {{cutoff_date}} to {{today}} ({{review_days}} days)
Analyzed: {{total_sessions}} sessions, {{total_commits}} commits
Location: ~/DevJournals/{{project_name}} - Review {{today}}.md

Top recommendation: {{top_rec}}
```

Where `{{top_rec}}` is the first recommendation from the list.
