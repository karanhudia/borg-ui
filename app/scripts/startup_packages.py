#!/usr/bin/env python3
"""
Start package installation jobs on container startup.
This ensures packages are automatically installed when the container starts.
Non-blocking - jobs run in the background via the FastAPI app's package service.
"""
import os
import sys
import asyncio
import sqlite3
from pathlib import Path


def is_package_actually_installed(package_name):
    """Check if a package is actually installed in the OS"""
    import subprocess
    try:
        # Try to check with dpkg (Debian/Ubuntu)
        result = subprocess.run(
            ["dpkg", "-s", package_name],
            capture_output=True,
            text=True,
            timeout=5
        )
        # If exit code is 0, package is installed
        return result.returncode == 0
    except Exception:
        return False


def get_packages_to_install():
    """
    Get list of packages that need to be installed.
    Verifies actual OS installation status, not just database status.
    """
    try:
        db_path = Path("/data/borg.db")
        if not db_path.exists():
            print("ℹ️  No database found, skipping package startup")
            return []

        conn = sqlite3.connect(str(db_path))
        cursor = conn.cursor()

        # Get ALL packages from database (regardless of status)
        # We'll verify actual installation below
        cursor.execute("""
            SELECT p.id, p.name, p.status, p.install_command
            FROM installed_packages p
            WHERE NOT EXISTS (
                SELECT 1 FROM package_install_jobs j
                WHERE j.package_id = p.id
                AND j.status IN ('pending', 'installing')
            )
        """)

        all_packages = cursor.fetchall()
        conn.close()

        # Filter packages: only install if NOT actually installed in OS
        packages_to_install = []
        for pkg_id, pkg_name, db_status, install_cmd in all_packages:
            actually_installed = is_package_actually_installed(pkg_name)

            if not actually_installed:
                # Package is in DB but not actually installed - need to install
                print(f"📦 Package '{pkg_name}' (DB status: {db_status}) not found in OS, will install")
                packages_to_install.append((pkg_id, pkg_name, "pending", install_cmd))

                # Update DB status to pending if it was marked as installed
                if db_status == "installed":
                    conn = sqlite3.connect(str(db_path))
                    cursor = conn.cursor()
                    cursor.execute("UPDATE installed_packages SET status='pending' WHERE id=?", (pkg_id,))
                    conn.commit()
                    conn.close()
            else:
                print(f"✓ Package '{pkg_name}' already installed in OS")

        return packages_to_install

    except Exception as e:
        print(f"✗ Error querying packages: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        return []


def trigger_package_installations(packages):
    """
    Trigger package installations by starting them directly.
    Runs installations synchronously in this startup script.
    """
    import subprocess
    import time

    if not packages:
        print("ℹ️  No packages to install")
        return

    print(f"🚀 Starting installation of {len(packages)} package(s)...")

    # Install packages one by one
    for package_id, package_name, status, install_command in packages:
        try:
            print(f"")
            print(f"{'='*60}")
            print(f"📦 Installing: {package_name}")
            print(f"{'='*60}")
            print(f"Command: {install_command}")

            # Update package status to installing
            conn = sqlite3.connect("/data/borg.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE installed_packages SET status='installing' WHERE id=?", (package_id,))
            conn.commit()
            conn.close()

            # Run installation command
            start_time = time.time()
            result = subprocess.run(
                install_command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=300,  # 5 minute timeout
                env={**os.environ, 'DEBIAN_FRONTEND': 'noninteractive'}
            )
            duration = time.time() - start_time

            # Update database with results
            conn = sqlite3.connect("/data/borg.db")
            cursor = conn.cursor()

            if result.returncode == 0:
                cursor.execute("""
                    UPDATE installed_packages
                    SET status='installed',
                        installed_at=datetime('now'),
                        install_log=?,
                        last_check=datetime('now')
                    WHERE id=?
                """, (f"STDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}", package_id))
                print(f"✓ Successfully installed {package_name} in {duration:.1f}s")
            else:
                cursor.execute("""
                    UPDATE installed_packages
                    SET status='failed',
                        install_log=?
                    WHERE id=?
                """, (f"Exit code: {result.returncode}\n\nSTDOUT:\n{result.stdout}\n\nSTDERR:\n{result.stderr}", package_id))
                print(f"✗ Failed to install {package_name} (exit code: {result.returncode})")
                print(f"STDERR: {result.stderr[:200]}")

            conn.commit()
            conn.close()

        except subprocess.TimeoutExpired:
            print(f"✗ Installation of {package_name} timed out (5 minute limit)")
            conn = sqlite3.connect("/data/borg.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE installed_packages SET status='failed', install_log='Installation timed out' WHERE id=?", (package_id,))
            conn.commit()
            conn.close()

        except Exception as e:
            print(f"✗ Error installing {package_name}: {e}")
            conn = sqlite3.connect("/data/borg.db")
            cursor = conn.cursor()
            cursor.execute("UPDATE installed_packages SET status='failed', install_log=? WHERE id=?", (str(e), package_id))
            conn.commit()
            conn.close()


def main():
    """Main entry point"""
    try:
        print("=" * 60)
        print("Package Startup Script")
        print("=" * 60)

        # Get packages to install
        packages = get_packages_to_install()

        if not packages:
            print("✓ No packages need installation")
            return 0

        print(f"📦 Found {len(packages)} package(s) in database")
        for package_id, package_name, status, install_command in packages:
            print(f"  - {package_name} (DB status: {status})")

        # Trigger installations
        trigger_package_installations(packages)

        print("")
        print("=" * 60)
        print("✓ Package startup script completed")
        print("=" * 60)
        return 0

    except Exception as e:
        print(f"✗ Unexpected error in package startup: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
