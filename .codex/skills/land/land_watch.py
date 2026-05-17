#!/usr/bin/env python3
import argparse
import asyncio
import json
import random
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Any

POLL_SECONDS = 10
CHECKS_APPEAR_TIMEOUT_SECONDS = 120
CODEX_BOTS = {
    "chatgpt-codex-connector[bot]",
    "github-actions[bot]",
    "codex-gc-app[bot]",
    "app/codex-gc-app",
}
MAX_GH_RETRIES = 5
BASE_GH_BACKOFF_SECONDS = 2
FAST_PATH_FALLBACK_EXIT_CODE = 6
FAST_PATH_MERGE_STATES = {"CLEAN", "HAS_HOOKS"}
HANDOFF_NOTE_RE = re.compile(
    r"Human Review handoff:\s*head=`?([0-9a-fA-F]{7,40})`?;\s*at=`?([^;`\n]+)`?",
    re.IGNORECASE,
)


@dataclass
class PrInfo:
    number: int
    url: str
    head_sha: str
    mergeable: str | None
    merge_state: str | None


@dataclass
class FastPathDecision:
    can_fast_path: bool
    reasons: list[str]


class RateLimitError(RuntimeError):
    pass


def is_rate_limit_error(error: str) -> bool:
    return "HTTP 429" in error or "rate limit" in error.lower()


