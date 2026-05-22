# Code Review Reply Mode Spec

## Goal

Add a lightweight Linear/Symphony mode for addressing pull request review
comments without using the full `Rework` reset path.

## Current Behavior

The Borg UI Symphony contract recognizes `Todo`, `In Progress`, `Merging`, and
`Rework` as active states. `Human Review` feedback currently routes to `Rework`,
whose documented behavior closes the existing PR, removes the workpad, creates a
fresh branch, and starts over. That is too heavy when a PR only needs review
comments addressed in place.

## Desired Behavior

The Borg UI Linear workflow includes a started state named
`Code Review Reply`. Symphony polls that state as active. When a human moves an
issue into `Code Review Reply`, the agent keeps the existing PR and workpad,
runs the full PR feedback sweep, addresses actionable comments or replies with
justified pushback, reruns validation, pushes any updates, sweeps feedback and
checks again, then returns the issue to `Human Review`.

`Rework` remains the full-reset path for cases where the current PR should not
be salvaged.

## Repository Scope

- Update `WORKFLOW.md` so the orchestration prompt has an explicit
  `Code Review Reply` route.
- Update `docs/symphony.md` so setup requirements list the new Linear status.
- Add a focused unit test that treats the workflow file and setup docs as the
  repository contract.

No Borg UI app frontend component changes are required; the user-visible
control is the Linear workflow state.

## Acceptance Criteria

- `Code Review Reply` exists in Linear as a started workflow state.
- `WORKFLOW.md` polls `Code Review Reply` as an active state.
- The status map routes `Code Review Reply` to a feedback-reply flow that keeps
  the existing PR.
- `Human Review` feedback routes to `Code Review Reply` instead of `Rework`
  when comments can be addressed in place.
- `Rework` remains documented as a full reset.
- `docs/symphony.md` lists `Code Review Reply` in the required status set and
  in the active states that Symphony polls.

## Validation

- `pytest tests/unit/test_workflow_code_review_reply_mode.py -v`
- `ruff check app tests`
- `ruff format --check app tests`
- `git diff --check`
