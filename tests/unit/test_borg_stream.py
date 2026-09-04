import asyncio
import sys

import pytest

from app.core.borg_stream import CommandLineStream


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_yields_lines_then_exposes_exit_and_stderr():
    stream = CommandLineStream(
        [
            sys.executable,
            "-c",
            "import sys; print('a'); print('b'); sys.stderr.write('warn'); sys.exit(1)",
        ]
    )
    lines = [line async for line in stream]
    assert lines == ["a", "b"]
    assert stream.return_code == 1
    assert stream.stderr == "warn"


@pytest.mark.unit
@pytest.mark.asyncio
async def test_stream_close_terminates_a_running_process():
    stream = CommandLineStream(
        [sys.executable, "-c", "import time; print('a', flush=True); time.sleep(30)"]
    )
    first = None
    async for line in stream:
        first = line
        await stream.close()
        break
    assert first == "a"
    assert stream.return_code is not None and stream.return_code != 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_timeout_bounds_the_whole_command_not_each_read():
    """A per-read timeout never fires for a command that keeps emitting a line
    just often enough, so it could hold the repository metadata lock forever.
    The deadline covers the run as a whole."""
    stream = CommandLineStream(
        [
            sys.executable,
            "-c",
            (
                "import sys, time\n"
                "while True:\n"
                "    print('tick', flush=True)\n"
                "    time.sleep(0.05)\n"
            ),
        ],
        timeout=1,
    )

    with pytest.raises(asyncio.TimeoutError):
        async for _ in stream:
            pass

    assert stream.return_code is not None and stream.return_code != 0
