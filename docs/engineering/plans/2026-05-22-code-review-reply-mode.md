# Code Review Reply Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:subagent-driven-development (recommended) or
> superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Borg UI Symphony workflow state that addresses PR review
comments in place and returns the issue to Human Review.

**Architecture:** Keep the change in the repository-owned orchestration
contract. `WORKFLOW.md` defines the state machine behavior, `docs/symphony.md`
documents required setup, and a focused pytest file guards the contract.

**Tech Stack:** Markdown workflow contract, Linear workflow state, pytest.

---

### Task 1: Workflow Contract Test

**Files:**
- Create: `tests/unit/test_workflow_code_review_reply_mode.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_workflow_polls_code_review_reply_mode():
    workflow = read("WORKFLOW.md")

    assert "    - Code Review Reply" in workflow
    assert "- `Code Review Reply` -> run code review reply flow." in workflow


def test_human_review_feedback_routes_to_code_review_reply():
    workflow = read("WORKFLOW.md")

    assert (
        "If review feedback requires changes that can be addressed in the "
        "existing PR, move the issue to `Code Review Reply`"
    ) in workflow
    assert "Code Review Reply keeps the existing PR, branch, and workpad" in workflow
    assert "Treat `Rework` as a full approach reset" in workflow


def test_symphony_docs_list_code_review_reply_status():
    docs = read("docs/symphony.md")

    assert (
        "Linear project statuses: `Todo`, `In Progress`, `Human Review`, "
        "`Code Review Reply`, `Merging`, `Rework`, and `Done`"
    ) in docs
    assert "active `Todo`, `In Progress`, `Code Review Reply`, `Merging`," in docs
```

- [ ] **Step 2: Run the test and confirm it fails**

Run: `pytest tests/unit/test_workflow_code_review_reply_mode.py -v`

Expected: failures show `Code Review Reply` is missing from `WORKFLOW.md` and
`docs/symphony.md`.

### Task 2: Workflow Mode

**Files:**
- Modify: `WORKFLOW.md`

- [ ] **Step 1: Add `Code Review Reply` to active states**

Add this item under `tracker.active_states`:

```yaml
    - Code Review Reply
```

- [ ] **Step 2: Add status-map routing**

Add a status-map entry:

```md
- `Code Review Reply` -> run code review reply flow.
```

Define the flow as: keep the existing PR/workpad, run the required PR feedback
sweep, address comments or reply with justified pushback, validate, push, sweep
again, and return to `Human Review`.

- [ ] **Step 3: Update Human Review handling**

Change the Human Review feedback sentence so PR comments that can be addressed
in place move to `Code Review Reply`. Keep `Rework` reserved for full reset.

### Task 3: Setup Docs

**Files:**
- Modify: `docs/symphony.md`

- [ ] **Step 1: Add setup requirement**

Include `Code Review Reply` in the required Linear status list.

- [ ] **Step 2: Add polling behavior**

Include `Code Review Reply` in the list of active states Symphony polls.

### Task 4: Validate And Publish

**Files:**
- Update: Linear workpad
- Use: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Run focused validation**

Run:

```bash
pytest tests/unit/test_workflow_code_review_reply_mode.py -v
ruff check app tests
ruff format --check app tests
git diff --check
```

- [ ] **Step 2: Commit and push**

Use the repository `commit` and `push` skills. Create or update the PR, fill the
PR template, add the `symphony` label, link the PR to BOR-62, sweep PR feedback
and checks, then move Linear to `Human Review`.
