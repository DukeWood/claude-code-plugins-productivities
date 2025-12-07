#!/bin/bash
# Restore Slack notification hooks

python3 <<'PYTHON'
import json

# Read current settings
with open('/Users/Jason-uk/.claude/settings.json', 'r') as f:
    settings = json.load(f)

# Read backed up hooks
with open('/Users/Jason-uk/.claude/hooks-backup.json', 'r') as f:
    hooks = json.load(f)

# Restore hooks
settings['hooks'] = hooks

# Save
with open('/Users/Jason-uk/.claude/settings.json', 'w') as f:
    json.dump(settings, f, indent=2)

print("✅ Hooks restored successfully")
PYTHON
