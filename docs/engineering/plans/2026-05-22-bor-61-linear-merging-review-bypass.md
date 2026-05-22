# BOR-61 Linear Merging Review Bypass Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development to implement behavior changes test-first.

**Goal:** Let the land flow merge PRs that are blocked only because GitHub still requires review after Linear moves the issue to `Merging`.

**Architecture:** Extend the land preflight model with GitHub `reviewDecision` and explicit admin-bypass metadata. The bypass remains opt-in through the Merging land command, so ordinary preflight calls keep treating `BLOCKED` as conservative fallback.

**Tech Stack:** Python 3, pytest, ruff, GitHub CLI, Linear/Symphony workflow docs.

---

## Tasks

- [x] Reproduce the current failure signal with `evaluate_fast_path`.
- [x] Inspect PR #499 and PR #503 to evaluate the previous reverted approach.
- [x] Add a failing test for `MERGEABLE + BLOCKED + REVIEW_REQUIRED` with explicit admin bypass enabled.
- [x] Add a guard test proving the same GitHub state still blocks without the explicit bypass flag.
- [x] Extend `PrInfo`, `FastPathDecision`, `get_pr_info`, and `evaluate_fast_path`.
- [x] Add the `--allow-review-required-admin-bypass` CLI flag and JSON metadata.
- [x] Update `.codex/skills/land/SKILL.md` and `WORKFLOW.md` so Merging uses the explicit preflight flag and only then calls `gh pr merge --admin`.
- [x] Run targeted tests and lint.
- [x] Run backend policy gates.
- [ ] Commit, push, open a PR, attach it to BOR-61, and complete PR feedback sweep.

## Self-Review

- The plan covers the current root cause, the previous reverted patch, the narrower explicit gate, tests, docs, and validation.
- There are no placeholder implementation steps.
- The code-facing names are consistent: `review_decision`, `allow_review_required_admin_bypass`, `requires_admin_bypass`, and `admin_bypass_reason`.
