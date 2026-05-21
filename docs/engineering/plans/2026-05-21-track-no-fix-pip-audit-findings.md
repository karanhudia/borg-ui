# Track No-Fix pip-audit Findings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the PyJWT and markdown no-fix `pip-audit` findings out of temporary workflow inline ignores and into a tested, reviewable tracking file.

**Architecture:** Keep package pins unchanged while the advisory data has no fixed versions. Store no-fix findings in a small JSON file, render them into `pip-audit --ignore-vuln` arguments with a tested Python helper, and have the security workflow consume that helper.

**Tech Stack:** Python 3.11, pytest, GitHub Actions, pip-audit.

---

### Task 1: Helper Contract

**Files:**
- Create: `tests/unit/test_pip_audit_known_vulns.py`
- Create: `scripts/pip_audit_known_vulns.py`

- [ ] **Step 1: Write the failing test**

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/unit/test_pip_audit_known_vulns.py -v`
Expected: FAIL because `scripts.pip_audit_known_vulns` does not exist yet.

- [ ] **Step 3: Implement minimal helper**

Create `scripts/pip_audit_known_vulns.py` with `load_known_vulns`, `build_ignore_args`, and an `ignore-args` CLI command that prints one shell argument per line.

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/unit/test_pip_audit_known_vulns.py -v`
Expected: PASS.

### Task 2: Tracked Findings and Workflow

**Files:**
- Create: `security/pip-audit-known-vulns.json`
- Modify: `.github/workflows/security.yml`

- [ ] **Step 1: Add tracked no-fix findings**

Create `security/pip-audit-known-vulns.json` with `PYSEC-2025-183` and `PYSEC-2026-89`, their package/version, OSV URL, review date, and no-fixed-version reason.

- [ ] **Step 2: Load tracked findings in the workflow**

Replace the workflow's inline comments and `--ignore-vuln` entries for the two ticketed IDs with a note pointing to `security/pip-audit-known-vulns.json` and a bash array loaded from `python scripts/pip_audit_known_vulns.py ignore-args`.

- [ ] **Step 3: Validate helper output**

Run: `python3 scripts/pip_audit_known_vulns.py ignore-args`
Expected:

```text
--ignore-vuln
PYSEC-2025-183
--ignore-vuln
PYSEC-2026-89
```

### Task 3: Security Validation

**Files:**
- No additional source edits.

- [ ] **Step 1: Reconfirm fixed-version signal**

Run package/advisory checks against current PyPI/OSV and record whether fixed versions exist.

- [ ] **Step 2: Prove workflow-equivalent audit passes**

Run the workflow-equivalent `pip-audit -r requirements.txt` command with existing non-ticket ignores plus the helper-rendered tracked no-fix ignores. Expected: exit 0 for the gating command.

- [ ] **Step 3: Prove unignored audit still exposes the no-fix findings**

Run `pip-audit` without the tracked no-fix helper and confirm it still reports `PYSEC-2025-183` and `PYSEC-2026-89` with empty fix versions.

### Task 4: Repository Validation and Handoff

**Files:**
- No additional source edits.

- [ ] **Step 1: Run required checks**

Run `ruff check app tests`, `ruff format --check app tests`, `pytest tests/unit/test_pip_audit_known_vulns.py -v`, and `git diff --check`.

- [ ] **Step 2: Commit and publish**

Commit the plan, helper, tracked findings, tests, and workflow change. Push the branch, open a PR with the repository template, add the `symphony` label, attach/link it to BOR-44, and run the PR feedback/check sweep before moving back to `Human Review`.
