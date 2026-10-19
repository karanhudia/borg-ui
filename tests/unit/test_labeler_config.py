"""Guard: the pull request labeler must keep matching the files it names.

actions/labeler fails silently when a glob stops matching: a file gets renamed,
the label is no longer applied and nothing ever fails. This test turns that
drift into a build failure in the pull request that does the rename.

It also pins the labeler workflow to its safe shape. ``pull_request_target``
runs with a write token, so the workflow must never check out or execute pull
request code.
"""

import re
import subprocess
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
LABELER_CONFIG = REPO_ROOT / ".github" / "labeler.yml"
LABELER_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "labeler.yml"

DESTRUCTIVE_PATH_LABEL = "destructive-path"

_GLOB_KEYS = {
    "any-glob-to-any-file",
    "any-glob-to-all-files",
    "all-globs-to-any-file",
    "all-globs-to-all-files",
}
# The check understands `*`, `?` and `**` only. Anything else minimatch reads
# (classes, braces, negation, extglobs) is refused, so the test cannot pass on
# a pattern it interprets differently from actions/labeler.
_UNSUPPORTED_GLOB_CHARS = re.compile(r"[\[\]{}!()+@]")


def _glob_to_regex(glob: str) -> re.Pattern:
    if _UNSUPPORTED_GLOB_CHARS.search(glob):
        raise ValueError(f"unsupported glob syntax: {glob!r}")
    segments = glob.split("/")
    regex = ""
    for index, segment in enumerate(segments):
        last = index == len(segments) - 1
        if segment == "**":
            regex += ".*" if last else "(?:[^/]+/)*"
            continue
        for char in segment:
            if char == "*":
                regex += "[^/]*"
            elif char == "?":
                regex += "[^/]"
            else:
                regex += re.escape(char)
        if not last:
            regex += "/"
    return re.compile(regex)


def _collect_globs(node, found: list[str], keys=_GLOB_KEYS) -> None:
    """Collect a label's globs, refusing options actions/labeler would reject
    (it throws on an unknown changed-files option) or silently ignore."""
    if isinstance(node, list):
        for item in node:
            _collect_globs(item, found, keys)
        return
    for key, value in node.items():
        if key in ("any", "all"):
            _collect_globs(value, found, keys)
        elif key == "changed-files":
            for rule in value if isinstance(value, list) else [value]:
                unknown = set(rule) - _GLOB_KEYS
                if unknown:
                    raise ValueError(f"unknown changed-files option: {sorted(unknown)}")
                for rule_key, globs in rule.items():
                    if rule_key in keys:
                        found.extend([globs] if isinstance(globs, str) else globs)
        elif key not in ("head-branch", "base-branch"):
            raise ValueError(f"unknown labeler option: {key!r}")


def unmatched_globs(config: dict, files: list[str]) -> list[tuple[str, str]]:
    """Return (label, glob) for every configured glob that matches no file."""
    unmatched = []
    for label, matchers in config.items():
        globs: list[str] = []
        _collect_globs(matchers, globs)
        for glob in globs:
            pattern = _glob_to_regex(glob)
            if not any(pattern.fullmatch(path) for path in files):
                unmatched.append((label, glob))
    return unmatched


def _tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=REPO_ROOT,
        capture_output=True,
        check=True,
    )
    return [path for path in result.stdout.decode().split("\0") if path]


def _load_config() -> dict:
    return yaml.safe_load(LABELER_CONFIG.read_text())


def test_every_labeler_glob_matches_a_tracked_file():
    config = _load_config()
    files = _tracked_files()

    assert files, "git ls-files returned nothing"
    unmatched = unmatched_globs(config, files)
    assert not unmatched, (
        "globs in .github/labeler.yml match no tracked file (renamed or "
        "removed?): " + ", ".join(f"{label}: {glob}" for label, glob in unmatched)
    )


