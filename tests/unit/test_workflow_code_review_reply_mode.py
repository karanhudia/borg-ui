from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def squash(text: str) -> str:
    return " ".join(text.split())


def test_workflow_polls_code_review_reply_mode():
    workflow = read("WORKFLOW.md")

    assert "    - Code Review Reply" in workflow
    assert "- `Code Review Reply` -> run code review reply flow." in workflow


def test_human_review_feedback_routes_to_code_review_reply():
    workflow = read("WORKFLOW.md")
    normalized = squash(workflow)

    assert (
        "If review feedback requires changes that can be addressed in the "
        "existing PR, move the issue to `Code Review Reply`"
    ) in normalized
    assert "Code Review Reply keeps the existing PR, branch, and workpad" in workflow
    assert "Treat `Rework` as a full approach reset" in workflow


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
