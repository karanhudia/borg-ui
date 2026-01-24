#!/usr/bin/env python3
"""
Borg UI Archive Contents Testing

This script tests the archive browsing functionality by:
1. Creating test repositories with borg command line
2. Querying the Borg UI API to browse archive contents
3. Comparing UI results with actual borg list output
4. Identifying discrepancies and bugs

Usage:
    python test_archive_contents.py [test_dir] [--url http://localhost:8081]
"""

import subprocess
import json
import sys
import os
import argparse
from typing import List, Dict, Set, Any
import requests

class Colors:
    """Terminal colors for pretty output"""
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    BOLD = '\033[1m'
    END = '\033[0m'

class ArchiveContentsTester:
    def __init__(self, test_dir: str, base_url: str = "http://localhost:8081", container_mode: bool = False):
        self.test_dir = test_dir
        self.base_url = base_url
        self.repo_dir = os.path.join(test_dir, "repositories")
        self.container_mode = container_mode
        self.session = requests.Session()
        self.auth_token = None
        self.test_results = []
        # For Docker container: paths need /local prefix
        # Auto-detect: if port is 8081 or 8082, likely Docker; if 8000, likely local dev
        self.use_local_prefix = container_mode or (base_url.endswith(":8081") or base_url.endswith(":8082"))
        # For Docker container: paths need /local prefix
        self.use_local_prefix = True

    def log(self, message: str, level: str = "INFO"):
        """Log a message with color"""
        colors = {
            "INFO": Colors.BLUE,
            "SUCCESS": Colors.GREEN,
            "ERROR": Colors.RED,
            "WARNING": Colors.YELLOW
        }
        color = colors.get(level, "")
        print(f"{color}{message}{Colors.END}")

    def to_container_path(self, host_path: str) -> str:
        """Convert host path to container path if running in container mode"""
        if self.container_mode:
            # In Docker, host root (/) is mounted at /local
            return f"/local{host_path}"
        return host_path

    def authenticate(self) -> bool:
        """Authenticate with Borg UI"""
        try:
            login_data = {"username": "admin", "password": "admin123"}
            response = self.session.post(
                f"{self.base_url}/api/auth/login",
                data=login_data,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                self.auth_token = data.get("access_token")
                self.log("✅ Authenticated with Borg UI", "SUCCESS")
                return True
            else:
                self.log(f"❌ Authentication failed: {response.status_code}", "ERROR")
                return False
        except Exception as e:
            self.log(f"❌ Authentication error: {e}", "ERROR")
            return False

    def get_existing_repositories(self) -> list:
        """Get list of existing repositories"""
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = self.session.get(
                f"{self.base_url}/api/repositories/",
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                data = response.json()
                return data.get("repositories", [])
            return []
        except Exception as e:
            self.log(f"⚠️  Error getting repositories: {e}", "WARNING")
            return []

    def delete_repository(self, repo_id: int) -> bool:
        """Delete a repository by ID"""
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            response = self.session.delete(
                f"{self.base_url}/api/repositories/{repo_id}",
                headers=headers,
                timeout=10
            )

            return response.status_code in [200, 204]
        except Exception as e:
            self.log(f"⚠️  Error deleting repository: {e}", "WARNING")
            return False

    def cleanup_test_repositories(self, test_names: list):
        """Delete any existing repositories with test names"""
        existing_repos = self.get_existing_repositories()

        for repo in existing_repos:
            if repo.get("name") in test_names:
                repo_id = repo.get("id")
                repo_name = repo.get("name")
                if self.delete_repository(repo_id):
                    self.log(f"🧹 Cleaned up existing repository: {repo_name}", "INFO")
                else:
                    self.log(f"⚠️  Failed to delete repository: {repo_name}", "WARNING")

    def get_borg_archive_contents(self, repo_path: str, archive: str, path: str = "") -> Set[str]:
        """
        Get archive contents using borg command line
        Returns set of immediate children at the given path
        """
        try:
            cmd = ["borg", "list", "--json-lines", f"{repo_path}::{archive}"]
            if path:
                cmd.append(path)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30
            )

            if result.returncode != 0:
                self.log(f"❌ Borg command failed: {result.stderr}", "ERROR")
                return set()

            # Parse JSON lines and extract immediate children
            items = set()
            for line in result.stdout.strip().split('\n'):
                if line:
                    try:
                        item = json.loads(line)
                        item_path = item.get('path', '')

                        if not item_path:
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
                            # This is nested, get first component
                            dir_name = relative_path.split("/")[0]
                            items.add(dir_name)
                        else:
                            # This is immediate child
                            items.add(relative_path)

                    except json.JSONDecodeError:
                        continue

            return items

        except Exception as e:
            self.log(f"❌ Error getting borg contents: {e}", "ERROR")
            return set()

    def get_ui_archive_contents(self, repo_id: int, archive_name: str, path: str = "") -> Set[str]:
        """
        Get archive contents from Borg UI API
        Returns set of immediate children at the given path
        """
        try:
            headers = {"Authorization": f"Bearer {self.auth_token}"}
            params = {"path": path}

            response = self.session.get(
                f"{self.base_url}/api/restore/contents/{repo_id}/{archive_name}",
                headers=headers,
                params=params,
                timeout=30
            )

            if response.status_code != 200:
                self.log(f"❌ UI API failed: {response.status_code}", "ERROR")
                return set()

            data = response.json()
            items = set(item['name'] for item in data.get('items', []))
            return items

        except Exception as e:
            self.log(f"❌ Error getting UI contents: {e}", "ERROR")
            return set()

    def add_repository_to_ui(self, name: str, path: str, passphrase: str = None) -> int:
        """Add a repository to Borg UI, returns repository ID"""
        try:
            headers = {
                "Authorization": f"Bearer {self.auth_token}",
                "Content-Type": "application/json"
            }

            # Convert path for Docker container (add /local prefix)
            container_path = f"/local{path}" if self.use_local_prefix else path

            repo_data = {
                "name": name,
                "path": container_path,
                "encryption": "none" if not passphrase else "repokey",
                "compression": "lz4",
                "repository_type": "local",
                "source_directories": [],
                "exclude_patterns": [],
                "mode": "observe"  # Observe mode since we're importing existing repo
            }

            if passphrase:
                repo_data["passphrase"] = passphrase

            response = self.session.post(
                f"{self.base_url}/api/repositories/",
                headers=headers,
                json=repo_data,
                timeout=30
            )

            if response.status_code == 200:
                data = response.json()
                repo_id = data.get("repository", {}).get("id")
                self.log(f"✅ Added repository '{name}' with ID {repo_id}", "SUCCESS")
                return repo_id
            else:
                try:
                    error_detail = response.json().get("detail", response.text)
                except:
                    error_detail = response.text
                self.log(f"❌ Failed to add repository: {response.status_code}", "ERROR")
                self.log(f"   Error details: {error_detail}", "ERROR")

                # Provide helpful hints for common issues
                if "Permission denied" in str(error_detail) and self.use_local_prefix:
                    self.log("", "INFO")
                    self.log("💡 Docker permission issue detected. Try:", "WARNING")
                    self.log(f"   1. Check container user ID: docker exec borg-web-ui id", "WARNING")
                    self.log(f"   2. Fix permissions: sudo chown -R $(id -u):$(id -g) /tmp/borg-ui-tests", "WARNING")
                    self.log(f"   3. Or set PUID/PGID in docker-compose: PUID=$(id -u) PGID=$(id -g)", "WARNING")

                return None

        except Exception as e:
            self.log(f"❌ Error adding repository: {e}", "ERROR")
            return None

    def test_archive_browsing(self, repo_id: int, repo_path: str, archive: str, test_paths: List[str] = None):
        """
        Test archive browsing by comparing borg output with UI output
        """
        if test_paths is None:
            test_paths = [""]  # Test root only by default

        self.log(f"\n{'='*60}", "INFO")
        self.log(f"Testing Archive: {archive}", "INFO")
        self.log(f"{'='*60}", "INFO")

        all_passed = True

        for path in test_paths:
            path_display = path if path else "(root)"
            self.log(f"\n📂 Testing path: {path_display}", "INFO")

            # Get expected contents from borg
            borg_items = self.get_borg_archive_contents(repo_path, archive, path)
            self.log(f"  Borg found: {len(borg_items)} items", "INFO")

            # Get actual contents from UI
            ui_items = self.get_ui_archive_contents(repo_id, archive, path)
            self.log(f"  UI found: {len(ui_items)} items", "INFO")

            # Compare
            if borg_items == ui_items:
                self.log(f"  ✅ PASS - Contents match perfectly!", "SUCCESS")
                self.test_results.append({
                    "archive": archive,
                    "path": path,
                    "status": "PASS",
                    "borg_count": len(borg_items),
                    "ui_count": len(ui_items)
                })
            else:
                self.log(f"  ❌ FAIL - Contents don't match!", "ERROR")
                all_passed = False

                # Show differences
                missing_in_ui = borg_items - ui_items
                extra_in_ui = ui_items - borg_items

                if missing_in_ui:
                    self.log(f"    Missing in UI ({len(missing_in_ui)} items):", "ERROR")
                    for item in sorted(list(missing_in_ui)[:10]):  # Show first 10
                        self.log(f"      - {item}", "ERROR")
                    if len(missing_in_ui) > 10:
                        self.log(f"      ... and {len(missing_in_ui) - 10} more", "ERROR")

                if extra_in_ui:
                    self.log(f"    Extra in UI ({len(extra_in_ui)} items):", "WARNING")
                    for item in sorted(list(extra_in_ui)[:10]):
                        self.log(f"      + {item}", "WARNING")
                    if len(extra_in_ui) > 10:
                        self.log(f"      ... and {len(extra_in_ui) - 10} more", "WARNING")

                self.test_results.append({
                    "archive": archive,
                    "path": path,
                    "status": "FAIL",
                    "borg_count": len(borg_items),
                    "ui_count": len(ui_items),
                    "missing_in_ui": len(missing_in_ui),
                    "extra_in_ui": len(extra_in_ui),
                    "missing_items": list(missing_in_ui)[:20],
                    "extra_items": list(extra_in_ui)[:20]
                })

        return all_passed

    def run_tests(self):
        """Run all tests"""
        self.log(f"\n{'='*70}", "INFO")
        self.log("🧪 Borg UI Archive Contents Test Suite", "INFO")
        self.log(f"{'='*70}\n", "INFO")

        # Check if test environment exists
        if not os.path.exists(self.repo_dir):
            self.log(f"❌ Test directory not found: {self.repo_dir}", "ERROR")
            self.log("Please run: ./tests/setup_test_env.sh first", "ERROR")
            return False

        # Show path mapping info for Docker
        if self.use_local_prefix:
            self.log(f"ℹ️  Docker mode detected (paths will use /local prefix)", "INFO")
            self.log(f"   Host path: {self.repo_dir}", "INFO")
            self.log(f"   Container path: /local{self.repo_dir}", "INFO")
            self.log(f"   Ensure your docker-compose.yml mounts / as /local", "INFO")

        # Authenticate
        if not self.authenticate():
            return False

        # Test repositories configuration
        test_configs = [
            {
                "name": "Test Repo 1 (Unencrypted)",
                "path": os.path.join(self.repo_dir, "repo1-unencrypted"),
                "passphrase": None,
                "archives": [
                    {
                        "name": "test-full-backup",
                        "test_paths": ["", "Documents", "Photos/2024", "Code"]
                    },
                    {
                        "name": "test-partial-backup",
                        "test_paths": ["", "Documents"]
                    }
                ]
            },
            {
                "name": "Test Repo 2 (Encrypted)",
                "path": os.path.join(self.repo_dir, "repo2-encrypted"),
                "passphrase": "test123",
                "archives": [
                    {
                        "name": "encrypted-backup",
                        "test_paths": [""]
                    }
                ]
            }
        ]

        # Clean up any existing test repositories
        test_names = [config["name"] for config in test_configs]
        self.log("\n🧹 Cleaning up existing test repositories...", "INFO")
        self.cleanup_test_repositories(test_names)

        all_tests_passed = True

        for repo_config in test_configs:
            self.log(f"\n{'*'*70}", "INFO")
            self.log(f"Testing Repository: {repo_config['name']}", "INFO")
            self.log(f"{'*'*70}", "INFO")

            # Add repository to UI
            repo_id = self.add_repository_to_ui(
                repo_config['name'],
                repo_config['path'],
                repo_config.get('passphrase')
            )

            if not repo_id:
                self.log("❌ Failed to add repository, skipping tests", "ERROR")
                all_tests_passed = False
                continue

            # Test each archive
            for archive_config in repo_config['archives']:
                passed = self.test_archive_browsing(
                    repo_id,
                    repo_config['path'],
                    archive_config['name'],
                    archive_config.get('test_paths', [""])
                )
                if not passed:
                    all_tests_passed = False

        # Summary
        self.log(f"\n{'='*70}", "INFO")
        self.log("📊 TEST SUMMARY", "INFO")
        self.log(f"{'='*70}", "INFO")

        passed_tests = sum(1 for r in self.test_results if r['status'] == 'PASS')
        total_tests = len(self.test_results)

        for result in self.test_results:
            status_icon = "✅" if result['status'] == 'PASS' else "❌"
            path_display = result['path'] if result['path'] else "(root)"
            self.log(
                f"{status_icon} {result['archive']} @ {path_display}: "
                f"Borg={result['borg_count']}, UI={result['ui_count']}",
                "SUCCESS" if result['status'] == 'PASS' else "ERROR"
            )

        self.log(f"\n🎯 Result: {passed_tests}/{total_tests} tests passed", "INFO")

        if all_tests_passed:
            self.log("\n🎉 All tests passed! Archive browsing works correctly.", "SUCCESS")
        else:
            self.log("\n⚠️  Some tests failed. See details above.", "ERROR")

        return all_tests_passed

def main():
    parser = argparse.ArgumentParser(description="Test Borg UI archive contents")
    parser.add_argument(
        "test_dir",
        nargs="?",
        default="/tmp/borg-ui-tests",
        help="Test directory (default: /tmp/borg-ui-tests)"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8081",
        help="Borg UI URL (default: http://localhost:8081)"
    )

    args = parser.parse_args()

    tester = ArchiveContentsTester(args.test_dir, args.url)
    success = tester.run_tests()

    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
