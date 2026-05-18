import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace


def load_land_watch():
    module_path = (
        Path(__file__).resolve().parents[2] / ".codex/skills/land/land_watch.py"
    )
    spec = importlib.util.spec_from_file_location("land_watch", module_path)
    module = importlib.util.module_from_spec(spec)
    sys.modules["land_watch"] = module
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


land_watch = load_land_watch()


def pr_info(
    *,
    head_sha="abc1234",
    mergeable="MERGEABLE",
    merge_state="CLEAN",
):
    return land_watch.PrInfo(
        number=22,
        url="https://github.com/example/repo/pull/22",
        head_sha=head_sha,
        mergeable=mergeable,
        merge_state=merge_state,
    )


def completed_check(*, conclusion="success", name="unit"):
    return {
        "name": name,
        "status": "completed",
        "conclusion": conclusion,
        "completed_at": "2026-05-17T10:05:00Z",
    }


def pending_check():
    return {
        "name": "unit",
        "status": "in_progress",
        "conclusion": None,
        "started_at": "2026-05-17T10:05:00Z",
    }


def issue_comment(*, body="Looks wrong", login="reviewer", created_at=None):
    timestamp = created_at or "2026-05-17T10:05:00Z"
    return {
        "id": 1,
        "body": body,
        "created_at": timestamp,
        "updated_at": timestamp,
        "user": {"login": login, "type": "User"},
    }


def review_comment(*, body="Please adjust", login="reviewer", created_at=None):
    timestamp = created_at or "2026-05-17T10:05:00Z"
    return {
        "id": 2,
        "body": body,
        "created_at": timestamp,
        "updated_at": timestamp,
        "user": {"login": login, "type": "User"},
    }


def review(*, state="CHANGES_REQUESTED", body="Please adjust", login="reviewer"):
    return {
        "id": 3,
        "state": state,
        "body": body,
        "submitted_at": "2026-05-17T10:05:00Z",
        "user": {"login": login, "type": "User"},
    }


def green_decision(**overrides):
    params = {
        "pr": pr_info(),
        "human_review_sha": "abc1234",
        "human_review_at": land_watch.parse_time("2026-05-17T10:00:00Z"),
        "check_runs": [completed_check()],
        "issue_comments": [],
        "review_comments": [],
        "reviews": [],
        "review_request_at": None,
    }
    params.update(overrides)
    return land_watch.evaluate_fast_path(**params)


def assert_requires_full_validation(decision, reason):
    assert decision.can_fast_path is False
    assert any(reason in item for item in decision.reasons)


def test_fast_path_allows_unchanged_green_pr_without_new_feedback():
    decision = green_decision()

    assert decision.can_fast_path is True
    assert decision.reasons == []


def test_fast_path_requires_full_validation_when_head_changed():
    decision = green_decision(pr=pr_info(head_sha="def5678"))

    assert_requires_full_validation(
        decision,
        "PR head changed since Human Review handoff",
    )


def test_fast_path_requires_full_validation_when_mergeability_conflicts():
    decision = green_decision(pr=pr_info(mergeable="CONFLICTING", merge_state="DIRTY"))

    assert_requires_full_validation(decision, "PR has merge conflicts")


def test_fast_path_requires_full_validation_when_mergeability_unknown():
    decision = green_decision(pr=pr_info(mergeable="UNKNOWN", merge_state="CLEAN"))

    assert_requires_full_validation(decision, "PR mergeability is not MERGEABLE")


def test_fast_path_requires_full_validation_when_merge_state_is_not_clean():
    decision = green_decision(pr=pr_info(mergeable="MERGEABLE", merge_state="BLOCKED"))

    assert_requires_full_validation(decision, "PR merge state is BLOCKED")


def test_fast_path_requires_full_validation_when_merge_state_is_missing():
    decision = green_decision(pr=pr_info(mergeable="MERGEABLE", merge_state=None))

    assert_requires_full_validation(decision, "PR merge state is unknown")


