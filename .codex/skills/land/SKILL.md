---
name: land
description:
  Land a PR by monitoring conflicts, resolving them, waiting for checks, and
  squash-merging when green; use when asked to land, merge, or shepherd a PR to
  completion.
---

# Land

## Goals

- Ensure the PR is conflict-free with main.
- Keep CI green and fix failures when they occur.
- Use a fast path for already-green PRs whose head SHA matches the Human Review
  handoff.
- Squash-merge the PR once checks pass.
- Do not yield to the user until the PR is merged; keep the watcher loop running
  unless the fast path proves the full watcher is unnecessary or landing is
  blocked.
- No need to delete remote branches after merge; the repo auto-deletes head
  branches.

## Preconditions

- `gh` CLI is authenticated.
- You are on the PR branch with a clean working tree.

## Steps

1. Locate the PR for the current branch.
2. Read the workpad final handoff notes and find the exact line:
   `Human Review handoff: head=<PR head SHA>; at=<ISO-8601 timestamp>; validation=<commands>`.
3. Run the fast-path preflight:
   `python3 .codex/skills/land/land_watch.py --preflight --handoff-note '<handoff note>'`.
4. If the preflight exits `0`, skip full local validation and the full watcher
   loop for this already-green PR. The preflight has confirmed the head SHA is
   unchanged since Human Review, mergeability is clean, checks are green, and no
   new human/Codex feedback appeared since Human Review. Squash-merge with the
   PR title/body after one final `gh pr view --json mergeable,mergeStateStatus`
   check still reports a clean merge state.
5. If the preflight exits `6`, fails, or reports missing/uncertain data, use the
   conservative fallback below.
6. Conservative fallback: confirm the Borg UI validation gauntlet is green
   locally before any push:
   `git diff --check`; backend checks for backend changes; frontend checks for
   frontend changes; and smoke/runtime checks for user-facing app changes.
7. If the working tree has uncommitted changes, commit with the `commit` skill
   and push with the `push` skill before proceeding.
8. Check mergeability and conflicts against main.
9. If conflicts exist, use the `pull` skill to fetch/merge `origin/main` and
   resolve conflicts, then use the `push` skill to publish the updated branch.
10. Ensure Codex review comments (if present) are acknowledged and any required
   fixes are handled before merging.
11. Watch checks until complete.
12. If checks fail, pull logs, fix the issue, commit with the `commit` skill,
   push with the `push` skill, and re-run checks.
13. When all checks are green and review feedback is addressed, squash-merge and
   delete the branch using the PR title/body for the merge subject/body.
14. **Context guard:** Before implementing review feedback, confirm it does not
    conflict with the user’s stated intent or task context. If it conflicts,
    respond inline with a justification and ask the user before changing code.
15. **Pushback template:** When disagreeing, reply inline with: acknowledge +
    rationale + offer alternative.
16. **Ambiguity gate:** When ambiguity blocks progress, use the clarification
    flow (assign PR to current GH user, mention them, wait for response). Do not
    implement until ambiguity is resolved.
    - If you are confident you know better than the reviewer, you may proceed
      without asking the user, but reply inline with your rationale.
17. **Per-comment mode:** For each review comment, choose one of: accept,
    clarify, or push back. Reply inline (or in the issue thread for Codex
    reviews) stating the mode before changing code.
18. **Reply before change:** Always respond with intended action before pushing
    code changes (inline for review comments, issue thread for Codex reviews).

## Commands

