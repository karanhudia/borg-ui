import asyncio
import subprocess
import json
import yaml
import os
import structlog
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timezone
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

        # Configure lock behavior with quick timeout
        # Wait only 20 seconds for locks - if stale, we'll break and retry
        # This provides fast feedback to users instead of waiting 3 minutes
        exec_env["BORG_LOCK_WAIT"] = "20"

        # Mark this container's hostname as unique to avoid lock conflicts
        exec_env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

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

    async def _execute_command_streaming(self, cmd: List[str], max_lines: int = 1_000_000,
                                        timeout: int = 3600, cwd: str = None, env: dict = None) -> Dict:
        """Execute a command with line-by-line streaming and size limits

        This prevents OOM by counting lines as they arrive and terminating early if limits are exceeded.
        Designed for commands that produce large outputs (like borg list on archives with millions of files).

        Args:
            cmd: Command to execute
            max_lines: Maximum number of output lines before termination (default: 1 million)
            timeout: Command timeout in seconds
            cwd: Working directory
            env: Environment variables

        Returns:
            Dict with return_code, stdout (joined lines), stderr, success, and line_count_exceeded flag
        """
        logger.info("Executing command with streaming",
                   command=" ".join(cmd),
                   max_lines=max_lines,
                   cwd=cwd)

        # Set up environment with SSH options for remote repositories
        exec_env = os.environ.copy()
        exec_env["BORG_LOCK_WAIT"] = "20"
        exec_env["BORG_HOSTNAME_IS_UNIQUE"] = "yes"

        ssh_opts = [
            "-o", "StrictHostKeyChecking=no",
            "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR"
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

            # Stream stdout line by line with limit enforcement
            stdout_lines = []
            line_count = 0
            line_count_exceeded = False
            start_time = asyncio.get_event_loop().time()

            try:
                async for line in process.stdout:
                    # Check timeout
                    if asyncio.get_event_loop().time() - start_time > timeout:
                        logger.error("Command timed out during streaming",
                                   command=" ".join(cmd),
                                   lines_read=line_count)
                        process.kill()
                        await process.wait()
                        return {
                            "return_code": -1,
                            "stdout": "\n".join(stdout_lines),
                            "stderr": f"Command timed out after {timeout} seconds (read {line_count:,} lines)",
                            "success": False,
                            "line_count_exceeded": False,
                            "lines_read": line_count
                        }

                    line_count += 1

                    # Check if we've exceeded the line limit
                    if line_count > max_lines:
                        logger.error("Line limit exceeded, terminating command",
                                   command=" ".join(cmd),
                                   line_count=line_count,
                                   max_lines=max_lines)
                        line_count_exceeded = True
                        # Kill the process to prevent further memory consumption
                        process.kill()
                        await process.wait()
                        break

                    # Decode and store line (keep in memory only up to limit)
                    stdout_lines.append(line.decode('utf-8', errors='replace').rstrip('\n'))

                    # Log progress every 100k lines
                    if line_count % 100_000 == 0:
                        logger.info("Streaming progress",
                                   command=" ".join(cmd),
                                   lines_read=line_count)

            except Exception as e:
                logger.error("Error during streaming", command=" ".join(cmd), error=str(e))
                process.kill()
                await process.wait()
                raise

            # Read stderr (should be small for list commands)
            stderr_data = await process.stderr.read()
            stderr = stderr_data.decode('utf-8', errors='replace') if stderr_data else ""

            # Wait for process to complete (if not already killed)
            if process.returncode is None:
                await process.wait()

            result = {
                "return_code": process.returncode,
                "stdout": "\n".join(stdout_lines),
                "stderr": stderr,
                "success": process.returncode == 0 and not line_count_exceeded,
                "line_count_exceeded": line_count_exceeded,
                "lines_read": line_count
            }

            if result["success"]:
                logger.info("Command executed successfully with streaming",
                           command=" ".join(cmd),
                           lines_read=line_count)
            else:
                if line_count_exceeded:
                    logger.warning("Command terminated due to line limit",
                                 command=" ".join(cmd),
                                 lines_read=line_count,
                                 max_lines=max_lines)
                else:
                    logger.error("Command failed",
                               command=" ".join(cmd),
                               return_code=process.returncode,
                               stderr=stderr[:500])  # Limit stderr logging

            return result

        except asyncio.TimeoutError:
            logger.error("Command timed out", command=" ".join(cmd), timeout=timeout)
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": f"Command timed out after {timeout} seconds",
                "success": False,
                "line_count_exceeded": False,
                "lines_read": 0
            }
        except Exception as e:
            logger.error("Command execution failed", command=" ".join(cmd), error=str(e))
            return {
                "return_code": -1,
                "stdout": "",
                "stderr": str(e),
                "success": False,
                "line_count_exceeded": False,
                "lines_read": 0
            }

    async def break_lock(self, repository: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """Break a stale lock on a repository and its cache"""
        logger.warning("Breaking stale lock", repository=repository)

        cmd = [self.borg_cmd, "break-lock"]

        # Add remote-path if specified
        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        cmd.append(repository)

        # Set passphrase environment variable if provided
        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        # Break repository lock
        result = await self._execute_command(cmd, timeout=30, env=env if env else None)

        # Also try to break cache lock by deleting cache lock files
        # This handles the case where cache locks remain after repository locks are broken
        try:
            import glob

            # Get the actual repository ID from borg info (most reliable method)
            # This ensures we target the correct cache directory
            info_cmd = [self.borg_cmd, "info", "--json"]
            if remote_path:
                info_cmd.extend(["--remote-path", remote_path])
            info_cmd.append(repository)

            info_result = await self._execute_command(info_cmd, timeout=30, env=env if env else None)

            if info_result.get("success"):
                info_data = json.loads(info_result["stdout"])
                repo_id = info_data.get("repository", {}).get("id")

                if repo_id:
                    logger.info("Found repository ID for cache cleanup", repo_id=repo_id)
                    cache_dir = os.path.expanduser(f"~/.cache/borg/{repo_id}")

                    if os.path.exists(cache_dir):
                        # Remove all types of lock files/directories in cache directory
                        # Borg 1.4+ uses: lock.exclusive, lock.roster, and lock.* patterns
                        lock_patterns = [
                            f"{cache_dir}/lock.*",           # Legacy lock files
                            f"{cache_dir}/lock.exclusive",   # Borg 1.4+ exclusive lock
                            f"{cache_dir}/lock.roster"       # Borg 1.4+ roster lock
                        ]

                        all_locks = []
                        for pattern in lock_patterns:
                            all_locks.extend(glob.glob(pattern))

                        # Remove duplicates
                        all_locks = list(set(all_locks))

                        if all_locks:
                            logger.info("Breaking cache locks", cache_dir=cache_dir, count=len(all_locks), locks=all_locks)
                            for lock_path in all_locks:
                                try:
                                    if os.path.isfile(lock_path):
                                        os.unlink(lock_path)
                                        logger.info("Removed cache lock file", file=lock_path)
                                    elif os.path.isdir(lock_path):
                                        import shutil
                                        shutil.rmtree(lock_path)
                                        logger.info("Removed cache lock directory", dir=lock_path)
                                except Exception as e:
                                    logger.warning("Failed to remove cache lock", path=lock_path, error=str(e))
                        else:
                            logger.info("No cache locks found", cache_dir=cache_dir)
                    else:
                        logger.info("Cache directory does not exist", cache_dir=cache_dir)
                else:
                    logger.warning("Could not extract repository ID from borg info")
            else:
                logger.warning("Could not get repository info for cache cleanup", error=info_result.get("stderr"))
        except Exception as e:
            logger.warning("Failed to clean cache locks", error=str(e))

        return result

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

    async def list_archive_contents(self, repository: str, archive: str, path: str = "",
                                   remote_path: str = None, passphrase: str = None,
                                   max_lines: int = 1_000_000) -> Dict:
        """List contents of an archive with streaming to prevent OOM

        Note: borg list doesn't support path filtering as an argument,
        so we always fetch all items and filter them in the caller.

        Args:
            repository: Repository path
            archive: Archive name
            path: Path filter (applied in caller, not by borg)
            remote_path: Remote borg executable path
            passphrase: Repository passphrase
            max_lines: Maximum number of files to list before terminating (default: 1 million)

        Returns:
            Dict with stdout, stderr, success, and line_count_exceeded flag
        """
        cmd = [self.borg_cmd, "list"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.extend([f"{repository}::{archive}", "--json-lines"])
        # Note: path parameter is not passed to borg, filtering happens in the API layer

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        # Use streaming execution to prevent OOM on large archives
        return await self._execute_command_streaming(cmd, max_lines=max_lines, env=env if env else None)

    async def extract_archive(self, repository: str, archive: str, paths: List[str],
                            destination: str, dry_run: bool = False, remote_path: str = None, passphrase: str = None) -> Dict:
        """Extract files from an archive"""
        cmd = [self.borg_cmd, "extract"]

        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        if dry_run:
            cmd.append("--dry-run")

        # Skip extended attributes and ACLs to avoid errors on filesystems that don't support them
        # This prevents "Operation not supported" errors when extracting files with NFS4 ACLs, etc.
        cmd.extend(["--noacls", "--noxattrs", "--noflags"])

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

    async def delete_archive(self, repository: str, archive: str, remote_path: str = None, passphrase: str = None) -> Dict:
        """Delete an archive"""
        cmd = [self.borg_cmd, "delete"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])
        cmd.append(f"{repository}::{archive}")

        env = {}
        if passphrase:
            env["BORG_PASSPHRASE"] = passphrase

        return await self._execute_command(cmd, env=env)

    async def prune_archives(self, repository: str, keep_hourly: int = 0, keep_daily: int = 7,
                           keep_weekly: int = 4, keep_monthly: int = 6, keep_quarterly: int = 0,
                           keep_yearly: int = 1, dry_run: bool = False,
                           remote_path: str = None, passphrase: str = None) -> Dict:
        """Prune old archives

        Args:
            repository: Repository path
            keep_hourly: Keep N hourly backups (0 = disabled)
            keep_daily: Keep N daily backups
            keep_weekly: Keep N weekly backups
            keep_monthly: Keep N monthly backups
            keep_quarterly: Keep N quarterly backups (0 = disabled, uses --keep-3monthly)
            keep_yearly: Keep N yearly backups
            dry_run: Run in dry-run mode
            remote_path: Path to remote borg binary
            passphrase: Repository passphrase
        """
        cmd = [self.borg_cmd, "prune"]
        if remote_path:
            cmd.extend(["--remote-path", remote_path])

        cmd.append(repository)

        # Only add keep options if they are > 0
        if keep_hourly > 0:
            cmd.extend(["--keep-hourly", str(keep_hourly)])
        if keep_daily > 0:
            cmd.extend(["--keep-daily", str(keep_daily)])
        if keep_weekly > 0:
            cmd.extend(["--keep-weekly", str(keep_weekly)])
        if keep_monthly > 0:
            cmd.extend(["--keep-monthly", str(keep_monthly)])
        if keep_quarterly > 0:
            # Borg uses --keep-3monthly for quarterly (every 3 months)
            cmd.extend(["--keep-3monthly", str(keep_quarterly)])
        if keep_yearly > 0:
            cmd.extend(["--keep-yearly", str(keep_yearly)])

        cmd.append("--list")

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
                    # Convert Unix timestamp to timezone-aware UTC datetime, then to ISO format
                    last_backup = datetime.fromtimestamp(latest_archive["time"], tz=timezone.utc).isoformat()
                
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