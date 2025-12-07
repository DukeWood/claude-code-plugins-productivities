# Credential Encryption Module

**Status:** Implemented (TDD approach)
**Version:** V2
**Security:** Fernet symmetric encryption with AES-128-CBC + HMAC

## Overview

This module provides secure encryption for sensitive configuration values like Slack webhook URLs. It follows TDD principles with comprehensive test coverage.

## Features

### Core Functionality
- **Automatic key generation**: Creates encryption key on first use
- **Secure storage**: Key stored at `~/.claude/state/encryption.key` with 0o600 permissions
- **Base64 encoding**: Ciphertext safe for JSON storage
- **Encrypted value detection**: Heuristic to identify encrypted vs plaintext values
- **Key rotation**: Support for rotating encryption keys without data loss

### Security Features
- **No plaintext logging**: Never logs secrets to stdout/stderr
- **Permission validation**: Warns if key file has insecure permissions
- **Fernet encryption**: Industry-standard symmetric encryption (AES-128-CBC + HMAC-SHA256)
- **Unique nonces**: Each encryption includes randomness (same plaintext → different ciphertext)
- **Graceful error handling**: Generic error messages to avoid leaking data

## Quick Start

```python
from lib import encryption

# Encrypt a webhook URL
webhook_url = "https://example.com/webhook/your-secret-token"
encrypted = encryption.encrypt(webhook_url)
# Returns: "gAAAAABf3Q7x..." (base64-encoded ciphertext)

# Decrypt later
decrypted = encryption.decrypt(encrypted)
# Returns: "https://example.com/webhook/your-secret-token"

# Check if value is encrypted
if encryption.is_encrypted(value):
    value = encryption.decrypt(value)
```

## API Reference

### Key Management

#### `get_or_create_key(key_path=None)`
Get existing encryption key or generate a new one.

- **Args:**
  - `key_path` (str, optional): Path to key file. Default: `~/.claude/state/encryption.key`
- **Returns:** `bytes` - Fernet encryption key
- **Side effects:**
  - Creates key file if it doesn't exist
  - Creates parent directories as needed
  - Sets file permissions to 0o600
  - Prints warning to stderr if permissions are insecure

**Example:**
```python
key = encryption.get_or_create_key()
# Key created at ~/.claude/state/encryption.key with 0o600 permissions

# Use custom path
key = encryption.get_or_create_key("/path/to/custom.key")
```

### Encryption/Decryption

#### `encrypt(plaintext, key_path=None)`
Encrypt a plaintext string.

- **Args:**
  - `plaintext` (str): String to encrypt
  - `key_path` (str, optional): Path to encryption key
- **Returns:** `str` - Base64-encoded ciphertext
- **Note:** Each encryption includes a unique nonce, so same plaintext produces different ciphertexts

**Example:**
```python
cipher1 = encryption.encrypt("secret")
cipher2 = encryption.encrypt("secret")
# cipher1 != cipher2 (due to nonce), but both decrypt to "secret"
```

#### `decrypt(ciphertext, key_path=None)`
Decrypt a Fernet-encrypted ciphertext.

- **Args:**
  - `ciphertext` (str): Base64-encoded ciphertext from `encrypt()`
  - `key_path` (str, optional): Path to encryption key (must match key used for encryption)
- **Returns:** `str` - Decrypted plaintext
- **Raises:** `DecryptionError` - If decryption fails (wrong key, corrupted data, invalid format)

**Example:**
```python
try:
    plaintext = encryption.decrypt(ciphertext)
except encryption.DecryptionError as e:
    print(f"Decryption failed: {e}")
```

### Value Detection

#### `is_encrypted(value)`
Detect if a value is encrypted (vs plaintext).

- **Args:**
  - `value` (any): Value to check (can be str, None, or other types)
- **Returns:** `bool` - True if value appears to be Fernet-encrypted
- **Heuristic:** Fernet ciphertexts start with "gAAAAA" (base64-encoded version bytes)

**Example:**
```python
encryption.is_encrypted("gAAAAABf...")  # True (encrypted)
encryption.is_encrypted("https://...")   # False (plaintext)
encryption.is_encrypted(None)            # False
```

### Key Rotation

#### `rotate_key(old_key_path=None, new_key_path=None)`
Generate a new encryption key for key rotation.

- **Args:**
  - `old_key_path` (str, optional): Path to existing key (for reference)
  - `new_key_path` (str): Path where new key should be created
