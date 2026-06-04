# Symphony Linear Ticket Metadata Bootstrap Spec

## Goal

Make Symphony normalize Linear ticket metadata before execution so rough intake
tickets become understandable, durable work items with useful labels.

## Current Behavior

`WORKFLOW.md` starts by fetching the issue state and routing by status. It asks
the agent to keep a workpad current, but it does not require the agent to
rewrite rough ticket titles, rewrite rough descriptions, create or assign
labels, or backfill older Borg UI tickets. A reproduction grep before edits
only found `title/description` in the follow-up issue guardrail.

The Symphony runtime itself is not vendored into this repository. Borg UI owns
the repository contract in `WORKFLOW.md` and operator documentation in
`docs/symphony.md`.

## Desired Behavior

For every active issue Symphony picks up, the prompt requires a Linear metadata
bootstrap before normal implementation work:

- rewrite the title into a concise outcome-oriented title;
- rewrite the description into durable sections that preserve original intent,
  acceptance criteria, validation requirements, and important constraints;
- derive the problem, desired outcome, and acceptance criteria from the rough
  request and linked context instead of using repeated generic boilerplate
  (generic lines such as 'the title and labels clearly identify the work'); see
  `WORKFLOW.md` for concrete examples;
- preserve the raw original request in a Markdown block quote appendix so the
  rewritten ticket body leads with actionable work in Linear;
- choose an appropriate type label from the existing labels when possible;
- create and apply an additional label when the existing label set is
  insufficient for a clear workflow or domain classification;
- record the bootstrap result in the single workpad after the workpad exists;
- preserve `Backlog`, terminal, and planning-only guardrails.

The prompt also documents a one-time backfill step for BOR-70: query previous
Borg UI project tickets, apply the same metadata logic, create missing labels
as needed, and record counts and any skips in the workpad.

## Repository Scope

- Update `WORKFLOW.md` to add the metadata bootstrap sequence and backfill
  requirements.
- Update `docs/symphony.md` so operators know Symphony now updates Linear
  titles, descriptions, and labels during issue startup.
- Add a focused unit test that treats the workflow and setup docs as the
  repository-owned Symphony contract.
- Execute the BOR-70 Linear metadata update/backfill through the available
  Linear GraphQL tooling and record evidence in the workpad.

No Borg UI app runtime or frontend changes are required.

## Acceptance Criteria

- `WORKFLOW.md` requires active tickets to run a Linear metadata bootstrap
  before implementation work.
- The bootstrap requires title and description updates through Linear.
- The bootstrap requires request-specific descriptions and acceptance criteria,
  not generic metadata boilerplate.
- The bootstrap requires label assignment and creating missing labels when the
  existing label set is not enough.
- The BOR-70 previous-ticket backfill is documented as a required one-time
  step with count/skip reporting in the workpad.
- `docs/symphony.md` documents the title, description, label, and backfill
  behavior for operators.
- Focused pytest coverage fails before the workflow/docs change and passes
  after it.

## Validation

- `pytest tests/unit/test_workflow_ticket_metadata_setup.py -v`
- `ruff check app tests`
- `ruff format --check app tests`
- `git diff --check`
- Linear workpad evidence showing BOR-70 metadata was updated and previous
  ticket backfill was run or explicitly skipped with reason.
