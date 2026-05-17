from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import Iterable, Optional


@dataclass(frozen=True)
class BorgBinary:
    major: int
    version: str
    path: str

    def to_api_payload(self) -> dict:
        return {"major": self.major, "version": self.version, "path": self.path}


def detect_platform() -> dict:
    return {
        "hostname": platform.node(),
        "os": platform.system().lower() or "unknown",
        "arch": platform.machine() or "unknown",
    }


def _parse_borg_version(output: str) -> Optional[tuple[int, str]]:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?(?:[A-Za-z0-9.+-]*)?", output)
    if not match:
        return None
    version = match.group(0)
    return int(match.group(1)), version


def detect_borg_binaries(
    candidates: Iterable[str] = ("borg", "borg2"),
    timeout_seconds: int = 5,
) -> list[BorgBinary]:
    binaries: list[BorgBinary] = []
    seen_paths: set[str] = set()

    for candidate in candidates:
        path = shutil.which(candidate)
        if not path or path in seen_paths:
            continue
        seen_paths.add(path)
        try:
            result = subprocess.run(
                [path, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
            )
        except (OSError, subprocess.TimeoutExpired):
            continue

        parsed = _parse_borg_version(f"{result.stdout}\n{result.stderr}")
        if not parsed:
            continue
        major, version = parsed
        binaries.append(BorgBinary(major=major, version=version, path=path))

    return binaries
