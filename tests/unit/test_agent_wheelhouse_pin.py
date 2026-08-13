"""The managed-agent wheelhouse is version-pinned so the same commit always stages
the same dependency wheels. These guards keep the pin wired and exact -- a dropped
`--constraint` or a range slipping into the lock would silently reintroduce the
build-time drift the pin removes."""

import re
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def _constraints_lines():
    text = (_REPO_ROOT / "agent" / "constraints.txt").read_text()
    return [
        line.strip()
        for line in text.splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    ]


def _agent_builder_stage(dockerfile_text):
    """The lines of the `agent-builder` build stage only -- from its
    `FROM ... AS agent-builder` up to the next stage -- so a check cannot be
    satisfied by text belonging to another stage."""
    lines = dockerfile_text.splitlines()
    start = next(
        (
            i
            for i, line in enumerate(lines)
            if re.match(r"\s*FROM\b", line)
            and re.search(r"\bAS\s+agent-builder\b", line)
        ),
        None,
    )
    assert start is not None, "no agent-builder stage found in the Dockerfile"
    end = next(
        (j for j in range(start + 1, len(lines)) if re.match(r"\s*FROM\b", lines[j])),
        len(lines),
    )
    return lines[start:end]


def _pip_download_command(dockerfile_text):
    """Return the agent-builder's `pip download` invocation with its line
    continuations joined, scoped to that stage and ignoring comments, so a check
    binds to the active command -- a comment or another stage mentioning the same
    flag cannot satisfy it."""
    code = [
        line
        for line in _agent_builder_stage(dockerfile_text)
        if not line.lstrip().startswith("#")
    ]
    for i, line in enumerate(code):
        if "pip download" in line:
            collected = [line]
            j = i
            while collected[-1].rstrip().endswith("\\") and j + 1 < len(code):
                j += 1
                collected.append(code[j])
            return " ".join(part.rstrip().rstrip("\\").strip() for part in collected)
    raise AssertionError("no `pip download` command found in the agent-builder stage")


def test_the_agent_builder_download_uses_the_constraints_file():
    """The agent-builder's `pip download` must pass the constraints, or the closure
    floats to whatever PyPI resolves at build time. Bind the check to that command
    so a mention in a comment cannot satisfy it."""
    command = _pip_download_command((_REPO_ROOT / "Dockerfile").read_text())
    assert "--constraint agent/constraints.txt" in command


def test_every_constraint_is_an_exact_pin():
    """A range (>=, <, ~=) in the lock defeats reproducibility; each line must be
    a single `==` pin."""
    for line in _constraints_lines():
        assert re.fullmatch(r"[A-Za-z0-9._-]+==[A-Za-z0-9.]+", line), (
            f"constraints.txt entry is not an exact pin: {line!r}"
        )


def test_the_pinned_closure_is_exactly_the_agents_dependency_closure():
    """requests and websocket-client are the agent's declared deps; together with
    the transitive closure requests pulls in, the pinned set is exactly these six.
    Equality (not containment) means adding or removing a pin without updating this
    list fails the guard, so constraints.txt and the documented closure cannot
    drift apart unnoticed."""
    pinned_names = [
        line.split("==", 1)[0].replace("_", "-").lower()
        for line in _constraints_lines()
    ]
    assert len(pinned_names) == len(set(pinned_names)), (
        "constraints.txt contains duplicate package pins"
    )
    pinned = set(pinned_names)
    expected = {
        "requests",
        "websocket-client",
        "urllib3",
        "idna",
        "certifi",
        "charset-normalizer",
    }
    assert pinned == expected, (
        f"missing pins: {expected - pinned}; unexpected pins: {pinned - expected}"
    )
