# BOR-22 Landing Fast Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Subagent execution is not used here because the active ticket instructions require an unattended single-workspace orchestration flow.

**Goal:** Add a conservative fast landing preflight for already-green PRs so `Merging` can skip repeated local validation and the full watcher loop when the Human Review handoff state is unchanged.

**Architecture:** Extend `.codex/skills/land/land_watch.py` with pure decision helpers plus a `--preflight` CLI mode. The preflight uses GitHub PR state, mergeability, check runs, and review/comment activity after the Human Review handoff to decide whether fast merge is allowed or the existing conservative local-validation/watcher path is required. `WORKFLOW.md` and `.codex/skills/land/SKILL.md` document the fast path, fallback triggers, and required Human Review handoff note format.

**Tech Stack:** Python 3 standard library (`argparse`, `asyncio`, `dataclasses`, `datetime`, `json`, `re`), pytest, Markdown workflow docs.

---

### Task 1: Add Fast Path Unit Tests

**Files:**
- Create: `tests/unit/test_land_watch_fast_path.py`
- Modify later: `.codex/skills/land/land_watch.py`

- [ ] **Step 1: Write failing tests for the decision API**

  Add a test module that imports `.codex/skills/land/land_watch.py` through `importlib.util.spec_from_file_location`, then asserts these behaviors:

  ```python
  def test_fast_path_allows_unchanged_green_pr_without_new_feedback():
      pr = land_watch.PrInfo(
          number=22,
          url="https://github.com/example/repo/pull/22",
          head_sha="abc1234",
          mergeable="MERGEABLE",
          merge_state="CLEAN",
      )
      decision = land_watch.evaluate_fast_path(
          pr=pr,
          human_review_sha="abc1234",
          human_review_at=land_watch.parse_time("2026-05-17T10:00:00Z"),
          check_runs=[
              {
                  "name": "unit",
                  "status": "completed",
                  "conclusion": "success",
                  "completed_at": "2026-05-17T10:05:00Z",
              },
          ],
          issue_comments=[],
          review_comments=[],
          reviews=[],
          review_request_at=None,
      )
      assert decision.can_fast_path is True
      assert decision.reasons == []
  ```

  Add companion tests for head SHA changes, conflict/unknown mergeability, missing/pending/failed checks, human issue comments after handoff, Codex review issue comments after handoff, human inline review comments after handoff, blocking reviews after handoff, and parsing the exact handoff note format `Human Review handoff: head=<sha>; at=<iso timestamp>`.

- [ ] **Step 2: Run the targeted test and confirm RED**

  Run:

  ```bash
  python3 -m pytest --noconftest tests/unit/test_land_watch_fast_path.py -q
  ```

  Expected result: fail because `evaluate_fast_path`, `FastPathDecision`, or `parse_handoff_note` does not exist yet.

### Task 2: Implement Pure Preflight Decision Helpers

**Files:**
- Modify: `.codex/skills/land/land_watch.py`

