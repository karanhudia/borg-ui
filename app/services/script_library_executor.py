"""
Script Library Executor Service

Handles execution of scripts from the script library, including:
- Loading scripts for a repository
- Chaining multiple scripts in order
- Checking run_on conditions
- Recording executions in database
- Rendering script templates with parameters
"""
from typing import List, Dict, Optional, Literal
from sqlalchemy.orm import Session, joinedload
from datetime import datetime
from pathlib import Path
import time
import structlog
import json
import os

from app.database.models import Script, RepositoryScript, ScriptExecution, Repository, BackupJob
from app.services.script_executor import execute_script
from app.services.template_service import get_system_variables
from app.config import settings

logger = structlog.get_logger()

HookType = Literal["pre-backup", "post-backup"]
BackupResult = Literal["success", "failure", "warning"]

class ScriptLibraryExecutor:
    """Manages script library execution for backup hooks"""

    def __init__(self, db: Session):
        self.db = db

    async def execute_hooks(
        self,
        repository_id: int,
        hook_type: HookType,
        backup_result: Optional[BackupResult] = None,
        backup_job_id: Optional[int] = None
    ) -> Dict:
        """
        Execute all scripts for a repository hook

        Args:
            repository_id: Repository ID
            hook_type: 'pre-backup' or 'post-backup'
            backup_result: 'success', 'failure', 'warning' (required for post-backup)
            backup_job_id: BackupJob ID for execution tracking

        Returns:
            Dict with execution results:
            {
                'success': bool,
                'scripts_executed': int,
                'scripts_failed': int,
                'execution_logs': List[str],
                'executions': List[Dict]  # Execution records
            }
        """
        logger.info("Executing script library hooks",
                   repository_id=repository_id,
                   hook_type=hook_type,
                   backup_result=backup_result)

        # Load scripts for this repository and hook type
        repo_scripts = self.db.query(RepositoryScript).filter(
            RepositoryScript.repository_id == repository_id,
            RepositoryScript.hook_type == hook_type,
            RepositoryScript.enabled == True
        ).options(
            joinedload(RepositoryScript.script)
        ).order_by(RepositoryScript.execution_order).all()

        if not repo_scripts:
            logger.debug("No scripts configured for hook",
                        repository_id=repository_id,
                        hook_type=hook_type)
            return {
                'success': True,
                'scripts_executed': 0,
                'scripts_failed': 0,
                'execution_logs': [],
                'executions': []
            }

        # Filter scripts based on run_on condition (post-backup only)
        scripts_to_run = []
        if hook_type == "post-backup" and backup_result:
            for rs in repo_scripts:
                # Use custom_run_on if set, otherwise use script's default
                run_on = rs.custom_run_on or rs.script.run_on

                should_run = self._should_run_script(run_on, backup_result)
                if should_run:
                    scripts_to_run.append(rs)
                else:
                    logger.debug("Skipping script due to run_on condition",
                               script_id=rs.script_id,
                               script_name=rs.script.name,
                               run_on=run_on,
                               backup_result=backup_result)
        else:
            # Pre-backup: run all enabled scripts
            scripts_to_run = repo_scripts

        logger.info("Scripts to execute",
                   total_configured=len(repo_scripts),
                   will_execute=len(scripts_to_run),
                   hook_type=hook_type)

        # Execute scripts in order
        execution_logs = []
        executions = []
        scripts_failed = 0

        for rs in scripts_to_run:
            script = rs.script
            logger.info("Executing script",
                       script_id=script.id,
                       script_name=script.name,
                       execution_order=rs.execution_order)

            # Execute script and record results
            result = await self._execute_script_and_record(
                repo_script=rs,
                repository_id=repository_id,
                backup_job_id=backup_job_id,
                hook_type=hook_type
            )

            executions.append(result)
            execution_logs.extend(result['logs'])

            if not result['success']:
                # Check if we should continue despite error
                continue_on_error = rs.continue_on_error if rs.continue_on_error is not None else True
                
                if not continue_on_error:
                    scripts_failed += 1
                    logger.warning("Script execution failed",
                                 script_id=script.id,
                                 script_name=script.name,
                                 exit_code=result['exit_code'])
                else:
                    logger.warning("Script execution failed but continuing (continue_on_error=True)",
                                 script_id=script.id,
                                 script_name=script.name,
                                 exit_code=result['exit_code'])
                    # Add a log entry for clarity
                    execution_logs.append(f"WARNING: Script '{script.name}' failed but 'Continue on Failure' is enabled. Backup will proceed.")

        overall_success = scripts_failed == 0

        logger.info("Hook execution completed",
                   repository_id=repository_id,
                   hook_type=hook_type,
                   scripts_executed=len(scripts_to_run),
                   scripts_failed=scripts_failed,
                   overall_success=overall_success)

        return {
            'success': overall_success,
            'scripts_executed': len(scripts_to_run),
            'scripts_failed': scripts_failed,
            'execution_logs': execution_logs,
            'executions': executions
        }

    def _should_run_script(self, run_on: str, backup_result: BackupResult) -> bool:
        """Check if script should run based on run_on condition"""
        if run_on == "always":
            return True
        elif run_on == "success" and backup_result == "success":
            return True
        elif run_on == "failure" and backup_result == "failure":
            return True
        elif run_on == "warning" and backup_result == "warning":
            return True
        return False

    async def _execute_script_and_record(
        self,
        repo_script: RepositoryScript,
        repository_id: int,
        backup_job_id: Optional[int],
        hook_type: HookType
    ) -> Dict:
        """Execute a single script and record execution in database"""
        script = repo_script.script
        start_time = time.time()

        # Create execution record (pending)
        execution = ScriptExecution(
            script_id=script.id,
            repository_id=repository_id,
            backup_job_id=backup_job_id,
            hook_type=hook_type,
            status="running",
            started_at=datetime.utcnow(),
            triggered_by="backup"
        )
        self.db.add(execution)
        self.db.commit()
        self.db.refresh(execution)

        try:
            # Read script content from file
            file_path = Path(settings.data_dir) / "scripts" / script.file_path
            if not file_path.exists():
                raise FileNotFoundError(f"Script file not found: {script.file_path}")

            script_content = file_path.read_text()

            # Get repository info for system variables
            repository = self.db.query(Repository).filter(Repository.id == repository_id).first()
            
            # Prepare environment variables with parameters
            script_env = os.environ.copy()
            
            # Add system variables
            system_vars = get_system_variables(
                repository_id=repository_id,
                repository_name=repository.name if repository else None,
                repository_path=repository.path if repository else None,
                hook_type=hook_type
            )
            script_env.update(system_vars)
            
            # Add script parameters as environment variables
            if script.parameters:
                try:
                    # Parse parameter definitions
                    parameters = json.loads(script.parameters)
                    
                    # Get parameter values (may be encrypted)
                    parameter_values = json.loads(repo_script.parameter_values) if repo_script.parameter_values else {}
                    
                    # Decrypt password-type parameters and add to environment
                    for param_def in parameters:
                        param_name = param_def['name']
                        param_type = param_def.get('type', 'text')
                        default_value = param_def.get('default', '')
                        
                        # Get value from parameter_values or use default
                        value = parameter_values.get(param_name, default_value) if parameter_values else default_value
                        
                        # Decrypt password-type parameters
                        if param_type == 'password' and value:
                            try:
                                from app.core.security import decrypt_secret
                                value = decrypt_secret(value)
                                logger.debug("Decrypted password parameter for env", param_name=param_name)
                            except Exception as e:
                                logger.error("Failed to decrypt password parameter",
                                           param_name=param_name, error=str(e))
                                raise
                        
                        # Add to environment (bash will handle ${VAR:-default} syntax)
                        script_env[param_name] = value or ''
                    
                    logger.info("Prepared script environment with parameters",
                               script_id=script.id,
                               param_count=len(parameters),
                               password_params=[p['name'] for p in parameters if p.get('type') == 'password'])
                except Exception as e:
                    logger.error("Failed to prepare script parameters", script_id=script.id, error=str(e))
                    raise

            # Get timeout (custom or default)
            timeout = repo_script.custom_timeout or script.timeout

            # Execute script with parameters in environment
            logger.info("Executing script file",
                       script_id=script.id,
                       file_path=str(file_path),
                       timeout=timeout)

            exec_result = await execute_script(
                script=script_content,
                timeout=float(timeout),
                env=script_env,  # Pass environment with parameters
                context=f"repo:{repository_id}:script:{script.id}"
            )

            execution_time = time.time() - start_time

            # Update execution record with results
            execution.status = "completed" if exec_result["success"] else "failed"
            execution.completed_at = datetime.utcnow()
            execution.execution_time = execution_time
            execution.exit_code = exec_result["exit_code"]
            execution.stdout = exec_result["stdout"]
            execution.stderr = exec_result["stderr"]

            if not exec_result["success"]:
                execution.error_message = f"Script exited with code {exec_result['exit_code']}"

            self.db.commit()

            # Update script usage
            script.last_used_at = datetime.utcnow()
            self.db.commit()

            # Format logs
            logs = self._format_execution_logs(script, exec_result, execution_time)

            return {
                'success': exec_result["success"],
                'script_id': script.id,
                'script_name': script.name,
                'exit_code': exec_result["exit_code"],
                'execution_time': execution_time,
                'stdout': exec_result["stdout"],
                'stderr': exec_result["stderr"],
                'logs': logs,
                'execution_id': execution.id
            }

        except Exception as e:
            # Record execution failure
            execution.status = "failed"
            execution.completed_at = datetime.utcnow()
            execution.execution_time = time.time() - start_time
            execution.error_message = str(e)
            self.db.commit()

            logger.error("Script execution exception",
                        script_id=script.id,
                        error=str(e))

            logs = [
                "=" * 80,
                f"SCRIPT: {script.name}",
                "=" * 80,
                f"STATUS: FAILED (Exception)",
                f"ERROR: {str(e)}",
                "=" * 80,
                ""
            ]

            return {
                'success': False,
                'script_id': script.id,
                'script_name': script.name,
                'exit_code': None,
                'execution_time': time.time() - start_time,
                'stdout': "",
                'stderr': str(e),
                'logs': logs,
                'execution_id': execution.id
            }

    def _format_execution_logs(self, script: Script, exec_result: Dict, execution_time: float) -> List[str]:
        """Format execution logs for display"""
        status = "SUCCESS" if exec_result["success"] else "FAILED"

        logs = [
            "=" * 80,
            f"SCRIPT: {script.name}",
            "=" * 80,
            f"Exit Code: {exec_result['exit_code']}",
            f"Status: {status}",
            f"Execution Time: {execution_time:.2f}s",
            "",
            "STDOUT:",
            exec_result['stdout'] if exec_result['stdout'] else "(empty)",
            "",
            "STDERR:",
            exec_result['stderr'] if exec_result['stderr'] else "(empty)",
            "=" * 80,
            ""
        ]

        return logs

    async def execute_inline_script(
        self,
        script_content: str,
        script_type: str,
        timeout: int,
        repository_id: int,
        backup_job_id: Optional[int] = None
    ) -> Dict:
        """
        Execute an inline script (backward compatibility)

        This is for repositories still using the old pre_backup_script/post_backup_script fields.
        """
        logger.info("Executing inline script (legacy)",
                   repository_id=repository_id,
                   script_type=script_type)

        start_time = time.time()

        try:
            exec_result = await execute_script(
                script=script_content,
                timeout=float(timeout),
                context=f"repo:{repository_id}:inline:{script_type}"
            )

            execution_time = time.time() - start_time

            logs = [
                "=" * 80,
                f"INLINE {script_type.upper()} SCRIPT",
                "=" * 80,
                f"Exit Code: {exec_result['exit_code']}",
                f"Status: {'SUCCESS' if exec_result['success'] else 'FAILED'}",
                f"Execution Time: {execution_time:.2f}s",
                "",
                "STDOUT:",
                exec_result['stdout'] if exec_result['stdout'] else "(empty)",
                "",
                "STDERR:",
                exec_result['stderr'] if exec_result['stderr'] else "(empty)",
                "=" * 80,
                ""
            ]

            return {
                'success': exec_result["success"],
                'exit_code': exec_result["exit_code"],
                'execution_time': execution_time,
                'stdout': exec_result["stdout"],
                'stderr': exec_result["stderr"],
                'logs': logs
            }

        except Exception as e:
            logger.error("Inline script execution exception",
                        repository_id=repository_id,
                        error=str(e))

            logs = [
                "=" * 80,
                f"INLINE {script_type.upper()} SCRIPT",
                "=" * 80,
                f"STATUS: FAILED (Exception)",
                f"ERROR: {str(e)}",
                "=" * 80,
                ""
            ]

            return {
                'success': False,
                'exit_code': None,
                'execution_time': time.time() - start_time,
                'stdout': "",
                'stderr': str(e),
                'logs': logs
            }
