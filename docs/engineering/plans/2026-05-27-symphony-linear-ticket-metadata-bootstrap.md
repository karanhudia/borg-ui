# Symphony Linear Ticket Metadata Bootstrap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use
> superpowers:executing-plans to implement this plan task-by-task. Subagent
> execution is not used here because BOR-70 is running as an unattended
> single-workspace orchestration session.

**Goal:** Add a repository-owned Symphony workflow contract requiring Linear
ticket title, description, and label cleanup before active work proceeds.

**Architecture:** Keep the change in the orchestration prompt and setup docs.
`WORKFLOW.md` defines the metadata bootstrap, previous-ticket backfill, and
guardrail exceptions. `docs/symphony.md` documents operator expectations. A
focused pytest file guards the contract text.

**Tech Stack:** Markdown workflow contract, Linear GraphQL operations, pytest,
ruff.

---

### Task 1: Workflow Contract Test

**Files:**
- Create: `tests/unit/test_workflow_ticket_metadata_setup.py`

- [ ] **Step 1: Write the failing test**

Create tests that assert the workflow has a required metadata bootstrap before
Step 0, that it mentions `issueUpdate`, `issueLabelCreate`, title/description
rewrites, label creation, and previous-ticket backfill. Also assert
`docs/symphony.md` documents the operator behavior, that descriptions derive
the problem, desired outcome, and acceptance criteria from the original request,
and that raw original request text is preserved in a collapsed or quoted
appendix instead of repeated as the primary ticket body.

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
pytest tests/unit/test_workflow_ticket_metadata_setup.py -v
```

Expected: failures show the metadata bootstrap and docs text are missing.

### Task 2: Workflow Metadata Bootstrap

**Files:**
- Modify: `WORKFLOW.md`

- [ ] **Step 1: Add the required bootstrap section**

Insert a `## Linear metadata bootstrap` section before Step 0. Require active
issues to polish the title and description using Linear `issueUpdate`, assign
labels using `labelIds`/`addedLabelIds`, and create missing labels using
`issueLabelCreate`. Explicitly prohibit repeated generic acceptance criteria;
the rewritten problem, desired outcome, and acceptance criteria must be derived
from the original request and linked context.

- [ ] **Step 2: Integrate startup sequencing**

Update Step 0 and the Todo startup order so metadata cleanup runs before normal
implementation work while preserving `Backlog` and terminal-state safety.

- [ ] **Step 3: Add the BOR-70 backfill step**

Require BOR-70 to query previous Borg UI tickets, apply the same metadata
policy, create missing labels as needed, and record updated/skipped counts in
the workpad.

### Task 3: Setup Documentation

**Files:**
- Modify: `docs/symphony.md`

- [ ] **Step 1: Document startup metadata cleanup**

Add operator-facing text explaining that Symphony updates Linear titles,
descriptions, and labels before execution.

- [ ] **Step 2: Document backfill behavior**

Add text explaining that BOR-70 performs the one-time previous-ticket backfill
and that future backfills should use the same metadata bootstrap policy.

### Task 4: Linear Metadata Backfill

**Files:**
- Update: Linear issue metadata through `linear_graphql`
- Update: Linear workpad only

- [ ] **Step 1: Update BOR-70 metadata**

Rewrite BOR-70 title/description to durable wording and apply appropriate
labels.

- [ ] **Step 2: Backfill previous tickets**

Query previous Borg UI project issues, apply the same title/description/label
policy where the issue is still editable, replace repeated generic descriptions
with request-specific problem/outcome/acceptance criteria, preserve raw request
text in a collapsed or quoted appendix, and record counts/skips in the workpad.

### Task 5: Validate And Publish

**Files:**
- Update: Linear workpad
- Use: `.github/PULL_REQUEST_TEMPLATE.md`

- [ ] **Step 1: Run validation**

Run:

```bash
pytest tests/unit/test_workflow_ticket_metadata_setup.py -v
ruff check app tests
ruff format --check app tests
git diff --check
```

- [ ] **Step 2: Commit and push**

Use the repository `commit` and `push` skills. Create or update the PR, fill the
PR template, add the `symphony` label, attach it to BOR-70, sweep PR feedback
and checks, then move Linear to `Human Review`.
