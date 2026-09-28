# macOS Agent Platform Implementation Plan

Spec: `../specs/2026-09-28-macos-agent-platform.md`. Issue: #1151. One PR,
agent version 0.1.14.

## Task 1: Agent platform defaults

- Add `agent/borg_ui_agent/paths.py` with `default_agent_root()` and
  `default_config_dir()`; `config.default_config_path()` reads from it.
- `scripts.py`: `default_scripts_dir()` from the config dir on Darwin,
  `/etc/borg-ui-agent/scripts.d` elsewhere; the env override stays.
- `borg.py`: `_classify_install_source` with the per-user root, `homebrew` and
  `macports`.
- Tests fake `platform.system()` and assert each default.

## Task 2: Portable du

- The session's CA bundle needs no change: `truststore`, injected at the CLI
  entry since 0.1.13 (#1278), verifies `wss://` through the macOS keychain.
- `storage_usage.du_storage_used`: `du -A -sk` × 1024 on Darwin.
- Tests: `du` command and scaling on Darwin, `-sb` unchanged elsewhere.

## Task 3: Remote upgrade readiness on Darwin

- `self_upgrade.py`: platform defaults for conf, trigger, job definition and
  watcher; read the helper from a plist's `ProgramArguments` on Darwin.
- Tests: a complete per-user install is ready; each missing piece is reported
  by the same reasons as on Linux.

## Task 4: Manifests

- `app/api/borg_binaries.json`: `platform` on every entry, Darwin entries with
  `min_macos`; `borg_binaries.py` renders the platform and floor columns.
- `scripts/refresh_borg_binary_manifest.py`: the macOS asset pattern; a
  release stays adoptable on its Linux pair, a lost macOS pair is reported as
  a coverage regression.
- `app/api/python_runtimes.json`, `app/api/python_runtimes.py`,
  `scripts/refresh_python_runtime_manifest.py`; rendered as
  `PINNED_PYTHON_VERSION` / `PINNED_PYTHON_RUNTIMES`.
- Tests in `test_borg_binaries.py` and a new `test_python_runtimes.py`.

## Task 5: Installer and uninstaller

- Platform detection after argument parsing; per-platform path variables;
  the shared functions (checksum, binary selection and download, forwarders,
  package source, upgrade conf and helper) take their paths from variables.
- Darwin flow: refusals, Python runtime, Borg with the macOS floor, venv and
  package, registration, plist rendering, upgrade job, bootstrap or kickstart.
- Helper: exit without a trigger; checksum through `shasum` where `sha256sum`
  is absent.
- Uninstaller: Darwin branch.
- `agent/install/launchd/com.borg-ui.agent.plist` replaced by the per-user
  template the installer renders.
- Tests: existing installer tests keep passing (literals that moved into
  variables are asserted through their Linux values); Darwin assertions and
  the stubbed dry run.

## Task 6: Server mount gate

- `app/api/mounts.py`: 400 for `executor_type == "agent"` before the service is
  called; locale key in the four backend error dictionaries.
- Test in the mounts route tests.

## Task 7: UI

- `agentInstallCommandText.ts`: a platform parameter for install, reinstall
  and uninstall commands.
- Add Agent dialog: platform choice; the service-user group hidden for macOS.
  Reinstall and uninstall dialogs take the platform from `agent.os`.
- Archives and archive detail: mount action hidden for agent repositories.
- Locale keys in `en`, `de`, `es`, `it`; stories for the macOS command and the
  hidden mount action; frontend gates (prettier, typecheck, eslint, locales).

## Task 8: Documentation and version

- `agent/README.md` macOS section, `docs/managed-agents.md` upgrade table.
- `__init__.py` and `pyproject.toml` to 0.1.14; README "from 0.1.14" line.

## Task 9: Verification

- `pytest tests/unit` in an untouched clone; `ruff check` and `ruff format
  --check`; frontend gates and vitest under Node 22; `bash -n` of the served
  script under macOS `/bin/bash` 3.2 as well as Linux bash.
