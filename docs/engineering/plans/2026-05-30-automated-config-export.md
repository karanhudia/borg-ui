# Automated Configuration Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a script-friendly Borg UI configuration export command that reuses the web UI export format.

**Architecture:** Keep `BorgmaticExportService` as the repository export source. Add a shared export artifact builder for YAML/ZIP packaging, update the FastAPI route to use it, and add `app.scripts.export_config` as the local CLI wrapper around the same service.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, PyYAML, pytest, ruff.

---

## Task 1: Shared Export Artifact Builder

**Files:**
- Modify: `app/services/borgmatic_service.py`
- Modify: `app/routers/config.py`
- Test: `tests/unit/test_borgmatic_service.py`
- Test: `tests/unit/test_api_config_export.py`

- [ ] Add failing service tests for a single-repository artifact returning YAML bytes and a `.yaml` filename.
- [ ] Add failing service tests for a multi-repository artifact returning ZIP bytes and a `.zip` filename.
- [ ] Implement a `BorgmaticExportArtifact` dataclass and `build_borgmatic_export_artifact(configs, timestamp=None)` helper.
- [ ] Refactor `app/routers/config.py` to use the helper instead of duplicating YAML/ZIP packaging.
- [ ] Run `pytest tests/unit/test_borgmatic_service.py tests/unit/test_api_config_export.py -q`.

## Task 2: Local Export Script

**Files:**
- Create: `app/scripts/export_config.py`
- Test: `tests/unit/test_export_config_script.py`

- [ ] Add failing CLI tests for `--output /tmp/borg-ui-config.yaml` writing YAML when one repository is exported.
- [ ] Add failing CLI tests for repeated `--repository-id` writing a ZIP when multiple repositories are exported.
- [ ] Add failing CLI tests for `--output -` writing the artifact to stdout.
- [ ] Add failing CLI tests for no repositories returning exit code `1` and an explanatory stderr message.
- [ ] Implement argparse options: `--output`, `--repository-id`, `--no-schedules`.
- [ ] Open and close `SessionLocal` inside `main()`.
- [ ] Write parent directories for file outputs and write bytes atomically enough for normal pre-backup use by using a temporary sibling file followed by `replace()`.
- [ ] Run `pytest tests/unit/test_export_config_script.py -q`.

## Task 3: Documentation

**Files:**
- Modify: `docs/export-import.md`
- Modify: `docs/disaster-recovery.md`

- [ ] Document the local command, selected-repository options, stdout mode, and sensitivity of exports.
- [ ] Add a disaster recovery pre-backup script example that stores the automated export beside the `/data` backup.
- [ ] Preserve the guidance that `/data` remains the full Borg UI recovery boundary.

## Task 4: Final Validation and Handoff

**Files:**
- Update Linear workpad only

- [ ] Run targeted tests: `pytest tests/unit/test_borgmatic_service.py tests/unit/test_api_config_export.py tests/unit/test_export_config_script.py -q`.
- [ ] Run backend gates: `ruff check app tests` and `ruff format --check app tests`.
- [ ] Run local smoke: create a temporary SQLite database, seed one repository, and run `python3 -m app.scripts.export_config --output /tmp/borg-ui-config.yaml`.
- [ ] Commit with the commit skill, push with the push skill, create/link the PR, apply the `symphony` PR label, sweep PR feedback/checks, and move the Linear issue to Human Review when green.
