"""The size probe sent over ssh runs on whatever du the remote host has (#1291).

GNU du takes -b; BSD du (macOS) rejects it, so the command falls back to
-A -sk and tags the KiB output. Each test runs the real shell command against
a fake du on PATH.
"""

import subprocess
from pathlib import Path

import pytest

from app.utils.fs import parse_remote_du, remote_du_command

GNU_DU = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
[ "$1" = -sb ] || { echo "du: invalid option -- 'A'" >&2; exit 1; }
for last; do :; done
printf '169984\\t%s\\n' "$last"
"""

BSD_DU = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
[ "$1" = -sb ] && { echo "du: invalid option -- b" >&2; exit 64; }
for last; do :; done
printf '166\\t%s\\n' "$last"
"""


def _run(tmp_path: Path, fake_du: str, command: str) -> tuple[str, list[str]]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    du = bin_dir / "du"
    du.write_text(fake_du)
    du.chmod(0o755)
    proc = subprocess.run(
        ["/bin/sh", "-c", command],
        capture_output=True,
        text=True,
        env={"PATH": f"{bin_dir}:/usr/bin:/bin"},
        check=True,
    )
    return proc.stdout, (bin_dir / "calls").read_text().splitlines()


@pytest.mark.unit
def test_gnu_du_reports_apparent_bytes(tmp_path):
    stdout, calls = _run(tmp_path, GNU_DU, remote_du_command("/srv/a b", ["*.tmp"]))

    assert parse_remote_du(stdout) == 169984
    assert calls[-1] == "-sb --exclude=*.tmp -- /srv/a b"


@pytest.mark.unit
def test_bsd_du_reports_apparent_kib_scaled_to_bytes(tmp_path):
    stdout, calls = _run(tmp_path, BSD_DU, remote_du_command("/srv/a b", ["*.tmp"]))

    assert parse_remote_du(stdout) == 166 * 1024
    assert calls[-1] == "-A -sk -I *.tmp -- /srv/a b"


@pytest.mark.unit
@pytest.mark.parametrize("stdout", ["", "KiB\n", "du: oops\n", "KiB\nx\t/p\n"])
def test_output_without_a_size_is_unknown(stdout):
    assert parse_remote_du(stdout) is None


GNU_DU_ALLOCATED = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
for last; do :; done
case "$1 $2" in
  "-s -B1") printf '172032\\t%s\\n' "$last" ;;
  -sb*) printf '169984\\t%s\\n' "$last" ;;
  *) echo "du: invalid option -- 'A'" >&2; exit 1 ;;
esac
"""

# Real BSD du accepts -B (a blocksize) and prints 512-byte blocks, so only
# a rejected -b tells it apart from GNU du.
BSD_DU_ALLOCATED = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
for last; do :; done
case "$1" in
  -sb) echo "du: invalid option -- b" >&2; exit 64 ;;
  -s) printf '336\\t%s\\n' "$last" ;;
  *) printf '168\\t%s\\n' "$last" ;;
esac
"""

# BusyBox du has -b but no -B.
BUSYBOX_DU = """#!/bin/sh
echo "$@" >> "$(dirname "$0")/calls"
for last; do :; done
case "$1 $2" in
  "-s -B1") echo "du: invalid option -- 'B'" >&2; exit 1 ;;
  -sb*) printf '169984\\t%s\\n' "$last" ;;
  *) printf '168\\t%s\\n' "$last" ;;
esac
"""


@pytest.mark.unit
def test_gnu_du_reports_allocated_bytes(tmp_path):
    # The mount size probe reports allocated size, as its local `du -s -B1`.
    stdout, calls = _run(
        tmp_path, GNU_DU_ALLOCATED, remote_du_command("/srv/m", apparent=False)
    )

    assert parse_remote_du(stdout) == 172032
    assert calls[-1] == "-s -B1 -- /srv/m"


@pytest.mark.unit
def test_bsd_du_reports_allocated_kib_scaled_to_bytes(tmp_path):
    stdout, calls = _run(
        tmp_path, BSD_DU_ALLOCATED, remote_du_command("/srv/m", apparent=False)
    )

    assert parse_remote_du(stdout) == 168 * 1024
    assert calls[-1] == "-sk -- /srv/m"


@pytest.mark.unit
def test_busybox_du_reports_allocated_kib_scaled_to_bytes(tmp_path):
    stdout, calls = _run(
        tmp_path, BUSYBOX_DU, remote_du_command("/srv/m", apparent=False)
    )

    assert parse_remote_du(stdout) == 168 * 1024
    assert calls[-1] == "-sk -- /srv/m"
