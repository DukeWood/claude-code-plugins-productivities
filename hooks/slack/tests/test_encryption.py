"""
Tests for credential encryption module (TDD approach).

This test suite verifies:
- Key generation and persistence
- Encryption/decryption roundtrip
- Encrypted value detection
- Key file permissions validation
- Key rotation support
- Error handling and security
"""
import os
import sys
import stat
import pytest
import tempfile
from pathlib import Path
from unittest.mock import patch

# Add lib directory to path for imports
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

import encryption


# =============================================================================
# Key Management Tests
# =============================================================================

class TestKeyManagement:
    """Test encryption key generation, storage, and retrieval."""

    def test_get_or_create_key_generates_new_key(self, tmp_path):
        """Should generate a new key if one doesn't exist."""
        key_path = tmp_path / "encryption.key"

        key = encryption.get_or_create_key(str(key_path))

        # Verify key was created
        assert key is not None
        assert isinstance(key, bytes)
        assert len(key) > 0
        assert key_path.exists()

        # Verify key file has correct permissions (0o600)
        file_stat = key_path.stat()
        file_mode = stat.S_IMODE(file_stat.st_mode)
        assert file_mode == 0o600, f"Expected 0o600, got {oct(file_mode)}"

    def test_get_or_create_key_loads_existing_key(self, tmp_path):
        """Should load existing key if one already exists."""
        key_path = tmp_path / "encryption.key"

        # Create key first time
        key1 = encryption.get_or_create_key(str(key_path))

        # Load key second time
        key2 = encryption.get_or_create_key(str(key_path))

        # Keys should be identical
        assert key1 == key2

    def test_get_or_create_key_creates_parent_directory(self, tmp_path):
        """Should create parent directories if they don't exist."""
        key_path = tmp_path / "state" / "nested" / "encryption.key"

        key = encryption.get_or_create_key(str(key_path))

        assert key is not None
        assert key_path.exists()
        assert key_path.parent.exists()

    def test_get_or_create_key_validates_permissions(self, tmp_path, capfd):
        """Should warn if key file has insecure permissions."""
        key_path = tmp_path / "encryption.key"

        # Create key with correct permissions first
        key = encryption.get_or_create_key(str(key_path))

        # Change permissions to insecure (0o644)
        key_path.chmod(0o644)

        # Load key again - should warn
        key2 = encryption.get_or_create_key(str(key_path))

        # Capture stderr output
        captured = capfd.readouterr()

        # Should warn about insecure permissions
        assert "WARNING" in captured.err or "warning" in captured.err.lower()
        assert "0o600" in captured.err or "600" in captured.err

        # But should still load the key
        assert key2 == key

    def test_key_is_valid_fernet_key(self, tmp_path):
        """Generated key should be a valid Fernet key."""
        from cryptography.fernet import Fernet

        key_path = tmp_path / "encryption.key"
        key = encryption.get_or_create_key(str(key_path))

        # Should be able to create Fernet instance
        f = Fernet(key)
        assert f is not None


# =============================================================================
# Encryption/Decryption Tests
# =============================================================================

