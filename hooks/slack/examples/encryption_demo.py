#!/usr/bin/env python3
"""
Demonstration of encryption module functionality.

This script shows practical usage of the credential encryption module
for securing Slack webhook URLs and other sensitive configuration values.

Run: python3 examples/encryption_demo.py
"""
import sys
import os
from pathlib import Path

# Add lib directory to path
SLACK_DIR = Path(__file__).parent.parent
sys.path.insert(0, str(SLACK_DIR / "lib"))

import encryption


def demo_basic_encryption():
    """Demonstrate basic encryption and decryption."""
    print("=" * 60)
    print("Demo 1: Basic Encryption/Decryption")
    print("=" * 60)

    # Example webhook URL (placeholder for demo)
    webhook_url = "https://example.com/webhook/test-placeholder"
    print(f"Original (plaintext): {webhook_url}")

    # Encrypt
    encrypted = encryption.encrypt(webhook_url)
    print(f"Encrypted (base64):   {encrypted}")
    print(f"Length:               {len(encrypted)} bytes")

    # Decrypt
    decrypted = encryption.decrypt(encrypted)
    print(f"Decrypted:            {decrypted}")

    # Verify
    assert decrypted == webhook_url, "Decryption failed!"
    print("✓ Encryption/decryption successful\n")


def demo_unique_ciphertexts():
    """Demonstrate that same plaintext produces different ciphertexts."""
    print("=" * 60)
    print("Demo 2: Unique Ciphertexts (Nonce)")
    print("=" * 60)

    secret = "my_secret_webhook_url"
    print(f"Plaintext: {secret}\n")

    # Encrypt same value multiple times
    ciphertexts = []
    for i in range(3):
        cipher = encryption.encrypt(secret)
        ciphertexts.append(cipher)
        print(f"Encryption {i+1}: {cipher}")

    # Verify all different
    print(f"\nAll unique? {len(set(ciphertexts)) == 3}")

    # But all decrypt to same value
    print("All decrypt to same value?", end=" ")
    decrypted_values = [encryption.decrypt(c) for c in ciphertexts]
    print(all(d == secret for d in decrypted_values))
    print("✓ Nonce working correctly (security feature)\n")


def demo_encrypted_detection():
    """Demonstrate encrypted value detection."""
    print("=" * 60)
    print("Demo 3: Encrypted Value Detection")
    print("=" * 60)

    values = [
        ("Encrypted value", encryption.encrypt("secret")),
        ("Plaintext URL", "https://example.com/webhook/test"),
        ("Regular string", "just_a_string"),
        ("Empty string", ""),
        ("None", None),
    ]

    for label, value in values:
        is_enc = encryption.is_encrypted(value)
        print(f"{label:20s} → is_encrypted={is_enc}")

    print("✓ Detection working correctly\n")


def demo_key_rotation():
    """Demonstrate key rotation process."""
    print("=" * 60)
    print("Demo 4: Key Rotation")
    print("=" * 60)

    import tempfile

    # Create temporary keys
    with tempfile.TemporaryDirectory() as tmpdir:
        old_key_path = os.path.join(tmpdir, "old.key")
        new_key_path = os.path.join(tmpdir, "new.key")

        # Encrypt with old key
        secret = "webhook_url_to_rotate"
        old_cipher = encryption.encrypt(secret, old_key_path)
        print(f"Original secret:  {secret}")
        print(f"Old key path:     {old_key_path}")
        print(f"Old ciphertext:   {old_cipher}")

        # Rotate key
        print("\n[Rotating key...]")
        new_key = encryption.rotate_key(old_key_path, new_key_path)
        print(f"New key path:     {new_key_path}")

        # Re-encrypt with new key
        new_cipher = encryption.reencrypt_value(old_cipher, old_key_path, new_key_path)
        print(f"New ciphertext:   {new_cipher}")

        # Verify both keys still work
        print("\n[Verifying...]")
        old_decrypted = encryption.decrypt(old_cipher, old_key_path)
        new_decrypted = encryption.decrypt(new_cipher, new_key_path)

        print(f"Old key decrypts: {old_decrypted}")
        print(f"New key decrypts: {new_decrypted}")

        assert old_decrypted == new_decrypted == secret
        print("✓ Key rotation successful\n")


