"""Guard: borg-rendered timestamps must go through parse_borg_archive_time.

Borg renders timestamps in the zone of the invoking process, so any direct
fromisoformat/strptime on borg output has to know or guess the render zone -
the mechanism behind the last_backup zone-shift bug. The shared parser
(app/utils/datetime_utils.py) carries that provenance explicitly; a new
direct parse is suspect by construction and must either route through it or
be added to the allowlist below with a reason.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCAN_ROOTS = ("app", "agent")

PARSE_PATTERN = re.compile(
    r"\.fromisoformat\(|\.strptime\(|\.fromtimestamp\(|\.utcfromtimestamp\(|\bdateutil\b"
)

# Direct parse sites that do NOT touch borg-rendered timestamps.
ALLOWED = {
    "app/utils/datetime_utils.py",  # the shared parser itself
    "app/api/agents.py",  # agent session/heartbeat fields (agent-generated)
    "app/api/rclone.py",  # rclone lsjson timestamps
    "app/services/licensing_service.py",  # license validity timestamps
    "app/services/mount_service.py",  # mount bookkeeping timestamps
    "app/api/filesystem.py",  # local file stat mtimes
    "app/services/log_manager.py",  # log file stat mtimes
}


def test_direct_timestamp_parses_are_allowlisted():
    offenders = []
    for root in SCAN_ROOTS:
        for path in sorted((REPO_ROOT / root).rglob("*.py")):
            rel = path.relative_to(REPO_ROOT).as_posix()
            if "__pycache__" in rel:
                continue
            if PARSE_PATTERN.search(path.read_text(encoding="utf-8")):
                if rel not in ALLOWED:
                    offenders.append(rel)

    assert not offenders, (
        "Direct timestamp parsing found outside the allowlist: "
        f"{offenders}. If the value is borg output, route it through "
        "app.utils.datetime_utils.parse_borg_archive_time (it carries the "
        "render-zone provenance); otherwise add the file to ALLOWED in "
        "this test with a reason."
    )