class TestEncryptionDecryption:
    """Test encryption and decryption of plaintext values."""

    def test_encrypt_returns_base64_string(self, tmp_path):
        """Encrypted value should be a base64-encoded string."""
        key_path = tmp_path / "encryption.key"
        plaintext = "https://hooks.slack.com/services/SECRET"

        ciphertext = encryption.encrypt(plaintext, str(key_path))

        assert isinstance(ciphertext, str)
        assert len(ciphertext) > 0
        assert ciphertext != plaintext

        # Fernet uses URL-safe base64 (with - and _ instead of + and /)
        import base64
        try:
            base64.urlsafe_b64decode(ciphertext)
        except Exception:
            pytest.fail("Ciphertext is not valid URL-safe base64")

    def test_encrypt_decrypt_roundtrip(self, tmp_path):
        """Encrypting then decrypting should return original value."""
        key_path = tmp_path / "encryption.key"
        plaintext = "https://example.com/webhook/your-secret-token"

        ciphertext = encryption.encrypt(plaintext, str(key_path))
        decrypted = encryption.decrypt(ciphertext, str(key_path))

        assert decrypted == plaintext

    def test_encrypt_different_values_produce_different_ciphertexts(self, tmp_path):
        """Same key should encrypt different values differently."""
        key_path = tmp_path / "encryption.key"

        ciphertext1 = encryption.encrypt("secret1", str(key_path))
        ciphertext2 = encryption.encrypt("secret2", str(key_path))

        assert ciphertext1 != ciphertext2

    def test_encrypt_same_value_twice_produces_different_ciphertexts(self, tmp_path):
        """Fernet should add randomness (nonce) to each encryption."""
        key_path = tmp_path / "encryption.key"
        plaintext = "same_secret"

        ciphertext1 = encryption.encrypt(plaintext, str(key_path))
        ciphertext2 = encryption.encrypt(plaintext, str(key_path))

        # Due to Fernet's nonce, same plaintext produces different ciphertext
        assert ciphertext1 != ciphertext2

        # But both should decrypt to same value
        assert encryption.decrypt(ciphertext1, str(key_path)) == plaintext
        assert encryption.decrypt(ciphertext2, str(key_path)) == plaintext

    def test_encrypt_empty_string(self, tmp_path):
        """Should handle empty string encryption."""
        key_path = tmp_path / "encryption.key"

        ciphertext = encryption.encrypt("", str(key_path))
        decrypted = encryption.decrypt(ciphertext, str(key_path))

        assert decrypted == ""

    def test_encrypt_unicode_characters(self, tmp_path):
        """Should handle Unicode characters in plaintext."""
        key_path = tmp_path / "encryption.key"
        plaintext = "Secret with émojis 🔐🔑 and 中文"

        ciphertext = encryption.encrypt(plaintext, str(key_path))
        decrypted = encryption.decrypt(ciphertext, str(key_path))

        assert decrypted == plaintext

    def test_encrypt_long_value(self, tmp_path):
        """Should handle long webhook URLs."""
        key_path = tmp_path / "encryption.key"
        # Test with long URL string
        plaintext = "https://example.com/webhook/test-placeholder-for-long-value-testing" * 3

        ciphertext = encryption.encrypt(plaintext, str(key_path))
        decrypted = encryption.decrypt(ciphertext, str(key_path))

        assert decrypted == plaintext

    def test_decrypt_with_wrong_key_raises_error(self, tmp_path):
        """Decrypting with wrong key should raise an error."""
        key_path1 = tmp_path / "key1.key"
        key_path2 = tmp_path / "key2.key"

        plaintext = "secret"
        ciphertext = encryption.encrypt(plaintext, str(key_path1))

        # Try to decrypt with different key
        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt(ciphertext, str(key_path2))

    def test_decrypt_invalid_ciphertext_raises_error(self, tmp_path):
        """Decrypting invalid ciphertext should raise DecryptionError."""
        key_path = tmp_path / "encryption.key"

        # Create key first
        encryption.get_or_create_key(str(key_path))

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt("not_valid_ciphertext", str(key_path))

    def test_decrypt_empty_string_raises_error(self, tmp_path):
        """Decrypting empty string should raise DecryptionError."""
        key_path = tmp_path / "encryption.key"

        # Create key first
        encryption.get_or_create_key(str(key_path))

        with pytest.raises(encryption.DecryptionError):
            encryption.decrypt("", str(key_path))


# =============================================================================
# Encrypted Value Detection Tests
# =============================================================================

class TestEncryptedValueDetection:
    """Test detection of encrypted vs plaintext values."""

    def test_is_encrypted_detects_encrypted_value(self, tmp_path):
        """Should return True for encrypted values."""
        key_path = tmp_path / "encryption.key"
        plaintext = "https://hooks.slack.com/services/SECRET"

        ciphertext = encryption.encrypt(plaintext, str(key_path))

        assert encryption.is_encrypted(ciphertext) is True

    def test_is_encrypted_detects_plaintext_value(self):
        """Should return False for plaintext values."""
        plaintext_values = [
            "https://hooks.slack.com/services/SECRET",
            "just_a_regular_string",
            "12345",
            "",
            "some base64-looking but not encrypted: SGVsbG8gV29ybGQ="
        ]

        for value in plaintext_values:
            assert encryption.is_encrypted(value) is False

    def test_is_encrypted_handles_none(self):
        """Should return False for None."""
        assert encryption.is_encrypted(None) is False

    def test_is_encrypted_handles_non_string(self):
        """Should return False for non-string types."""
        assert encryption.is_encrypted(12345) is False
        assert encryption.is_encrypted({"key": "value"}) is False
        assert encryption.is_encrypted([1, 2, 3]) is False


