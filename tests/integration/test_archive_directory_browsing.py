#!/usr/bin/env python3
"""
Test for Archive Directory Browsing

Tests that the archive browsing functionality works correctly by:
1. Fetching one directory level at a time (not all files)
2. Showing all directories at each level (no file limit issues)
3. Proper path navigation through nested directories

This test validates the fix for the issue where only 2 out of 4 year folders
were showing due to the 1000 file limit on bulk file fetching.
"""

import requests
import subprocess
import json
import os
import tempfile
import shutil
from typing import Set, List

# Handle both pytest (relative import) and direct script execution (absolute import)
try:
    from .test_helpers import DockerPathHelper
except ImportError:
    from test_helpers import DockerPathHelper

class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    END = '\033[0m'

class ArchiveBrowsingTester:
    def __init__(self, base_url: str = "http://localhost:8082"):
        self.base_url = base_url
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []
        self.test_dir = None
        self.path_helper = DockerPathHelper(base_url)

    def log(self, message: str, level: str = "INFO"):
        colors = {
            "INFO": Colors.BLUE,
            "SUCCESS": Colors.GREEN,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW
        }
        color = colors.get(level, "")
        print(f"{color}{message}{Colors.END}")

    def authenticate(self) -> bool:
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

    def get_borg_directories(self, repo_path: str, archive: str, path: str = "") -> Set[str]:
        """
        Get directories at a specific path using borg CLI
        Returns set of directory names (not full paths)
        """
        try:
            cmd = ["borg", "list", "--json-lines", f"{repo_path}::{archive}"]
            if path:
                cmd.append(path)

            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

            if result.returncode != 0:
                self.log(f"✗ Borg command failed: {result.stderr}", "ERROR")
                return set()

            # Parse JSON lines and extract immediate children
            items = set()
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        item = json.loads(line)
                        item_path = item.get('path', '')
                        item_type = item.get('type', '')

                        if not item_path or item_type != 'd':
                            continue

                        # Get relative path
                        if path and item_path.startswith(path + "/"):
                            relative_path = item_path[len(path) + 1:]
                        elif path and item_path == path:
                            continue
                        else:
                            relative_path = item_path

                        # Strip leading slash
                        relative_path = relative_path.lstrip("/")

                        if not relative_path:
                            continue

                        # Get immediate child only
                        if "/" in relative_path:
                            dir_name = relative_path.split("/")[0]
                            items.add(dir_name)
                        else:
                            items.add(relative_path)

                    except json.JSONDecodeError:
                        continue

            return items

        except Exception as e:
            self.log(f"✗ Error getting borg directories: {e}", "ERROR")
            return set()

    def get_ui_directories(self, repo_id: int, archive_name: str, path: str = "") -> Set[str]:
        """
        Get directories from Borg UI API at a specific path
        Returns set of directory names
        """
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            params = {"path": path}

            response = self.session.get(
                f"{self.base_url}/api/browse/{repo_id}/{archive_name}",
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                self.log(f"✗ UI API failed: {response.status_code} - {response.text}", "ERROR")
                return set()

            data = response.json()
            items = set()

            for item in data.get('items', []):
                if item.get('type') == 'directory':
                    items.add(item['name'])

            return items

        except Exception as e:
            self.log(f"✗ Error getting UI directories: {e}", "ERROR")
            return set()

    def test_directory_level(self, repo_id: int, repo_path: str, archive: str, path: str,
                           expected_min_dirs: int = None) -> bool:
        """
        Test that a specific directory level shows all directories correctly
        """
        path_display = path if path else "(root)"
        self.log(f"\n📂 Testing path: {path_display}", "INFO")

        # Get expected directories from borg
        borg_dirs = self.get_borg_directories(repo_path, archive, path)
        self.log(f"  Borg CLI found: {len(borg_dirs)} directories", "INFO")

        # Get actual directories from UI
        ui_dirs = self.get_ui_directories(repo_id, archive, path)
        self.log(f"  UI API found: {len(ui_dirs)} directories", "INFO")

        # Check if they match
        if borg_dirs == ui_dirs:
            self.log(f"  ✓ PASS - All directories shown correctly!", "SUCCESS")

            if expected_min_dirs and len(ui_dirs) < expected_min_dirs:
                self.log(f"  ⚠ WARNING: Expected at least {expected_min_dirs} dirs, got {len(ui_dirs)}", "WARNING")
                return False

            self.test_results.append({
                "path": path,
                "status": "PASS",
                "borg_count": len(borg_dirs),
                "ui_count": len(ui_dirs)
            })
            return True
        else:
            self.log(f"  ✗ FAIL - Directories don't match!", "ERROR")

            missing = borg_dirs - ui_dirs
            extra = ui_dirs - borg_dirs

            if missing:
                self.log(f"    Missing in UI ({len(missing)}): {sorted(list(missing)[:10])}", "ERROR")

            if extra:
                self.log(f"    Extra in UI ({len(extra)}): {sorted(list(extra)[:10])}", "WARNING")

            self.test_results.append({
                "path": path,
                "status": "FAIL",
                "borg_count": len(borg_dirs),
                "ui_count": len(ui_dirs),
                "missing": list(missing)[:20],
                "extra": list(extra)[:20]
            })
            return False

    def test_response_size(self, repo_id: int, archive_name: str, path: str = "") -> bool:
        """
        Test that response size is reasonable (not fetching all files)
        """
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            params = {"path": path}

            response = self.session.get(
                f"{self.base_url}/api/browse/{repo_id}/{archive_name}",
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                return False

            response_size = len(response.content)
            self.log(f"\n📊 Response size for path '{path}': {response_size:,} bytes", "INFO")

            # Response should be reasonable (< 100kb for a directory level)
            # If it's > 100kb, it might be fetching too much data
            if response_size > 100000:
                self.log(f"  ⚠ WARNING: Response size is large (> 100kb)", "WARNING")
                self.log(f"  This might indicate fetching all files instead of one level", "WARNING")
                return False
            else:
                self.log(f"  ✓ Response size is reasonable (< 100kb)", "SUCCESS")
                return True

        except Exception as e:
            self.log(f"✗ Error checking response size: {e}", "ERROR")
            return False

    def create_test_environment(self):
        """Create test repository with deep nested structure"""
        self.test_dir = tempfile.mkdtemp(prefix="borg-test-browsing-")
        repo_dir = os.path.join(self.test_dir, "repo")
        source_dir = os.path.join(self.test_dir, "source")

        self.log("📁 Creating test environment with nested directories...", "INFO")

        # Create deep nested structure to test browsing
        # Photos/2023/January, Photos/2023/February, Photos/2024/January, Photos/2024/February
        os.makedirs(os.path.join(source_dir, "Photos/2023/January"))
        os.makedirs(os.path.join(source_dir, "Photos/2023/February"))
        os.makedirs(os.path.join(source_dir, "Photos/2024/January"))
        os.makedirs(os.path.join(source_dir, "Photos/2024/February"))

        # Documents/Work/Projects, Documents/Personal
        os.makedirs(os.path.join(source_dir, "Documents/Work/Projects"))
        os.makedirs(os.path.join(source_dir, "Documents/Personal"))

        # Create some files
        with open(os.path.join(source_dir, "Photos/2023/January/photo1.jpg"), "w") as f:
            f.write("photo data")
        with open(os.path.join(source_dir, "Documents/Work/Projects/report.txt"), "w") as f:
            f.write("report")

        # Initialize borg repository
        try:
            subprocess.run(
                ["borg", "init", "--encryption", "none", repo_dir],
                capture_output=True,
                check=True,
                env={**os.environ, "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes"}
            )
        except subprocess.CalledProcessError as e:
            self.log(f"✗ Failed to init borg repo: {e.stderr.decode()}", "ERROR")
            return None, None

        # Create archive
        try:
            subprocess.run(
                ["borg", "create", f"{repo_dir}::test-archive", source_dir],
                capture_output=True,
                check=True,
                env={**os.environ, "BORG_UNKNOWN_UNENCRYPTED_REPO_ACCESS_IS_OK": "yes"}
            )
        except subprocess.CalledProcessError as e:
            self.log(f"✗ Failed to create archive: {e.stderr.decode()}", "ERROR")
            return None, None

        self.log(f"✓ Created test repository at {repo_dir}", "SUCCESS")
        return repo_dir, source_dir

    def cleanup(self):
        """Clean up test environment"""
        if self.test_dir and os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
            self.log("✓ Cleaned up test environment", "SUCCESS")

    def add_repository_to_ui(self, repo_path: str) -> int:
        """Add repository to Borg UI and return repo ID"""
        try:
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }

            # Convert path for Docker if needed
            container_path = self.path_helper.to_container_path(repo_path)

            response = self.session.post(
                f"{self.base_url}/api/repositories/",
                headers=headers,
                json={
                    "name": "test-browsing",
                    "path": container_path,
                    "encryption": "none",
                    "compression": "lz4",
                    "repository_type": "local",
                    "source_directories": [],
                    "exclude_patterns": [],
                    "mode": "observe"  # Observe mode since we're importing existing repo
                },
                timeout=30
            )

            if response.status_code == 200:
                repo_id = response.json().get("repository", {}).get("id")
                self.log(f"✓ Added repository to UI with ID: {repo_id}", "SUCCESS")
                return repo_id
            else:
                self.log(f"✗ Failed to add repository: {response.status_code} - {response.text}", "ERROR")
                return None

        except Exception as e:
            self.log(f"✗ Error adding repository: {e}", "ERROR")
            return None

    def delete_repository_from_ui(self, repo_id: int):
        """Delete repository from UI"""
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            self.session.delete(
                f"{self.base_url}/api/repositories/{repo_id}",
                headers=headers,
                timeout=10
            )
        except Exception:
            pass  # Ignore cleanup errors

    def run_tests(self, test_repo_path: str = None):
        """Run all tests"""
        self.log(f"\n{'='*70}", "INFO")
        self.log("🧪 Archive Directory Browsing Test Suite", "INFO")
        self.log(f"{'='*70}\n", "INFO")

        # Log environment detection
        self.path_helper.log_environment(lambda msg: self.log(msg, "INFO"))
        self.log("", "INFO")

        # Authenticate
        if not self.authenticate():
            return False

        repo_id = None
        all_tests_passed = True

        try:
            # Create test environment
            repo_path, source_dir = self.create_test_environment()
            if not repo_path:
                return False

            # Add repository to UI
            repo_id = self.add_repository_to_ui(repo_path)
            if not repo_id:
                return False

            # Test root level (should show Photos, Documents)
            self.log("\n" + "="*70, "INFO")
            self.log("TEST 1: Root Level Directory Browsing", "INFO")
            self.log("="*70, "INFO")
            if not self.test_directory_level(repo_id, repo_path, "test-archive", "", expected_min_dirs=2):
                all_tests_passed = False

            # Test Photos level (should show 2023, 2024)
            self.log("\n" + "="*70, "INFO")
            self.log("TEST 2: Photos Directory Level", "INFO")
            self.log("="*70, "INFO")
            photos_path = os.path.join(source_dir, "Photos").replace(source_dir + "/", "")
            if not self.test_directory_level(repo_id, repo_path, "test-archive", photos_path, expected_min_dirs=2):
                all_tests_passed = False

            # Test Photos/2023 level (should show January, February)
            self.log("\n" + "="*70, "INFO")
            self.log("TEST 3: Photos/2023 Directory Level", "INFO")
            self.log("="*70, "INFO")
            photos_2023_path = os.path.join(source_dir, "Photos/2023").replace(source_dir + "/", "")
            if not self.test_directory_level(repo_id, repo_path, "test-archive", photos_2023_path, expected_min_dirs=2):
                all_tests_passed = False

            # Test Documents level (should show Work, Personal)
            self.log("\n" + "="*70, "INFO")
            self.log("TEST 4: Documents Directory Level", "INFO")
            self.log("="*70, "INFO")
            docs_path = os.path.join(source_dir, "Documents").replace(source_dir + "/", "")
            if not self.test_directory_level(repo_id, repo_path, "test-archive", docs_path, expected_min_dirs=2):
                all_tests_passed = False

            # Test response size
            self.log("\n" + "="*70, "INFO")
            self.log("TEST 5: Response Size Check", "INFO")
            self.log("="*70, "INFO")
            if not self.test_response_size(repo_id, "test-archive", ""):
                all_tests_passed = False

        finally:
            # Cleanup
            if repo_id:
                self.delete_repository_from_ui(repo_id)
            self.cleanup()

        # Summary
        self.log(f"\n{'='*70}", "INFO")
        self.log("📊 TEST SUMMARY", "INFO")
        self.log(f"{'='*70}", "INFO")

        passed = sum(1 for r in self.test_results if r['status'] == 'PASS')
        total = len(self.test_results)

        if total > 0:
            for result in self.test_results:
                status_icon = "✓" if result['status'] == 'PASS' else "✗"
                path_display = result['path'] if result['path'] else "(root)"
                self.log(
                    f"{status_icon} {path_display}: Borg={result['borg_count']}, UI={result['ui_count']}",
                    "SUCCESS" if result['status'] == 'PASS' else "ERROR"
                )

            self.log(f"\n🎯 Result: {passed}/{total} tests passed", "INFO")
        else:
            self.log("No tests were run.", "ERROR")
            return False

        if all_tests_passed and passed == total:
            self.log("\n✓ All archive browsing tests passed!", "SUCCESS")
        else:
            self.log("\n⚠ Some tests failed. See details above.", "ERROR")

        return all_tests_passed and passed == total

def main():
    import argparse

    parser = argparse.ArgumentParser(description="Test archive directory browsing")
    parser.add_argument("--url", default="http://localhost:8082", help="Borg UI URL")
    parser.add_argument("--repo-path", help="Path to test repository")
    args = parser.parse_args()

    tester = ArchiveBrowsingTester(args.url)
    success = tester.run_tests(args.repo_path)

    exit(0 if success else 1)

if __name__ == "__main__":
    main()
