"""CI routing must never turn incomplete evidence into permission to skip."""

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]


def render_concurrency_group(template, github):
    """Resolve context references and || fallbacks in the workflow group."""

    def expression(match):
        for reference in match.group(1).split(" || "):
            value = {"github": github}
            for key in reference.strip().split("."):
                value = value.get(key, "") if isinstance(value, dict) else ""
            if value:
                return str(value)
        return ""

    return re.sub(r"\$\{\{\s*(.*?)\s*\}\}", expression, template)


@pytest.mark.parametrize("event", ["push", "schedule", "workflow_dispatch"])
def test_security_non_pr_runs_never_share_a_pending_slot(event):
    config = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    context = {
        "workflow": "Security Scan",
        "event_name": event,
        "ref": "refs/heads/main",
        "event": {},
    }
    groups = [
        render_concurrency_group(
            config["concurrency"]["group"], {**context, "run_id": run_id}
        )
        for run_id in (100, 101, 102)
    ]
    assert len(set(groups)) == 3


def test_security_repeated_pr_runs_share_the_same_group():
    config = yaml.safe_load((ROOT / ".github/workflows/security.yml").read_text())
    context = {
        "workflow": "Security Scan",
        "event_name": "pull_request",
        "ref": "refs/pull/42/merge",
        "event": {"pull_request": {"number": 42}},
    }
    first = render_concurrency_group(
        config["concurrency"]["group"], {**context, "run_id": 100}
    )
    second = render_concurrency_group(
        config["concurrency"]["group"], {**context, "run_id": 101}
    )
    other = render_concurrency_group(
        config["concurrency"]["group"],
        {
            **context,
            "ref": "refs/pull/43/merge",
            "event": {"pull_request": {"number": 43}},
            "run_id": 102,
        },
    )
    assert first == second
    assert first != other


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f"scripts/ci/{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    "diff",
    [
        b"M\0frontend/src/App.tsx\0",
        b"A\0frontend/.storybook/preview.tsx\0D\0frontend/src/old.ts\0",
        b"M\0frontend/scripts/capture.mjs\0M\0frontend/public/logo.svg\0",
    ],
)
def test_only_allowlisted_frontend_changes_can_omit_backend(diff):
    assert load("pr_scope").backend_required(diff) is False


@pytest.mark.parametrize(
    "diff",
    [
        b"",
        b"M\0frontend/src/App.tsx",
        b"unexpected",
        b"M\0frontend/src/App.tsx\0M\0app/main.py\0",
        b"D\0tests/unit/test_api.py\0",
        b"M\0frontend/package.json\0",
        b"M\0frontend/package-lock.json\0",
        b"M\0frontend/vitest.config.ts\0",
        b"M\0requirements.txt\0",
        b"M\0.github/workflows/tests.yml\0",
        b"M\0scripts/ci/pr_scope.py\0",
        b"M\0docs/README.md\0",
        b"M\0new-top-level-config\0",
        b"R100\0app/example.py\0frontend/src/example.py\0",
        b"R100\0frontend/src/old.ts\0frontend/src/new.ts\0",
        b"T\0frontend/src/App.tsx\0",
        b"X\0frontend/src/App.tsx\0",
        b"M\0frontend/src/../package.json\0",
    ],
)
def test_ambiguous_shared_or_unknown_changes_require_all_backend_checks(diff):
    assert load("pr_scope").backend_required(diff) is True


def test_scope_cli_handles_missing_git_metadata_by_running_everything(tmp_path):
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/ci/pr_scope.py"),
            "--event",
            "pull_request",
            "--base",
            "missing",
            "--head",
            "missing",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert "backend=true" in result.stdout


BACKEND = [
    "backend-unit-coverage",
    "backend-unit-coverage-combine",
    "backend-migration-paths",
    "backend-api-integration",
]
OTHER = [
    "typecheck-lint-format",
    "frontend-vitest",
    "frontend-build",
    "smoke-borg-core",
    "smoke-borg-extended",
    "smoke-borg-ssh-localhost",
]


def job_results(backend="true", event="pull_request"):
    jobs = {name: {"result": "success"} for name in BACKEND + OTHER}
    jobs["prepare"] = {"result": "success", "outputs": {"backend": backend}}
    if backend == "false":
        for name in BACKEND:
            jobs[name]["result"] = "skipped"
    if event == "schedule":
        jobs["smoke-borg-core"]["result"] = "skipped"
    return jobs


@pytest.mark.parametrize(
    "backend,event",
    [
        ("true", "pull_request"),
        ("false", "pull_request"),
        ("true", "schedule"),
        ("true", "push"),
    ],
)
def test_summary_accepts_only_intentionally_skipped_lanes(backend, event):
    assert load("check_results").failures(job_results(backend, event), event) == []


@pytest.mark.parametrize("name", BACKEND + OTHER + ["prepare"])
@pytest.mark.parametrize("result", ["failure", "cancelled", "skipped"])
def test_full_run_cannot_pass_with_any_failed_cancelled_or_skipped_job(name, result):
    jobs = job_results()
    jobs[name]["result"] = result
    assert load("check_results").failures(jobs, "pull_request")


@pytest.mark.parametrize("name", OTHER)
def test_frontend_only_run_still_requires_all_smoke_and_frontend_checks(name):
    jobs = job_results("false")
    jobs[name]["result"] = "skipped"
    assert load("check_results").failures(jobs, "pull_request")