# =============================================================================
# Key Rotation Tests
# =============================================================================

class TestKeyRotation:
    """Test key rotation functionality."""

    def test_rotate_key_creates_new_key(self, tmp_path):
        """Should create a new key file at new path."""
        old_key_path = tmp_path / "old.key"
        new_key_path = tmp_path / "new.key"

        # Create old key
        old_key = encryption.get_or_create_key(str(old_key_path))

        # Rotate to new key
        new_key = encryption.rotate_key(str(old_key_path), str(new_key_path))

        assert new_key_path.exists()
        assert new_key != old_key

    def test_rotate_key_preserves_old_key(self, tmp_path):
        """Should keep old key file intact."""
        old_key_path = tmp_path / "old.key"
        new_key_path = tmp_path / "new.key"

        old_key = encryption.get_or_create_key(str(old_key_path))
        encryption.rotate_key(str(old_key_path), str(new_key_path))

        # Old key should still exist
        assert old_key_path.exists()

        # Old key should be unchanged
        reloaded_old_key = encryption.get_or_create_key(str(old_key_path))
        assert reloaded_old_key == old_key

    def test_reencrypt_value_with_new_key(self, tmp_path):
        """Should re-encrypt a value with a new key."""
        old_key_path = tmp_path / "old.key"
        new_key_path = tmp_path / "new.key"
        plaintext = "https://hooks.slack.com/services/SECRET"

        # Encrypt with old key
        old_ciphertext = encryption.encrypt(plaintext, str(old_key_path))

        # Rotate key
        encryption.rotate_key(str(old_key_path), str(new_key_path))

        # Re-encrypt with new key
        new_ciphertext = encryption.reencrypt_value(
            old_ciphertext,
            str(old_key_path),
            str(new_key_path)
        )

        # Should be different ciphertext
        assert new_ciphertext != old_ciphertext

        # Should decrypt to same plaintext with new key
        decrypted = encryption.decrypt(new_ciphertext, str(new_key_path))
        assert decrypted == plaintext

        # Old ciphertext should still decrypt with old key
        old_decrypted = encryption.decrypt(old_ciphertext, str(old_key_path))
        assert old_decrypted == plaintext


# =============================================================================
# Security Tests
# =============================================================================

class TestSecurity:
    """Test security-related functionality."""

    def test_encrypt_never_logs_plaintext(self, tmp_path, capfd):
        """Encryption should never log plaintext values."""
        key_path = tmp_path / "encryption.key"
        secret = "SUPER_SECRET_WEBHOOK_URL_12345"

        encryption.encrypt(secret, str(key_path))

        captured = capfd.readouterr()

        # Secret should not appear in stdout or stderr
        assert secret not in captured.out
        assert secret not in captured.err

    def test_decrypt_never_logs_plaintext(self, tmp_path, capfd):
        """Decryption should never log plaintext values."""
        key_path = tmp_path / "encryption.key"
        secret = "SUPER_SECRET_WEBHOOK_URL_12345"

        ciphertext = encryption.encrypt(secret, str(key_path))
        encryption.decrypt(ciphertext, str(key_path))

        captured = capfd.readouterr()

        # Secret should not appear in stdout or stderr
        assert secret not in captured.out
        assert secret not in captured.err

    def test_decryption_error_does_not_leak_partial_data(self, tmp_path, capfd):
        """DecryptionError should not include plaintext in error message."""
        key_path = tmp_path / "encryption.key"

        # Create key
        encryption.get_or_create_key(str(key_path))

        try:
            encryption.decrypt("invalid_ciphertext", str(key_path))
        except encryption.DecryptionError as e:
            error_msg = str(e)
            # Error message should be generic
            assert "invalid_ciphertext" not in error_msg.lower() or len(error_msg) < 100

    def test_key_file_not_world_readable(self, tmp_path):
        """Key file should not be readable by other users."""
        key_path = tmp_path / "encryption.key"

        encryption.get_or_create_key(str(key_path))

        file_stat = key_path.stat()
        file_mode = stat.S_IMODE(file_stat.st_mode)

        # Check that group and other have no permissions
        assert file_mode & 0o077 == 0, f"Key file is world/group readable: {oct(file_mode)}"


