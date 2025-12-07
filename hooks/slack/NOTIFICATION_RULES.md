# Slack Notification Rules - Quick Reference

## Task Complete Notifications (Stop Hook)

### Current Configuration
```json
{
  "notify_always": true  // ✅ You have this enabled
}
```

### When Will You Get Notified?

**With `notify_always: true` (your current setting):**
- ✅ Every time Claude Code session ends (Ctrl+D or task finishes)
- ✅ In tmux sessions
- ✅ Outside tmux (VSCode, Terminal, SSH, etc.)
- ✅ All projects, all directories

**If you change to `notify_always: false`:**
- ✅ Only in tmux sessions
- ❌ NOT in regular terminal/VSCode
- Use case: Only get notified for background tasks

### Examples

#### Scenario 1: You're in tmux
```bash
tmux new-session -s work
claude code
# Ask: "Refactor the auth system"
# Work for 20 minutes
# Press Ctrl+D
```
**Notification:** ✅ YES - "Task Complete | Modified 8 files | 45K tokens"

#### Scenario 2: You're in VSCode terminal
```bash
claude code
# Ask: "What's 2+2?"
# Press Ctrl+D
```
**With notify_always=true:** ✅ YES - "Task Complete"
**With notify_always=false:** ❌ NO - Only notifies in tmux

#### Scenario 3: Quick question, no file changes
```bash
claude code
# Ask: "Explain how async/await works"
# Press Ctrl+D
```
**Notification:** ✅ YES - "Task Complete | Research"

### Summary Table

| Session Type | notify_always: true | notify_always: false |
|--------------|---------------------|----------------------|
| tmux session | ✅ Always notify | ✅ Always notify |
| VSCode terminal | ✅ Always notify | ❌ Never notify |
| Regular Terminal | ✅ Always notify | ❌ Never notify |
| SSH session | ✅ Always notify | ❌ Never notify |

---

## Permission Required Notifications (Notification Hook)

### When Will You Get Notified?

**You get notified when Claude needs permission for:**

### ✅ Tools That Show Permission Prompts

1. **Bash commands** (not in auto-approve list)
   ```bash
   # Example: cd ~/.claude && ls -la
   # Not in auto-approve → Shows permission prompt → Slack notification
   ```

2. **Edit/Write** (if not auto-approved)
   - Currently `Write` is auto-approved, so NO notification
   - `Edit` is auto-approved, so NO notification

3. **WebFetch** (new domains not in allow list)
   ```bash
   # Example: Fetching from example.com (not in allow list)
   # Shows permission prompt → Slack notification
   ```

4. **Any tool in your "ask" list**
   - Currently your `ask` list is empty
   - Tools are either auto-approved or denied

### ❌ You DON'T Get Notified When:

1. **Tool is auto-approved**
   ```bash
   # Example: ls (Bash(ls:*) is in auto-approve)
   # Auto-approved → No prompt → No notification
   ```

2. **Tool is auto-denied**
   ```bash
   # Example: If something is in your deny list
   # Auto-denied → No prompt → No notification
   ```

3. **Edit/Write operations** (currently auto-approved)
   - `Write` is in your allow list → No notification
   - `Edit` is in your allow list → No notification

### Your Current Auto-Approve List

```json
{
  "allow": [
    "Bash(ls:*)",      // ✅ Auto-approved
    "Bash(git:*)",     // ✅ Auto-approved
    "Bash(cat:*)",     // ✅ Auto-approved
    "Write",           // ✅ Auto-approved
    "Edit",            // ✅ Auto-approved
    "Read",            // ✅ Auto-approved
    // ... and many more
  ]
}
```

### Examples

#### Scenario 1: Auto-Approved Command
```bash
# User asks: "Show me the git log"
# Claude runs: Bash(git log)
```
**Notification:** ❌ NO - Auto-approved (matches `Bash(git:*)`)

