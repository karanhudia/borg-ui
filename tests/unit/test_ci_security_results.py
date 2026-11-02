"""Consolidating security scans must not allow failed or omitted gates to pass."""

import importlib.util
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
GATES = [
    "path-checker-self-test",
    "personal-paths",
    "npm-audit",
    "pip-audit",
    "trivy-fs",
]


def module():
    spec = importlib.util.spec_from_file_location(
        "check_security_results", ROOT / "scripts/ci/check_security_results.py"
    )
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def test_all_security_gates_must_succeed():
    assert module().failures({name: {"outcome": "success"} for name in GATES}) == []


@pytest.mark.parametrize("name", GATES)
@pytest.mark.parametrize("outcome", ["failure", "cancelled", "skipped", "missing"])
def test_any_failed_cancelled_skipped_or_missing_scan_fails_summary(name, outcome):
    results = {key: {"outcome": "success"} for key in GATES}
    if outcome == "missing":
        del results[name]
    else:
        results[name]["outcome"] = outcome
    assert module().failures(results)


def test_all_required_scan_steps_run_after_an_earlier_failure():
    jobs = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())["jobs"]
    assert set(jobs) == {"security-summary", "trivy-docker"}
    steps = {s.get("id"): s for s in jobs["security-summary"]["steps"] if s.get("id")}
    assert all(steps[name].get("if") == "${{ !cancelled() }}" for name in GATES)
    assert all(not steps[name].get("continue-on-error", False) for name in GATES)
    final = jobs["security-summary"]["steps"][-1]
    assert final["if"] == "always()"
    assert "check_security_results.py" in final["run"]


@pytest.mark.parametrize("install_kind", ["project", "global"])
def test_audit_installs_cannot_modify_later_security_scan_inputs(
    tmp_path, install_kind
):
    """Run workflow install flags against real offline package lifecycle hooks."""
    import io
    import json
    import os
    import shlex
    import shutil
    import subprocess
    import tarfile

    npm = shutil.which("npm")
    assert npm, "npm is required to verify security install isolation"
    frontend = tmp_path / "frontend"
    frontend.mkdir()
    targets = [
        tmp_path / "requirements.txt",
        tmp_path / "security" / "pip-audit-known-vulns.json",
        tmp_path / "scripts" / "ci" / "check_security_results.py",
    ]
    for target in targets:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("original scanner input\n")
    mutation = (
        "const fs = require('node:fs');\n"
        "for (const path of JSON.parse(process.env.AUDIT_TEST_INPUTS)) "
        "fs.writeFileSync(path, 'modified by lifecycle script');\n"
    )
    package = {
        "name": "audit-lifecycle-fixture",
        "version": "1.0.0",
        "scripts": {"postinstall": "node mutate.cjs"},
        "bin": {"audit-fixture": "cli.cjs"},
    }
    tarball = tmp_path / "audit-lifecycle-fixture.tgz"
    with tarfile.open(tarball, "w:gz") as archive:
        for name, content in {
            "package.json": json.dumps(package),
            "mutate.cjs": mutation,
            "cli.cjs": '#!/usr/bin/env node\nconsole.log("fixture-cli-ready");\n',
        }.items():
            payload = content.encode()
            info = tarfile.TarInfo(f"package/{name}")
            info.size = len(payload)
            info.mode = 0o755 if name == "cli.cjs" else 0o644
            archive.addfile(info, io.BytesIO(payload))
    (frontend / "package.json").write_text(
        json.dumps(
            {
                "name": "audit-root-fixture",
                "version": "1.0.0",
                "scripts": {"prepare": "node mutate-root.cjs"},
                "dependencies": {"audit-lifecycle-fixture": f"file:{tarball}"},
            }
        )
    )
    (frontend / "mutate-root.cjs").write_text(mutation)
    prefix = tmp_path / "global-prefix"
    env = {
        **os.environ,
        "AUDIT_TEST_INPUTS": json.dumps([str(path) for path in targets]),
        "npm_config_cache": str(tmp_path / "npm-cache"),
        "npm_config_offline": "true",
        "npm_config_prefix": str(prefix),
        "npm_config_update_notifier": "false",
    }
    # Build a real local lockfile without fetching or executing fixture scripts.
    locked = subprocess.run(
        [npm, "install", "--package-lock-only", "--ignore-scripts", "--no-audit"],
        cwd=frontend,
        env=env,
        capture_output=True,
        text=True,
    )
    assert locked.returncode == 0, locked.stdout + locked.stderr
    original_lock = (frontend / "package-lock.json").read_bytes()
    steps = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())[
        "jobs"
    ]["security-summary"]["steps"]
    step_name = (
        "Install dependencies"
        if install_kind == "project"
        else "Update npm for the bulk advisory endpoint"
    )
    command = shlex.split(
        next(
            step["run"] for step in steps if step.get("name") == step_name
        ).splitlines()[0]
    )
    if install_kind == "global":
        # Substitute only the registry package operand; exercise the workflow's
        # real flags offline and retain its global executable-link behavior.
        package_index = next(
            index
            for index, argument in enumerate(command)
            if argument.startswith("npm@")
        )
        command[package_index] = str(tarball)
    command[0] = npm
    result = subprocess.run(
        command, cwd=frontend, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stdout + result.stderr
    installed = (
        frontend / "node_modules" / "audit-lifecycle-fixture"
        if install_kind == "project"
        else prefix / "lib" / "node_modules" / "audit-lifecycle-fixture"
    )
    assert (installed / "package.json").is_file()
    assert (frontend / "package-lock.json").read_bytes() == original_lock
    executable = (
        frontend / "node_modules" / ".bin" / "audit-fixture"
        if install_kind == "project"
        else prefix / "bin" / "audit-fixture"
    )
    cli = subprocess.run([str(executable)], env=env, capture_output=True, text=True)
    assert cli.returncode == 0, cli.stderr
    assert cli.stdout.strip() == "fixture-cli-ready"
    assert [target.read_text() for target in targets] == [
        "original scanner input\n"
    ] * 3
