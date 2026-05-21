# Borg UI Agent Service User Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Linux `borg-ui-agent` service setup fail fast with clear
service user and group diagnostics before systemd reaches `status=217/USER`.

**Architecture:** Keep the shipped systemd unit simple, add a Python service
setup validator inside the existing agent package, expose it as a
`borg-ui-agent service-check` CLI command, and make the documented Linux install
path create and validate the expected account before enabling the unit.

**Tech Stack:** Python 3.11 stdlib `pwd`/`grp`/`pathlib`, argparse, pytest,
Markdown documentation, systemd unit template.

---

### Task 1: Service Setup Validator And CLI

**Files:**
- Create: `agent/borg_ui_agent/service_setup.py`
- Modify: `agent/borg_ui_agent/cli.py`
- Test: `tests/unit/agent/test_service_setup.py`

- [ ] **Step 1: Write failing service user and group validation tests**

```python
from pathlib import Path

import pytest

from agent.borg_ui_agent.service_setup import (
    DEFAULT_SERVICE_GROUP,
    DEFAULT_SERVICE_USER,
    ServiceSetupError,
    validate_service_identity,
)


def test_validate_service_identity_reports_missing_user(monkeypatch):
    def missing_user(name):
        raise KeyError(name)

    monkeypatch.setattr("agent.borg_ui_agent.service_setup.pwd.getpwnam", missing_user)

    with pytest.raises(ServiceSetupError) as exc:
        validate_service_identity(DEFAULT_SERVICE_USER, DEFAULT_SERVICE_GROUP)

    assert "Service user 'borg-ui-agent' does not exist" in str(exc.value)
    assert "sudo useradd --system --user-group" in str(exc.value)
```

Run:

```bash
pytest tests/unit/agent/test_service_setup.py -q
```

Expected result: fails because `agent.borg_ui_agent.service_setup` does not
exist yet.

- [ ] **Step 2: Implement the minimal validator**

Create `agent/borg_ui_agent/service_setup.py` with:

```python
from __future__ import annotations

import grp
import os
import pwd
from pathlib import Path

DEFAULT_SERVICE_USER = "borg-ui-agent"
DEFAULT_SERVICE_GROUP = "borg-ui-agent"
DEFAULT_SERVICE_EXECUTABLE = Path("/opt/borg-ui-agent/.venv/bin/borg-ui-agent")
DEFAULT_SERVICE_CONFIG = Path("/etc/borg-ui-agent/config.toml")


class ServiceSetupError(RuntimeError):
    pass


def validate_service_identity(user: str, group: str) -> None:
    if not user.strip():
        raise ServiceSetupError("Service user must not be empty.")
    if not group.strip():
        raise ServiceSetupError("Service group must not be empty.")
    try:
        pwd.getpwnam(user)
    except KeyError as exc:
        raise ServiceSetupError(
            f"Service user '{user}' does not exist. Create it with: "
            f"sudo useradd --system --user-group --home-dir "
            f"/var/lib/borg-ui-agent --shell /usr/sbin/nologin {user}"
        ) from exc
    try:
        grp.getgrnam(group)
    except KeyError as exc:
        raise ServiceSetupError(
            f"Service group '{group}' does not exist. Create it with: "
            f"sudo groupadd --system {group}"
        ) from exc
```

- [ ] **Step 3: Add path validation and CLI coverage**

Add tests showing `validate_service_paths()` rejects a missing executable and
that `borg-ui-agent service-check --user ... --group ... --exec ... --config ...`
prints an OK line when all inputs exist.

Run:

```bash
pytest tests/unit/agent/test_service_setup.py -q
```

Expected result: fails until `validate_service_paths()` and the CLI subcommand
are implemented.

- [ ] **Step 4: Wire the CLI command**

Modify `agent/borg_ui_agent/cli.py` so `build_parser()` adds:

```python
service_check = subparsers.add_parser("service-check")
service_check.add_argument("--user", default=DEFAULT_SERVICE_USER)
service_check.add_argument("--group", default=DEFAULT_SERVICE_GROUP)
service_check.add_argument("--exec", dest="executable", type=Path, default=DEFAULT_SERVICE_EXECUTABLE)
service_check.add_argument("--config", dest="service_config", type=Path, default=DEFAULT_SERVICE_CONFIG)
```

Add `_service_check(args)` to call `validate_service_setup()` and print a
single success line containing the validated user, group, executable, and config
paths. Include `ServiceSetupError` in the existing CLI error handling tuple.

Run:

```bash
pytest tests/unit/agent/test_service_setup.py -q
```

Expected result: all service setup tests pass.

### Task 2: Linux Service Documentation And Template Notes

**Files:**
- Modify: `agent/README.md`
- Modify: `docs/managed-agents.md`
- Modify: `agent/install/systemd/borg-ui-agent.service`

- [ ] **Step 1: Document the required Linux service account**

Document this account setup before copying/enabling the unit:

```bash
sudo useradd --system --user-group --home-dir /var/lib/borg-ui-agent \
  --create-home --shell /usr/sbin/nologin borg-ui-agent
sudo install -d -o borg-ui-agent -g borg-ui-agent -m 0750 /etc/borg-ui-agent
```

- [ ] **Step 2: Document the pre-enable validation command**

Document this command immediately before `systemctl daemon-reload`:

```bash
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check \
  --user borg-ui-agent \
  --group borg-ui-agent \
  --exec /opt/borg-ui-agent/.venv/bin/borg-ui-agent \
  --config /etc/borg-ui-agent/config.toml
```

Expected invalid-user output includes:

```text
borg-ui-agent: Service user 'borg-ui-agent' does not exist.
```

- [ ] **Step 3: Add troubleshooting guidance**

Add a short troubleshooting section that maps systemd `status=217/USER` and
`Failed at step USER` to a missing or invalid `User=`/`Group=` value and tells
operators to run:

```bash
getent passwd borg-ui-agent
getent group borg-ui-agent
sudo /opt/borg-ui-agent/.venv/bin/borg-ui-agent service-check
```

- [ ] **Step 4: Annotate the service template**

Add comments above `User=` and `Group=` in
`agent/install/systemd/borg-ui-agent.service` saying the account must exist and
should be validated with `borg-ui-agent service-check` before enabling the unit.

### Task 3: Validation And Handoff

**Files:**
- Validate: `agent/borg_ui_agent/service_setup.py`
- Validate: `agent/borg_ui_agent/cli.py`
- Validate: `tests/unit/agent/test_service_setup.py`
- Validate: `agent/README.md`
- Validate: `docs/managed-agents.md`
- Validate: `agent/install/systemd/borg-ui-agent.service`

- [ ] Run targeted tests:

```bash
pytest tests/unit/agent/test_service_setup.py -q
```

- [ ] Run the broader agent regression test:

```bash
pytest tests/unit/test_agent_runtime.py tests/unit/agent/test_service_setup.py -q
```

- [ ] Run backend policy checks:

```bash
ruff check app tests
ruff format --check app tests
```

- [ ] Run local service-check proof with temporary files:

```bash
tmpdir="$(mktemp -d)"
install -m 0755 "$(command -v true)" "$tmpdir/borg-ui-agent"
install -m 0600 /dev/null "$tmpdir/config.toml"
python3 -m agent.borg_ui_agent.cli service-check \
  --user "$(id -un)" \
  --group "$(id -gn)" \
  --exec "$tmpdir/borg-ui-agent" \
  --config "$tmpdir/config.toml"
rm -rf "$tmpdir"
```

Expected result: command exits 0 and prints `borg-ui-agent service setup OK`.