async def run_gh(*args: str) -> str:
    max_delay = BASE_GH_BACKOFF_SECONDS * (2 ** (MAX_GH_RETRIES - 1))
    delay_seconds = BASE_GH_BACKOFF_SECONDS
    last_error = "gh command failed"
    for attempt in range(1, MAX_GH_RETRIES + 1):
        proc = await asyncio.create_subprocess_exec(
            "gh",
            *args,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await proc.communicate()
        if proc.returncode == 0:
            return stdout.decode()
        error = stderr.decode().strip() or "gh command failed"
        if not is_rate_limit_error(error):
            raise RuntimeError(error)
        last_error = error
        if attempt >= MAX_GH_RETRIES:
            break
        jitter = random.uniform(0, delay_seconds)
        await asyncio.sleep(min(delay_seconds + jitter, max_delay))
        delay_seconds = min(delay_seconds * 2, max_delay)
    raise RateLimitError(last_error)


async def get_pr_info() -> PrInfo:
    data = await run_gh(
        "pr",
        "view",
        "--json",
        "number,url,headRefOid,mergeable,mergeStateStatus",
    )
    parsed = json.loads(data)
    return PrInfo(
        number=parsed["number"],
        url=parsed["url"],
        head_sha=parsed["headRefOid"],
        mergeable=parsed.get("mergeable"),
        merge_state=parsed.get("mergeStateStatus"),
    )


async def get_paginated_list(endpoint: str) -> list[dict[str, Any]]:
    page = 1
    items: list[dict[str, Any]] = []
    while True:
        data = await run_gh(
            "api",
            "--method",
            "GET",
            endpoint,
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        )
        batch = json.loads(data)
        if not batch:
            break
        items.extend(batch)
        page += 1
    return items


async def get_issue_comments(pr_number: int) -> list[dict[str, Any]]:
    return await get_paginated_list(
        f"repos/{{owner}}/{{repo}}/issues/{pr_number}/comments",
    )


async def get_review_comments(pr_number: int) -> list[dict[str, Any]]:
    return await get_paginated_list(
        f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/comments",
    )


async def get_reviews(pr_number: int) -> list[dict[str, Any]]:
    page = 1
    reviews: list[dict[str, Any]] = []
    while True:
        data = await run_gh(
            "api",
            "--method",
            "GET",
            f"repos/{{owner}}/{{repo}}/pulls/{pr_number}/reviews",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        )
        batch = json.loads(data)
        if not batch:
            break
        reviews.extend(batch)
        page += 1
    return reviews


async def get_check_runs(head_sha: str) -> list[dict[str, Any]]:
    page = 1
    check_runs: list[dict[str, Any]] = []
    while True:
        data = await run_gh(
            "api",
            "--method",
            "GET",
            f"repos/{{owner}}/{{repo}}/commits/{head_sha}/check-runs",
            "-f",
            "per_page=100",
            "-f",
            f"page={page}",
        )
        payload = json.loads(data)
        batch = payload.get("check_runs", [])
        if not batch:
            break
        check_runs.extend(batch)
        total_count = payload.get("total_count")
        if total_count is not None and len(check_runs) >= total_count:
            break
        page += 1
    return check_runs


def parse_time(value: str) -> datetime:
    normalized = value.replace("Z", "+00:00")
    return datetime.fromisoformat(normalized)


def parse_handoff_note(note: str) -> tuple[str | None, datetime | None]:
    match = HANDOFF_NOTE_RE.search(note)
    if not match:
        return None, None
    return match.group(1), parse_time(match.group(2).strip())


def resolve_handoff_inputs(
    args: argparse.Namespace,
) -> tuple[str | None, datetime | None]:
    parsed_sha: str | None = None
    parsed_at: datetime | None = None
    handoff_note_file = getattr(args, "handoff_note_file", None)
    if handoff_note_file:
        with open(handoff_note_file, encoding="utf-8") as note_file:
            parsed_sha, parsed_at = parse_handoff_note(note_file.read())

    handoff_note = getattr(args, "handoff_note", None)
    if handoff_note:
        note_sha, note_at = parse_handoff_note(handoff_note)
        parsed_sha = note_sha or parsed_sha
        parsed_at = note_at or parsed_at

    human_review_sha = getattr(args, "human_review_sha", None) or parsed_sha
    human_review_at_value = getattr(args, "human_review_at", None)
    human_review_at = (
        parse_time(human_review_at_value) if human_review_at_value else parsed_at
    )
    return human_review_sha, human_review_at


CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def sanitize_terminal_output(value: str) -> str:
    return CONTROL_CHARS_RE.sub("", value)


def check_timestamp(check: dict[str, Any]) -> datetime | None:
    for key in ("completed_at", "started_at", "run_started_at", "created_at"):
        value = check.get(key)
        if value:
            return parse_time(value)
    return None


def dedupe_check_runs(check_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_name: dict[str, dict[str, Any]] = {}
    for check in check_runs:
        name = check.get("name", "unknown")
        timestamp = check_timestamp(check)
        if name not in latest_by_name:
            latest_by_name[name] = check
            continue
        existing = latest_by_name[name]
        existing_timestamp = check_timestamp(existing)
        if timestamp is None:
            continue
        if existing_timestamp is None or timestamp > existing_timestamp:
            latest_by_name[name] = check
    return list(latest_by_name.values())


def summarize_checks(check_runs: list[dict[str, Any]]) -> tuple[bool, bool, list[str]]:
    if not check_runs:
        return True, False, ["no checks reported"]
    check_runs = dedupe_check_runs(check_runs)
    pending = False
    failed = False
    failures: list[str] = []
    for check in check_runs:
        status = check.get("status")
        conclusion = check.get("conclusion")
        name = check.get("name", "unknown")
        if status != "completed":
            pending = True
            continue
        if conclusion not in ("success", "skipped", "neutral"):
            failed = True
            failures.append(f"{name}: {conclusion}")
    return pending, failed, failures


def latest_review_request_at(comments: list[dict[str, Any]]) -> datetime | None:
    latest: datetime | None = None
    for comment in comments:
        if is_codex_bot_user(comment.get("user", {})):
            continue
        body = comment.get("body") or ""
        if "@codex review" not in body:
            continue
        timestamp = comment_time(comment)
        if timestamp is None:
            continue
        if latest is None or timestamp > latest:
            latest = timestamp
    return latest


def comments_after_handoff(
    comments: list[dict[str, Any]],
    handoff_at: datetime,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for comment in comments:
        created_time = comment_time(comment)
        if created_time is not None and created_time > handoff_at:
            filtered.append(comment)
    return filtered


def reviews_after_handoff(
    reviews: list[dict[str, Any]],
    handoff_at: datetime,
) -> list[dict[str, Any]]:
    filtered: list[dict[str, Any]] = []
    for review in reviews:
        created_time = review_timestamp(review)
        if created_time is not None and created_time > handoff_at:
            filtered.append(review)
    return filtered


def filter_codex_comments(
    comments: list[dict[str, Any]],
    review_requested_at: datetime | None,
) -> list[dict[str, Any]]:
    latest_codex_reply = latest_codex_reply_by_thread(comments)
    latest_issue_ack = latest_codex_issue_reply_time(comments)
    codex_comments = [c for c in comments if is_codex_bot_user(c.get("user", {}))]
    filtered: list[dict[str, Any]] = []
    for comment in codex_comments:
        created_time = comment_time(comment)
        if created_time is None:
            continue
        if review_requested_at is not None and created_time <= review_requested_at:
            continue
        is_threaded = bool(
            comment.get("in_reply_to_id") or comment.get("pull_request_review_id")
        )
        if not is_threaded:
            if latest_issue_ack is not None and created_time <= latest_issue_ack:
                continue
        else:
            thread_root = thread_root_id(comment)
            last_reply = None
            if thread_root is not None:
                last_reply = latest_codex_reply.get(thread_root)
            if last_reply and last_reply > created_time:
                continue
        filtered.append(comment)
    return filtered


def is_codex_bot_user(user: dict[str, Any]) -> bool:
    login = user.get("login") or ""
    return login in CODEX_BOTS


def is_bot_user(user: dict[str, Any]) -> bool:
    login = user.get("login") or ""
    if is_codex_bot_user(user):
        return True
    if user.get("type") == "Bot":
        return True
    return login.endswith("[bot]")


def is_codex_reply_body(body: str) -> bool:
    return body.startswith("[codex]")


def is_codex_review_body(body: str) -> bool:
    return body.startswith("## Codex Review")


def latest_codex_issue_reply_time(
    comments: list[dict[str, Any]],
) -> datetime | None:
    latest: datetime | None = None
    for comment in comments:
        body = (comment.get("body") or "").strip()
        if not is_codex_reply_body(body):
            continue
        created_time = comment_time(comment)
        if created_time is None:
            continue
        if latest is None or created_time > latest:
            latest = created_time
    return latest


def filter_human_issue_comments(comments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_ack = latest_codex_issue_reply_time(comments)
    filtered: list[dict[str, Any]] = []
    for comment in comments:
        if is_bot_user(comment.get("user", {})):
            continue
        body = (comment.get("body") or "").strip()
        if is_codex_reply_body(body):
            continue
        if is_codex_review_body(body):
            continue
        if "@codex review" in body:
            continue
        created_time = comment_time(comment)
        if (
            latest_ack is not None
            and created_time is not None
            and created_time <= latest_ack
        ):
            continue
        filtered.append(comment)
    return filtered


def filter_codex_review_issue_comments(
    comments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_ack = latest_codex_issue_reply_time(comments)
    filtered: list[dict[str, Any]] = []
    for comment in comments:
        body = (comment.get("body") or "").strip()
        if not is_codex_review_body(body):
            continue
        created_time = comment_time(comment)
        if (
            latest_ack is not None
            and created_time is not None
            and created_time <= latest_ack
        ):
            continue
        filtered.append(comment)
    return filtered


def thread_root_id(comment: dict[str, Any]) -> int | None:
    return comment.get("in_reply_to_id") or comment.get("id")


def comment_time(comment: dict[str, Any]) -> datetime | None:
    timestamp = comment.get("updated_at") or comment.get("created_at")
    if not timestamp:
        return None
    return parse_time(timestamp)


def latest_codex_reply_by_thread(
    comments: list[dict[str, Any]],
) -> dict[int, datetime]:
    latest: dict[int, datetime] = {}
    for comment in comments:
        body = (comment.get("body") or "").strip()
        if not is_codex_reply_body(body):
            continue
        thread_root = thread_root_id(comment)
        created_time = comment_time(comment)
        if thread_root is None or created_time is None:
            continue
        existing = latest.get(thread_root)
        if existing is None or created_time > existing:
            latest[thread_root] = created_time
    return latest


def filter_human_review_comments(
    comments: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    latest_codex_reply = latest_codex_reply_by_thread(comments)
    filtered: list[dict[str, Any]] = []
    for comment in comments:
        if is_bot_user(comment.get("user", {})):
            continue
        body = (comment.get("body") or "").strip()
        if is_codex_reply_body(body):
            continue
        thread_root = thread_root_id(comment)
        created_time = comment_time(comment)
        last_codex_reply = None
        if thread_root is not None:
            last_codex_reply = latest_codex_reply.get(thread_root)
        if last_codex_reply and created_time and created_time <= last_codex_reply:
            continue
        filtered.append(comment)
    return filtered


def is_blocking_review(
    review: dict[str, Any],
    review_requested_at: datetime | None,
) -> bool:
    created_at = review.get("submitted_at") or review.get("created_at")
    if not created_at:
        return False
    user_login = review.get("user", {}).get("login")
    created_time = parse_time(created_at)
    if (
        user_login in CODEX_BOTS
        and review_requested_at is not None
        and created_time <= review_requested_at
    ):
        return False
    body = (review.get("body") or "").strip()
    state = review.get("state")
    if user_login in CODEX_BOTS:
        return state == "CHANGES_REQUESTED"
    if body.startswith("[codex]") or state in ("APPROVED", "DISMISSED"):
        return False
    blocking = False
    if body or state == "CHANGES_REQUESTED":
        blocking = True
    elif state == "COMMENTED":
        blocking = False
    elif state:
        blocking = state not in ("APPROVED", "DISMISSED")
    return blocking


def review_timestamp(review: dict[str, Any]) -> datetime | None:
    created_at = review.get("submitted_at") or review.get("created_at")
    if not created_at:
        return None
    return parse_time(created_at)


def dedupe_reviews(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    latest_by_user: dict[str, dict[str, Any]] = {}
    for review in reviews:
        user_login = review.get("user", {}).get("login")
        if not user_login:
            continue
        timestamp = review_timestamp(review)
        if user_login not in latest_by_user:
            latest_by_user[user_login] = review
            continue
        existing = latest_by_user[user_login]
        existing_timestamp = review_timestamp(existing)
        if timestamp is None:
            continue
        if existing_timestamp is None or timestamp > existing_timestamp:
            latest_by_user[user_login] = review
    return list(latest_by_user.values())


def filter_blocking_reviews(
    reviews: list[dict[str, Any]],
    review_requested_at: datetime | None,
) -> list[dict[str, Any]]:
    return [
        review
        for review in dedupe_reviews(reviews)
        if is_blocking_review(review, review_requested_at)
    ]


def collect_feedback_reasons_after_handoff(
    issue_comments: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    review_request_at: datetime | None,
    human_review_at: datetime,
) -> list[str]:
    issue_comments_after = comments_after_handoff(issue_comments, human_review_at)
    review_comments_after = comments_after_handoff(review_comments, human_review_at)
    reviews_after = reviews_after_handoff(reviews, human_review_at)

    human_issue_comments = filter_human_issue_comments(issue_comments_after)
    codex_review_comments = filter_codex_review_issue_comments(issue_comments_after)
    codex_inline_comments = filter_codex_comments(
        review_comments_after,
        review_request_at,
    )
    human_review_comments = filter_human_review_comments(review_comments_after)
    blocking_reviews = filter_blocking_reviews(reviews_after, review_request_at)

    reasons: list[str] = []
    if human_issue_comments:
        reasons.append(
            f"Human issue comments after handoff: {len(human_issue_comments)}"
        )
    if codex_review_comments:
        reasons.append(
            f"Codex review comments after handoff: {len(codex_review_comments)}"
        )
    if codex_inline_comments:
        reasons.append(
            f"Codex inline comments after handoff: {len(codex_inline_comments)}"
        )
    if human_review_comments:
        reasons.append(
            f"Human inline review comments after handoff: {len(human_review_comments)}"
        )
    if blocking_reviews:
        reasons.append(f"Blocking reviews after handoff: {len(blocking_reviews)}")
    return reasons


def evaluate_fast_path(
    *,
    pr: PrInfo,
    human_review_sha: str | None,
    human_review_at: datetime | None,
    check_runs: list[dict[str, Any]],
    issue_comments: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    review_request_at: datetime | None,
) -> FastPathDecision:
    reasons: list[str] = []

    if not human_review_sha:
        reasons.append("Missing Human Review handoff SHA")
    elif pr.head_sha != human_review_sha:
        reasons.append(
            "PR head changed since Human Review handoff "
            f"({human_review_sha} -> {pr.head_sha})"
        )

    if human_review_at is None:
        reasons.append("Missing Human Review handoff timestamp")

    if is_merge_conflicting(pr):
        reasons.append("PR has merge conflicts")
    elif pr.mergeable != "MERGEABLE":
        reasons.append(f"PR mergeability is not MERGEABLE: {pr.mergeable}")

    if pr.merge_state is None:
        reasons.append("PR merge state is unknown")
    elif pr.merge_state not in FAST_PATH_MERGE_STATES:
        reasons.append(f"PR merge state is {pr.merge_state}")

    if not check_runs:
        reasons.append("GitHub checks are missing")
    else:
        pending, failed, failures = summarize_checks(check_runs)
        if pending:
            reasons.append("GitHub checks are pending")
        if failed:
            reasons.append(
                "GitHub checks failed or inconclusive: " + ", ".join(failures)
            )

    if human_review_at is not None:
        reasons.extend(
            collect_feedback_reasons_after_handoff(
                issue_comments,
                review_comments,
                reviews,
                review_request_at,
                human_review_at,
            )
        )

    return FastPathDecision(can_fast_path=not reasons, reasons=reasons)


def is_merge_conflicting(pr: PrInfo) -> bool:
    return pr.mergeable == "CONFLICTING" or pr.merge_state == "DIRTY"


async def fetch_review_context(
    pr_number: int,
) -> tuple[
    list[dict[str, Any]],
    list[dict[str, Any]],
    list[dict[str, Any]],
    datetime | None,
]:
    issue_comments = await get_issue_comments(pr_number)
    review_request_at = latest_review_request_at(issue_comments)
    review_comments = await get_review_comments(pr_number)
    reviews = await get_reviews(pr_number)
    return issue_comments, review_comments, reviews, review_request_at


def raise_on_human_feedback(
    issue_comments: list[dict[str, Any]],
    review_comments: list[dict[str, Any]],
    reviews: list[dict[str, Any]],
    review_request_at: datetime | None,
) -> None:
    human_issue_comments = filter_human_issue_comments(issue_comments)
    codex_review_comments = filter_codex_review_issue_comments(issue_comments)
    human_review_comments = filter_human_review_comments(review_comments)
    if human_issue_comments or human_review_comments or codex_review_comments:
        print("Review comments detected. Address before merge.")
        print(
            "Reminder: decide whether feedback stays in scope; defer if needed "
            "and note in your root-level update.",
        )
        raise SystemExit(2)
    blocking_reviews = filter_blocking_reviews(reviews, review_request_at)
    if blocking_reviews:
        print("Review states/comments detected. Address before merge.")
        print(
            "Reminder: keep PR title/description aligned with the full scope "
            "when changes expand.",
        )
        raise SystemExit(2)


async def wait_for_codex(pr_number: int, checks_done: asyncio.Event) -> None:
    print("Waiting for review feedback...", flush=True)
    while True:
        (
            issue_comments,
            review_comments,
            reviews,
            review_request_at,
        ) = await fetch_review_context(pr_number)
        bot_issue_comments = filter_codex_comments(issue_comments, review_request_at)
        bot_review_comments = filter_codex_comments(review_comments, review_request_at)
        bot_comments = bot_issue_comments + bot_review_comments
        raise_on_human_feedback(
            issue_comments,
            review_comments,
            reviews,
            review_request_at,
        )
        if bot_comments:
            latest = max(
                bot_comments,
                key=lambda comment: parse_time(comment["created_at"]),
            )
            body = sanitize_terminal_output(latest.get("body") or "").strip()
            if body:
                print("Codex left comments. Address feedback before merge.")
                print(body)
                raise SystemExit(2)
        if checks_done.is_set():
            return
        await asyncio.sleep(POLL_SECONDS)


async def wait_for_checks(head_sha: str, checks_done: asyncio.Event) -> None:
    print("Waiting for CI checks...", flush=True)
    empty_seconds = 0
    while True:
        check_runs = await get_check_runs(head_sha)
        if not check_runs:
            empty_seconds += POLL_SECONDS
            if empty_seconds >= CHECKS_APPEAR_TIMEOUT_SECONDS:
                print(
                    "No checks detected after 120s; check CI configuration",
                )
                raise SystemExit(3)
            await asyncio.sleep(POLL_SECONDS)
            continue
        empty_seconds = 0
        pending, failed, failures = summarize_checks(check_runs)
        if failed:
            print("Checks failed:")
            for failure in failures:
                print(f"- {failure}")
            raise SystemExit(3)
        if not pending:
            print("Checks passed")
            checks_done.set()
            return
        await asyncio.sleep(POLL_SECONDS)


async def watch_pr() -> None:
    pr = await get_pr_info()
    if is_merge_conflicting(pr):
        print(
            "PR has merge conflicts. Resolve/rebase against main and push before "
            "running land_watch again.",
        )
        raise SystemExit(5)
    head_sha = pr.head_sha
    checks_done = asyncio.Event()
    codex_task = asyncio.create_task(wait_for_codex(pr.number, checks_done))
    checks_task = asyncio.create_task(wait_for_checks(head_sha, checks_done))

    async def head_monitor() -> None:
        while True:
            current = await get_pr_info()
            if is_merge_conflicting(current):
                print(
                    "PR has merge conflicts. Resolve/rebase against main and push "
                    "before running land_watch again.",
                )
                raise SystemExit(5)
            if current.head_sha != head_sha:
                print("PR head updated; pull/amend/force-push to retrigger CI")
                raise SystemExit(4)
            await asyncio.sleep(POLL_SECONDS)

    monitor_task = asyncio.create_task(head_monitor())
    success_task = asyncio.gather(codex_task, checks_task)

    done, pending = await asyncio.wait(
        [monitor_task, success_task],
        return_when=asyncio.FIRST_COMPLETED,
    )
    for task in pending:
        task.cancel()
    for task in done:
        exc = task.exception()
        if exc:
            raise exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Watch or preflight a PR for the Symphony landing flow.",
    )
    parser.add_argument(
        "--preflight",
        action="store_true",
        help="check whether already-green PR landing can use the fast path",
    )
    parser.add_argument(
        "--human-review-sha",
        help="PR head SHA recorded in the Human Review handoff note",
    )
    parser.add_argument(
        "--human-review-at",
        help="ISO-8601 timestamp recorded in the Human Review handoff note",
    )
    parser.add_argument(
        "--handoff-note",
        help="workpad handoff note containing Human Review handoff metadata",
    )
    parser.add_argument(
        "--handoff-note-file",
        help="path to a file containing the workpad handoff note",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        dest="json_output",
        help="print preflight output as JSON",
    )
    return parser


def print_preflight_decision(
    decision: FastPathDecision,
    *,
    json_output: bool,
) -> None:
    if json_output:
        print(
            json.dumps(
                {
                    "can_fast_path": decision.can_fast_path,
                    "reasons": decision.reasons,
                },
                indent=2,
            )
        )
        return

    if decision.can_fast_path:
        print(
            "Fast path ready: PR head unchanged, mergeable, checks green, and "
            "no new feedback since Human Review."
        )
        return

    print("Full validation required:")
    for reason in decision.reasons:
        print(f"- {reason}")


async def preflight_fast_path(args: argparse.Namespace) -> None:
    human_review_sha, human_review_at = resolve_handoff_inputs(args)
    pr = await get_pr_info()
    review_context_task = asyncio.create_task(fetch_review_context(pr.number))
    check_runs_task = asyncio.create_task(get_check_runs(pr.head_sha))
    (
        issue_comments,
        review_comments,
        reviews,
        review_request_at,
    ) = await review_context_task
    check_runs = await check_runs_task

    decision = evaluate_fast_path(
        pr=pr,
        human_review_sha=human_review_sha,
        human_review_at=human_review_at,
        check_runs=check_runs,
        issue_comments=issue_comments,
        review_comments=review_comments,
        reviews=reviews,
        review_request_at=review_request_at,
    )
    print_preflight_decision(
        decision,
        json_output=getattr(args, "json_output", False),
    )
    if not decision.can_fast_path:
        raise SystemExit(FAST_PATH_FALLBACK_EXIT_CODE)


async def main() -> None:
    args = build_parser().parse_args()
    if args.preflight:
        await preflight_fast_path(args)
        return
    await watch_pr()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except SystemExit as exc:
        raise SystemExit(exc.code) from None
