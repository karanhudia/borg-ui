# Docker Mount Size Scan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for implementation. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add best-effort Docker mount size metadata to container scans and render the result in the backup-plan Docker source UI.

**Architecture:** Extend the existing Docker scan contract rather than adding a new endpoint. Container scan parsing builds mount rows first, then enriches them with per-mount bounded `du` results for local or SSH targets. The frontend treats size fields as optional metadata on existing mount rows so mount selection behavior remains unchanged.

**Tech Stack:** FastAPI, Pydantic, subprocess, pytest, React, TypeScript, MUI, Vitest, Storybook.

---

## Task 1: Backend Mount Size Contract

**Files:**

- Modify: `app/api/source_discovery.py`
- Modify: `tests/unit/test_source_discovery.py`

- [ ] Write a failing test in `tests/unit/test_source_discovery.py` that scans a local container with a bind mount and expects `size_bytes` plus `size_status: "available"`.
- [ ] Write failing tests for missing source path, permission failure, and timeout states.
- [ ] Add `size_bytes` and `size_status` to `ContainerMount`.
- [ ] Add local and remote bounded mount-size probe helpers.
- [ ] Enrich parsed container mounts after Docker inspect parsing without changing scan failure behavior.
- [ ] Run `pytest tests/unit/test_source_discovery.py -k "container_scan" -q` and keep it green.

## Task 2: Frontend Types And Rendering

**Files:**

- Modify: `frontend/src/services/api.ts`
- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.tsx`
- Modify: `frontend/src/pages/backup-plans/__tests__/SourceStep.test.tsx`

- [ ] Write a failing SourceStep test that expects a scanned Docker mount with `size_status: "available"` to display the formatted size near the mount source path.
- [ ] Write a failing SourceStep test that expects unavailable/permission/timeout state copy to render clearly.
- [ ] Add optional mount size fields to `SourceDiscoveryContainerMount`.
- [ ] Add compact mount size/status rendering in the existing Docker mount rows.
- [ ] Run the targeted SourceStep test and keep it green.

## Task 3: Storybook, Locales, And Validation

**Files:**

- Modify: `frontend/src/pages/backup-plans/wizard-step/SourceSelectionDialog.stories.tsx`
- Modify: `frontend/src/locales/en.json`
- Modify: `frontend/src/locales/de.json`
- Modify: `frontend/src/locales/es.json`
- Modify: `frontend/src/locales/it.json`

- [ ] Add locale keys for available, unavailable, permission-denied, and timeout mount-size states.
- [ ] Update the Docker detected-container story with available, unavailable, permission-denied, and timeout mount-size examples.
- [ ] Run backend validation: `ruff check app tests`, `ruff format --check app tests`, and `pytest tests/unit/test_source_discovery.py -k "container_scan" -q`.
- [ ] Run frontend validation: `cd frontend && npm test -- src/pages/backup-plans/__tests__/SourceStep.test.tsx -t "Docker|container" --run`, `npm run check:locales`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Run local UI/runtime proof or document the concrete browser/runtime blocker in the Linear workpad.
