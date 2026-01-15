#!/usr/bin/env python3
"""
CLI tool to delete SSH keys from the database.
This is useful for removing incorrectly generated keys or cleaning up.

Usage:
  python3 delete_ssh_key.py --id <key_id>
  python3 delete_ssh_key.py --name <key_name>
  python3 delete_ssh_key.py --system  # Delete the system key
"""
import os
import sys
import sqlite3
import argparse
from pathlib import Path


def delete_ssh_key(key_id=None, key_name=None, is_system=False, force=False):
    """Delete SSH key from database and filesystem"""
    try:
        # Connect to database
        db_path = Path("/data/borg.db")
        if not db_path.exists():
            print("✗ Error: Database not found at /data/borg.db", file=sys.stderr)
            return 1

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Find the key to delete
        if is_system:
            cursor.execute("SELECT id, name, key_type, is_system_key FROM ssh_keys WHERE is_system_key = 1")
        elif key_id:
            cursor.execute("SELECT id, name, key_type, is_system_key FROM ssh_keys WHERE id = ?", (key_id,))
        elif key_name:
            cursor.execute("SELECT id, name, key_type, is_system_key FROM ssh_keys WHERE name = ?", (key_name,))
        else:
            print("✗ Error: Must specify --id, --name, or --system", file=sys.stderr)
            conn.close()
            return 1

        row = cursor.fetchone()
        if not row:
            if is_system:
                print("ℹ️  No system SSH key found")
            elif key_id:
                print(f"ℹ️  No SSH key found with ID {key_id}")
            elif key_name:
                print(f"ℹ️  No SSH key found with name '{key_name}'")
            conn.close()
            return 0

        found_id, found_name, key_type, is_system_key = row

        # Check for active connections and repositories
        cursor.execute("SELECT COUNT(*) FROM ssh_connections WHERE ssh_key_id = ?", (found_id,))
        connection_count = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM repositories WHERE ssh_key_id = ?", (found_id,))
        repository_count = cursor.fetchone()[0]

        # Show warning and ask for confirmation
        print(f"\n⚠️  WARNING: You are about to delete the following SSH key:")
        print(f"  ID: {found_id}")
        print(f"  Name: {found_name}")
        print(f"  Type: {key_type}")
        print(f"  System Key: {'Yes' if is_system_key else 'No'}")
        print(f"  Active Connections: {connection_count}")
        print(f"  Repositories Using Key: {repository_count}")

        if connection_count > 0:
            print(f"\nℹ️  This key has {connection_count} active connection(s).")
            print("  Connections will be preserved but marked as failed.")
            print("  You can deploy a new key to these hosts to restore access.")

        if repository_count > 0:
            print(f"\nℹ️  This key is used by {repository_count} repository/repositories.")
            print("  The key reference will be cleared from these repositories.")

        if is_system_key:
            print("\n⚠️  This is the SYSTEM KEY! Deleting it will remove the key used for remote access.")
            print("  You will need to generate or import a new key and deploy it to your hosts.")

        if not force:
            print("\nType 'yes' to confirm deletion: ", end='')
            confirmation = input().strip().lower()
            if confirmation != 'yes':
                print("Deletion cancelled.")
                conn.close()
                return 0

        # Clear SSH key from repositories
        if repository_count > 0:
            cursor.execute(
                "UPDATE repositories SET ssh_key_id = NULL WHERE ssh_key_id = ?",
                (found_id,)
            )
            print(f"\n✓ Cleared SSH key from {repository_count} repository/repositories")

        # Preserve SSH connections but mark them as failed
        if connection_count > 0:
            error_msg = f"SSH key '{found_name}' was deleted. Deploy a new key to restore access."
            cursor.execute(
                "UPDATE ssh_connections SET ssh_key_id = NULL, status = 'failed', error_message = ? WHERE ssh_key_id = ?",
                (error_msg, found_id)
            )
            print(f"✓ Preserved {connection_count} SSH connection(s) (marked as failed)")

        # Delete the SSH key
        cursor.execute("DELETE FROM ssh_keys WHERE id = ?", (found_id,))
        conn.commit()
        print(f"✓ Deleted SSH key: {found_name} (ID: {found_id})")

        # Remove key files from filesystem
        ssh_dir = Path("/home/borg/.ssh")
        private_key_file = ssh_dir / f"id_{key_type}"
        public_key_file = ssh_dir / f"id_{key_type}.pub"

        if private_key_file.exists():
            private_key_file.unlink()
            print(f"✓ Removed private key file: {private_key_file}")

        if public_key_file.exists():
            public_key_file.unlink()
            print(f"✓ Removed public key file: {public_key_file}")

        conn.close()

        print("\n✓ SSH key deletion completed successfully")
        return 0

    except Exception as e:
        print(f"✗ Error deleting SSH key: {e}", file=sys.stderr)
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="Delete SSH keys from Borg UI database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Delete by key ID
  python3 delete_ssh_key.py --id 1

  # Delete by key name
  python3 delete_ssh_key.py --name "My SSH Key"

  # Delete system key
  python3 delete_ssh_key.py --system

  # Force delete without confirmation (use with caution!)
  python3 delete_ssh_key.py --system --force
        """
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--id', type=int, help='ID of the SSH key to delete')
    group.add_argument('--name', type=str, help='Name of the SSH key to delete')
    group.add_argument('--system', action='store_true', help='Delete the system SSH key')

    parser.add_argument('--force', action='store_true', help='Skip confirmation prompt')

    args = parser.parse_args()

    return delete_ssh_key(
        key_id=args.id,
        key_name=args.name,
        is_system=args.system,
        force=args.force
    )


if __name__ == "__main__":
    sys.exit(main())
