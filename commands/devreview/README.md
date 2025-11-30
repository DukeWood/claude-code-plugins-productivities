# /devreview Command

Analyze development patterns from your journal entries to identify themes, blockers, effective strategies, and learning opportunities.

## Usage

```
/devreview my-project           # Review last 30 days (default)
/devreview my-project 7         # Review last 7 days
/devreview my-project 90        # Review last 90 days
```

## What It Does

1. **Reads your journal** at `~/DevJournals/{project} - Dev Log.md`
2. **Parses all entries** within the review period
3. **Calculates metrics**: sessions, commits, files, velocity trends
4. **Identifies patterns**: themes, failure modes, effective strategies
5. **Generates a report** with actionable recommendations
6. **Saves the review** as a separate file for reference

## Output

### Console Summary

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

Full report: ~/DevJournals/torlyAI - Review 2024-01-20.md
```

### Saved Report

A comprehensive markdown file with:
- Activity metrics (volume, frequency, velocity)
- Theme analysis with work distribution
- Failure modes and root causes
- Effective strategies that worked
- Learning observations (skills, insights, gaps)
- Actionable recommendations
- Technical workflow checklist

## Report Sections

| Section | What It Contains |
|---------|-----------------|
| Activity Metrics | Sessions, commits, files, lines changed |
| Frequency | Sessions/week, active days, average duration |
| Velocity | Commits/week, trend (increasing/decreasing/stable) |
| Themes & Patterns | Recurring focus areas, work distribution |
| Failure Modes | Blockers, what didn't work, root causes |
| Effective Strategies | What worked, velocity accelerators |
| Learning | Skills developed, insights, knowledge gaps |
| Recommendations | Immediate actions, process improvements |

## Requirements

- Journal must exist (created via `/devjournal`)
- At least 3 entries recommended for meaningful patterns
- More entries = better pattern detection

## Tips

- **Weekly reviews**: Use `/devreview project 7` at end of week
- **Monthly retros**: Default 30-day review for monthly planning
- **Quarterly planning**: Use `/devreview project 90` for bigger picture
- **Compare reviews**: Review files are dated, so you can compare over time

## File Locations

| File | Location |
|------|----------|
| Input journal | `~/DevJournals/{project} - Dev Log.md` |
| Output review | `~/DevJournals/{project} - Review {date}.md` |

## Related

- `/devjournal` - Log a development session (creates journal entries)
- `docs/devjournal-guide.md` - Complete workflow guide