- **Returns:** `bytes` - New encryption key
- **Side effects:**
  - Creates new key file at `new_key_path`
  - Old key file remains unchanged

**Example:**
```python
new_key = encryption.rotate_key(
    old_key_path="~/.claude/state/encryption.key",
    new_key_path="~/.claude/state/encryption-new.key"
)
```

#### `reencrypt_value(old_ciphertext, old_key_path, new_key_path)`
Re-encrypt a value with a new key (for key rotation).

- **Args:**
  - `old_ciphertext` (str): Ciphertext encrypted with old key
  - `old_key_path` (str): Path to old encryption key
  - `new_key_path` (str): Path to new encryption key
- **Returns:** `str` - New ciphertext encrypted with new key
- **Raises:** `DecryptionError` - If decryption with old key fails

**Example:**
```python
# Complete key rotation
new_key = rotate_key(old_key_path, new_key_path)
new_cipher = reencrypt_value(old_cipher, old_key_path, new_key_path)

# Update config
config.set('webhook_url', new_cipher)

# Delete old key (after verifying new key works)
os.remove(old_key_path)
```

### Convenience Functions

#### `encrypt_if_needed(value, key_path=None)`
Encrypt a value if it's not already encrypted (idempotent).

**Example:**
```python
# Safe to call multiple times
value = encrypt_if_needed(value)
value = encrypt_if_needed(value)  # No-op if already encrypted
```

#### `decrypt_if_needed(value, key_path=None)`
Decrypt a value if it's encrypted, otherwise return as-is.

**Example:**
```python
# Handle both encrypted and plaintext values
webhook_url = decrypt_if_needed(config.get('webhook_url'))
```

## Testing

The module was developed using TDD (Test-Driven Development). Tests are comprehensive and cover:

- Key generation and persistence
- Encryption/decryption roundtrip
- Encrypted value detection
- Key file permissions validation
- Key rotation support
- Error handling and security
- Edge cases (Unicode, empty strings, concurrent access)

### Run Tests

```bash
cd hooks/slack
chmod +x run_encryption_tests.sh
./run_encryption_tests.sh
```

Or manually:
```bash
python3 -m pytest tests/test_encryption.py -v
```

### Test Coverage

The test suite includes:

- **Key Management Tests** (6 tests)
  - Key generation
  - Key persistence
  - Directory creation
  - Permission validation
  - Fernet compatibility

- **Encryption/Decryption Tests** (10 tests)
  - Base64 encoding
  - Roundtrip consistency
  - Unique ciphertexts (nonce)
  - Empty strings
  - Unicode characters
  - Long values
  - Wrong key detection
  - Invalid ciphertext handling

- **Value Detection Tests** (4 tests)
  - Encrypted value detection
  - Plaintext value detection
  - None/null handling
  - Non-string types

- **Key Rotation Tests** (3 tests)
  - New key generation
  - Old key preservation
  - Re-encryption with new key

- **Security Tests** (4 tests)
  - No plaintext logging
  - Generic error messages
  - Secure file permissions
  - Non-world-readable keys

- **Edge Cases Tests** (5 tests)
  - Path expansion (~)
  - Concurrent key generation
  - Corrupted key files
  - Read-only directories
  - Default key path

**Total: 32 comprehensive tests**

## Usage in V2 Architecture

### Storing Encrypted Config

```python
import sqlite3
from lib import encryption

# Encrypt webhook URL before storing
webhook_url = "https://hooks.slack.com/services/SECRET"
encrypted_url = encryption.encrypt(webhook_url)

# Store in config table
db = sqlite3.connect("~/.claude/state/notifications.db")
db.execute("""
    INSERT INTO config (key, value, is_encrypted, updated_at)
    VALUES ('slack_webhook_url', ?, 1, ?)
""", (encrypted_url, int(time.time())))
db.commit()
```

### Loading Encrypted Config

```python
# Load from database
row = db.execute(
    "SELECT value, is_encrypted FROM config WHERE key='slack_webhook_url'"
).fetchone()

if row:
    value, is_encrypted = row
    if is_encrypted:
        webhook_url = encryption.decrypt(value)
    else:
        webhook_url = value
```

### Migration from V1 (Plaintext)

```python
# Load V1 config
with open("~/.claude/config/slack-config.json") as f:
    v1_config = json.load(f)

plaintext_url = v1_config['webhook_url']

# Encrypt for V2
encrypted_url = encryption.encrypt(plaintext_url)

# Store in V2 database
db.execute("""
    INSERT INTO config (key, value, is_encrypted, updated_at)
    VALUES ('slack_webhook_url', ?, 1, ?)
""", (encrypted_url, int(time.time())))
```

