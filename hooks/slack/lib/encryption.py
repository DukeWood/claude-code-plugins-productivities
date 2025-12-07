"""
Credential encryption module for Slack Notification V2.

This module provides Fernet symmetric encryption for sensitive config values
like webhook URLs. Key features:

- Automatic key generation and secure storage
- Base64-encoded ciphertext for JSON compatibility
- Key rotation support without data loss
- Secure key file permissions (0o600)
- Encrypted value detection

Security considerations:
- Never logs plaintext secrets
- Validates key file permissions
- Uses Fernet (AES-128 in CBC mode with HMAC)
- Each encryption includes unique nonce (randomness)

Usage:
    # Encrypt a webhook URL
    ciphertext = encrypt("https://hooks.slack.com/services/SECRET")

    # Decrypt later
    plaintext = decrypt(ciphertext)

    # Check if value is encrypted
    if is_encrypted(value):
        value = decrypt(value)

    # Rotate keys
    new_key = rotate_key(old_key_path, new_key_path)
    new_ciphertext = reencrypt_value(old_ciphertext, old_key_path, new_key_path)
"""
import os
import sys
import stat
from pathlib import Path
from cryptography.fernet import Fernet, InvalidToken


# =============================================================================
# Constants
# =============================================================================

DEFAULT_KEY_PATH = os.path.expanduser("~/.claude/state/encryption.key")


# =============================================================================
# Custom Exceptions
# =============================================================================

class DecryptionError(Exception):
    """Raised when decryption fails (wrong key, corrupted data, etc)."""
    pass


# =============================================================================
# Key Management
# =============================================================================

def get_or_create_key(key_path=None):
    """
    Get existing encryption key or generate a new one.

    Args:
        key_path: Path to key file (default: ~/.claude/state/encryption.key)

    Returns:
        bytes: Fernet encryption key

    Side effects:
        - Creates key file if it doesn't exist
        - Creates parent directories as needed
        - Sets file permissions to 0o600
        - Prints warning to stderr if permissions are insecure
    """
    if key_path is None:
        key_path = DEFAULT_KEY_PATH

    # Expand ~ in path
    key_path = os.path.expanduser(key_path)
    key_path_obj = Path(key_path)

    # If key exists, load it
    if key_path_obj.exists():
        # Validate permissions
        _validate_key_permissions(key_path_obj)

        # Load key
        try:
            with open(key_path, 'rb') as f:
                key = f.read()
            return key
        except Exception as e:
            raise ValueError(f"Failed to read encryption key: {e}")

    # Generate new key
    key = Fernet.generate_key()

    # Create parent directories
    key_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Write key to file
    try:
        with open(key_path, 'wb') as f:
            f.write(key)
    except Exception as e:
        raise PermissionError(f"Failed to write encryption key: {e}")

    # Set secure permissions (read/write for owner only)
    os.chmod(key_path, 0o600)

    return key


def _validate_key_permissions(key_path_obj):
    """
    Validate that key file has secure permissions (0o600).

    Prints warning to stderr if permissions are insecure, but doesn't fail.
    This allows the key to still be used, but alerts the user to fix permissions.

    Args:
        key_path_obj: Path object for key file
    """
    file_stat = key_path_obj.stat()
    file_mode = stat.S_IMODE(file_stat.st_mode)

    expected_mode = 0o600

    if file_mode != expected_mode:
        # Print warning to stderr
        print(
            f"WARNING: Encryption key file has insecure permissions: {oct(file_mode)}\n"
            f"Expected: 0o600 (read/write for owner only)\n"
            f"Fix with: chmod 600 {key_path_obj}",
            file=sys.stderr
        )


# =============================================================================
# Encryption/Decryption
# =============================================================================

def encrypt(plaintext, key_path=None):
    """
    Encrypt a plaintext string using Fernet symmetric encryption.

    Args:
        plaintext: String to encrypt (e.g., webhook URL)
        key_path: Path to encryption key (default: ~/.claude/state/encryption.key)

    Returns:
        str: Base64-encoded ciphertext (safe for JSON storage)

    Note:
        - Each encryption includes a unique nonce (randomness)
        - Same plaintext encrypted twice produces different ciphertexts
        - This is a security feature, not a bug
    """
    if not isinstance(plaintext, str):
        raise TypeError(f"plaintext must be str, got {type(plaintext)}")

    # Get encryption key
    key = get_or_create_key(key_path)

    # Create Fernet instance
    f = Fernet(key)

    # Encrypt (returns bytes)
    ciphertext_bytes = f.encrypt(plaintext.encode('utf-8'))

    # Return as base64 string
    return ciphertext_bytes.decode('ascii')


