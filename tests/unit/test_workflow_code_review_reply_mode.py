from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def squash(text: str) -> str:
    return " ".join(text.split())


def workflow_active_states(workflow: str) -> list[str]:
    if not isinstance(workflow, str):
        return []

    parts = workflow.split("---", 2)
    if len(parts) < 3:
        return []

    front_matter = yaml.safe_load(parts[1]) or {}
    tracker = front_matter.get("tracker", {})
    states = tracker.get("active_states") if isinstance(tracker, dict) else None
    if states is None:
        states = front_matter.get("active_states", [])
    if not isinstance(states, list):
        return []

    return [state for state in states if isinstance(state, str)]


def test_workflow_active_states_handles_missing_front_matter():
    assert workflow_active_states("no front matter") == []
    assert workflow_active_states("---\nactive_states: In Progress\n---") == []
    assert (
        workflow_active_states("---\ntracker:\n  active_states: In Progress\n---") == []
    )


def test_workflow_polls_code_review_reply_mode():
    workflow = read("WORKFLOW.md")

    assert "Code Review Reply" in workflow_active_states(workflow)
    assert "- `Code Review Reply` -> run code review reply flow." in workflow


def test_human_review_feedback_routes_to_code_review_reply():
    workflow = read("WORKFLOW.md")
    normalized = squash(workflow)

    assert (
        "If review feedback requires changes that can be addressed in the "
        "existing PR, move the issue to `Code Review Reply`"
    ) in normalized
    assert "Code Review Reply keeps the existing PR, branch, and workpad" in normalized
    assert "Treat `Rework` as a full approach reset" in normalized


def test_symphony_docs_list_code_review_reply_status():
    docs = read("docs/symphony.md")
    normalized = squash(docs)

    assert (
        "Linear project statuses: `Todo`, `In Progress`, `Human Review`, "
        "`Code Review Reply`, `Merging`, `Rework`, and `Done`"
    ) in normalized
    assert (
        "active `Todo`, `In Progress`, `Code Review Reply`, `Merging`,"
    ) in normalized
