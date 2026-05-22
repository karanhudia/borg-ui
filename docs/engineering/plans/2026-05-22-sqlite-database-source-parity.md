# SQLite Database Source Parity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQLite to the existing database source discovery and script-template flow.

**Architecture:** Extend the existing source-discovery database template list and path probe model rather than adding a new source flow. The frontend already renders any `SourceDiscoveryDatabase` template, so the only UI artifact update is the Storybook mock data and snapshot.

**Tech Stack:** FastAPI, Pydantic, pytest, React, MUI, Storybook snapshots.

---

## Files

- Modify: `app/api/source_discovery.py`
- Modify: `tests/unit/test_source_discovery.py`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
- Generated: `frontend/storybook-snapshots/backup-plans-sourceselectiondialog--*.png`

## Tasks

- [x] Add failing backend tests.
  - Update the supported-template expectation to include `sqlite`.
  - Add a SQLite-template assertion for `sqlite3`, `SQLITE_DATABASE_PATH`, and `/var/tmp/borg-ui/database-dumps/sqlite`.
  - Add local scan detection for a `.sqlite3` file.
  - Add remote probe-output detection for a `.db` file.
  - Run `DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_discovery.py -q` and confirm the new tests fail because SQLite is not implemented.
- [x] Implement SQLite source discovery.
  - Add `sqlite` defaults to `DEFAULT_DATABASE_SCAN_PATHS_BY_ENGINE`.
  - Add `sqlite_database_file` to `PathProbe`.
  - Add `_sqlite_template()` with pre/post script drafts.
  - Include `_sqlite_template()` in `_templates()`.
  - Detect local SQLite files by suffix and `is_file()`.
  - Emit and parse remote `SQLITE_DB` probe records.
  - Run `DATA_DIR=/tmp/borg-ui-test .venv/bin/pytest tests/unit/test_source_discovery.py -q` and confirm it passes.
- [x] Update UI story coverage.
  - Add a SQLite mock template to `SourceSelectionDialog.stories.tsx`.
  - Update the database detected story description from four to five templates.
  - Run the required frontend checks and snapshots.
- [x] Final verification and handoff.
  - Run backend lint/format checks required for backend changes.
  - Run frontend validation required for the story/snapshot change.
  - Commit, push, link the PR to Linear, sweep PR feedback/checks, then move BOR-54 to Human Review.