def decrypt(ciphertext, key_path=None):
    """
    Decrypt a Fernet-encrypted ciphertext.

    Args:
        ciphertext: Base64-encoded ciphertext from encrypt()
        key_path: Path to encryption key (must match key used for encryption)

    Returns:
        str: Decrypted plaintext

    Raises:
        DecryptionError: If decryption fails (wrong key, corrupted data, invalid format)

    Security:
        - Never logs plaintext values
        - Error messages are generic to avoid leaking data
    """
    if not ciphertext:
        raise DecryptionError("Ciphertext cannot be empty")

    if not isinstance(ciphertext, str):
        raise DecryptionError(f"Ciphertext must be str, got {type(ciphertext)}")

    # Get encryption key
    try:
        key = get_or_create_key(key_path)
    except Exception as e:
        raise DecryptionError(f"Failed to load encryption key: {e}")

    # Create Fernet instance
    f = Fernet(key)

    # Decrypt
    try:
        plaintext_bytes = f.decrypt(ciphertext.encode('ascii'))
        return plaintext_bytes.decode('utf-8')
    except InvalidToken:
        raise DecryptionError("Decryption failed: invalid ciphertext or wrong key")
    except Exception as e:
        raise DecryptionError(f"Decryption failed: {type(e).__name__}")


# =============================================================================
# Encrypted Value Detection
# =============================================================================

def is_encrypted(value):
    """
    Detect if a value is encrypted (vs plaintext).

    Uses heuristic: Fernet ciphertexts start with "gAAAAA" (base64-encoded version bytes).
    This is not 100% reliable but works for practical purposes.

    Args:
        value: Value to check (can be str, None, or other types)

    Returns:
        bool: True if value appears to be Fernet-encrypted, False otherwise

    Examples:
        >>> is_encrypted("gAAAAABf...")  # Encrypted
        True
        >>> is_encrypted("https://hooks.slack.com")  # Plaintext
        False
        >>> is_encrypted(None)
        False
    """
    if value is None:
        return False

    if not isinstance(value, str):
        return False

    if not value:
        return False

    # Fernet tokens start with version byte (0x80) which base64-encodes to 'gAAAAA'
    # This is a heuristic, not perfect, but good enough for our use case
    return value.startswith('gAAAAA')


# =============================================================================
# Key Rotation
# =============================================================================

def rotate_key(old_key_path=None, new_key_path=None):
    """
    Generate a new encryption key for key rotation.

    This creates a new key file at new_key_path, but preserves the old key.
    To complete rotation, re-encrypt all encrypted values using reencrypt_value().

    Args:
        old_key_path: Path to existing key (for reference)
        new_key_path: Path where new key should be created

    Returns:
        bytes: New encryption key

    Side effects:
        - Creates new key file at new_key_path
        - Old key file remains unchanged

    Example:
        # Step 1: Rotate key
        new_key = rotate_key(old_key_path, new_key_path)

        # Step 2: Re-encrypt all values
        new_ciphertext = reencrypt_value(old_ciphertext, old_key_path, new_key_path)

        # Step 3: Update config to use new ciphertext
        # Step 4: Delete old key file
    """
    if new_key_path is None:
        raise ValueError("new_key_path is required")

    # Generate new key
    new_key = Fernet.generate_key()

    # Create parent directories
    new_key_path_obj = Path(os.path.expanduser(new_key_path))
    new_key_path_obj.parent.mkdir(parents=True, exist_ok=True)

    # Write new key
    try:
        with open(new_key_path_obj, 'wb') as f:
            f.write(new_key)
    except Exception as e:
        raise PermissionError(f"Failed to write new encryption key: {e}")

    # Set secure permissions
    os.chmod(new_key_path_obj, 0o600)

    return new_key


def reencrypt_value(old_ciphertext, old_key_path, new_key_path):
    """
    Re-encrypt a value with a new key (for key rotation).

    Args:
        old_ciphertext: Ciphertext encrypted with old key
        old_key_path: Path to old encryption key
        new_key_path: Path to new encryption key

    Returns:
        str: New ciphertext encrypted with new key

    Raises:
        DecryptionError: If decryption with old key fails

    Example:
        # Rotate webhook URL encryption
        old_cipher = config.get('webhook_url')
        new_cipher = reencrypt_value(old_cipher, old_key_path, new_key_path)
        config.set('webhook_url', new_cipher)
    """
    # Decrypt with old key
    plaintext = decrypt(old_ciphertext, old_key_path)

    # Encrypt with new key
    new_ciphertext = encrypt(plaintext, new_key_path)

    return new_ciphertext


# =============================================================================
# Convenience Functions
# =============================================================================

def encrypt_if_needed(value, key_path=None):
    """
    Encrypt a value if it's not already encrypted.

    Args:
        value: Plaintext or ciphertext string
        key_path: Path to encryption key

    Returns:
        str: Encrypted value (either original if already encrypted, or newly encrypted)

    Example:
        # Idempotent encryption
        webhook_url = encrypt_if_needed(config.get('webhook_url'))
    """
    if is_encrypted(value):
        return value
    return encrypt(value, key_path)


def decrypt_if_needed(value, key_path=None):
    """
    Decrypt a value if it's encrypted, otherwise return as-is.

    Args:
        value: Ciphertext or plaintext string
        key_path: Path to encryption key

    Returns:
        str: Plaintext value

    Example:
        # Handle both encrypted and plaintext values
        webhook_url = decrypt_if_needed(config.get('webhook_url'))
    """
    if is_encrypted(value):
        return decrypt(value, key_path)
    return value