def demo_convenience_functions():
    """Demonstrate convenience functions."""
    print("=" * 60)
    print("Demo 5: Convenience Functions")
    print("=" * 60)

    # encrypt_if_needed (idempotent)
    print("Testing encrypt_if_needed (idempotent):")
    value = "plaintext_url"
    print(f"  Original:        {value}")

    encrypted1 = encryption.encrypt_if_needed(value)
    print(f"  After 1st call:  {encrypted1[:50]}...")

    encrypted2 = encryption.encrypt_if_needed(encrypted1)
    print(f"  After 2nd call:  {encrypted2[:50]}...")

    print(f"  Same? {encrypted1 == encrypted2} (should be True - no double encryption)")

    # decrypt_if_needed
    print("\nTesting decrypt_if_needed:")
    plaintext = encryption.decrypt_if_needed("plaintext")
    print(f"  Plaintext → {plaintext}")

    encrypted = encryption.encrypt("secret")
    decrypted = encryption.decrypt_if_needed(encrypted)
    print(f"  Encrypted → {decrypted}")

    print("✓ Convenience functions working\n")


def demo_error_handling():
    """Demonstrate error handling."""
    print("=" * 60)
    print("Demo 6: Error Handling")
    print("=" * 60)

    # Invalid ciphertext
    print("1. Decrypting invalid ciphertext:")
    try:
        encryption.decrypt("invalid_ciphertext_12345")
        print("   ERROR: Should have raised DecryptionError")
    except encryption.DecryptionError as e:
        print(f"   ✓ Caught DecryptionError: {e}")

    # Empty ciphertext
    print("\n2. Decrypting empty string:")
    try:
        encryption.decrypt("")
        print("   ERROR: Should have raised DecryptionError")
    except encryption.DecryptionError as e:
        print(f"   ✓ Caught DecryptionError: {e}")

    # Wrong key
    print("\n3. Decrypting with wrong key:")
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        key1 = os.path.join(tmpdir, "key1.key")
        key2 = os.path.join(tmpdir, "key2.key")

        cipher = encryption.encrypt("secret", key1)

        try:
            encryption.decrypt(cipher, key2)
            print("   ERROR: Should have raised DecryptionError")
        except encryption.DecryptionError as e:
            print(f"   ✓ Caught DecryptionError: {e}")

    print("\n✓ Error handling working correctly\n")


def demo_real_world_usage():
    """Demonstrate real-world usage scenario."""
    print("=" * 60)
    print("Demo 7: Real-World Usage (Config Storage)")
    print("=" * 60)

    import sqlite3
    import tempfile
    import time

    # Simulate V2 database
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test.db")
        db = sqlite3.connect(db_path)

        # Create config table
        db.execute("""
            CREATE TABLE config (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                is_encrypted INTEGER DEFAULT 0,
                updated_at INTEGER NOT NULL
            )
        """)

        # Store encrypted webhook URL
        webhook_url = "https://example.com/webhook/your-secret-token"
        encrypted_url = encryption.encrypt(webhook_url)

        db.execute("""
            INSERT INTO config (key, value, is_encrypted, updated_at)
            VALUES (?, ?, 1, ?)
        """, ("slack_webhook_url", encrypted_url, int(time.time())))
        db.commit()

        print(f"Stored encrypted webhook URL in database")
        print(f"Ciphertext (first 50 chars): {encrypted_url[:50]}...")

        # Load and decrypt
        row = db.execute(
            "SELECT value, is_encrypted FROM config WHERE key='slack_webhook_url'"
        ).fetchone()

        if row:
            value, is_encrypted = row
            if is_encrypted:
                loaded_url = encryption.decrypt(value)
            else:
                loaded_url = value

            print(f"\nLoaded from database: {loaded_url}")
            assert loaded_url == webhook_url
            print("✓ Real-world usage successful")

        db.close()


def main():
    """Run all demonstrations."""
    print("\n" + "=" * 60)
    print("CREDENTIAL ENCRYPTION MODULE - DEMONSTRATION")
    print("=" * 60)
    print()

    demos = [
        demo_basic_encryption,
        demo_unique_ciphertexts,
        demo_encrypted_detection,
        demo_key_rotation,
        demo_convenience_functions,
        demo_error_handling,
        demo_real_world_usage,
    ]

    for demo in demos:
        try:
            demo()
        except Exception as e:
            print(f"ERROR in {demo.__name__}: {e}")
            import traceback
            traceback.print_exc()

    print("=" * 60)
    print("ALL DEMONSTRATIONS COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