```
# Ensure branch and PR context
branch=$(git branch --show-current)
pr_number=$(gh pr view --json number -q .number)
pr_title=$(gh pr view --json title -q .title)
pr_body=$(gh pr view --json body -q .body)
handoff_note='Human Review handoff: head=<sha>; at=<timestamp>; validation=<commands>'

# Fast path for already-green PRs. If this exits 0, skip local validation and
# the full watcher loop. If it exits 6 or errors, use the conservative fallback.
if python3 .codex/skills/land/land_watch.py --preflight --handoff-note "$handoff_note"; then
  mergeable=$(gh pr view --json mergeable -q .mergeable)
  merge_state=$(gh pr view --json mergeStateStatus -q .mergeStateStatus)
  if [ "$mergeable" = "MERGEABLE" ] && { [ "$merge_state" = "CLEAN" ] || [ "$merge_state" = "HAS_HOOKS" ]; }; then
    gh pr merge --squash --subject "$pr_title" --body "$pr_body"
    exit 0
  fi
fi

# Check mergeability and conflicts for the conservative fallback.
mergeable=$(gh pr view --json mergeable -q .mergeable)

if [ "$mergeable" = "CONFLICTING" ]; then
  # Run the `pull` skill to handle fetch + merge + conflict resolution.
  # Then run the `push` skill to publish the updated branch.
fi

# Conservative fallback: Borg UI local validation before merge. Keep this
# scope-sensitive for the PR.
git diff --check
if git diff --name-only origin/main...HEAD | rg -q '^(app|tests|requirements.txt|pytest.ini|ruff.toml)(/|$)'; then
  ruff check app tests
  ruff format --check app tests
  pytest tests/unit -v
fi
if git diff --name-only origin/main...HEAD | rg -q '^frontend/'; then
  (cd frontend && npm run check:locales && npm run typecheck && npm run lint && npm run build)
fi

# Fallback watcher path. The manual loop is a fallback when Python cannot run or
# the helper script is unavailable.
# Wait for review feedback: Codex reviews arrive as issue comments that start
# with "## Codex Review — <persona>". Treat them like reviewer feedback: reply
# with a `[codex]` issue comment acknowledging the findings and whether you're
# addressing or deferring them.
while true; do
  gh api repos/{owner}/{repo}/issues/"$pr_number"/comments \
    --jq '.[] | select(.body | startswith("## Codex Review")) | .id' | rg -q '.' \
    && break
  sleep 10
done

# Watch checks
if ! gh pr checks --watch; then
  gh pr checks
  # Identify failing run and inspect logs
  # gh run list --branch "$branch"
  # gh run view <run-id> --log
  exit 1
fi

# Squash-merge (remote branches auto-delete on merge in this repo)
gh pr merge --squash --subject "$pr_title" --body "$pr_body"
```

## Fast Path Preflight

For already-green PRs, the preflight command checks current GitHub state instead
of repeating local validation:

```
python3 .codex/skills/land/land_watch.py --preflight --handoff-note "$handoff_note"
```

The handoff note must come from the workpad final handoff notes:

```
Human Review handoff: head=<PR head SHA>; at=<ISO-8601 timestamp>; validation=<commands>
```

The fast path is allowed only when all of these are true:

- The current PR head SHA matches the Human Review handoff SHA.
- Mergeability is `MERGEABLE` and merge state is `CLEAN` or `HAS_HOOKS`.
- GitHub check runs exist and are complete with successful, neutral, or skipped
  conclusions.
- No human issue comments, human inline review comments, blocking review states,
  Codex review issue comments, or Codex inline comments appeared after the
  Human Review handoff timestamp.

Exit codes:

- 0: Fast path ready; skip full local validation and full watcher mode.
- 6: Full validation required; use the conservative fallback.

## Async Watch Helper

Use the asyncio watcher in the conservative fallback to monitor review comments,
CI, and head updates in parallel:

```
python3 .codex/skills/land/land_watch.py
```

Exit codes:

- 2: Review comments detected (address feedback)
- 3: CI checks failed
- 4: PR head updated (autofix commit detected)
- 5: PR has merge conflicts
- 6: Fast-path preflight requires full validation

## Failure Handling

- If checks fail, pull details with `gh pr checks` and `gh run view --log`, then
  fix locally, commit with the `commit` skill, push with the `push` skill, and
  re-run the watch.
- Run the full local validation and watcher fallback when the preflight reports
  changed PR head, missing handoff data, conflicts, missing/pending/failed/
  inconclusive checks, feedback after Human Review, or any uncertain GitHub
  state.
- Use judgment to identify flaky failures. If a failure is a flake (e.g., a
  timeout on only one platform), you may proceed without fixing it.
- If CI pushes an auto-fix commit (authored by GitHub Actions), it does not
  trigger a fresh CI run. Detect the updated PR head, pull locally, merge
  `origin/main` if needed, add a real author commit, and force-push to retrigger
  CI, then restart the checks loop.
- If all jobs fail with corrupted npm lockfile errors on the merge commit, the
  remediation is to fetch latest `origin/main`, merge, force-push, and rerun CI.
