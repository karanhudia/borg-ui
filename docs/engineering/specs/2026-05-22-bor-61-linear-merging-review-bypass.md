# BOR-61 Linear Merging Review Bypass Spec

## Context

Symphony lands Borg UI pull requests through `.codex/skills/land/SKILL.md` when a
Linear issue moves to `Merging`. That state is the workflow's human approval
signal, but GitHub can still report `reviewDecision=REVIEW_REQUIRED` when the PR
was created by the same GitHub account that would otherwise approve it.

The current land fast path reads `mergeable` and `mergeStateStatus`, but not
`reviewDecision`. A clean PR with `mergeable=MERGEABLE`,
`mergeStateStatus=BLOCKED`, green checks, unchanged head SHA, and no post-handoff
feedback is forced into the conservative fallback with reason
`PR merge state is BLOCKED`. The fallback eventually attempts a normal
`gh pr merge --squash`, which GitHub rejects when the only remaining blocker is
the review requirement.

## Decision

Keep the previous reverted approach's core model, but make the bypass explicit:

- Fetch GitHub `reviewDecision` in `land_watch.py`.
- Keep ordinary preflight conservative: `BLOCKED` still requires full validation
  unless the caller explicitly passes `--allow-review-required-admin-bypass`.
- When that flag is present, allow fast path only if all existing head, check,
  and feedback requirements pass and the PR state is exactly
  `MERGEABLE + BLOCKED + REVIEW_REQUIRED`.
- Return JSON metadata with `requires_admin_bypass=true` so the land skill can
  choose `gh pr merge --admin`.
- Before using `--admin`, re-read GitHub's final `mergeable`,
  `mergeStateStatus`, and `reviewDecision` values and require the same exact
  shape.

## Non-Goals

- Do not bypass merge conflicts, failed checks, missing checks, changed PR heads,
  unknown mergeability, or post-handoff human/Codex feedback.
- Do not change GitHub branch protection or create a separate bot account.
- Do not make every `mergeStateStatus=BLOCKED` bypassable.

## Validation

- Add a failing regression test for the explicit review-required admin-bypass
  path, then make it pass.
- Keep a test proving `BLOCKED + REVIEW_REQUIRED` still blocks when the explicit
  bypass flag is absent.
- Run the full `tests/unit/test_land_watch_fast_path.py` suite.
- Run helper lint and Borg UI backend policy gates.