#### Scenario 2: NOT Auto-Approved Command
```bash
# User asks: "Check what Charlie did last week"
# Claude runs: Bash(cd ~/.claude && ls -la)
```
**Before Hookify fix:** ❌ Interrupted (no permission shown)
**After Hookify fix:**
- Shows permission prompt in terminal
- ✅ Sends Slack notification: "🔐 Permission Required | Bash | cd ~/.claude && ls -la"

#### Scenario 3: WebFetch to New Domain
```bash
# User asks: "Fetch data from api.example.com"
# Claude runs: WebFetch(url: "https://api.example.com/data")
```
**Notification:** ✅ YES - "🔐 Permission Required | Web Access | URL: https://api.example.com/data"

---

## Configuration Examples

### Option 1: Get All Notifications (Current)
```json
{
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": true  // ← Notify even outside tmux
}
```
**You get:** Every completion + Every permission request

### Option 2: Only tmux Notifications
```json
{
  "enabled": true,
  "notify_on": {
    "permission_required": true,
    "task_complete": true,
    "input_required": true
  },
  "notify_always": false  // ← Only in tmux
}
```
**You get:** Completions only in tmux + Every permission request

### Option 3: Only Completions, No Permission Prompts
```json
{
  "enabled": true,
  "notify_on": {
    "permission_required": false,  // ← Disabled
    "task_complete": true,
    "input_required": true
  },
  "notify_always": true
}
```
**You get:** Every completion + No permission notifications

### Option 4: Minimal (Only tmux completions)
```json
{
  "enabled": true,
  "notify_on": {
    "permission_required": false,
    "task_complete": true,
    "input_required": false
  },
  "notify_always": false
}
```
**You get:** Only completions in tmux

---

## Special Cases

### Input Required (AskUserQuestion)
**Currently NOT working** because we only implemented:
- Notification hook (permission prompts)
- Stop hook (task completion)

**NOT implemented:**
- PostToolUse hook for AskUserQuestion

If you want notifications when Claude asks questions, we'd need to add that hook.

### Idle Prompt
**✅ NOW SUPPORTED** - Sends notifications for idle_prompt events.

When Claude is waiting for your input (e.g., VSCode file review dialogs), you'll get:
- **Notification:** "⏳ Waiting for Input"
- **Color:** Orange (#FFA500)
- **Message:** "Claude is waiting for your response - Please check the terminal to continue."

Example scenarios:
- VSCode file review prompts
- Multi-file edit confirmations
- Any time Claude pauses waiting for user input

---

## How to Change Configuration

Edit `~/.claude/config/slack-config.json`:

```bash
nano ~/.claude/config/slack-config.json
```

Changes take effect **immediately** - no restart needed!

---

## Testing Your Configuration

### Test Task Complete Notification
```bash
claude code
# Ask: "What's 2+2?"
# Press Ctrl+D
# Check Slack - should see "✅ Task Complete"
```

### Test Permission Notification
```bash
claude code
# Ask: "Run this command: python3 --version"
# Should see permission prompt AND Slack notification
# (python3 is not in auto-approve list)
```

### Test Idle Prompt Notification
```bash
claude code
# Ask: "Please review these 5 files and make changes"
# When Claude shows VSCode file review dialog
# Check Slack - should see "⏳ Waiting for Input"
```

---

## Troubleshooting

### "I'm not getting task complete notifications"
1. Check `notify_always` setting
2. If false, you must be in tmux
3. Check `notify_on.task_complete` is true
4. Check debug log: `tail ~/.claude/logs/notify-stop-debug.log`

### "I'm not getting permission notifications"
1. Check if tool is auto-approved (in allow list)
2. Check `notify_on.permission_required` is true
3. Tool must actually show a permission prompt
4. Check debug log: `tail ~/.claude/logs/notify-permission-debug.log`

### "I'm getting too many notifications"
1. Set `notify_always: false` - only notify in tmux
2. Disable permission notifications: `"permission_required": false`
3. Or disable completely: `"enabled": false`

---

## End of Document
