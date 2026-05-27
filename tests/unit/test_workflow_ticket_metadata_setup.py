from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def squash(text: str) -> str:
    return " ".join(text.split())


def test_metadata_bootstrap_runs_before_status_routing():
    workflow = read("WORKFLOW.md")

    assert "## Linear Metadata Bootstrap" in workflow
    assert workflow.index("## Linear Metadata Bootstrap") < workflow.index(
        "## Step 0: Determine current ticket state and route"
    )


def test_metadata_bootstrap_updates_title_description_and_labels():
    workflow = read("WORKFLOW.md")
    normalized = squash(workflow)
    lower_normalized = normalized.lower()

    assert "rewrite the linear issue title" in lower_normalized
    assert "rewrite the linear issue description" in lower_normalized
    assert "issueUpdate" in workflow
    assert "title" in workflow
    assert "description" in workflow
    assert "labelIds" in workflow
    assert "addedLabelIds" in workflow
    assert "issueLabelCreate" in workflow
    assert "create the missing label" in normalized


def test_todo_metadata_bootstrap_runs_once_before_status_routing():
    workflow = read("WORKFLOW.md")
    normalized = squash(workflow)

    assert (
        "If the current state is `Todo`, `In Progress`, `Code Review Reply`, or "
        "`Rework`, run the Linear metadata bootstrap before routing."
    ) in normalized
    assert (
        "`Todo` -> immediately move to `In Progress`, then ensure bootstrap "
        "workpad comment exists"
    ) in normalized
    assert (
        "For `Todo` tickets, do startup sequencing in this exact order: - "
        '`update_issue(..., state: "In Progress")`'
    ) in normalized


def test_previous_ticket_backfill_is_required_for_bor_70():
    workflow = read("WORKFLOW.md")
    normalized = squash(workflow)
    lower_normalized = normalized.lower()

    assert "BOR-70 previous-ticket backfill" in workflow
    assert "query previous borg ui project tickets" in lower_normalized
    assert "apply the same title, description, and label policy" in lower_normalized
    assert "updated, skipped, and failed counts" in normalized


def test_symphony_docs_document_metadata_bootstrap_and_backfill():
    docs = read("docs/symphony.md")
    normalized = squash(docs)

    assert "Linear ticket metadata bootstrap" in docs
    assert "updates the Linear issue title, description, and labels" in normalized
    assert "creates a missing label when the existing label set is insufficient" in (
        normalized
    )
    assert "BOR-70 previous-ticket backfill" in docs
