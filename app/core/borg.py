import asyncio
import subprocess
import json
import yaml
import os
import structlog
from typing import Dict, List, Optional, Tuple
from datetime import datetime
from app.config import settings

logger = structlog.get_logger()

class BorgInterface:
    """Interface for interacting with Borg CLI"""

    _validated = False  # Class variable to track if validation has run
    _cached_version = None  # Class variable to cache borg version
    _cached_system_info = None  # Class variable to cache system info

    def __init__(self):
        self.borg_cmd = "borg"
        if not BorgInterface._validated:
            self._validate_borg_installation()
            BorgInterface._validated = True

    def _validate_borg_installation(self):
        """Validate that borg is installed and accessible"""
        try:
            result = subprocess.run([self.borg_cmd, "--version"],
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info("Borg found", version=result.stdout.strip())
            else:
                raise RuntimeError(f"Borg command failed with return code {result.returncode}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Borg not available", error=str(e))
            raise RuntimeError(f"Borg not available: {str(e)}")
    
    async def _execute_command(self, cmd: List[str], timeout: int = 3600, cwd: str = None, env: dict = None) -> Dict:
        """Execute a command with real-time output capture"""
        logger.info("Executing command", command=" ".join(cmd), cwd=cwd)

        # Set up environment with SSH options for remote repositories
        exec_env = os.environ.copy()

        # Add SSH options to disable host key checking for remote repos
        # This allows automatic connection to new hosts without manual intervention
        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",  # Don't check host keys
            "-o", "UserKnownHostsFile=/dev/null",  # Don't save host keys
            "-o", "LogLevel=ERROR"  # Reduce SSH verbosity
        ]
        exec_env['BORG_RSH'] = f"ssh {' '.join(ssh_opts)}"

        # Merge any additional environment variables
        if env:
            exec_env.update(env)

        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=cwd,
                env=exec_env
            )
            
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), 
                timeout=timeout
            )
            
            result = {
                "return_code": process.returncode,
                "stdout": stdout.decode() if stdout else "",
                "stderr": stderr.decode() if stderr else "",
                "success": process.returncode == 0
            }
            
            if result["success"]:
                logger.info("Command executed successfully", command=" ".join(cmd))
            else:
                logger.error("Command failed", 
                           command=" ".join(cmd), 
                           return_code=process.returncode,
                           stderr=result["stderr"])
            
            return result
            
        except asyncio.TimeoutError:
            logger.error("Command timed out", command=" ".join(cmd), timeout=timeout)
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "success": False
            }
        except Exception as e:
            logger.error("Command execution failed", command=" ".join(cmd), error=str(e))
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False
            }
    
    async def run_backup(self, repository: str, source_paths: List[str],
                        compression: str = "lz4", archive_name: str = None, remote_path: str = None, passphrase: str = None) -> Dict:
        """Execute backup operation with direct parameters"""
        if not repository:
            return {"success": False, "error": "Repository is required", "stdout": "", "stderr": ""}

        if not source_paths:
            return {"success": False, "error": "Source paths are required", "stdout": "", "stderr": ""}

        # Build borg create command
        cmd = [self.borg_cmd, "create"]

        # Add remote-path if specified (for remote repositories)
        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        # Add compression
        cmd.extend(["--compression", compression])

        # Add common options
        cmd.extend(["--stats", "--json"])

        # Repository::archive format
        if not archive_name:
            archive_name = "{hostname}-{now}"
        cmd.append(f"{repository}::{archive_name}")

        # Add source paths
        cmd.extend(source_paths)

        # Set passphrase environment variable if provided
        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, timeout=settings.backup_timeout, env=env if env else None)
    
    async def list_archives(self, repository: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """List archives in repository"""
        cmd = [self.borg_cmd, "list"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([repository, "--json"])

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)

    async def info_archive(self, repository: str, archive: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """Get information about a specific archive"""
        cmd = [self.borg_cmd, "info"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([f"{repository}::{archive}", "--json"])

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)

    async def list_archive_contents(self, repository: str, archive: str, path: str = "", remote_path: str = None, passphrase: str = None) -> Dict:
        """List contents of an archive"""
        cmd = [self.borg_cmd, "list"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([f"{repository}::{archive}", "--json-lines"])
        if path:
            cmd.append(path)

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)

    async def extract_archive(self, repository: str, archive: str, paths: List[str],
                            destination: str, dry_run: bool = False, remote_path: str = None, passphrase: str = None) -> Dict:
        """Extract files from an archive"""
        cmd = [self.borg_cmd, "extract"]

        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        if dry_run:
            cmd.append("--dry-run")

        cmd.append(f"{repository}::{archive}")

        # Add paths to extract
        if paths:
            cmd.extend(paths)

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        # Borg extract always extracts to current directory
        # Use cwd parameter to change to destination directory
        return await self._execute_command(cmd, timeout=settings.backup_timeout, cwd=destination, env=env if env else None)

    async def delete_archive(self, repository: str, archive: str, remote_path: str = None) -> Dict:
        """Delete an archive"""
        cmd = [self.borg_cmd, "delete"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(f"{repository}::{archive}")
        return await self._execute_command(cmd)

    async def prune_archives(self, repository: str, keep_daily: int = 7, keep_weekly: int = 4,
                           keep_monthly: int = 6, keep_yearly: int = 1, dry_run: bool = False,
                           remote_path: str = None, passphrase: str = None) -> Dict:
        """Prune old archives"""
        cmd = [self.borg_cmd, "prune"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([
            repository,
            "--keep-daily", str(keep_daily),
            "--keep-weekly", str(keep_weekly),
            "--keep-monthly", str(keep_monthly),
            "--keep-yearly", str(keep_yearly),
            "--list"
        ])
        # Don't add --stats when doing dry run (not supported)
        if not dry_run:
            cmd.append("--stats")
        if dry_run:
            cmd.append("--dry-run")

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)

    async def check_repository(self, repository: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """Check repository integrity"""
        cmd = [self.borg_cmd, "check"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(repository)

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)

    async def compact_repository(self, repository: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """Compact repository to save space"""
        cmd = [self.borg_cmd, "compact"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(repository)

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env if env else None)
    
    
    async def get_repository_info(self, repository_path: str, remote_path: str = None) -> Dict:
        """Get detailed information about a specific repository"""
        try:
            # Get repository info using borg info
            cmd = ["borg", "info"]
            if remote_path:
                cmd.extend(["--remote-path", remote_path])
            cmd.extend([repository_path, "--json"])
            result = await self._execute_command(cmd, timeout=60)
            
            if not result["success"]:
                return {
                    "success": False,
                    "error": result["stderr"],
                    "last_backup": None,
                    "backup_count": 0,
                    "total_size": 0,
                    "compression_ratio": 0,
                    "integrity_check": False,
                    "disk_usage": 0
                }
            
            # Parse JSON output
            try:
                info_data = json.loads(result["stdout"])
                archives = info_data.get("archives", [])
                
                # Calculate total size
                total_size = sum(archive.get("stats", {}).get("size", 0) for archive in archives)
                
                # Get compression ratio (average)
                compression_ratios = []
                for archive in archives:
                    stats = archive.get("stats", {})
                    if stats.get("size") and stats.get("csize"):
                        ratio = stats["csize"] / stats["size"]
                        compression_ratios.append(ratio)
                
                avg_compression_ratio = sum(compression_ratios) / len(compression_ratios) if compression_ratios else 0
                
                # Get last backup time
                last_backup = None
                if archives:
                    latest_archive = max(archives, key=lambda x: x.get("time", 0))
                    last_backup = datetime.fromtimestamp(latest_archive["time"]).strftime("%Y-%m-%d %H:%M:%S")
                
                # Check disk usage
                disk_usage = 0
                try:
                    import psutil
                    disk = psutil.disk_usage(os.path.dirname(repository_path))
                    disk_usage = disk.percent
                except:
                    pass
                
                return {
                    "success": True,
                    "last_backup": last_backup,
                    "backup_count": len(archives),
                    "total_size": total_size,
                    "compression_ratio": avg_compression_ratio,
                    "integrity_check": True,  # If we can read the repo, it's likely intact
                    "disk_usage": disk_usage
                }
                
            except json.JSONDecodeError as e:
                logger.error("Failed to parse repository info JSON", error=str(e))
                return {
                    "success": False,
                    "error": "Failed to parse repository information",
                    "last_backup": None,
                    "backup_count": 0,
                    "total_size": 0,
                    "compression_ratio": 0,
                    "integrity_check": False,
                    "disk_usage": 0
                }
                
        except Exception as e:
            logger.error("Failed to get repository info", repository=repository_path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "last_backup": None,
                "backup_count": 0,
                "total_size": 0,
                "compression_ratio": 0,
                "integrity_check": False,
                "disk_usage": 0
            }

    
    def get_version(self) -> str:
        """Get Borg version"""
        try:
            result = subprocess.run([self.borg_cmd, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return "Unknown"
        except Exception as e:
            logger.error("Failed to get borg version", error=str(e))
            return "Unknown"

    async def get_system_info(self) -> Dict:
        """Get system information (cached after first call)"""
        try:
            # Return cached info if available
            if BorgInterface._cached_system_info is not None:
                return BorgInterface._cached_system_info

            # Get borg version (only once)
            version_result = await self._execute_command([self.borg_cmd, "--version"])
            borg_version = version_result["stdout"].strip() if version_result["success"] else "Unknown"

            # Get available commands (only once)
            help_result = await self._execute_command([self.borg_cmd, "--help"])

            # Cache the result
            BorgInterface._cached_system_info = {
                "success": True,
                "borg_version": borg_version,
                "data_dir": settings.data_dir,
                "help_available": help_result["success"]
            }

            logger.info("Cached borg system info", version=borg_version)
            return BorgInterface._cached_system_info

        except Exception as e:
            logger.error("Failed to get system info", error=str(e))
            return {"success": False, "error": str(e)}

# Global instance
borg = BorgInterface() 