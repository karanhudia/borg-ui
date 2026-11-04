#!/usr/bin/env python3
"""Fail CI for unsuccessful selected checks, including accidental skips."""

from __future__ import annotations

import json
import os

BACKEND_JOBS = {
    "backend-unit-coverage",
    "backend-unit-coverage-combine",
    "backend-migration-paths",
    "backend-api-integration",
}
ALWAYS_JOBS = {
    "typecheck-lint-format",
    "frontend-vitest",
    "frontend-build",
    "smoke-borg-core",
    "smoke-borg-extended",
    "smoke-borg-ssh-localhost",
}


def failures(jobs: dict, event: str) -> list[str]:
    errors = []
    prepare = jobs.get("prepare", {})
    scope = prepare.get("outputs", {}).get("backend")
    if prepare.get("result") != "success" or scope not in {"true", "false"}:
        errors.append("CI preparation failed or returned invalid scope")
    if event != "pull_request" and scope != "true":
        errors.append("Non-PR runs must select the full suite")
    for name in sorted(BACKEND_JOBS | ALWAYS_JOBS):
        result = jobs.get(name, {}).get("result", "missing")
        skip_allowed = (name in BACKEND_JOBS and scope == "false") or (
            name == "smoke-borg-core" and event == "schedule"
        )
        if result != "success" and not (result == "skipped" and skip_allowed):
            errors.append(f"{name}: {result}")
    return errors


def main() -> None:
    jobs = json.loads(os.environ["CI_JOB_RESULTS"])
    errors = failures(jobs, os.environ["CI_EVENT_NAME"])
    for name, job in sorted(jobs.items()):
        print(f"{name}: {job.get('result', 'missing')}")
    if errors:
        raise SystemExit("\n".join(errors))
    print("All selected CI lanes passed")


if __name__ == "__main__":
    main()
