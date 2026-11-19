"""Read facts about a running process from /proc."""

import structlog

logger = structlog.get_logger()


def get_process_start_time(pid: int) -> int:
    """Start time of a process in jiffies since boot, or 0 when it cannot be read.

    Stored next to the PID so a reused PID is not mistaken for the same process.
    """
    try:
        with open(f"/proc/{pid}/stat", "r") as f:
            stat_data = f.read()
        # pid (comm) state ppid ... starttime. Split on ")" because the process
        # name may hold spaces or parentheses; starttime is the 22nd field overall.
        fields = stat_data.split(")")[1].split()
        return int(fields[19])
    except Exception as e:
        logger.error("Failed to read process start time", pid=pid, error=str(e))
        return 0
