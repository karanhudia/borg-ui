from __future__ import annotations

import asyncio
import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.config import settings


class RcloneUnavailable(RuntimeError):
    """Raised when the rclone binary is not available."""


@dataclass
class RcloneCommandResult:
    success: bool
    return_code: int
    stdout: str
    stderr: str
    command: list[str]
    redacted_command: str

    def json(self) -> Any:
        return json.loads(self.stdout or "null")


class RcloneService:
    def __init__(
        self,
        *,
        binary: str = "rclone",
        config_path: str | None = None,
        default_transfers: int | None = None,
        default_checkers: int | None = None,
    ):
        self.binary = binary
        self.config_path = config_path
        self.default_transfers = default_transfers or settings.rclone_default_transfers
        self.default_checkers = default_checkers or settings.rclone_default_checkers

    def _base_command(self, *, include_config: bool = True) -> list[str]:
        command = [self.binary]
        if include_config and self.config_path:
            command.extend(["--config", self.config_path])
        return command

    def version_command(self) -> list[str]:
        return self._base_command(include_config=False) + ["version"]

    def listremotes_command(self) -> list[str]:
        return self._base_command() + ["listremotes"]

    def lsjson_command(self, target: str) -> list[str]:
        return self._base_command() + ["lsjson", target]

    def about_command(self, target: str) -> list[str]:
        return self._base_command() + ["about", target]

    def authorize_command(
        self,
        provider: str,
        *,
        client_id: str | None = None,
        client_secret: str | None = None,
    ) -> list[str]:
        command = self._base_command(include_config=False) + ["authorize", provider]
        if client_id and client_secret:
            command.extend([client_id, client_secret])
        command.append("--auth-no-open-browser")
        return command

    def sync_command(
        self, source: str, destination: str, *, extra_flags: list[str] | None = None
    ) -> list[str]:
        command = self._base_command() + [
            "sync",
            source,
            destination,
            "--transfers",
            str(self.default_transfers),
            "--checkers",
            str(self.default_checkers),
        ]
        command.extend(extra_flags or [])
        return command

    def check_command(
        self, source: str, destination: str, *, extra_flags: list[str] | None = None
    ) -> list[str]:
        command = self._base_command() + ["check", source, destination]
        command.extend(extra_flags or [])
        return command

    def redact_command(self, command: list[str]) -> str:
        sensitive_flags = {
            "--password",
            "--s3-access-key-id",
            "--s3-secret-access-key",
            "--token",
            "--client-secret",
            "--drive-client-secret",
            "--b2-key",
        }
        redacted: list[str] = []
        redact_next = False
        for part in command:
            if redact_next:
                redacted.append("<redacted>")
                redact_next = False
                continue
            if part == "--config":
                redacted.append(part)
                redact_next = True
                continue
            if part.startswith("--config="):
                redacted.append("--config=<rclone-config>")
                continue
            if part in sensitive_flags:
                redacted.append(part)
                redact_next = True
                continue
            if any(part.startswith(f"{flag}=") for flag in sensitive_flags):
                flag = part.split("=", 1)[0]
                redacted.append(f"{flag}=<redacted>")
                continue
            if part == self.config_path:
                redacted.append("<rclone-config>")
                continue
            if _looks_like_path_or_remote(part):
                redacted.append("<path>")
                continue
            redacted.append(part)
        return " ".join(redacted).replace(
            "--config <redacted>", "--config <rclone-config>"
        )

    async def execute(self, command: list[str], *, timeout: int) -> RcloneCommandResult:
        try:
            process = await asyncio.create_subprocess_exec(
                *command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except (FileNotFoundError, OSError) as exc:
            raise RcloneUnavailable(f"rclone binary not found: {exc}") from exc

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )
        except asyncio.TimeoutError:
            process.kill()
            await process.wait()
            raise

        return RcloneCommandResult(
            success=process.returncode == 0,
            return_code=process.returncode or 0,
            stdout=stdout.decode() if stdout else "",
            stderr=stderr.decode() if stderr else "",
            command=command,
            redacted_command=self.redact_command(command),
        )

    async def status(self) -> dict[str, Any]:
        if shutil.which(self.binary) is None and not os.path.exists(self.binary):
            raise RcloneUnavailable("rclone binary not found")
        result = await self.execute(self.version_command(), timeout=30)
        first_line = (result.stdout or "").splitlines()[0] if result.stdout else None
        return {
            "available": result.success,
            "version": first_line,
            "error": None if result.success else result.stderr,
        }

    async def about(self, target: str, *, timeout: int = 60) -> dict[str, Any]:
        result = await self.execute(self.about_command(target), timeout=timeout)
        return {
            "success": result.success,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "redacted_command": result.redacted_command,
        }

    async def lsjson(self, target: str, *, timeout: int = 60) -> list[dict[str, Any]]:
        result = await self.execute(self.lsjson_command(target), timeout=timeout)
        if not result.success:
            raise RuntimeError(result.stderr or "rclone lsjson failed")
        parsed = result.json()
        return parsed if isinstance(parsed, list) else []

    async def sync(
        self,
        source: str,
        destination: str,
        *,
        timeout: int,
        extra_flags: list[str] | None = None,
    ) -> RcloneCommandResult:
        return await self.execute(
            self.sync_command(source, destination, extra_flags=extra_flags),
            timeout=timeout,
        )


def _looks_like_path_or_remote(value: str) -> bool:
    if value.startswith("-"):
        return False
    return (
        value.startswith("/")
        or value.startswith("~")
        or (":" in value and not value.startswith("http"))
    )


def _default_config_path() -> str:
    return str(Path(settings.rclone_config_root) / "rclone.conf")


rclone_service = RcloneService(config_path=_default_config_path())
