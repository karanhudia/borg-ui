"""
Migration 057: Populate connection_id for legacy SSH repositories

This migration migrates existing SSH repositories that were created before
the connection_id refactoring. It attempts to match them to existing SSH
connections based on host, port, and username.

Background:
- Old repos used repository_type='ssh' with separate host/port/username fields
- New approach uses connection_id to reference an SSHConnection record
- This migration bridges the gap for existing repositories
"""

from sqlalchemy import text


def upgrade(db):
    """Populate connection_id for legacy SSH repositories"""
    print("Running migration 057: Populate connection_id for legacy SSH repositories")

    try:
        # Find all SSH repositories without connection_id
        legacy_repos = db.execute(text("""
            SELECT id, name, host, port, username, ssh_key_id, repository_type
            FROM repositories
            WHERE repository_type = 'ssh'
              AND connection_id IS NULL
              AND host IS NOT NULL
        """)).fetchall()

        if not legacy_repos:
            print("✓ No legacy SSH repositories found - all repositories are up to date")
            db.commit()
            return

        print(f"Found {len(legacy_repos)} legacy SSH repositories to migrate")

        migrated = 0
        failed = 0

        for repo in legacy_repos:
            repo_id, name, host, port, username, ssh_key_id, repo_type = repo

            # Try to find matching SSH connection
            connection = db.execute(text("""
                SELECT id FROM ssh_connections
                WHERE host = :host
                  AND port = :port
                  AND username = :username
                LIMIT 1
            """), {
                'host': host,
                'port': port or 22,
                'username': username
            }).fetchone()

            if connection:
                connection_id = connection[0]

                # Update repository with connection_id
                db.execute(text("""
                    UPDATE repositories
                    SET connection_id = :connection_id
                    WHERE id = :repo_id
                """), {
                    'connection_id': connection_id,
                    'repo_id': repo_id
                })

                migrated += 1
                print(f"  ✓ Migrated '{name}' → connection_id={connection_id} ({username}@{host}:{port})")
            else:
                failed += 1
                print(f"  ⚠ WARNING: No SSH connection found for '{name}' ({username}@{host}:{port})")
                print(f"    → Repository will need manual configuration in the UI")

        db.commit()

        print(f"\n✓ Migration 057 completed:")
        print(f"  • Migrated: {migrated} repositories")
        if failed > 0:
            print(f"  • Failed: {failed} repositories (need manual configuration)")
        print(f"\nNote: Failed repositories still work with legacy fields,")
        print(f"but should be edited in the UI to select an SSH connection.")

    except Exception as e:
        print(f"✗ Migration 057 failed: {e}")
        db.rollback()
        raise


def downgrade(db):
    """Downgrade migration 057 - reset connection_id for migrated repos"""
    print("Running downgrade for migration 057")

    try:
        # Reset connection_id to NULL for SSH repos that were migrated
        db.execute(text("""
            UPDATE repositories
            SET connection_id = NULL
            WHERE repository_type = 'ssh'
              AND connection_id IS NOT NULL
        """))

        db.commit()
        print("✓ Downgrade completed for migration 057")

    except Exception as e:
        print(f"✗ Downgrade failed: {e}")
        db.rollback()
        raise