- [ ] **Step 1: Add decision types and constants**

  Add a dataclass:

  ```python
  @dataclass
  class FastPathDecision:
      can_fast_path: bool
      reasons: list[str]
  ```

  Add conservative merge state constants:

  ```python
  FAST_PATH_MERGE_STATES = {"CLEAN", "HAS_HOOKS"}
  HANDOFF_NOTE_RE = re.compile(
      r"Human Review handoff:\s*head=`?([0-9a-fA-F]{7,40})`?;\s*at=`?([^;`\n]+)`?",
      re.IGNORECASE,
  )
  ```

- [ ] **Step 2: Add handoff parsing and feedback filters**

  Implement:

  ```python
  def parse_handoff_note(note: str) -> tuple[str | None, datetime | None]:
      match = HANDOFF_NOTE_RE.search(note)
      if not match:
          return None, None
      return match.group(1), parse_time(match.group(2).strip())
  ```

  Add helpers that keep only comments or reviews whose `comment_time()` / `review_timestamp()` is later than the Human Review handoff timestamp.

- [ ] **Step 3: Add `evaluate_fast_path`**

  Implement a pure function that appends fallback reasons when:

  - Human Review SHA or timestamp is missing.
  - PR head SHA differs from the Human Review SHA.
  - `is_merge_conflicting(pr)` is true.
  - `pr.mergeable != "MERGEABLE"`.
  - `pr.merge_state` exists and is not in `FAST_PATH_MERGE_STATES`.
  - Check runs are missing.
  - Check runs are pending.
  - Check runs have failed/inconclusive conclusions.
  - Existing review/comment filters find human or Codex feedback after the handoff.

  Return `FastPathDecision(can_fast_path=not reasons, reasons=reasons)`.

- [ ] **Step 4: Run the targeted test and confirm GREEN**

  Run:

  ```bash
  python3 -m pytest --noconftest tests/unit/test_land_watch_fast_path.py -q
  ```

  Expected result: all tests pass.

### Task 3: Add Preflight CLI Mode

**Files:**
- Modify: `.codex/skills/land/land_watch.py`
- Update: `tests/unit/test_land_watch_fast_path.py`

- [ ] **Step 1: Add argument parsing**

  Add `argparse` support for:

  - `--preflight`
  - `--human-review-sha`
  - `--human-review-at`
  - `--handoff-note`
  - `--handoff-note-file`
  - `--json`

  `--handoff-note` and `--handoff-note-file` use `parse_handoff_note`; explicit `--human-review-sha` and `--human-review-at` override parsed values.

- [ ] **Step 2: Add async preflight command**

  Implement `preflight_fast_path(...)` that fetches PR info, check runs, issue comments, review comments, reviews, and review request time, then prints either:

  ```text
  Fast path ready: PR head unchanged, mergeable, checks green, and no new feedback since Human Review.
  ```

  or:

  ```text
  Full validation required:
  - <reason>
  ```

  Exit `0` for fast path and `6` for fallback. Keep the existing no-argument behavior as `watch_pr()`.

- [ ] **Step 3: Add focused CLI helper tests**

  Add tests for resolving explicit handoff args over parsed note values and loading a handoff note file through a temporary path.

- [ ] **Step 4: Run targeted tests**

  Run:

  ```bash
  python3 -m pytest --noconftest tests/unit/test_land_watch_fast_path.py -q
  ```

### Task 4: Update Workflow Documentation

**Files:**
- Modify: `WORKFLOW.md`
- Modify: `.codex/skills/land/SKILL.md`

- [ ] **Step 1: Update `WORKFLOW.md` Step 2 Human Review handoff**

  Require final workpad handoff notes to include:

  ```text
  Human Review handoff: head=<PR head SHA>; at=<ISO-8601 timestamp>; validation=<commands>
  ```

- [ ] **Step 2: Update `WORKFLOW.md` Step 3 Merging flow**

  Describe:

  - Read the workpad Human Review handoff note.
  - Run `python3 .codex/skills/land/land_watch.py --preflight --handoff-note '<note>'`.
  - If preflight exits `0`, skip full local validation and merge after final mergeability/feedback confirmation.
  - If preflight exits `6` or is uncertain, run the existing conservative land flow.
  - Continue using full local validation after conflicts, branch updates, failed/missing/pending checks, or new feedback.

- [ ] **Step 3: Update `.codex/skills/land/SKILL.md`**

  Document the same fast path and fallback path while keeping the existing local validation and watcher flow available for uncertain PRs.

### Task 5: Validate and Handoff

**Files:**
- Review all touched files.

- [ ] **Step 1: Run targeted tests**

  ```bash
  python3 -m pytest --noconftest tests/unit/test_land_watch_fast_path.py -q
  ```

- [ ] **Step 2: Run backend validation required by repository policy**

  ```bash
  ruff check app tests
  ruff format --check app tests
  ```

  This change does not alter app runtime code, so the targeted pytest file is the relevant pytest path unless doc/script review identifies a broader Python contract.

- [ ] **Step 3: Check formatting and prohibited config changes**

  ```bash
  git diff --check
  git diff -- WORKFLOW.md .codex/skills/land/SKILL.md .codex/skills/land/land_watch.py tests/unit/test_land_watch_fast_path.py docs/engineering/plans/2026-05-17-bor-22-landing-fast-path.md
  ```

  Confirm the diff does not change model or reasoning-effort configuration.

- [ ] **Step 4: Update Linear workpad and publish**

  Mark acceptance and validation checkboxes complete, record the latest commit SHA and Human Review handoff note, commit with the `commit` skill, push with the `push` skill, attach the PR to Linear, ensure label `symphony`, sweep PR feedback/checks, then move the issue to `Human Review`.

### Self-Review

- Spec coverage: the plan covers unchanged head SHA fast path, mergeability, new feedback checks, fallback triggers, conditional `land_watch.py` use, workflow docs, conservative fallback, and no model/reasoning-effort config changes.
- Placeholder scan: no `TBD`, `TODO`, or unspecified test commands remain.
- Type consistency: the plan consistently names `FastPathDecision.can_fast_path`, `evaluate_fast_path`, `parse_handoff_note`, and `preflight_fast_path`.
