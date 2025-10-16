#!/usr/bin/env python3
"""
Deploy SSH keys from database to filesystem on container startup.
This ensures SSH keys are always available for borg operations.
"""
import os
import stat
import sqlite3
import base64
import sys
from pathlib import Path
from cryptography.fernet import Fernet


def deploy_ssh_keys():
    """Deploy SSH keys from database to /root/.ssh/"""
    try:
        # Create .ssh directory
        ssh_dir = Path("/root/.ssh")
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)

        # Read SECRET_KEY
        secret_key_file = Path("/data/.secret_key")
        if not secret_key_file.exists():
            print("⚠️  No SECRET_KEY file found, skipping SSH key deployment")
            return

        secret_key = secret_key_file.read_text().strip()
        encryption_key = secret_key.encode()[:32]
        fernet = Fernet(base64.urlsafe_b64encode(encryption_key))

        # Get SSH keys from database
        conn = sqlite3.connect("/data/borg.db")
        cursor = conn.cursor()
        cursor.execute("SELECT private_key, key_type, public_key FROM ssh_keys WHERE is_system_key = 1")
        row = cursor.fetchone()

        if not row:
            print("ℹ️  No system SSH key found in database")
            conn.close()
            return

        encrypted_key, key_type, public_key = row
        private_key = fernet.decrypt(encrypted_key.encode()).decode()

        # Write private key
        key_file = ssh_dir / f"id_{key_type}"
        key_file.write_text(private_key)
        key_file.chmod(0o600)

        # Write public key
        pub_key_file = ssh_dir / f"id_{key_type}.pub"
        pub_key_file.write_text(public_key)
        pub_key_file.chmod(0o644)

        print(f"✓ SSH keys deployed to {ssh_dir}")
        print(f"  - Private key: {key_file}")
        print(f"  - Public key: {pub_key_file}")

        conn.close()

    except Exception as e:
        print(f"✗ Error deploying SSH keys: {e}", file=sys.stderr)
        # Don't fail container startup if SSH keys can't be deployed
        # They might not exist yet (first run)


if __name__ == "__main__":
    deploy_ssh_keys()
