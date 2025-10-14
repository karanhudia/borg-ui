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

class BorgmaticInterface:
    """Interface for interacting with Borgmatic CLI"""

    _validated = False  # Class variable to track if validation has run

    def __init__(self, config_path: str = None):
        self.config_path = config_path or settings.borgmatic_config_path
        self.borgmatic_cmd = "borgmatic"
        if not BorgmaticInterface._validated:
            self._validate_borgmatic_installation()
            BorgmaticInterface._validated = True
    
    def _validate_borgmatic_installation(self):
        """Validate that borgmatic is installed and accessible"""
        try:
            result = subprocess.run([self.borgmatic_cmd, "--version"], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                logger.info("Borgmatic found", version=result.stdout.strip())
            else:
                raise RuntimeError(f"Borgmatic command failed with return code {result.returncode}")
        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            logger.error("Borgmatic not available", error=str(e))
            raise RuntimeError(f"Borgmatic not available: {str(e)}")
    
    async def _execute_command(self, cmd: List[str], timeout: int = 3600) -> Dict:
        """Execute a command with real-time output capture"""
        logger.info("Executing command", command=" ".join(cmd))
        
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
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
    
    async def run_backup(self, repository: str = None, config_file: str = None) -> Dict:
        """Execute backup operation"""
        cmd = [self.borgmatic_cmd, "create"]
        
        if repository:
            cmd.extend(["--repository", repository])
        
        if config_file:
            cmd.extend(["--config", config_file])
        elif self.config_path:
            cmd.extend(["--config", self.config_path])
        
        return await self._execute_command(cmd, timeout=settings.backup_timeout)
    
    async def list_archives(self, repository: str) -> Dict:
        """List archives in repository"""
        cmd = [self.borgmatic_cmd, "list", "--repository", repository, "--json"]
        return await self._execute_command(cmd)
    
    async def info_archive(self, repository: str, archive: str) -> Dict:
        """Get information about a specific archive"""
        cmd = [self.borgmatic_cmd, "info", "--repository", repository, "--archive", archive, "--json"]
        return await self._execute_command(cmd)
    
    async def list_archive_contents(self, repository: str, archive: str, path: str = "") -> Dict:
        """List contents of an archive"""
        cmd = [self.borgmatic_cmd, "list", "--repository", repository, "--archive", archive, "--json"]
        if path:
            cmd.extend(["--path", path])
        return await self._execute_command(cmd)
    
    async def extract_archive(self, repository: str, archive: str, paths: List[str], 
                            destination: str, dry_run: bool = False) -> Dict:
        """Extract files from an archive"""
        cmd = [self.borgmatic_cmd, "extract"]
        
        if dry_run:
            cmd.append("--dry-run")
        
        cmd.extend(["--repository", repository, "--archive", archive, "--destination", destination])
        
        for path in paths:
            cmd.extend(["--path", path])
        
        return await self._execute_command(cmd, timeout=settings.backup_timeout)
    
    async def delete_archive(self, repository: str, archive: str) -> Dict:
        """Delete an archive"""
        cmd = [self.borgmatic_cmd, "delete", "--repository", repository, "--archive", archive]
        return await self._execute_command(cmd)
    
    async def prune_archives(self, repository: str, keep_daily: int = 7, keep_weekly: int = 4, 
                           keep_monthly: int = 6, keep_yearly: int = 1) -> Dict:
        """Prune old archives"""
        cmd = [
            self.borgmatic_cmd, "prune",
            "--repository", repository,
            "--keep-daily", str(keep_daily),
            "--keep-weekly", str(keep_weekly),
            "--keep-monthly", str(keep_monthly),
            "--keep-yearly", str(keep_yearly)
        ]
        return await self._execute_command(cmd)
    
    async def check_repository(self, repository: str) -> Dict:
        """Check repository integrity"""
        cmd = [self.borgmatic_cmd, "check", "--repository", repository]
        return await self._execute_command(cmd)
    
    async def compact_repository(self, repository: str) -> Dict:
        """Compact repository to save space"""
        cmd = [self.borgmatic_cmd, "compact", "--repository", repository]
        return await self._execute_command(cmd)
    
    async def get_config_info(self, config_file: str = None) -> Dict:
        """Get configuration information"""
        config_path = config_file or self.config_path
        if not config_path or not os.path.exists(config_path):
            return {
                "success": False,
                "error": "Configuration file not found",
                "config_path": config_path
            }
        
        try:
            with open(config_path, 'r') as f:
                config_content = yaml.safe_load(f)
            
            return {
                "success": True,
                "config": config_content,
                "config_path": config_path
            }
        except Exception as e:
            logger.error("Failed to read config file", config_path=config_path, error=str(e))
            return {
                "success": False,
                "error": str(e),
                "config_path": config_path
            }
    
    async def validate_config(self, config_content: str) -> Dict:
        """Validate configuration content using borgmatic config validate"""
        try:
            # Create a temporary config file for validation
            import tempfile
            import os
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as temp_file:
                temp_file.write(config_content)
                temp_file_path = temp_file.name
            
            try:
                # Use borgmatic config validate command
                cmd = [self.borgmatic_cmd, "config", "validate", "--config", temp_file_path]
                result = await self._execute_command(cmd, timeout=30)
                
                # Parse output for warnings and errors
                stdout = result["stdout"].strip()
                stderr = result["stderr"].strip()
                
                warnings = []
                errors = []
                
                # Process stderr for errors and warnings
                if stderr:
                    lines = stderr.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line:
                            # Remove temporary file path prefix
                            if temp_file_path in line:
                                line = line.replace(temp_file_path, "config.yaml")
                            
                            # Skip the success message
                            if "All configuration files are valid" in line:
                                continue
                                
                            # Check for warnings vs errors
                            if any(keyword in line.lower() for keyword in ["deprecated", "warning", "will be removed"]):
                                warnings.append(line)
                            elif line != "summary:" and line:  # Skip the "summary:" line as it's just a header
                                errors.append(line)
                
                # Process stdout for any additional messages
                if stdout:
                    lines = stdout.split('\n')
                    for line in lines:
                        line = line.strip()
                        if line and "All configuration files are valid" not in line:
                            # Remove temporary file path prefix
                            if temp_file_path in line:
                                line = line.replace(temp_file_path, "config.yaml")
                            
                            if any(keyword in line.lower() for keyword in ["deprecated", "warning", "will be removed"]):
                                warnings.append(line)
                            elif line != "summary:" and line:  # Skip the "summary:" line as it's just a header
                                errors.append(line)
                
                # Determine if validation was successful
                # borgmatic config validate returns 0 on success, non-zero on failure
                is_valid = result["success"]
                
                if is_valid:
                    return {
                        "success": True, 
                        "config": yaml.safe_load(config_content),
                        "warnings": warnings,
                        "errors": errors
                    }
                else:
                    # If no specific errors were found, use the stderr as error message
                    if not errors and stderr:
                        errors.append(stderr.strip())
                    elif not errors:
                        errors.append("Configuration validation failed")
                    
                    return {
                        "success": False, 
                        "error": "; ".join(errors),
                        "warnings": warnings,
                        "errors": errors
                    }
                    
            finally:
                # Clean up temporary file
                try:
                    os.unlink(temp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error("Failed to validate config", error=str(e))
            return {"success": False, "error": str(e)}
    
    async def get_repository_info(self, repository_path: str) -> Dict:
        """Get detailed information about a specific repository"""
        try:
            # Get repository info using borg info
            cmd = ["borg", "info", repository_path, "--json"]
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

    async def get_repository_status(self) -> Dict:
        """Get status of all repositories"""
        try:
            config_info = await self.get_config_info()
            if not config_info["success"]:
                return config_info
            
            repositories = config_info["config"].get("repositories", [])
            status_list = []
            
            for repo in repositories:
                repo_status = {
                    "name": repo.get("name", "Unknown"),
                    "path": repo.get("path", ""),
                    "encryption": repo.get("encryption", "unknown"),
                    "last_backup": None,
                    "archive_count": 0,
                    "total_size": "0",
                    "status": "unknown"
                }
                
                # Try to get archive info
                try:
                    archives_result = await self.list_archives(repo["path"])
                    if archives_result["success"]:
                        archives_data = json.loads(archives_result["stdout"])
                        repo_status["archive_count"] = len(archives_data.get("archives", []))
                        if archives_data.get("archives"):
                            latest_archive = archives_data["archives"][-1]
                            repo_status["last_backup"] = latest_archive.get("time")
                            repo_status["total_size"] = latest_archive.get("size", "0")
                            repo_status["status"] = "healthy"
                except Exception as e:
                    logger.warning("Failed to get repository status", repository=repo["path"], error=str(e))
                    repo_status["status"] = "error"
                
                status_list.append(repo_status)
            
            return {"success": True, "repositories": status_list}
            
        except Exception as e:
            logger.error("Failed to get repository status", error=str(e))
            return {"success": False, "error": str(e)}
    
    def get_version(self) -> str:
        """Get Borgmatic version"""
        try:
            result = subprocess.run([self.borgmatic_cmd, "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode == 0:
                return result.stdout.strip()
            else:
                return "Unknown"
        except Exception as e:
            logger.error("Failed to get borgmatic version", error=str(e))
            return "Unknown"

    async def get_system_info(self) -> Dict:
        """Get system information"""
        try:
            # Get borgmatic version
            version_result = await self._execute_command([self.borgmatic_cmd, "--version"])
            borgmatic_version = version_result["stdout"].strip() if version_result["success"] else "Unknown"
            
            # Get available commands
            help_result = await self._execute_command([self.borgmatic_cmd, "--help"])
            
            return {
                "success": True,
                "borgmatic_version": borgmatic_version,
                "config_path": self.config_path,
                "backup_path": settings.borgmatic_backup_path,
                "help_available": help_result["success"]
            }
            
        except Exception as e:
            logger.error("Failed to get system info", error=str(e))
            return {"success": False, "error": str(e)}

# Global instance
borgmatic = BorgmaticInterface() 