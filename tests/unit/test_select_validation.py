import importlib.util
from types import SimpleNamespace
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SELECTOR_PATH = ROOT / "scripts" / "select_validation.py"


def load_selector():
    assert SELECTOR_PATH.exists(), "scripts/select_validation.py is missing"
    spec = importlib.util.spec_from_file_location("select_validation", SELECTOR_PATH)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def select_validation(changed_files):
    return load_selector().select_validation(changed_files)


def command_ids(manifest):
    return [command["id"] for command in manifest["local_commands"]]


def reason_ids(manifest):
    return [reason["id"] for reason in manifest["broadening_reasons"]]


def test_docs_only_selects_diff_check_and_docs_build_for_docs_site():
    manifest = select_validation(["docs/testing.md"])

    assert manifest["manifest_version"] == 1
    assert manifest["changed_files"] == ["docs/testing.md"]
    assert manifest["domains"] == ["docs"]
    assert command_ids(manifest) == ["diff-check", "docs-build"]
    assert manifest["ci_lanes"]["backend_unit"] is False
    assert manifest["ci_lanes"]["frontend_build"] is False
    assert reason_ids(manifest) == []


def test_tests_readme_is_documentation_not_unmapped():
    manifest = select_validation(["tests/README.md"])

    assert manifest["domains"] == ["docs"]
    assert "unmapped-change" not in reason_ids(manifest)


def test_backend_leaf_selects_lint_format_and_relevant_pytest():
    manifest = select_validation(["app/api/repositories.py"])

    assert "backend" in manifest["domains"]
    assert command_ids(manifest) == [
        "diff-check",
        "backend-ruff-check",
        "backend-ruff-format",
        "backend-api-tests",
    ]
    assert manifest["ci_lanes"]["backend_lint"] is True
    assert manifest["ci_lanes"]["backend_unit"] is True
    assert manifest["ci_lanes"]["backend_integration"] is True
    assert manifest["ci_lanes"]["frontend_build"] is False
    assert "backend-api-surface" in reason_ids(manifest)


def test_backend_unit_test_change_selects_that_file():
    manifest = select_validation(["tests/unit/test_api_repositories.py"])

    assert "backend" in manifest["domains"]
    assert command_ids(manifest) == [
        "diff-check",
        "backend-ruff-check",
        "backend-ruff-format",
        "backend-targeted-pytest",
    ]
    targeted = next(
        command
        for command in manifest["local_commands"]
        if command["id"] == "backend-targeted-pytest"
    )
    assert targeted["command"] == "pytest tests/unit/test_api_repositories.py -v"


def test_frontend_component_selects_quality_and_vitest_changed():
    manifest = select_validation(["frontend/src/components/RepositoryCard.tsx"])

    assert "frontend" in manifest["domains"]
    assert command_ids(manifest) == [
        "diff-check",
        "frontend-vitest-changed",
        "frontend-typecheck",
        "frontend-lint",
    ]
    assert manifest["ci_lanes"]["frontend_quality"] is True
    assert manifest["ci_lanes"]["frontend_unit"] is True
    assert manifest["ci_lanes"]["frontend_build"] is False
    assert reason_ids(manifest) == []


def test_frontend_config_broadens_to_full_frontend():
    manifest = select_validation(["frontend/package.json"])

    assert "frontend" in manifest["domains"]
    assert "dependencies" in manifest["domains"]
    assert command_ids(manifest) == [
        "diff-check",
        "frontend-check-locales",
        "frontend-typecheck",
        "frontend-lint",
        "frontend-build",
    ]
    assert "frontend-dependency-change" in reason_ids(manifest)
    assert manifest["ci_lanes"]["frontend_quality"] is True
    assert manifest["ci_lanes"]["frontend_unit"] is True
    assert manifest["ci_lanes"]["frontend_build"] is True