# =============================================================================
# Default Key Path Tests
# =============================================================================

class TestDefaultKeyPath:
    """Test using default key path (~/.claude/state/encryption.key)."""

    def test_encrypt_with_default_path(self, tmp_path):
        """Should use DEFAULT_KEY_PATH if no path provided."""
        # Create a fake default key path
        fake_key_path = tmp_path / "encryption.key"

        # Patch DEFAULT_KEY_PATH to use our temp path
        with patch.object(encryption, 'DEFAULT_KEY_PATH', str(fake_key_path)):
            plaintext = "secret"

            # Encrypt without specifying key_path
            ciphertext = encryption.encrypt(plaintext)

            # Verify key was created at the patched default path
            assert fake_key_path.exists()

            # Should be able to decrypt
            decrypted = encryption.decrypt(ciphertext)
            assert decrypted == plaintext

    def test_default_key_path_value(self):
        """Verify DEFAULT_KEY_PATH constant has correct format."""
        # DEFAULT_KEY_PATH is computed at module import time
        # Just verify it has the expected structure
        actual = encryption.DEFAULT_KEY_PATH

        # Should be an expanded path (not starting with ~)
        assert not actual.startswith("~")

        # Should end with expected path components
        assert actual.endswith(".claude/state/encryption.key")

        # Should be an absolute path
        assert os.path.isabs(actual)


# =============================================================================
# Edge Cases and Error Handling
# =============================================================================

class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_key_path_expansion(self, monkeypatch, tmp_path):
        """Should expand ~ in key path."""
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        key_path = "~/test.key"
        plaintext = "secret"

        ciphertext = encryption.encrypt(plaintext, key_path)

        # Key should be created in expanded path
        expanded_path = fake_home / "test.key"
        assert expanded_path.exists()

    def test_concurrent_key_generation(self, tmp_path):
        """Multiple threads accessing key should all get valid Fernet keys."""
        import threading
        from cryptography.fernet import Fernet
        key_path = tmp_path / "encryption.key"
        results = []
        errors = []

        def generate_key():
            try:
                key = encryption.get_or_create_key(str(key_path))
                # Verify it's a valid Fernet key by using it
                f = Fernet(key)
                f.encrypt(b"test")  # Will raise if key is invalid
                results.append(key)
            except Exception as e:
                errors.append(e)

        # Simulate concurrent key generation
        threads = [threading.Thread(target=generate_key) for _ in range(5)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # All threads should complete without errors
        assert len(errors) == 0, f"Concurrent key generation produced errors: {errors}"
        assert len(results) == 5, "Not all threads completed"

        # All keys should be valid and usable
        for key in results:
            f = Fernet(key)
            f.encrypt(b"test")  # Verify each key is valid

    def test_key_file_corrupted(self, tmp_path):
        """Should handle corrupted key file gracefully."""
        key_path = tmp_path / "encryption.key"

        # Create corrupted key file
        key_path.write_bytes(b"corrupted_key_data")

        # Should raise error when trying to use it
        with pytest.raises(Exception):  # Could be ValueError or InvalidToken
            encryption.encrypt("test", str(key_path))

    def test_readonly_key_directory(self, tmp_path):
        """Should raise error if can't write key file."""
        # Create readonly directory
        readonly_dir = tmp_path / "readonly"
        readonly_dir.mkdir()
        readonly_dir.chmod(0o555)  # Read and execute only

        key_path = readonly_dir / "encryption.key"

        try:
            # Should raise PermissionError or similar
            with pytest.raises((PermissionError, OSError)):
                encryption.get_or_create_key(str(key_path))
        finally:
            # Cleanup: restore permissions
            readonly_dir.chmod(0o755)
