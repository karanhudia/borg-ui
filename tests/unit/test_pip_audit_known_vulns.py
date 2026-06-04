from pathlib import Path

import pytest

from scripts.pip_audit_known_vulns import build_ignore_args, load_known_vulns


def test_build_ignore_args_preserves_file_order(tmp_path: Path) -> None:
    known_vulns_file = tmp_path / "known-vulns.json"
    known_vulns_file.write_text(
        """[
  {"id": "PYSEC-2025-183", "package": "PyJWT", "version": "2.12.1"},
  {"id": "PYSEC-2026-89", "package": "markdown", "version": "3.10.2"}
]""",
        encoding="utf-8",
    )

    assert build_ignore_args(load_known_vulns(known_vulns_file)) == [
        "--ignore-vuln",
        "PYSEC-2025-183",
        "--ignore-vuln",
        "PYSEC-2026-89",
    ]


def test_load_known_vulns_rejects_blank_ids(tmp_path: Path) -> None:
    known_vulns_file = tmp_path / "known-vulns.json"
    known_vulns_file.write_text(
        """[
  {"id": "PYSEC-2025-183"},
  {"id": "   "}
]""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="entry 2"):
        load_known_vulns(known_vulns_file)
