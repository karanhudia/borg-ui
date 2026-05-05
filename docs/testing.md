---
title: Testing
nav_order: 11
description: "Local and CI checks for Borg UI"
permalink: /testing
---

# Testing

Run checks that match the area you changed.

## Docs

```bash
cd docs
npm ci
npm run build
```

## Frontend

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run format:check
npm test
npm run build
```

## Backend

```bash
ruff check app tests
ruff format --check app tests
pytest
```

## Smoke Tests

Smoke tests need a running Borg UI instance.

```bash
docker compose up -d --build
python3 tests/smoke/run_core_smoke.py --url http://localhost:8081
```

Run broader suites when touching backup, restore, repository, archive, SSH, or scheduling behavior.

Some smoke tests require host capabilities or external setup:

- FUSE archive mounting tests require FUSE support.
- Remote SSH tests require SSH test configuration.
- OIDC tests require an OIDC test setup.

## What To Run

| Change | Minimum check |
| --- | --- |
| Docs only | `cd docs && npm run build` |
| Frontend UI | frontend typecheck, lint, tests |
| Backend API | backend lint and relevant pytest |
| Backup/restore core | relevant unit tests plus smoke tests |
| Docker/runtime | build image and run smoke tests |
