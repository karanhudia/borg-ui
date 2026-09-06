#!/usr/bin/env python3
"""
Deploy SSH keys from database to filesystem on container startup.
This ensures SSH keys are always available for borg operations.

All paths come from app.config: the key pair is written to
settings.ssh_home_dir and decrypted with settings.secret_key, so the same
script works in Docker (DATA_DIR=/data, SSH_HOME_DIR=/home/borg/.ssh) and in a
native install where the data directory lives elsewhere.
"""

import os
import sys
import pwd
import grp
from pathlib import Path

# Run as a file (`python3 deploy_ssh_key.py`), so the repository root is not on
# sys.path by itself.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config import settings  # noqa: E402
from app.core.security import decrypt_secret  # noqa: E402


def deploy_ssh_keys():
    """Deploy SSH keys from database to settings.ssh_home_dir."""
    try:
        # Create the SSH directory the keys are deployed to. In Docker this is
        # /home/borg/.ssh, which the entrypoint symlinks to $DATA_DIR/ssh_keys;
        # elsewhere it defaults to $DATA_DIR/ssh_keys directly.
        ssh_dir = Path(settings.ssh_home_dir)
        ssh_dir.mkdir(parents=True, exist_ok=True)
        ssh_dir.chmod(0o700)

        # Read the system SSH key from whichever database the app is configured
        # for. Going through the ORM (not a hardcoded sqlite3 path) means this
        # follows DATABASE_URL to Postgres when set, and never creates a stray
        # SQLite file when the real database lives elsewhere.
        from app.database.database import SessionLocal
        from app.database.models import SSHKey

        db = SessionLocal()
        try:
            key = db.query(SSHKey).filter(SSHKey.is_system_key.is_(True)).first()
        finally:
            db.close()

        if not key:
            print("ℹ️  No system SSH key found in database")
            return

        encrypted_key, key_type, public_key = (
            key.private_key,
            key.key_type,
            key.public_key,
        )
        # Same SECRET_KEY derivation (and legacy fallback) the app encrypts with.
        private_key = decrypt_secret(encrypted_key)

        # Write private key
        key_file = ssh_dir / f"id_{key_type}"
        key_file.write_text(private_key)
        key_file.chmod(0o600)

        # Write public key
        pub_key_file = ssh_dir / f"id_{key_type}.pub"
        pub_key_file.write_text(public_key)
        pub_key_file.chmod(0o644)

        # Change ownership to borg user
        try:
            borg_uid = pwd.getpwnam("borg").pw_uid
            borg_gid = grp.getgrnam("borg").gr_gid
            os.chown(ssh_dir, borg_uid, borg_gid)
            os.chown(key_file, borg_uid, borg_gid)
            os.chown(pub_key_file, borg_uid, borg_gid)
        except KeyError:
            print("⚠️  Warning: borg user not found, skipping ownership change")

        print(f"✓ SSH keys deployed to {ssh_dir}")
        print(f"  - Private key: {key_file}")
        print(f"  - Public key: {pub_key_file}")

    except Exception as e:
        print(f"✗ Error deploying SSH keys: {e}", file=sys.stderr)
        # Don't fail container startup if SSH keys can't be deployed
        # They might not exist yet (first run)


if __name__ == "__main__":
    deploy_ssh_keys()