- If mergeability is `UNKNOWN`, wait and re-check.
- Do not merge while review comments (human or Codex review) are outstanding.
- Codex review jobs retry on failure and are non-blocking; use the presence of
  `## Codex Review — <persona>` issue comments (not job status) as the signal
  that review feedback is available.
- Do not enable auto-merge; wait for the repository's GitHub checks and review
  feedback loop to finish before merging.
- If the remote PR branch advanced due to your own prior force-push or merge,
  avoid redundant merges; re-run the formatter locally if needed and
  `git push --force-with-lease`.

## Review Handling

- Codex reviews now arrive as issue comments posted by GitHub Actions. They
  start with `## Codex Review — <persona>` and include the reviewer’s
  methodology + guardrails used. Treat these as feedback that must be
  acknowledged before merge.
- Human review comments are blocking and must be addressed (responded to and
  resolved) before requesting a new review or merging.
- If multiple reviewers comment in the same thread, respond to each comment
  (batching is fine) before closing the thread.
- Fetch review comments via `gh api` and reply with a prefixed comment.
- Use review comment endpoints (not issue comments) to find inline feedback:
  - List PR review comments:
    ```
    gh api repos/{owner}/{repo}/pulls/<pr_number>/comments
    ```
  - PR issue comments (top-level discussion):
    ```
    gh api repos/{owner}/{repo}/issues/<pr_number>/comments
    ```
  - Reply to a specific review comment:
    ```
    gh api -X POST /repos/{owner}/{repo}/pulls/<pr_number>/comments \
      -f body='[codex] <response>' -F in_reply_to=<comment_id>
    ```
- `in_reply_to` must be the numeric review comment id (e.g., `2710521800`), not
  the GraphQL node id (e.g., `PRRC_...`), and the endpoint must include the PR
  number (`/pulls/<pr_number>/comments`).
- If GraphQL review reply mutation is forbidden, use REST.
- A 404 on reply typically means the wrong endpoint (missing PR number) or
  insufficient scope; verify by listing comments first.
- All GitHub comments generated by this agent must be prefixed with `[codex]`.
- For Codex review issue comments, reply in the issue thread (not a review
  thread) with `[codex]` and state whether you will address the feedback now or
  defer it (include rationale).
- If feedback requires changes:
  - For inline review comments (human), reply with intended fixes
    (`[codex] ...`) **as an inline reply to the original review comment** using
    the review comment endpoint and `in_reply_to` (do not use issue comments for
    this).
  - Implement fixes, commit, push.
  - Reply with the fix details and commit sha (`[codex] ...`) in the same place
    you acknowledged the feedback (issue comment for Codex reviews, inline reply
    for review comments).
  - The land watcher treats Codex review issue comments as unresolved until a
    newer `[codex]` issue comment is posted acknowledging the findings.
- Only request a new Codex review when you need a rerun (e.g., after new
  commits). Do not request one without changes since the last review.
  - Before requesting a new Codex review, re-run the land watcher and ensure
    there are zero outstanding review comments (all have `[codex]` inline
    replies).
  - After pushing new commits, the Codex review workflow will rerun on PR
    synchronization (or you can re-run the workflow manually). Post a concise
    root-level summary comment so reviewers have the latest delta:
    ```
    [codex] Changes since last review:
    - <short bullets of deltas>
    Commits: <sha>, <sha>
    Tests: <commands run>
    ```
  - Only request a new review if there is at least one new commit since the
    previous request.
  - Wait for the next Codex review comment before merging.

## Scope + PR Metadata

- The PR title and description should reflect the full scope of the change, not
  just the most recent fix.
- If review feedback expands scope, decide whether to include it now or defer
  it. You can accept, defer, or decline feedback. If deferring or declining,
  call it out in the root-level `[codex]` update with a brief reason (e.g.,
  out-of-scope, conflicts with intent, unnecessary).
- Correctness issues raised in review comments should be addressed. If you plan
  to defer or decline a correctness concern, validate first and explain why the
  concern does not apply.
- Classify each review comment as one of: correctness, design, style,
  clarification, scope.
- For correctness feedback, provide concrete validation (test, log, or
  reasoning) before closing it.
- When accepting feedback, include a one-line rationale in the root-level
  update.
- When declining feedback, offer a brief alternative or follow-up trigger.
- Prefer a single consolidated "review addressed" root-level comment after a
  batch of fixes instead of many small updates.
- For doc feedback, confirm the doc change matches behavior (no doc-only edits
  to appease review).
