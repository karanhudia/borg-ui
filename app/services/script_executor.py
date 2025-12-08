"""
Shared script execution service.

This module provides a centralized way to execute shell scripts,
ensuring consistent behavior across test runs and production hook execution.
"""
import asyncio
import tempfile
import os
import time
from typing import Dict, Optional
import structlog

logger = structlog.get_logger()


async def execute_script(
    script: str,
    timeout: float = 30.0,
    env: Optional[Dict[str, str]] = None,
    context: str = "script"
) -> Dict:
    """
    Execute a shell script with bash.

    This is the single source of truth for script execution.
    Both test endpoint and backup hooks use this same method.

    Args:
        script: Shell script content to execute
        timeout: Timeout in seconds
        env: Environment variables (defaults to current environment if None)
        context: Context string for logging (e.g., "test", "pre-backup hook")

    Returns:
        Dict with:
            - success: bool
            - stdout: str
            - stderr: str
            - exit_code: int (returncode)
            - execution_time: float
    """
    temp_script = None
    start_time = time.time()

    try:
        logger.info(f"Executing {context}", script_preview=script[:100])

        # Write script to temporary file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.sh', delete=False) as f:
            f.write(script)
            temp_script = f.name

        # Make script executable
        os.chmod(temp_script, 0o755)

        # Use environment if provided, otherwise copy current environment
        script_env = env if env is not None else os.environ.copy()

        # Execute script with bash explicitly
        # This ensures bash-specific syntax (arrays, etc.) works correctly
        process = await asyncio.create_subprocess_exec(
            '/bin/bash',
            temp_script,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=script_env
        )

        # Wait for completion with timeout
        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout
            )
            exit_code = process.returncode
        except asyncio.TimeoutError:
            # Kill the process if it times out
            process.kill()
            await process.wait()
            execution_time = time.time() - start_time

            logger.error(f"{context} timed out", timeout=timeout, execution_time=execution_time)
            return {
                "success": False,
                "stdout": "",
                "stderr": f"Script execution timed out after {timeout} seconds",
                "exit_code": -1,
                "execution_time": execution_time
            }

        execution_time = time.time() - start_time

        # Decode output
        stdout_str = stdout.decode('utf-8', errors='replace') if stdout else ""
        stderr_str = stderr.decode('utf-8', errors='replace') if stderr else ""

        success = exit_code == 0

        if success:
            logger.info(f"{context} completed successfully",
                       exit_code=exit_code,
                       execution_time=execution_time)
        else:
            logger.warning(f"{context} failed",
                          exit_code=exit_code,
                          execution_time=execution_time,
                          stderr=stderr_str[:500])

        return {
            "success": success,
            "stdout": stdout_str,
            "stderr": stderr_str,
            "exit_code": exit_code,
            "execution_time": execution_time
        }

    except Exception as e:
        execution_time = time.time() - start_time
        logger.error(f"{context} execution failed", error=str(e), execution_time=execution_time)
        return {
            "success": False,
            "stdout": "",
            "stderr": f"Script execution error: {str(e)}",
            "exit_code": -1,
            "execution_time": execution_time
        }

    finally:
        # Clean up temporary file
        if temp_script and os.path.exists(temp_script):
            try:
                os.unlink(temp_script)
            except Exception as e:
                logger.warning("Failed to delete temporary script file", error=str(e))
