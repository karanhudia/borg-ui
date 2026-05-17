#!/usr/bin/env python3
"""Select local validation and CI lanes from changed Borg UI files."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable


DOMAIN_ORDER = [
    "all",
    "backend",
    "frontend",
    "docs",
    "workflow",
    "ci",
    "smoke",
    "runtime",
    "storybook",
    "dependencies",
    "security",
    "unknown",
    "none",
]

CI_LANE_ORDER = [
    "docs",
    "backend_lint",
    "backend_unit",
    "backend_integration",
    "frontend_quality",
    "frontend_unit",
    "frontend_build",
    "smoke_core",
    "smoke_extended",
    "smoke_ssh",
]


def select_validation(
    changed_files: Iterable[str], *, all_changes: bool = False
) -> dict:
    files = normalize_files(changed_files)
    domains: set[str] = set()
    commands: list[dict[str, str]] = []
    reasons: list[dict[str, object]] = []
    ci_lanes = {lane: False for lane in CI_LANE_ORDER}
    notes: list[str] = []

    add_command(
        commands,
        "diff-check",
        "git diff --check",
        "Always check whitespace and conflict-marker hygiene.",
    )

    if all_changes:
        domains.add("all")
        add_reason(
            reasons,
            "all-changes-requested",
            "All validation lanes requested by schedule, workflow_dispatch, or explicit selector input.",
            [],
        )
        add_full_backend(commands, ci_lanes)
        add_full_frontend(commands, ci_lanes)
        enable_smoke(ci_lanes)
        ci_lanes["docs"] = True
        notes.append("All CI lanes selected.")
        return finalize_manifest([], domains, commands, reasons, ci_lanes, notes)

    if not files:
        domains.add("none")
        notes.append(
            "No changed files were provided; only repository hygiene is selected."
        )
        return finalize_manifest(files, domains, commands, reasons, ci_lanes, notes)

    for file_name in files:
        classify_file(file_name, domains, commands, reasons, ci_lanes, notes)

    if "smoke" in domains or "runtime" in domains:
        ci_lanes["frontend_build"] = True

    return finalize_manifest(files, domains, commands, reasons, ci_lanes, notes)


def classify_file(
    file_name: str,
    domains: set[str],
    commands: list[dict[str, str]],
    reasons: list[dict[str, object]],
    ci_lanes: dict[str, bool],
    notes: list[str],
) -> None:
    path = Path(file_name)
    path_text = path.as_posix()

    if path_text.startswith("docs/"):
        domains.add("docs")
        ci_lanes["docs"] = True
        if path.suffix in {".md", ".mdx"} or path.name in {
            "package.json",
            "package-lock.json",
        }:
            add_command(
                commands,
                "docs-build",
                "cd docs && npm run build",
                "Docs site content or configuration changed.",
            )
        return

    if path.name.upper() == "README.MD":
        domains.add("docs")
        ci_lanes["docs"] = True
        return

    if path_text == "WORKFLOW.md" or path_text.startswith(".codex/skills/"):
        domains.add("workflow")
        add_reason(
            reasons,
            "workflow-contract-change",
            "Symphony workflow or Codex skill contract changed; preserve broad backend/frontend fallback.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        add_full_frontend(commands, ci_lanes)
        return

    if path_text.startswith(".github/workflows/"):
        domains.update({"ci", "workflow"})
        add_reason(
            reasons,
            "ci-workflow-change",
            "GitHub Actions workflow changed; select every affected lane and let CI prove the workflow.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        add_full_frontend(commands, ci_lanes)
        enable_smoke(ci_lanes)
        return

    if path_text in {"requirements.txt", "pytest.ini", "ruff.toml", ".coveragerc"}:
        domains.update({"backend", "dependencies"})
        add_reason(
            reasons,
            "backend-dependency-or-tooling-change",
            "Backend dependency or test/lint configuration changed.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        return

    if path_text.startswith("app/"):
        domains.add("backend")
        add_backend_quality(commands, ci_lanes)
        classify_backend_app_file(path_text, commands, reasons, ci_lanes)
        if path_text == "app/main.py":
            domains.add("runtime")
        return

    if path_text.startswith("tests/smoke/"):
        domains.update({"smoke", "runtime"})
        add_reason(
            reasons,
            "smoke-or-runtime-change",
            "Smoke/runtime coverage changed; select smoke lanes and require a frontend build artifact.",
            [path_text],
        )
        add_backend_quality(commands, ci_lanes)
        enable_smoke(ci_lanes)
        return

    if path_text.startswith("tests/integration/"):
        domains.add("backend")
        add_backend_quality(commands, ci_lanes)
        ci_lanes["backend_integration"] = True
        add_command(
            commands,
            "backend-targeted-pytest",
            f"pytest {path_text} -v",
            "Changed integration test should run directly.",
        )
        return

    if path_text.startswith("tests/unit/") and path.suffix == ".py":
        domains.add("backend")
        add_backend_quality(commands, ci_lanes)
        ci_lanes["backend_unit"] = True
        add_command(
            commands,
            "backend-targeted-pytest",
            f"pytest {path_text} -v",
            "Changed unit test should run directly.",
        )
        return

    if path_text.startswith("tests/") and path.suffix == ".py":
        domains.add("backend")
        add_reason(
            reasons,
            "backend-test-contract-change",
            "Shared or uncategorized Python test changed; broaden to backend unit validation.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        return

    if path_text in {
        "Dockerfile",
        "Dockerfile.runtime-base",
        "docker-compose.yml",
        "docker-compose.dev.yml",
    }:
        domains.update({"runtime", "smoke"})
        add_reason(
            reasons,
            "runtime-container-change",
            "Runtime container or compose configuration changed; select smoke coverage.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        add_full_frontend(commands, ci_lanes)
        enable_smoke(ci_lanes)
        return

    if path_text.startswith("frontend/"):
        domains.add("frontend")
        classify_frontend_file(path_text, domains, commands, reasons, ci_lanes)
        return

    if path_text.startswith("scripts/") and path.suffix in {
        ".py",
        ".sh",
        ".js",
        ".mjs",
    }:
        domains.add("workflow")
        add_reason(
            reasons,
            "workflow-script-change",
            "Repository script changed; run repository hygiene and targeted script tests when present.",
            [path_text],
        )
        if path_text.endswith(".py"):
            add_backend_quality(commands, ci_lanes)
        return

    if path_text.startswith("app/core/security") or "security" in path_text.lower():
        domains.add("security")
        add_reason(
            reasons,
            "security-sensitive-change",
            "Security-sensitive path changed; broaden validation.",
            [path_text],
        )
        add_full_backend(commands, ci_lanes)
        add_full_frontend(commands, ci_lanes)
        return

    domains.add("unknown")
    add_reason(
        reasons,
        "unmapped-change",
        "Changed file is not mapped by the selector; use full backend and frontend fallback.",
        [path_text],
    )
    add_full_backend(commands, ci_lanes)
    add_full_frontend(commands, ci_lanes)


def classify_backend_app_file(
    path_text: str,
    commands: list[dict[str, str]],
    reasons: list[dict[str, object]],
    ci_lanes: dict[str, bool],
) -> None:
    ci_lanes["backend_unit"] = True

    if path_text.startswith("app/api/"):
        ci_lanes["backend_integration"] = True
        add_reason(
            reasons,
            "backend-api-surface",
            "Backend API surface changed; include focused API tests and integration lane.",
            [path_text],
        )
        api_name = Path(path_text).stem
        unit_test = f"tests/unit/test_api_{api_name}.py"
        integration_test = f"tests/integration/test_api_{api_name}_integration.py"
        add_command(
            commands,
            "backend-api-tests",
            f"pytest {unit_test} {integration_test} -v",
            "Focused API unit and integration tests for the changed endpoint module.",
        )
        return

    if path_text.startswith("app/database/") or path_text.startswith("app/models/"):
        ci_lanes["backend_integration"] = True
        add_reason(
            reasons,
            "backend-data-contract-change",
            "Database/model code changed; include backend unit and integration lanes.",
            [path_text],
        )
        add_command(
            commands,
            "backend-unit-tests",
            "pytest tests/unit -v",
            "Database/model changes can affect broad unit contracts.",
        )
        return

    add_command(
        commands,
        "backend-unit-tests",
        "pytest tests/unit -v",
        "Backend module changed; unit suite is the conservative local proof.",
    )


def classify_frontend_file(
    path_text: str,
    domains: set[str],
    commands: list[dict[str, str]],
    reasons: list[dict[str, object]],
    ci_lanes: dict[str, bool],
) -> None:
    if path_text in {
        "frontend/package.json",
        "frontend/package-lock.json",
        "frontend/vite.config.ts",
        "frontend/tsconfig.json",
        "frontend/tsconfig.app.json",
        "frontend/tsconfig.node.json",
    }:
        domains.add("dependencies")
        add_reason(
            reasons,
            "frontend-dependency-change",
            "Frontend dependency or build configuration changed; run full frontend validation.",
            [path_text],
        )
        add_full_frontend(commands, ci_lanes)
        return

    if (
        "/.storybook/" in path_text
        or path_text.endswith(".stories.tsx")
        or "storybook-snapshots/" in path_text
    ):
        domains.add("storybook")
        add_reason(
            reasons,
            "storybook-visual-change",
            "Storybook or snapshot path changed; run snapshots in addition to frontend quality.",
            [path_text],
        )
        add_frontend_quality(commands, ci_lanes)
        add_command(
            commands,
            "frontend-snapshots",
            "cd frontend && npm run snapshots",
            "Storybook visual evidence changed.",
        )
        ci_lanes["frontend_build"] = True
        return

    if path_text.startswith("frontend/src/locales/"):
        add_command(
            commands,
            "frontend-check-locales",
            "cd frontend && npm run check:locales",
            "Locale file changed.",
        )
        add_frontend_quality(commands, ci_lanes, include_locale=False)
        return

    if path_text.startswith("frontend/src/services/") or path_text.startswith(
        "frontend/src/context/"
    ):
        add_frontend_quality(commands, ci_lanes)
        ci_lanes["frontend_build"] = True
        add_reason(
            reasons,
            "frontend-shared-contract-change",
            "Frontend shared service/context changed; include build.",
            [path_text],
        )
        add_command(
            commands,
            "frontend-build",
            "cd frontend && npm run build",
            "Shared frontend contract changed.",
        )
        return

    add_frontend_quality(commands, ci_lanes)


def add_full_backend(commands: list[dict[str, str]], ci_lanes: dict[str, bool]) -> None:
    add_backend_quality(commands, ci_lanes)
    ci_lanes["backend_unit"] = True
    ci_lanes["backend_integration"] = True
    add_command(
        commands,
        "backend-unit-tests",
        "pytest tests/unit -v",
        "Full backend unit fallback.",
    )


def add_backend_quality(
    commands: list[dict[str, str]], ci_lanes: dict[str, bool]
) -> None:
    ci_lanes["backend_lint"] = True
    add_command(
        commands, "backend-ruff-check", "ruff check app tests", "Backend lint gate."
    )
    add_command(
        commands,
        "backend-ruff-format",
        "ruff format --check app tests",
        "Backend format gate.",
    )


def add_full_frontend(
    commands: list[dict[str, str]], ci_lanes: dict[str, bool]
) -> None:
    ci_lanes["frontend_quality"] = True
    ci_lanes["frontend_unit"] = True
    add_command(
        commands,
        "frontend-check-locales",
        "cd frontend && npm run check:locales",
        "Full frontend fallback includes locale parity.",
    )
    add_command(
        commands,
        "frontend-typecheck",
        "cd frontend && npm run typecheck",
        "Frontend type gate.",
    )
    add_command(
        commands, "frontend-lint", "cd frontend && npm run lint", "Frontend lint gate."
    )
    ci_lanes["frontend_build"] = True
    add_command(
        commands,
        "frontend-build",
        "cd frontend && npm run build",
        "Full frontend build fallback.",
    )


def add_frontend_quality(
    commands: list[dict[str, str]],
    ci_lanes: dict[str, bool],
    *,
    include_locale: bool = False,
) -> None:
    ci_lanes["frontend_quality"] = True
    ci_lanes["frontend_unit"] = True
    if include_locale:
        add_command(
            commands,
            "frontend-check-locales",
            "cd frontend && npm run check:locales",
            "Locale parity check.",
        )
    add_command(
        commands,
        "frontend-vitest-changed",
        "cd frontend && npm run test:coverage -- --changed origin/main",
        "Frontend source changed; run Vitest changed-file coverage locally.",
    )
    add_command(
        commands,
        "frontend-typecheck",
        "cd frontend && npm run typecheck",
        "Frontend type gate.",
    )
    add_command(
        commands, "frontend-lint", "cd frontend && npm run lint", "Frontend lint gate."
    )


def enable_smoke(ci_lanes: dict[str, bool]) -> None:
    ci_lanes["smoke_core"] = True
    ci_lanes["smoke_extended"] = True
    ci_lanes["smoke_ssh"] = True
    ci_lanes["frontend_build"] = True


def add_command(
    commands: list[dict[str, str]], command_id: str, command: str, reason: str
) -> None:
    if any(existing["id"] == command_id for existing in commands):
        return
    commands.append({"id": command_id, "command": command, "reason": reason})


def add_reason(
    reasons: list[dict[str, object]], reason_id: str, reason: str, files: list[str]
) -> None:
    for existing in reasons:
        if existing["id"] == reason_id:
            existing_files = existing["files"]
            assert isinstance(existing_files, list)
            for file_name in files:
                if file_name not in existing_files:
                    existing_files.append(file_name)
            return
    reasons.append({"id": reason_id, "reason": reason, "files": files})


def finalize_manifest(
    changed_files: list[str],
    domains: set[str],
    commands: list[dict[str, str]],
    reasons: list[dict[str, object]],
    ci_lanes: dict[str, bool],
    notes: list[str],
) -> dict:
    manifest = {
        "manifest_version": 1,
        "changed_files": changed_files,
        "domains": sort_domains(domains),
        "local_commands": commands,
        "ci_lanes": {lane: bool(ci_lanes[lane]) for lane in CI_LANE_ORDER},
        "broadening_reasons": reasons,
        "notes": notes,
    }
    manifest["manifest_hash"] = manifest_hash(manifest)
    return manifest


def normalize_files(changed_files: Iterable[str]) -> list[str]:
    normalized = []
    seen = set()
    for file_name in changed_files:
        cleaned = file_name.strip().replace("\\", "/")
        if not cleaned or cleaned in seen:
            continue
        normalized.append(cleaned)
        seen.add(cleaned)
    return normalized


def merge_changed_file_sources(*sources: Iterable[str]) -> list[str]:
    return normalize_files(file_name for source in sources for file_name in source)


def sort_domains(domains: set[str]) -> list[str]:
    return sorted(
        domains,
        key=lambda domain: DOMAIN_ORDER.index(domain)
        if domain in DOMAIN_ORDER
        else 999,
    )


def manifest_hash(manifest: dict) -> str:
    stable_manifest = {
        key: value for key, value in manifest.items() if key != "manifest_hash"
    }
    encoded = json.dumps(
        stable_manifest, sort_keys=True, separators=(",", ":")
    ).encode()
    return hashlib.sha256(encoded).hexdigest()[:12]


def format_json(manifest: dict) -> str:
    return json.dumps(manifest, indent=2, sort_keys=True)


def format_text(manifest: dict) -> str:
    lines = [
        f"manifest_hash={manifest['manifest_hash']}",
        f"domains={','.join(manifest['domains'])}",
        "local_commands:",
    ]
    for command in manifest["local_commands"]:
        lines.append(f"- {command['id']}: {command['command']}")
    if manifest["broadening_reasons"]:
        lines.append("broadening_reasons:")
        for reason in manifest["broadening_reasons"]:
            files = ",".join(reason["files"])
            lines.append(f"- {reason['id']}: {reason['reason']} ({files})")
    else:
        lines.append("broadening_reasons: none")
    lines.append("ci_lanes:")
    for lane, enabled in manifest["ci_lanes"].items():
        lines.append(f"- {lane}: {str(enabled).lower()}")
    return "\n".join(lines)


def format_github_output(manifest: dict) -> str:
    lines = []
    for lane, enabled in manifest["ci_lanes"].items():
        lines.append(f"run_{lane}={str(enabled).lower()}")

    backend_lanes = ["backend_lint", "backend_unit", "backend_integration"]
    frontend_lanes = ["frontend_quality", "frontend_unit", "frontend_build"]
    smoke_lanes = ["smoke_core", "smoke_extended", "smoke_ssh"]
    lines.append(
        f"run_backend={str(any(manifest['ci_lanes'][lane] for lane in backend_lanes)).lower()}"
    )
    lines.append(
        f"run_frontend={str(any(manifest['ci_lanes'][lane] for lane in frontend_lanes)).lower()}"
    )
    lines.append(
        f"run_smoke={str(any(manifest['ci_lanes'][lane] for lane in smoke_lanes)).lower()}"
    )
    lines.append(f"manifest_hash={manifest['manifest_hash']}")
    lines.append(
        f"manifest_json={json.dumps(manifest, sort_keys=True, separators=(',', ':'))}"
    )
    return "\n".join(lines)


def changed_files_from_git(base: str, head: str) -> list[str]:
    command = ["git", "diff", "--name-only", f"{base}...{head}"]
    completed = subprocess.run(command, check=True, text=True, capture_output=True)
    committed_files = completed.stdout.splitlines()

    if head != "HEAD":
        return normalize_files(committed_files)

    staged = subprocess.run(
        ["git", "diff", "--name-only", "--cached"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    unstaged = subprocess.run(
        ["git", "diff", "--name-only"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    untracked = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        check=True,
        text=True,
        capture_output=True,
    ).stdout.splitlines()
    return merge_changed_file_sources(committed_files, staged, unstaged, untracked)


def changed_files_from_file(path: str) -> list[str]:
    if path == "-":
        return sys.stdin.read().splitlines()
    return Path(path).read_text(encoding="utf-8").splitlines()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main", help="Base ref for git diff.")
    parser.add_argument("--head", default="HEAD", help="Head ref for git diff.")
    parser.add_argument(
        "--changed-files",
        help="Path containing newline-separated changed files, or '-' for stdin.",
    )
    parser.add_argument(
        "--all", action="store_true", help="Select every validation lane."
    )
    parser.add_argument(
        "--format", choices=["json", "text", "github-output"], default="json"
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.all:
        changed_files: list[str] = []
    elif args.changed_files:
        changed_files = changed_files_from_file(args.changed_files)
    else:
        try:
            changed_files = changed_files_from_git(args.base, args.head)
        except subprocess.CalledProcessError as exc:
            print(exc.stderr, file=sys.stderr, end="")
            print(
                f"Unable to diff {args.base}...{args.head}; selecting all validation lanes.",
                file=sys.stderr,
            )
            manifest = select_validation([], all_changes=True)
            print_manifest(manifest, args.format)
            return 0

    manifest = select_validation(changed_files, all_changes=args.all)
    print_manifest(manifest, args.format)
    return 0


def print_manifest(manifest: dict, output_format: str) -> None:
    if output_format == "json":
        print(format_json(manifest))
    elif output_format == "text":
        print(format_text(manifest))
    else:
        print(format_github_output(manifest))


if __name__ == "__main__":
    raise SystemExit(main())