## Security Considerations

### Key Storage
- Key file stored at `~/.claude/state/encryption.key`
- Permissions: 0o600 (read/write for owner only)
- Warning printed to stderr if permissions are insecure
- Key never logged or displayed

### Encryption Algorithm
- **Algorithm:** Fernet (symmetric encryption)
- **Cipher:** AES-128 in CBC mode
- **Authentication:** HMAC-SHA256
- **Key derivation:** None (raw key)
- **Nonce:** Random, unique per encryption

### Threat Model
**Protected against:**
- Accidental exposure (config files in git)
- File system access by other users
- Plaintext logging/debugging

**NOT protected against:**
- Root/admin access to key file
- Memory inspection of running process
- Physical access to machine

### Best Practices
1. **Never commit key file to git** - Add to `.gitignore`
2. **Backup key securely** - Loss of key = loss of data
3. **Rotate keys periodically** - Use `rotate_key()` + `reencrypt_value()`
4. **Validate permissions** - Check for warnings in logs
5. **Use default path** - Avoid custom paths unless necessary

## File Structure

```
hooks/slack/lib/
├── encryption.py           # Implementation (this module)
└── ENCRYPTION_README.md    # Documentation (this file)

hooks/slack/tests/
├── test_encryption.py      # Comprehensive test suite (32 tests)
└── conftest.py             # Shared fixtures

~/.claude/state/
└── encryption.key          # Generated encryption key (0o600)
```

## Troubleshooting

### Error: "WARNING: Encryption key file has insecure permissions"

**Cause:** Key file permissions are not 0o600

**Fix:**
```bash
chmod 600 ~/.claude/state/encryption.key
```

### Error: "Decryption failed: invalid ciphertext or wrong key"

**Causes:**
1. Ciphertext was encrypted with a different key
2. Ciphertext is corrupted
3. Value is not actually encrypted (use `is_encrypted()` first)

**Fix:**
```python
# Check if value is encrypted before decrypting
if encryption.is_encrypted(value):
    value = encryption.decrypt(value)
else:
    # Value is plaintext, use as-is
    pass
```

### Error: "Failed to write encryption key: [Errno 13] Permission denied"

**Cause:** Cannot write to `~/.claude/state/` directory

**Fix:**
```bash
mkdir -p ~/.claude/state
chmod 755 ~/.claude/state
```

### Key Rotation Not Working

**Common issues:**
1. Old key file deleted before re-encrypting all values
2. Config still references old ciphertext
3. Database not updated with new ciphertext

**Correct rotation process:**
```python
# 1. Generate new key (preserves old key)
new_key = rotate_key(old_key_path, new_key_path)

# 2. Re-encrypt ALL values in database
db = sqlite3.connect("~/.claude/state/notifications.db")
rows = db.execute("SELECT key, value FROM config WHERE is_encrypted=1").fetchall()

for key, old_cipher in rows:
    new_cipher = reencrypt_value(old_cipher, old_key_path, new_key_path)
    db.execute("UPDATE config SET value=? WHERE key=?", (new_cipher, key))

db.commit()

# 3. Verify new key works
test_value = decrypt(new_cipher, new_key_path)

# 4. Only NOW delete old key
os.remove(old_key_path)
```

## Future Enhancements

### Potential Improvements
- [ ] Support for asymmetric encryption (public/private keys)
- [ ] Key derivation from password (PBKDF2)
- [ ] Hardware security module (HSM) integration
- [ ] Automatic key rotation on schedule
- [ ] Encryption audit log (who encrypted/decrypted what)
- [ ] Support for multiple keys (key versioning)

### Integration Ideas
- [ ] Encrypt other sensitive config (API tokens, passwords)
- [ ] Encrypted session transcripts
- [ ] Encrypted audit logs
- [ ] Encrypted metrics (PII protection)

## References

- [Cryptography library documentation](https://cryptography.io/en/latest/fernet/)
- [Fernet spec](https://github.com/fernet/spec/blob/master/Spec.md)
- [PRD V2: Section 8.1 Credential Encryption](../docs/PRD_SLACK_NOTIFICATIONS_V2_OPTIMIZED.md#81-credential-encryption)

## License

Part of claude-code-plugins-productivities project.
