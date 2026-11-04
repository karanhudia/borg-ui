#!/usr/bin/env python3
"""Require all consolidated security gates, including after an earlier failure."""

from __future__ import annotations

import json
import os

REQUIRED_GATES = (
    "path-checker-self-test",
    "personal-paths",
    "npm-audit",
    "pip-audit",
    "trivy-fs",
)


def failures(steps: dict) -> list[str]:
    errors = []
    for name in REQUIRED_GATES:
        outcome = steps.get(name, {}).get("outcome", "missing")
        if outcome != "success":
            errors.append(f"{name}: {outcome}")
    return errors


def main() -> None:
    steps = json.loads(os.environ["SECURITY_CHECK_RESULTS"])
    for name in REQUIRED_GATES:
        print(f"{name}: {steps.get(name, {}).get('outcome', 'missing')}")
    errors = failures(steps)
    if errors:
        raise SystemExit("\n".join(errors))


if __name__ == "__main__":
    main()
