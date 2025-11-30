# Charlie - Socratic Thinking Partner

Charlie is an AI thinking partner that helps you explore complex problems, decisions, and ideas through Socratic dialogue rather than providing direct answers.

## What Charlie Does

- **Asks Questions**: Opens up your thinking with "What makes you think that?", "What would happen if...?"
- **Reflects Back**: Ensures understanding by mirroring key points
- **Finds Patterns**: Identifies themes, contradictions, and connections
- **Takes Notes**: Captures insights progressively throughout the conversation
- **Remembers Context**: Links related thinking sessions over time

## What Charlie Doesn't Do

- Give direct answers or solutions
- Make decisions for you
- Create formal reports or presentations
- Push you toward premature conclusions

## How to Invoke

Charlie only activates on **explicit invocation**. Use any of these patterns:

```
Charlie, I'm trying to decide...
Hey Charlie, let's explore...
@charlie help me think through...
/charlie [topic]
Charlie?! What about...
```

## Example Sessions

### Career Decision
```
You: Charlie, I'm torn between staying at my stable job or joining a startup.

Charlie: That's a significant crossroads. Before we explore the options,
what's making this decision feel difficult right now?

You: I guess I'm afraid of making the wrong choice...

Charlie: "Wrong" is interesting. What would "wrong" look like in each scenario?
```

### Product Strategy
```
You: @charlie We're debating whether to add a free tier to our SaaS.

Charlie: A classic tension. What problem are you hoping the free tier would solve?

You: More users in the funnel, hopefully converting to paid.

Charlie: What assumptions are embedded in "hopefully"? What would need to
be true for free users to convert?
```

## Note-Taking System

Charlie saves notes to help you build on previous thinking:

| Location | Purpose |
|----------|---------|
| `~/.claude/charlie-sessions/` | Working session files |
| `~/.claude/charlie-index.md` | Topic index for memory |
| `~/.claude/charlie-config.md` | Your preferences |

### Note Structure

Each session captures:
- **Key Breakthrough**: The most important insight
- **Questions Opened**: Unresolved threads to explore later
- **Decisions & Leanings**: Where your thinking is heading
- **Action Threads**: Concrete next steps mentioned

## Configuration

On first use, Charlie will ask where to save notes. Options include:
- Obsidian vault
- Dedicated folder (`~/Documents/Charlie Thinking/`)
- Project-specific (`./thinking-notes/`)
- Custom path

## Tips for Best Results

1. **Be specific**: "Should I hire?" is less useful than "I'm considering hiring a junior developer to help with the backlog, but I'm worried about the time investment in training."

2. **Share context**: Charlie works better when you explain the background and constraints.

3. **Think out loud**: Don't wait for perfect thoughts - Charlie helps you develop them.

4. **Let it evolve**: Sessions often shift topics as deeper issues surface. That's good.

5. **Review notes**: Charlie's notes are designed to restart your thinking later.

## Related Commands

- `/charlie [topic]` - Start a thinking session with optional context

## Storage Locations

All Charlie data lives in `~/.claude/`:

```
~/.claude/
├── charlie-config.md      # Your preferences
├── charlie-index.md       # Topic memory index
└── charlie-sessions/      # Session note files
    ├── active-*.md        # Current session
    └── abandoned-*.md     # Incomplete sessions
```
