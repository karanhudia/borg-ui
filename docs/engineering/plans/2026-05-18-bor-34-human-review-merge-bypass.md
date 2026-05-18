# BOR-34 Human Review Merge Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Symphony's land flow treat Linear `Merging` as the human approval signal for GitHub `REVIEW_REQUIRED` branch-policy blockers while preserving other merge blockers.

**Architecture:** Extend the existing `.codex/skills/land/land_watch.py` preflight model with GitHub `reviewDecision` and explicit administrator-bypass metadata. Update the land workflow docs to use `gh pr merge --admin` only when preflight proves the BOR-34 review-policy case.

**Tech Stack:** Python 3, pytest, ruff, GitHub CLI, Linear-driven Borg UI workflow docs.

---

### Task 1: Add the Failing BOR-34 Fast-Path Test

**Files:**
- Modify: `tests/unit/test_land_watch_fast_path.py`

- [ ] **Step 1: Extend the test PR factory**

  Add a `review_decision` keyword to `pr_info` so tests can describe GitHub's
  review state:

  ```python
  def pr_info(
      *,
      head_sha="abc1234",
      mergeable="MERGEABLE",
      merge_state="CLEAN",
      review_decision="APPROVED",
  ):
      return land_watch.PrInfo(
          number=22,
          url="https://github.com/example/repo/pull/22",
          head_sha=head_sha,
          mergeable=mergeable,
          merge_state=merge_state,
          review_decision=review_decision,
      )
  ```

- [ ] **Step 2: Add the BOR-34 regression test**

  Add this test near the other merge-state tests:

  ```python
  def test_fast_path_allows_review_required_when_admin_bypass_is_required():
      decision = green_decision(
          pr=pr_info(merge_state="BLOCKED", review_decision="REVIEW_REQUIRED")
      )

      assert decision.can_fast_path is True
      assert decision.requires_admin_bypass is True
      assert decision.admin_bypass_reason == (
          "GitHub review requirement satisfied by Linear Merging"
      )
      assert decision.reasons == []
  ```

- [ ] **Step 3: Verify the test fails for the current implementation**

  Run:

  ```bash
  pytest tests/unit/test_land_watch_fast_path.py::test_fast_path_allows_review_required_when_admin_bypass_is_required -q
  ```

  Expected: FAIL because `PrInfo` does not yet accept `review_decision` or
  `FastPathDecision` does not expose `requires_admin_bypass`.

### Task 2: Implement Review-Required Bypass Metadata

**Files:**
- Modify: `.codex/skills/land/land_watch.py`
- Modify: `tests/unit/test_land_watch_fast_path.py`

- [ ] **Step 1: Extend the dataclasses**

  Add `review_decision` to `PrInfo` and bypass metadata to
  `FastPathDecision`:

  ```python
  @dataclass
  class PrInfo:
      number: int
      url: str
      head_sha: str
      mergeable: str | None
      merge_state: str | None
      review_decision: str | None = None


  @dataclass
  class FastPathDecision:
      can_fast_path: bool
      reasons: list[str]
      requires_admin_bypass: bool = False
      admin_bypass_reason: str | None = None
  ```

- [ ] **Step 2: Fetch `reviewDecision` from GitHub**

  Update `get_pr_info()` to request and store `reviewDecision`:

  ```python
  data = await run_gh(
      "pr",
      "view",
      "--json",
      "number,url,headRefOid,mergeable,mergeStateStatus,reviewDecision",
  )
  ```

- [ ] **Step 3: Add a narrow bypass predicate**

  Add a helper that recognizes only BOR-34's review-policy shape:

  ```python
  def requires_review_admin_bypass(pr: PrInfo) -> bool:
      return (
          pr.mergeable == "MERGEABLE"
          and pr.merge_state == "BLOCKED"
          and pr.review_decision == "REVIEW_REQUIRED"
      )
  ```

