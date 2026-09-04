"""Line-streaming subprocess runner for Borg commands whose output must not
be buffered whole: `borg diff --json-lines` and `borg list --json-lines` on
large archives (spec 6.7, "diff output is streamed line by line")."""

import asyncio
from typing import AsyncIterator, Optional

# Longest accepted output line. Paths are unbounded in theory; 4 MiB is far
# past anything a filesystem allows.
LINE_LIMIT = 4 * 1024 * 1024


class CommandLineStream:
    """Async iterator over a command's stdout lines.

    After iteration finishes (or `close()` is awaited) `return_code` and
    `stderr` are populated. Iterating twice is not supported.
    """

    def __init__(
        self, cmd: list[str], *, env: Optional[dict] = None, timeout: int = 3600
    ):
        self.cmd = cmd
        self.env = env
        self.timeout = timeout
        self.return_code: Optional[int] = None
        self.stderr: str = ""
        self._process: Optional[asyncio.subprocess.Process] = None
        self._stderr_task: Optional[asyncio.Task] = None

    async def _start(self) -> None:
        self._process = await asyncio.create_subprocess_exec(
            *self.cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=self.env,
            limit=LINE_LIMIT,
        )
        # Drain stderr concurrently so a chatty command cannot deadlock on a
        # full pipe while we read stdout.
        self._stderr_task = asyncio.create_task(self._process.stderr.read())

    async def __aiter__(self) -> AsyncIterator[str]:
        await self._start()
        try:
            while True:
                line = await asyncio.wait_for(
                    self._process.stdout.readline(), timeout=self.timeout
                )
                if not line:
                    break
                yield line.decode("utf-8", errors="replace").rstrip("\r\n")
        finally:
            await self._finish()

    async def _finish(self) -> None:
        if self._process is None:
            return
        if self._process.returncode is None:
            try:
                await asyncio.wait_for(self._process.wait(), timeout=30)
            except asyncio.TimeoutError:
                self._process.kill()
                await self._process.wait()
        self.return_code = self._process.returncode
        if self._stderr_task is not None:
            self.stderr = (await self._stderr_task).decode("utf-8", errors="replace")

    async def close(self) -> None:
        """Terminate early. Safe to call more than once."""
        if self._process is not None and self._process.returncode is None:
            self._process.kill()
        await self._finish()