def test_fast_path_requires_full_validation_when_checks_are_missing():
    decision = green_decision(check_runs=[])

    assert_requires_full_validation(decision, "GitHub checks are missing")


def test_fast_path_requires_full_validation_when_checks_are_pending():
    decision = green_decision(check_runs=[pending_check()])

    assert_requires_full_validation(decision, "GitHub checks are pending")


def test_fast_path_requires_full_validation_when_checks_failed_or_inconclusive():
    decision = green_decision(
        check_runs=[completed_check(name="lint", conclusion="failure")]
    )

    assert_requires_full_validation(
        decision,
        "GitHub checks failed or inconclusive: lint: failure",
    )


def test_fast_path_detects_human_issue_comment_after_handoff():
    decision = green_decision(issue_comments=[issue_comment()])

    assert_requires_full_validation(
        decision,
        "Human issue comments after handoff: 1",
    )


def test_fast_path_detects_codex_review_issue_comment_after_handoff():
    decision = green_decision(
        issue_comments=[
            issue_comment(
                body="## Codex Review - Correctness\n\nPlease adjust.",
                login="github-actions[bot]",
            )
        ]
    )

    assert_requires_full_validation(
        decision,
        "Codex review comments after handoff: 1",
    )


def test_fast_path_detects_codex_inline_review_comment_after_handoff():
    decision = green_decision(
        review_comments=[
            review_comment(
                body="Potential bug in this branch.",
                login="github-actions[bot]",
            )
        ]
    )

    assert_requires_full_validation(
        decision,
        "Codex inline comments after handoff: 1",
    )


def test_fast_path_detects_human_inline_review_comment_after_handoff():
    decision = green_decision(review_comments=[review_comment()])

    assert_requires_full_validation(
        decision,
        "Human inline review comments after handoff: 1",
    )


def test_fast_path_detects_blocking_review_after_handoff():
    decision = green_decision(reviews=[review()])

    assert_requires_full_validation(decision, "Blocking reviews after handoff: 1")


def test_fast_path_ignores_feedback_before_handoff():
    decision = green_decision(
        issue_comments=[
            issue_comment(created_at="2026-05-17T09:59:59Z"),
        ],
        review_comments=[
            review_comment(created_at="2026-05-17T09:59:59Z"),
        ],
    )

    assert decision.can_fast_path is True
    assert decision.reasons == []


def test_handoff_note_parser_accepts_exact_workpad_note():
    sha, handoff_at = land_watch.parse_handoff_note(
        "Human Review handoff: head=abc1234; at=2026-05-17T10:00:00Z; "
        "validation=pytest tests/unit/test_land_watch_fast_path.py"
    )

    assert sha == "abc1234"
    assert handoff_at == land_watch.parse_time("2026-05-17T10:00:00Z")


def test_resolve_handoff_inputs_prefers_explicit_args_over_note():
    args = SimpleNamespace(
        human_review_sha="feed123",
        human_review_at="2026-05-17T11:00:00Z",
        handoff_note=(
            "Human Review handoff: head=abc1234; "
            "at=2026-05-17T10:00:00Z; validation=pytest"
        ),
        handoff_note_file=None,
    )

    sha, handoff_at = land_watch.resolve_handoff_inputs(args)

    assert sha == "feed123"
    assert handoff_at == land_watch.parse_time("2026-05-17T11:00:00Z")


def test_resolve_handoff_inputs_loads_note_file(tmp_path):
    note_file = tmp_path / "handoff.txt"
    note_file.write_text(
        "Human Review handoff: head=abc1234; "
        "at=2026-05-17T10:00:00Z; validation=pytest",
        encoding="utf-8",
    )
    args = SimpleNamespace(
        human_review_sha=None,
        human_review_at=None,
        handoff_note=None,
        handoff_note_file=str(note_file),
    )

    sha, handoff_at = land_watch.resolve_handoff_inputs(args)

    assert sha == "abc1234"
    assert handoff_at == land_watch.parse_time("2026-05-17T10:00:00Z")
