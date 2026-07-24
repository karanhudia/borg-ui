from __future__ import annotations

import platform
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Optional


@dataclass(frozen=True)
class BorgBinary:
    major: int
    version: str
    path: str
    install_source: str

    def to_api_payload(self) -> dict:
        return {
            "major": self.major,
            "version": self.version,
            "path": self.path,
            "install_source": self.install_source,
        }


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


def _classify_install_source(path: str) -> str:
    resolved_path = Path(path).resolve(strict=False)
    installer_root = Path("/opt/borg-ui-agent").resolve(strict=False)

    try:
        if resolved_path.is_relative_to(installer_root):
            return "borg-ui-installer"
    except ValueError:
        pass

    if path.startswith(("/usr/bin/", "/usr/sbin/")):
        return "system-package"
    return "custom-path"


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
        binaries.append(
            BorgBinary(
                major=major,
                version=version,
                path=path,
                install_source=_classify_install_source(path),
            )
        )

    return binaries


def is_warning_return_code(return_code) -> bool:
    """Borg's warning exit codes: legacy rc 1, modern range 100-127.

    Warnings mean the operation ran to completion but something was worth
    telling the operator (a file changed mid-read, a path was missing). They
    are not failures, and the server records them as completed_with_warnings.
    """
    return isinstance(return_code, int) and (
        return_code == 1 or 100 <= return_code <= 127
    )
