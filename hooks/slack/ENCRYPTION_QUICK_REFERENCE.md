# Encryption Module - Quick Reference Card

**TL;DR:** Secure credential encryption for Slack webhooks and other sensitive config values.

## 5-Second Usage

```python
from lib import encryption

# Encrypt
encrypted = encryption.encrypt("https://hooks.slack.com/services/SECRET")

# Decrypt
plaintext = encryption.decrypt(encrypted)
```

## Common Operations

### Store Encrypted Config in Database

```python
import encryption
import sqlite3

db = sqlite3.connect("~/.claude/state/notifications.db")

# Encrypt webhook URL
webhook_url = "https://example.com/webhook/your-secret-token"
encrypted = encryption.encrypt(webhook_url)

# Store
db.execute(
    "INSERT INTO config (key, value, is_encrypted, updated_at) VALUES (?, ?, 1, ?)",
    ("slack_webhook_url", encrypted, int(time.time()))
)
db.commit()
```

### Load Encrypted Config from Database

```python
# Load
row = db.execute(
    "SELECT value, is_encrypted FROM config WHERE key='slack_webhook_url'"
).fetchone()

# Decrypt if needed
if row and row[1]:  # is_encrypted == 1
    webhook_url = encryption.decrypt(row[0])
else:
    webhook_url = row[0]
```

### Idempotent Encryption (Safe to Call Multiple Times)

```python
# Automatically handles both plaintext and encrypted values
value = encryption.encrypt_if_needed(config.get('webhook_url'))
# Call again - no double encryption
value = encryption.encrypt_if_needed(value)  # No-op
```

### Idempotent Decryption

```python
# Automatically detects and decrypts only if needed
plaintext = encryption.decrypt_if_needed(value)
```

### Migrate V1 Config to V2 (Plaintext → Encrypted)

```python
import json

# Load V1 config (plaintext)
with open("~/.claude/config/slack-config.json") as f:
    v1_config = json.load(f)

# Encrypt for V2
encrypted_url = encryption.encrypt(v1_config['webhook_url'])

# Store in V2 database
db.execute(
    "INSERT INTO config (key, value, is_encrypted, updated_at) VALUES (?, ?, 1, ?)",
    ("slack_webhook_url", encrypted_url, int(time.time()))
)
db.commit()
```

### Key Rotation (Complete Workflow)

```python
old_key = "~/.claude/state/encryption.key"
new_key = "~/.claude/state/encryption-new.key"

# Step 1: Generate new key
new_key = encryption.rotate_key(old_key, new_key)

# Step 2: Re-encrypt all values
db = sqlite3.connect("~/.claude/state/notifications.db")
rows = db.execute("SELECT key, value FROM config WHERE is_encrypted=1").fetchall()

for key, old_cipher in rows:
    new_cipher = encryption.reencrypt_value(old_cipher, old_key, new_key)
    db.execute("UPDATE config SET value=? WHERE key=?", (new_cipher, key))

db.commit()

# Step 3: Verify new key works
test = encryption.decrypt(new_cipher, new_key)
print(f"Verification: {test[:20]}...")

# Step 4: Delete old key (ONLY after verification!)
import os
os.remove(old_key)
```

## Function Reference (Quick)

| Function | Purpose | Example |
|----------|---------|---------|
| `encrypt(plaintext)` | Encrypt a string | `encrypt("secret")` |
| `decrypt(ciphertext)` | Decrypt a string | `decrypt("gAAAAA...")` |
| `is_encrypted(value)` | Check if encrypted | `is_encrypted("gAAAAA...")` → `True` |
| `get_or_create_key()` | Get/generate key | `get_or_create_key()` |
| `rotate_key(old, new)` | Generate new key | `rotate_key(old, new)` |
| `reencrypt_value(cipher, old, new)` | Re-encrypt with new key | `reencrypt_value(c, old, new)` |
| `encrypt_if_needed(val)` | Idempotent encrypt | `encrypt_if_needed(val)` |
| `decrypt_if_needed(val)` | Idempotent decrypt | `decrypt_if_needed(val)` |

## Security Checklist

✅ **DO:**
- Use default key path (`~/.claude/state/encryption.key`)
- Check key file permissions (should be `0o600`)
- Backup key file securely
- Rotate keys periodically
- Use `is_encrypted()` before decrypting

❌ **DON'T:**
- Commit key file to git (add to `.gitignore`)
- Share key file across machines
- Delete old key before re-encrypting all values
- Log plaintext secrets
- Use custom key paths unless necessary

## Troubleshooting One-Liners

### Fix key file permissions
```bash
chmod 600 ~/.claude/state/encryption.key
```

### Delete and regenerate key
```bash
rm ~/.claude/state/encryption.key
# Will auto-regenerate on next use
```

### Check if value is encrypted
```python
encryption.is_encrypted("gAAAAABf...")  # True
encryption.is_encrypted("plaintext")    # False
```

### Handle decryption errors
```python
try:
    plaintext = encryption.decrypt(ciphertext)
except encryption.DecryptionError as e:
    print(f"Decryption failed: {e}")
    # Fall back to treating as plaintext
    plaintext = ciphertext
```

## Testing

```bash
# Run all tests
cd hooks/slack
./run_encryption_tests.sh

# Run demo
python3 examples/encryption_demo.py
```

## Files

```
hooks/slack/lib/encryption.py              # Implementation
hooks/slack/lib/ENCRYPTION_README.md       # Full docs
hooks/slack/tests/test_encryption.py       # Test suite (32 tests)
hooks/slack/examples/encryption_demo.py    # Demo script (7 demos)
~/.claude/state/encryption.key             # Generated key (0o600)
```

## Performance

- Key generation: ~10ms (one-time)
- Encryption: <1ms
- Decryption: <1ms
- Permission check: <1ms

## Algorithm Details

- **Cipher:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Key size:** 32 bytes (256 bits)
- **Nonce:** Unique per encryption (random)
- **Output:** Base64-encoded ciphertext (JSON-safe)

## Default Paths

```python
encryption.DEFAULT_KEY_PATH
# → "~/.claude/state/encryption.key"
```

## Import

```python
# From lib directory
from lib import encryption

# Or add to path
import sys
sys.path.insert(0, 'lib')
import encryption
```

## Quick Validation

```bash
python3 -c "
import sys
sys.path.insert(0, 'lib')
import encryption

# Test roundtrip
plain = 'test'
cipher = encryption.encrypt(plain)
decrypted = encryption.decrypt(cipher)
assert plain == decrypted
print('✓ Encryption working')
"
```

## Next Steps

1. ✅ Read this quick reference
2. ✅ Run `./run_encryption_tests.sh`
3. ✅ Run `python3 examples/encryption_demo.py`
4. ✅ Read `lib/ENCRYPTION_README.md` for details
5. ✅ Integrate with V2 migration script

---

**Questions?** See full documentation in `lib/ENCRYPTION_README.md`
