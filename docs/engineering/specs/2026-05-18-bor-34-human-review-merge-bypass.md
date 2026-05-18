# BOR-34 Human Review Merge Bypass Spec

## Context

Symphony lands Borg UI pull requests through the local `land` skill when a Linear
issue moves to `Merging`. That state is already the workflow's human approval
signal, but GitHub can still report `reviewDecision=REVIEW_REQUIRED` because the
PR is created by the same GitHub account that would otherwise approve it.

The current fast landing helper evaluates PR head SHA, mergeability, check runs,
and feedback activity. It does not read `reviewDecision`, so it treats GitHub's
generic `mergeStateStatus=BLOCKED` as a full fallback case even when the only
remaining blocker is the branch approval policy described in BOR-34.

## Evidence

- `WORKFLOW.md` routes `Merging` issues into `.codex/skills/land/SKILL.md`.
- `.codex/skills/land/land_watch.py` fetches `mergeable` and
  `mergeStateStatus`, but not `reviewDecision`.
- A local reproduction call to `evaluate_fast_path` with unchanged head SHA,
  green checks, no feedback, `mergeable=MERGEABLE`, and
  `mergeStateStatus=BLOCKED` returns `can_fast_path=False` with reason
  `PR merge state is BLOCKED`.
- Local `gh pr view --help` lists `reviewDecision`, and
  `gh pr merge --help` lists `--admin` for administrator bypass merges.

## Decision

Use the Linear `Merging` state as the human approval signal for BOR-34's review
requirement case. The land preflight should fetch GitHub `reviewDecision` and
return a fast-path decision with explicit administrator-bypass metadata only
when all of these are true:

- PR head SHA matches the Human Review handoff SHA.
- `mergeable` is `MERGEABLE`.
- `mergeStateStatus` is `BLOCKED`.
- `reviewDecision` is `REVIEW_REQUIRED`.
- GitHub checks exist and are green.
- No human or Codex feedback appeared after the Human Review handoff.

All other blockers stay conservative. Merge conflicts, missing or non-green
checks, changed head SHA, missing handoff metadata, non-review `BLOCKED` states,
unknown mergeability, and post-handoff feedback must still force fallback or
block landing.

When the preflight reports administrator bypass is required, the land skill
should use `gh pr merge --admin`. If the authenticated GitHub account lacks
permission to bypass branch protection, that command fails and the workflow must
surface the permission blocker rather than pretending the PR was merged.

## Alternatives Considered

1. Create PRs as a separate bot account so the human can approve in GitHub.
   This addresses the root workflow ergonomics, but it requires new credentials
   and GitHub app/token changes outside this repository.

2. Remove or relax the GitHub review requirement.
   This is an external repository policy change and would weaken protections for
   all PRs, not just Symphony-managed work that has reached Linear `Merging`.

3. Treat every `mergeStateStatus=BLOCKED` as bypassable.
   This is too broad because `BLOCKED` can represent other branch protection
   failures. The implementation must require `reviewDecision=REVIEW_REQUIRED`
   and separately verify checks and feedback before requesting admin bypass.

## Validation

- Add a regression test showing `BLOCKED + REVIEW_REQUIRED` can fast-path with
  administrator-bypass metadata when all other preflight inputs are clean.
- Keep or add coverage showing non-review `BLOCKED` states still require full
  validation.
- Run targeted unit tests for `land_watch.py`.
- Run ruff checks for the helper and tests plus the repository backend
  lint/format gates required by Borg UI policy.
