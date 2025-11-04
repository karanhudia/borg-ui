#!/usr/bin/env python3
"""
Test for Multiple Source Directories Bug

This test reproduces and validates the fix for the issue where:
- User adds 2 source directories: /local/home/karanhudia/ImmichPhotos and /local/home/karanhudia/Immich
- Only one directory (ImmichPhotos) gets backed up
- The second directory (Immich) is missing from the backup

This could be caused by:
1. Frontend not properly sending both directories
2. Backend not properly parsing/storing both directories
3. Borg command not receiving both directories
4. Race condition in directory processing
"""

import requests
import subprocess
import json
import os
import tempfile
import shutil
from pathlib import Path

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class MultipleSourceDirTester:
    def __init__(self, base_url="http://localhost:8082"):
        self.base_url = base_url
        self.session = requests.Session()
        self.auth_token = None
        self.test_dir = None

    def log(self, message, level="INFO"):
        colors = {
            "INFO": Colors.BLUE,
            "SUCCESS": Colors.GREEN,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW
        }
        color = colors.get(level, "")
        print(f"{color}{message}{Colors.END}")

    def setup_test_environment(self):
        """Create test directories and repository"""
        self.test_dir = tempfile.mkdtemp(prefix="borg-test-multi-source-")

        # Create two source directories
        self.source1 = os.path.join(self.test_dir, "source1_photos")
        self.source2 = os.path.join(self.test_dir, "source2_documents")
        self.repo_path = os.path.join(self.test_dir, "test-repo")

        os.makedirs(self.source1)
        os.makedirs(self.source2)

        # Create test files in each directory
        with open(os.path.join(self.source1, "photo1.jpg"), "w") as f:
            f.write("photo content 1")
        with open(os.path.join(self.source1, "photo2.jpg"), "w") as f:
            f.write("photo content 2")

        with open(os.path.join(self.source2, "doc1.txt"), "w") as f:
            f.write("document content 1")
        with open(os.path.join(self.source2, "doc2.txt"), "w") as f:
            f.write("document content 2")

        self.log(f"✓ Created test environment at {self.test_dir}", "SUCCESS")
        self.log(f"  Source 1: {self.source1} (2 photos)", "INFO")
        self.log(f"  Source 2: {self.source2} (2 documents)", "INFO")

    def cleanup(self):
        """Clean up test environment"""
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            self.log(f"✓ Cleaned up test environment", "SUCCESS")

    def authenticate(self):
        """Authenticate with Borg UI"""
        try:
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                data={"username": "admin", "password": "admin123"},
                timeout=10
            )
            if response.status_code == 200:
                self.auth_token = response.json().get("access_token")
                self.log("✓ Authenticated", "SUCCESS")
                return True
            else:
                self.log(f"✗ Authentication failed: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"✗ Authentication error: {e}", "ERROR")
            return False

    def create_repository_with_two_sources(self):
        """Create repository with 2 source directories"""
        try:
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }

            repo_data = {
                "name": "test-multi-source",
                "path": self.repo_path,
                "encryption": "none",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": [self.source1, self.source2],  # TWO DIRECTORIES
                "exclude_patterns": []
            }

            self.log(f"\n📤 Creating repository with 2 source directories:", "INFO")
            self.log(f"  1. {self.source1}", "INFO")
            self.log(f"  2. {self.source2}", "INFO")

            response = self.session.post(
                f"{self.base_url}/api/repositories/",
                headers=headers,
                json=repo_data,
                timeout=30
            )

            if response.status_code == 200:
                result = response.json()
                repo_id = result.get("repository", {}).get("id")
                self.log(f"✓ Repository created with ID: {repo_id}", "SUCCESS")
                return repo_id
            else:
                self.log(f"✗ Repository creation failed: {response.status_code}", "ERROR")
                self.log(f"  Response: {response.text}", "ERROR")
                return None

        except Exception as e:
            self.log(f"✗ Error creating repository: {e}", "ERROR")
            return None

    def verify_repository_config(self, repo_id):
        """Verify repository has both source directories stored"""
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}

            response = self.session.get(
                f"{self.base_url}/api/repositories/",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                repos = response.json().get("repositories", [])
                repo = next((r for r in repos if r["id"] == repo_id), None)

                if repo:
                    source_dirs = repo.get("source_directories", [])
                    self.log(f"\n🔍 Repository configuration check:", "INFO")
                    self.log(f"  Stored source directories: {len(source_dirs)}", "INFO")
                    for i, dir_path in enumerate(source_dirs, 1):
                        self.log(f"    {i}. {dir_path}", "INFO")

                    if len(source_dirs) == 2:
                        if self.source1 in source_dirs and self.source2 in source_dirs:
                            self.log(f"✓ Both source directories stored correctly!", "SUCCESS")
                            return True
                        else:
                            self.log(f"✗ Wrong directories stored!", "ERROR")
                            return False
                    else:
                        self.log(f"✗ Expected 2 source directories, got {len(source_dirs)}", "ERROR")
                        return False
                else:
                    self.log(f"✗ Repository not found", "ERROR")
                    return False
            else:
                self.log(f"✗ Failed to fetch repositories: {response.status_code}", "ERROR")
                return False

        except Exception as e:
            self.log(f"✗ Error verifying config: {e}", "ERROR")
            return False

    def run_backup(self, repo_id):
        """Trigger a backup and return job ID"""
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}

            response = self.session.post(
                f"{self.base_url}/api/backup/start/{repo_id}",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                job_id = result.get("job_id")
                self.log(f"✓ Backup started, job ID: {job_id}", "SUCCESS")
                return job_id
            else:
                self.log(f"✗ Backup start failed: {response.status_code}", "ERROR")
                self.log(f"  Response: {response.text}", "ERROR")
                return None

        except Exception as e:
            self.log(f"✗ Error starting backup: {e}", "ERROR")
            return None

    def wait_for_backup(self, job_id, timeout=60):
        """Wait for backup to complete"""
        import time

        headers = {"Authorization": f"Bearer {self.auth_token}"}
        start_time = time.time()

        while time.time() - start_time < timeout:
            try:
                response = self.session.get(
                    f"{self.base_url}/api/backup/status/{job_id}",
                    headers=headers,
                    timeout=10
                )

                if response.status_code == 200:
                    status = response.json().get("status")

                    if status in ["completed", "failed", "cancelled"]:
                        if status == "completed":
                            self.log(f"✓ Backup completed", "SUCCESS")
                            return True
                        else:
                            self.log(f"✗ Backup {status}", "ERROR")
                            error_msg = response.json().get("error_message", "")
                            if error_msg:
                                self.log(f"  Error: {error_msg}", "ERROR")
                            return False

                    time.sleep(2)
                else:
                    self.log(f"✗ Status check failed: {response.status_code}", "ERROR")
                    return False

            except Exception as e:
                self.log(f"✗ Error checking status: {e}", "ERROR")
                return False

        self.log(f"✗ Backup timeout after {timeout}s", "ERROR")
        return False

    def verify_archive_contents(self):
        """Verify both source directories are in the archive"""
        try:
            # Get list of archives
            result = subprocess.run(
                ["borg", "list", self.repo_path],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                self.log(f"✗ Failed to list archives: {result.stderr}", "ERROR")
                return False

            # Get the first archive name
            lines = result.stdout.strip().split('\n')
            if not lines or not lines[0]:
                self.log(f"✗ No archives found", "ERROR")
                return False

            archive_name = lines[0].split()[0]
            self.log(f"\n🔍 Checking archive contents: {archive_name}", "INFO")

            # List archive contents
            result = subprocess.run(
                ["borg", "list", "--json-lines", f"{self.repo_path}::{archive_name}"],
                capture_output=True,
                text=True,
                timeout=10
            )

            if result.returncode != 0:
                self.log(f"✗ Failed to list archive: {result.stderr}", "ERROR")
                return False

            # Check which files are in the archive
            paths_in_archive = []
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        item = json.loads(line)
                        path = item.get('path', '')
                        if path:
                            paths_in_archive.append(path)
                    except json.JSONDecodeError:
                        continue

            # Check for files from each source directory
            source1_files = [p for p in paths_in_archive if "photo" in p.lower()]
            source2_files = [p for p in paths_in_archive if "doc" in p.lower()]

            self.log(f"  Total items in archive: {len(paths_in_archive)}", "INFO")
            self.log(f"  Files from source1 (photos): {len(source1_files)}", "INFO")
            self.log(f"  Files from source2 (documents): {len(source2_files)}", "INFO")

            if len(source1_files) > 0 and len(source2_files) > 0:
                self.log(f"✓ Both source directories are in the archive!", "SUCCESS")
                return True
            elif len(source1_files) > 0:
                self.log(f"✗ BUG DETECTED: Only source1 backed up, source2 missing!", "ERROR")
                return False
            elif len(source2_files) > 0:
                self.log(f"✗ BUG DETECTED: Only source2 backed up, source1 missing!", "ERROR")
                return False
            else:
                self.log(f"✗ No files from either source in archive!", "ERROR")
                return False

        except Exception as e:
            self.log(f"✗ Error verifying archive: {e}", "ERROR")
            return False

    def run_test(self):
        """Run the complete test"""
        self.log(f"\n{'='*70}", "INFO")
        self.log(f"TEST: Multiple Source Directories Bug", "INFO")
        self.log(f"{'='*70}\n", "INFO")

        try:
            # Setup
            self.setup_test_environment()

            # Authenticate
            if not self.authenticate():
                return False

            # Create repository with 2 sources
            repo_id = self.create_repository_with_two_sources()
            if not repo_id:
                return False

            # Verify config stored correctly
            if not self.verify_repository_config(repo_id):
                self.log(f"\n⚠️  CONFIG BUG: Both directories not stored in database!", "ERROR")
                return False

            # Run backup
            job_id = self.run_backup(repo_id)
            if not job_id:
                return False

            # Wait for completion
            if not self.wait_for_backup(job_id):
                return False

            # Verify archive contents
            if not self.verify_archive_contents():
                self.log(f"\n⚠️  BACKUP BUG: Not all source directories were backed up!", "ERROR")
                return False

            self.log(f"\n{'='*70}", "INFO")
            self.log(f"✓ TEST PASSED: Both source directories backed up correctly!", "SUCCESS")
            self.log(f"{'='*70}\n", "INFO")
            return True

        finally:
            self.cleanup()

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test multiple source directories bug")
    parser.add_argument("--url", default="http://localhost:8082", help="Borg UI URL")
    args = parser.parse_args()

    tester = MultipleSourceDirTester(args.url)
    success = tester.run_test()

    exit(0 if success else 1)

if __name__ == "__main__":
    main()