- [ ] **Step 4: Apply the predicate in `evaluate_fast_path`**

  When merge state is not in `FAST_PATH_MERGE_STATES`, suppress the normal
  `PR merge state is BLOCKED` reason only for `requires_review_admin_bypass(pr)`.
  Return bypass metadata only when the final decision has no other reasons:

  ```python
  admin_bypass_reason = None
  if pr.merge_state is None:
      reasons.append("PR merge state is unknown")
  elif pr.merge_state not in FAST_PATH_MERGE_STATES:
      if requires_review_admin_bypass(pr):
          admin_bypass_reason = (
              "GitHub review requirement satisfied by Linear Merging"
          )
      else:
          reasons.append(f"PR merge state is {pr.merge_state}")

  can_fast_path = not reasons
  return FastPathDecision(
      can_fast_path=can_fast_path,
      reasons=reasons,
      requires_admin_bypass=bool(can_fast_path and admin_bypass_reason),
      admin_bypass_reason=admin_bypass_reason if can_fast_path else None,
  )
  ```

- [ ] **Step 5: Include bypass metadata in preflight output**

  Extend JSON output with `requires_admin_bypass` and
  `admin_bypass_reason`. In human output, add one line when admin bypass is
  required:

  ```python
  if decision.requires_admin_bypass:
      print(f"Administrator bypass required: {decision.admin_bypass_reason}")
  ```

- [ ] **Step 6: Verify targeted tests pass**

  Run:

  ```bash
  pytest tests/unit/test_land_watch_fast_path.py -v
  ```

  Expected: all tests in the file pass.

### Task 3: Update Landing Workflow Instructions

**Files:**
- Modify: `.codex/skills/land/SKILL.md`
- Modify: `WORKFLOW.md`

- [ ] **Step 1: Document the BOR-34 admin-bypass fast path**

  State that `Merging` is the human approval signal, and that
  `REVIEW_REQUIRED` may use `gh pr merge --admin` only when preflight reports
  `requires_admin_bypass=true`.

- [ ] **Step 2: Update command examples to parse preflight JSON**

  Use:

  ```bash
  preflight_json=$(python3 .codex/skills/land/land_watch.py --preflight --json --handoff-note "$handoff_note")
  requires_admin_bypass=$(printf '%s' "$preflight_json" | python3 -c 'import json,sys; print(str(json.load(sys.stdin).get("requires_admin_bypass", False)).lower())')
  ```

  Then call `gh pr merge --squash --admin` only when
  `requires_admin_bypass=true`.

- [ ] **Step 3: Keep permission failure explicit**

  Document that a failed `--admin` merge is a real missing-permission blocker
  and must be recorded in the workpad.

### Task 4: Validate and Publish

**Files:**
- Test: `.codex/skills/land/land_watch.py`
- Test: `tests/unit/test_land_watch_fast_path.py`
- Test: `WORKFLOW.md`
- Test: `.codex/skills/land/SKILL.md`

- [ ] **Step 1: Run targeted unit tests**

  ```bash
  pytest tests/unit/test_land_watch_fast_path.py -v
  ```

- [ ] **Step 2: Run helper lint**

  ```bash
  ruff check .codex/skills/land/land_watch.py tests/unit/test_land_watch_fast_path.py
  ```

- [ ] **Step 3: Run Borg UI backend policy checks**

  ```bash
  ruff check app tests
  ruff format --check app tests
  ```

- [ ] **Step 4: Run diff whitespace validation**

  ```bash
  git diff --check
  ```

- [ ] **Step 5: Commit, push, and open PR**

  Use the repository `commit` and `push` skills. Fill the PR template with the
  BOR-34 behavior, validation evidence, and no placeholder comments. Attach the
  PR to Linear and add the `symphony` label.

## Self-Review

- Spec coverage: The plan covers `reviewDecision` ingestion, the narrow
  `BLOCKED + REVIEW_REQUIRED` bypass predicate, admin-bypass metadata, workflow
  command changes, targeted tests, and validation gates.
- Placeholder scan: No `TBD`, `TODO`, or vague implementation placeholders are
  present.
- Type consistency: The plan uses `review_decision`, `requires_admin_bypass`,
  and `admin_bypass_reason` consistently across test and implementation steps.