def test_workflow_change_broadens_backend_and_frontend_local_gates():
    manifest = select_validation(["WORKFLOW.md", ".codex/skills/push/SKILL.md"])

    assert "workflow" in manifest["domains"]
    assert "workflow-contract-change" in reason_ids(manifest)
    assert "backend-ruff-check" in command_ids(manifest)
    assert "frontend-build" in command_ids(manifest)
    assert manifest["ci_lanes"]["backend_unit"] is True
    assert manifest["ci_lanes"]["frontend_build"] is True


def test_smoke_change_selects_smoke_lane_without_frontend_quality():
    manifest = select_validation(["tests/smoke/run_core_smoke.py"])

    assert "smoke" in manifest["domains"]
    assert "runtime" in manifest["domains"]
    assert "smoke-or-runtime-change" in reason_ids(manifest)
    assert manifest["ci_lanes"]["smoke_core"] is True
    assert manifest["ci_lanes"]["smoke_extended"] is True
    assert manifest["ci_lanes"]["smoke_ssh"] is True
    assert manifest["ci_lanes"]["frontend_quality"] is False
    assert manifest["ci_lanes"]["frontend_build"] is True


def test_unknown_file_requires_full_backend_and_frontend_fallback():
    manifest = select_validation(["unexpected.bin"])

    assert "unknown" in manifest["domains"]
    assert "unmapped-change" in reason_ids(manifest)
    assert "backend-unit-tests" in command_ids(manifest)
    assert "frontend-build" in command_ids(manifest)
    assert manifest["ci_lanes"]["backend_lint"] is True
    assert manifest["ci_lanes"]["backend_unit"] is True
    assert manifest["ci_lanes"]["backend_integration"] is True
    assert manifest["ci_lanes"]["frontend_quality"] is True
    assert manifest["ci_lanes"]["frontend_unit"] is True
    assert manifest["ci_lanes"]["frontend_build"] is True


def test_all_changes_selects_every_required_ci_lane():
    manifest = load_selector().select_validation([], all_changes=True)

    assert "all" in manifest["domains"]
    assert "all-changes-requested" in reason_ids(manifest)
    assert all(manifest["ci_lanes"].values())


def test_github_output_contains_boolean_lane_keys():
    selector = load_selector()
    manifest = selector.select_validation(["docs/testing.md"])

    output = selector.format_github_output(manifest)

    assert "run_backend_unit=false" in output
    assert "run_docs=true" in output
    assert "manifest_json=" in output


def test_merge_changed_file_sources_dedupes_in_order():
    selector = load_selector()

    merged = selector.merge_changed_file_sources(
        ["WORKFLOW.md", "scripts/select_validation.py"],
        ["tests/unit/test_select_validation.py"],
        ["WORKFLOW.md", "frontend/package.json"],
    )

    assert merged == [
        "WORKFLOW.md",
        "scripts/select_validation.py",
        "tests/unit/test_select_validation.py",
        "frontend/package.json",
    ]


def test_changed_files_from_git_includes_staged_unstaged_and_untracked(monkeypatch):
    selector = load_selector()
    calls = []

    def fake_run(command, check, text, capture_output):
        calls.append(command)
        if command == ["git", "diff", "--name-only", "origin/main...HEAD"]:
            return SimpleNamespace(stdout="WORKFLOW.md\n")
        if command == ["git", "diff", "--name-only", "--cached"]:
            return SimpleNamespace(stdout="scripts/select_validation.py\n")
        if command == ["git", "diff", "--name-only"]:
            return SimpleNamespace(stdout="tests/README.md\n")
        if command == ["git", "ls-files", "--others", "--exclude-standard"]:
            return SimpleNamespace(stdout="tests/unit/test_select_validation.py\n")
        raise AssertionError(f"unexpected command: {command}")

    monkeypatch.setattr(selector.subprocess, "run", fake_run)

    files = selector.changed_files_from_git("origin/main", "HEAD")

    assert files == [
        "WORKFLOW.md",
        "scripts/select_validation.py",
        "tests/README.md",
        "tests/unit/test_select_validation.py",
    ]
    assert calls[-1] == ["git", "ls-files", "--others", "--exclude-standard"]