def test_unmatched_glob_is_reported():
    config = {
        "example": [
            {
                "changed-files": [
                    {
                        "any-glob-to-any-file": [
                            "app/services/kept.py",
                            "app/services/renamed.py",
                            "agent/**/ops.py",
                        ]
                    }
                ]
            }
        ]
    }
    files = ["app/services/kept.py", "agent/pkg/ops.py"]

    assert unmatched_globs(config, files) == [("example", "app/services/renamed.py")]


@pytest.mark.parametrize(
    ("glob", "path", "matches"),
    [
        ("app/core/borg.py", "app/core/borg.py", True),
        ("app/core/borg.py", "app/core/borg2.py", False),
        ("app/services/*_service.py", "app/services/prune_service.py", True),
        ("app/services/*_service.py", "app/services/v2/prune_service.py", False),
        ("app/**/prune_service.py", "app/prune_service.py", True),
        ("app/**/prune_service.py", "app/services/v2/prune_service.py", True),
        ("app/services/**", "app/services/v2/prune_service.py", True),
        ("app/core/borg?.py", "app/core/borg2.py", True),
    ],
)
def test_glob_translation(glob, path, matches):
    assert bool(_glob_to_regex(glob).fullmatch(path)) is matches


@pytest.mark.parametrize(
    "matchers",
    [
        # A misspelled rule next to a valid one: actions/labeler throws.
        [
            {
                "changed-files": [
                    {"any-glob-to-any-file": ["app/core/borg.py"]},
                    {"any-globs-to-any-file": ["app/core/borg2.py"]},
                ]
            }
        ],
        # A misspelled matcher: actions/labeler ignores it.
        [{"changed-file": [{"any-glob-to-any-file": ["app/core/borg.py"]}]}],
    ],
)
def test_unknown_labeler_option_is_refused(matchers):
    with pytest.raises(ValueError):
        unmatched_globs({"example": matchers}, ["app/core/borg.py"])


def test_unsupported_glob_syntax_is_refused():
    with pytest.raises(ValueError):
        _glob_to_regex("app/services/{prune,compact}_service.py")


def test_every_destructive_path_glob_labels_on_its_own():
    matchers = _load_config()[DESTRUCTIVE_PATH_LABEL]
    all_globs: list[str] = []
    _collect_globs(matchers, all_globs)
    any_to_any: list[str] = []
    _collect_globs(matchers, any_to_any, keys={"any-glob-to-any-file"})

    # Only any-glob-to-any-file, outside an `all:` block, applies the label when
    # a pull request changes just one of the listed files.
    assert all(set(matcher) == {"changed-files"} for matcher in matchers)
    assert all_globs == any_to_any
    assert ".github/labeler.yml" in any_to_any
    assert ".github/workflows/labeler.yml" in any_to_any


def test_labeler_workflow_never_runs_pull_request_code():
    text = LABELER_WORKFLOW.read_text()
    # No expressions at all: nothing the pull request controls (title, branch,
    # body) can reach a value in this workflow.
    assert "${{" not in text
    workflow = yaml.safe_load(text)
    # PyYAML reads the bare `on` key as boolean True.
    triggers = workflow.get("on", workflow.get(True))

    assert set(triggers) == {"pull_request_target"}
    # The default types leave out `edited`, so a changed base branch would
    # not be re-evaluated.
    assert set(triggers["pull_request_target"]["types"]) == {
        "opened",
        "synchronize",
        "reopened",
        "edited",
    }
    assert workflow["permissions"] == {
        "contents": "read",
        "pull-requests": "write",
    }
    for name, job in workflow["jobs"].items():
        # No permissions override, container, services or reusable workflow.
        assert set(job) <= {"name", "runs-on", "steps"}, f"job {name}: {set(job)}"
        for step in job["steps"]:
            # Only the labeler: no checkout, no run step, no other action.
            assert set(step) <= {"name", "id", "uses", "with"}, step
            assert step["uses"].startswith("actions/labeler@"), step