def test_summary_rejects_missing_results_invalid_scope_and_non_pr_skips():
    module = load("check_results")
    assert module.failures({}, "pull_request")
    jobs = job_results()
    jobs["prepare"]["outputs"] = {}
    assert module.failures(jobs, "pull_request")
    assert module.failures(job_results("false"), "push")
    jobs = job_results("false")
    jobs["backend-unit-coverage"]["result"] = "failure"
    assert module.failures(jobs, "pull_request")


def test_git_diff_cli_covers_entire_pr_and_both_sides_of_renames(tmp_path):
    def git(*args):
        return subprocess.run(
            ["git", *args], cwd=tmp_path, check=True, capture_output=True, text=True
        ).stdout.strip()

    def scope(base, event="pull_request"):
        return subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/ci/pr_scope.py"),
                "--event",
                event,
                "--base",
                base,
                "--head",
                "HEAD",
            ],
            cwd=tmp_path,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()

    git("init")
    git("config", "user.name", "CI test")
    git("config", "user.email", "ci@example.invalid")
    (tmp_path / "app").mkdir()
    (tmp_path / "app/old.py").write_text("print('backend')\n")
    git("add", ".")
    git("commit", "-m", "base")
    base = git("rev-parse", "HEAD")
    (tmp_path / "frontend/src").mkdir(parents=True)
    # More than one API page of files; the classifier uses the git diff itself.
    for index in range(350):
        (tmp_path / f"frontend/src/file-{index}.ts").write_text("export {}\n")
    git("add", ".")
    git("commit", "-m", "frontend")
    assert scope(base) == "backend=false"
    assert scope(base, "push") == "backend=true"
    git("mv", "app/old.py", "frontend/src/old.py")
    git("commit", "-m", "rename backend into frontend")
    assert scope(base) == "backend=true"


def test_summary_cli_fails_when_required_work_is_accidentally_skipped():
    import os
    import json

    jobs = job_results("false")
    jobs["smoke-borg-extended"]["result"] = "skipped"
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts/ci/check_results.py")],
        env={
            **os.environ,
            "CI_JOB_RESULTS": json.dumps(jobs),
            "CI_EVENT_NAME": "pull_request",
        },
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "smoke-borg-extended: skipped" in result.stderr


def test_workflow_summary_covers_every_job_and_scope_is_backend_only():
    jobs = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())["jobs"]
    summary = jobs["test-results"]
    assert summary["if"] == "always()"
    assert set(summary["needs"]) == set(jobs) - {"test-results"}
    assert set(jobs) - {"prepare", "test-results"} == set(BACKEND + OTHER)
    for name in BACKEND:
        assert jobs[name]["if"] == "needs.prepare.outputs.backend == 'true'"
        needs = jobs[name]["needs"]
        assert "prepare" in ([needs] if isinstance(needs, str) else needs)
    for name in OTHER:
        if name != "smoke-borg-core":
            assert "if" not in jobs[name]
    assert jobs["smoke-borg-core"]["if"] == "github.event_name != 'schedule'"
    assert jobs["backend-unit-coverage"]["strategy"]["matrix"]["shard"] == [
        1,
        2,
        3,
        4,
        5,
        6,
    ]
    assert jobs["backend-unit-coverage"]["strategy"]["matrix"]["total_shards"] == [6]
    for name in ("smoke-borg-core", "smoke-borg-extended", "smoke-borg-ssh-localhost"):
        assert jobs[name]["strategy"]["matrix"]["borg"] == ["image", "apt"]


def test_preparation_performs_every_unconditional_contract_guard():
    jobs = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())["jobs"]
    steps = jobs["prepare"]["steps"]
    contract = next(s for s in steps if s.get("id") == "frontend-contracts")
    # Lint failures must not suppress the previously independent guards.
    assert contract["if"] == "${{ !cancelled() }}"
    for test_file in (
        "test_borg2_only_url_prefixes_parity.py",
        "test_borg_version_boundaries.py",
        "test_borg_dispatch_guardrails.py",
        "test_npm_audit_known_vulns.py",
    ):
        assert test_file in contract["run"]
    assert "image" in jobs["prepare"]["outputs"]
    lint = next(s for s in steps if s.get("id") == "backend-lint")
    assert lint["if"] == "steps.scope.outputs.backend == 'true'"
    assert "ruff check app tests" in lint["run"]
    assert "ruff format --check app tests" in lint["run"]


def test_coverage_uploads_stay_on_producing_runners_and_migrations_are_isolated():
    jobs = yaml.safe_load((ROOT / ".github/workflows/tests.yml").read_text())["jobs"]
    for job_id in ("frontend-vitest", "backend-unit-coverage-combine"):
        assert any(
            s.get("uses", "").startswith("codecov/codecov-action@")
            for s in jobs[job_id]["steps"]
        )
    migrations = jobs["backend-migration-paths"]
    assert migrations["strategy"]["matrix"]["shard"] == [1, 2]
    assert migrations["services"]["postgres"]["env"]["POSTGRES_DB"] == "borg_test"
    assert migrations["strategy"]["fail-fast"] is False
    selection = next(
        s
        for s in migrations["steps"]
        if s.get("name") == "Select complete migration file shard"
    )
    assert "--balance-by files" in selection["run"]
    assert "pytest tests/migrations --collect-only" in selection["run"]
