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


TICKER = (
    "import sys, time\n"
    "n = int(sys.argv[1])\n"
    "for _ in range(n):\n"
    "    print('tick', flush=True)\n"
    "    time.sleep(0.05)\n"
)


@pytest.mark.unit
@pytest.mark.asyncio
async def test_max_duration_bounds_a_command_that_never_goes_idle():
    """A per-read timeout alone never fires for a command that keeps emitting a
    line just often enough, so it could hold the repository metadata lock
    forever. The total cap covers the run as a whole."""
    stream = CommandLineStream(
        [sys.executable, "-c", TICKER, "100000"], timeout=30, max_duration=1
    )

    with pytest.raises(asyncio.TimeoutError):
        async for _ in stream:
            pass

    assert stream.return_code is not None and stream.return_code != 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_a_steadily_progressing_command_is_not_killed_by_the_idle_timeout():
    """`timeout` is the idle bound: time waiting for the next line, not the
    whole run. A long `borg list` that keeps producing output has to be allowed
    to finish, or a large archive can never be indexed."""
    stream = CommandLineStream(
        [sys.executable, "-c", TICKER, "20"], timeout=1, max_duration=30
    )

    lines = [line async for line in stream]

    # 20 lines at 0.05s each runs past the 1s idle timeout without tripping it.
    assert len(lines) == 20
    assert stream.return_code == 0


@pytest.mark.unit
@pytest.mark.asyncio
async def test_idle_timeout_fires_when_no_line_arrives():
    stream = CommandLineStream(
        [sys.executable, "-c", "import time; time.sleep(30)"],
        timeout=1,
        max_duration=30,
    )

    with pytest.raises(asyncio.TimeoutError):
        async for _ in stream:
            pass

    assert stream.return_code is not None and stream.return_code != 0
