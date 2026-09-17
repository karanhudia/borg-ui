# Space Family Phase 3: Prune Preview Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents). Use
> superpowers:test-driven-development inside every task, and `ui-ux-pro-max`
> for the UI tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not
> commit at the end of a task; the phase has one commit gate (G2) at the end,
> per section 5.4 of the spec and `.claude/instructions.md`.

**Goal:** Before a prune runs, show which archives it would delete and keep,
how much space that frees at least, and (Pro) which files no surviving
archive of the series would still hold, on a page reached from the prune
dialog and the repository card (spec 4.4).

**Architecture:** One new service module, `app/services/prune_preview.py`,
owns the pieces: the dry-run runner (the inline dry-run branch the prune
route already has, moved there so the route and the preview share it), the
verdict parser over Borg's `--list` output (joined to `archives` rows by the
64-hex archive id both Borg 1.4 and Borg 2 print), the re-measure of the
deletion candidates through the existing `fill_archive_info`, and the
lost-files walk over `archive_changes`. Two new routes in
`app/api/archive_index.py`: `POST /repositories/{id}/prune/preview` and
`GET /repositories/{id}/prune/retention-defaults`. The frontend gets a page,
`/repositories/:repositoryId/prune-preview`, that re-uses the series
heatmap through two new optional props (cell color and cell label) and the
retention fields extracted from the prune dialog.

**Tech Stack:** FastAPI, SQLAlchemy, Pydantic, pytest with the `_repo` /
`_archive` / `_pro` helpers and the `test_client` / `admin_headers`
fixtures of `tests/unit/test_api_archive_index.py`; React 19, MUI, React
Router, `react-i18next`, TanStack Query, Vitest with `renderWithProviders`,
Storybook. No new dependencies. No migration.

**Spec:** `docs/engineering/specs/2026-09-16-pro-roadmap-search-space-source-guard.md`,
sections 4.1 (the re-measure of candidates), 4.4, 4.6, 4.7, 4.8 (phase 3
row), 5, Appendix B. Mockup, screen 3:
https://claude.ai/artifact/LsvMba2GFJLzgXytxZumbP

## Model

Section 4.8 names Sonnet 5 to implement phase 3 (Fable 5.1 for the
lost-files algorithm, Task 4, if the implementer asks) and Fable 5.1 to
review it. Plans are written on Fable 5.1; this one was drafted on Fable 5.1
on 2026-09-17, so G0 passed for the plan step. The implement step must check
G0 against Sonnet 5 and record any deviation in the 5.1 Notes column.

## What the live Borg binaries print (verified 2026-09-17)

Captured with `borg-live-debug` in `borg-web-ui-dev` (Borg 1.4.5, Borg
2.0.0b24). These are the fixtures for Task 1. Both binaries print one line
per archive, and the line ends with the archive's full id in brackets, so
the join to `archives.borg_id` is by id, never by name. Borg 2 series share
a name (four archives named `daily` below) and are told apart only by id.

Borg 1.4.5, `borg prune --dry-run --list --keep-daily 2 REPO`:

```
Keeping archive (rule: daily #1):            daily-4                              Thu, 2026-09-17 15:07:55 [a4bc6debbd7f130fbdb8b637a49cf6e10ae44196e271537c76f4cc79895770d7]
Would prune:                                 daily-3                              Thu, 2026-09-17 15:07:55 [9f35416b07a424f7f0ff1624b54cf1df72e07c5efa5f10fc0a8c9f8ab31ff2ba]
Would prune:                                 daily-2                              Thu, 2026-09-17 15:07:55 [d0edfe0a5d7cd33a747f8d72cd4b2b87bfa314c3fcd3e275e8a60a9878d372d4]
Keeping archive (rule: daily[oldest] #2):    daily-1                              Thu, 2026-09-17 15:07:55 [da727048048744c9f9fa3d15fe577ef59d14bf06807e87d5f5c871199e27ee4a]
```

Borg 2.0.0b24, `borg2 -r REPO prune --dry-run --list --keep-daily 2` (no
`-a`; the repository holds series `daily` and `other`; time carries a zone):

```
Keeping archive (rule: daily #1):            other                                Thu, 2026-09-17 15:08:23 +0530 [109fa62fcc349c8da7153ca58e85985948c17f43d026e8d8171255bbab00dce3]
Keeping archive (rule: daily #1):            daily                                Thu, 2026-09-17 15:08:22 +0530 [1bb758c0b8af73ada3cab77defb30bd8579b83ec392df17420cc78cd5362328e]
Would prune:                                 daily                                Thu, 2026-09-17 15:08:22 +0530 [81ca8589c60cca651571adb13dd522cd7597633523158aa5242ebda824fc50b7]
Would prune:                                 daily                                Thu, 2026-09-17 15:08:22 +0530 [a3c732c5eb4f4c3bc474f73e98903bedfb583e8dae45077dc71035095f432e78]
Keeping archive (rule: daily[oldest] #2):    daily                                Thu, 2026-09-17 15:08:21 +0530 [7654e3b38b6f055c67b7be5080d54eb7dc888f9dc102a02a720120cb38c7f58c]
```

With `--log-json` (what all three prune paths pass: `prune_service.py`,
`v2/prune_service.py`, the agent's `repository_ops.py`) each line is
wrapped, and the Borg 1 server service stores it with a stream prefix:

```
[stderr] {"type": "log_message", "time": 1789637876.6286383, "message": "Keeping archive (rule: daily #1):            daily-4                              Thu, 2026-09-17 15:07:55 [a4bc6debbd7f130fbdb8b637a49cf6e10ae44196e271537c76f4cc79895770d7]", "levelname": "INFO", "name": "borg.output.list"}
```

Other facts from the same session, recorded so nobody re-checks them:
`--stats` with `--dry-run` prints `Ignoring --stats. It is not supported
when using --dry-run.` on Borg 1 and is rejected on Borg 2 (Appendix B
stands). Borg 2 b24 also has `prune --json` (fields `archive`, `id`,
`name`, `kept`, `keep_rule`, `kept_archive_number`, `kept_oldest`,
`deleted_archive_number`, `time`), but the agent and the two services all
run `--list --log-json` and store the text, so the text parser is the one
code path (Appendix B: "one code path"); `--json` is a possible later
refinement, not used here. Borg 1 rejects `prune --json`. The keep-rule
label with `[oldest]` (`daily[oldest] #2`) is Borg's spelling for the
oldest archive kept by a rule; it is stored verbatim in `rule`.

## Global Constraints

- No em dashes anywhere: not in code comments, not in i18n strings, not in
  documentation. Use periods, commas or parentheses.
- Every user-visible string goes through `react-i18next`, with the key added
  to all four locale files (`frontend/src/locales/{en,de,es,it}.json`); the
  pre-push `check:locales` script enforces parity.
- All work happens in the worktree `../borg-ui-space-family` on branch
  `feat/space-family-phase-3`, created from `origin/main` (7a56b806 or
  newer), never in the main checkout. The worktree is on the merged
  `feat/space-family-phase-2` branch; reset it with
  `git fetch origin && git checkout -b feat/space-family-phase-3 origin/main`.
  It needs `fnm use 20.19.4` (or 24) before `npm ci`; the default Node
  20.17.0 silently skips the `@rolldown` native binding.
- Every task adds or updates a test. The full backend unit suite
  (`pytest tests/unit -q`) and the frontend `typecheck`, `lint`, `test`,
  `check:locales` and `format:check` run before G2.
- UI changes are verified visually in Storybook, light and dark and at
  400px width, before push (repository rule).
- Plan gating (spec 4.6, Appendix B): no new feature key. The preview is
  Community; only `lost_files` is Pro under `archive_history`. Do not gate
  anything else.
- Freed space is a lower bound, summed from the candidates' fresh
  `deduplicated_size` (Appendix B). Never compute it chunk-level, never sum
  it into a claim of exactness. The UI says "at least".
- Lost files are computed per series from the history index only, and the
  UI states the cross-series limitation (Appendix B).
- The prune preview is a page, not a dialog. The dialog keeps its retention
  form and its "Preview" button opens the page (Appendix B).

---

### Task 1: Verdict parser and its fixtures

**Files:**
- Create: `app/services/prune_preview.py`
- Create: `tests/fixtures/prune_dry_run_borg1.log`
- Create: `tests/fixtures/prune_dry_run_borg2.log`
- Create: `tests/unit/test_prune_preview.py`

**Interfaces:**
- Consumes: `app.services.prune_service._log_message(line: str) -> str`
  (unwraps a `--log-json` record to its `message`).
- Produces:
  ```python
  @dataclass(frozen=True)
  class Verdict:
      borg_id: str          # 64 hex chars
      name: str
      verdict: str          # "kept" | "deleted"
      rule: Optional[str]   # "daily #1", "daily[oldest] #2", None when deleted

  def parse_prune_verdicts(output: str) -> list[Verdict]
  ```
  Lines that are not verdict lines (progress, `Ignoring --stats`, warnings)
  are skipped. A `[stdout] ` or `[stderr] ` prefix is stripped before the
  JSON unwrap. Order is Borg's order.

- [x] **Step 1: Write the fixtures**

`tests/fixtures/prune_dry_run_borg1.log` holds the four Borg 1.4.5 lines
from "What the live Borg binaries print" above, exactly as printed, plus one
leading line `Ignoring --stats. It is not supported when using --dry-run.`.
`tests/fixtures/prune_dry_run_borg2.log` holds the five Borg 2.0.0b24 lines
(the `+0530` form). Copy them byte for byte from this plan; the column
padding is part of the real output.

- [x] **Step 2: Write the failing tests**

```python
# tests/unit/test_prune_preview.py
import json
from pathlib import Path

from app.services.prune_preview import Verdict, parse_prune_verdicts

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _wrap_log_json(text: str, prefix: str = "[stderr] ") -> str:
    """The stored form: each line a --log-json record with a stream prefix,
    as app/services/prune_service.py writes its log file."""
    return "\n".join(
        prefix
        + json.dumps(
            {
                "type": "log_message",
                "time": 1789637876.6,
                "message": line,
                "levelname": "INFO",
                "name": "borg.output.list",
            }
        )
        for line in text.splitlines()
        if line
    )


class TestParsePruneVerdicts:
    def test_borg1_lines_join_by_id_and_carry_the_rule(self):
        out = parse_prune_verdicts((FIXTURES / "prune_dry_run_borg1.log").read_text())
        assert out == [
            Verdict(
                "a4bc6debbd7f130fbdb8b637a49cf6e10ae44196e271537c76f4cc79895770d7",
                "daily-4", "kept", "daily #1",
            ),
            Verdict(
                "9f35416b07a424f7f0ff1624b54cf1df72e07c5efa5f10fc0a8c9f8ab31ff2ba",
                "daily-3", "deleted", None,
            ),
            Verdict(
                "d0edfe0a5d7cd33a747f8d72cd4b2b87bfa314c3fcd3e275e8a60a9878d372d4",
                "daily-2", "deleted", None,
            ),
            Verdict(
                "da727048048744c9f9fa3d15fe577ef59d14bf06807e87d5f5c871199e27ee4a",
                "daily-1", "kept", "daily[oldest] #2",
            ),
        ]

    def test_borg2_series_share_a_name_and_are_told_apart_by_id(self):
        out = parse_prune_verdicts((FIXTURES / "prune_dry_run_borg2.log").read_text())
        assert [v.name for v in out] == ["other", "daily", "daily", "daily", "daily"]
        assert [v.verdict for v in out] == ["kept", "kept", "deleted", "deleted", "kept"]
        assert len({v.borg_id for v in out}) == 5
        assert out[0].rule == "daily #1"
        assert out[-1].rule == "daily[oldest] #2"

    def test_log_json_records_with_stream_prefix_parse_the_same(self):
        raw = (FIXTURES / "prune_dry_run_borg1.log").read_text()
        assert parse_prune_verdicts(_wrap_log_json(raw)) == parse_prune_verdicts(raw)
        assert parse_prune_verdicts(_wrap_log_json(raw, "[stdout] ")) == parse_prune_verdicts(raw)

    def test_name_with_spaces_and_brackets(self):
        line = (
            "Would prune:                                 my [odd] name   "
            "Thu, 2026-09-17 15:07:55 [" + "ab" * 32 + "]"
        )
        out = parse_prune_verdicts(line)
        assert out == [Verdict("ab" * 32, "my [odd] name", "deleted", None)]

    def test_non_verdict_lines_are_skipped(self):
        assert parse_prune_verdicts("Ignoring --stats. It is not supported when using --dry-run.\n\n") == []
        assert parse_prune_verdicts("") == []
```

- [x] **Step 3: Run the tests to verify they fail**

Run: `pytest tests/unit/test_prune_preview.py -q`
Expected: FAIL, `ModuleNotFoundError: app.services.prune_preview`.

- [x] **Step 4: Write the module**

```python
# app/services/prune_preview.py
"""Prune preview (spec 4.4): run Borg's dry run, read its verdicts, join
them to the archive index, re-measure the deletion candidates and, on Pro,
find the files no surviving archive of a series would still hold."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.services.prune_service import _log_message

# One line per archive from `prune --list`, Borg 1.4 and Borg 2 alike:
#   Keeping archive (rule: daily #1):   <name>   Thu, 2026-09-17 15:07:55 [+0530] [<id>]
#   Would prune:                        <name>   Thu, 2026-09-17 15:07:55 [+0530] [<id>]
# The name may hold spaces and brackets, so the id anchors the match at the
# end and the timestamp closes the name. Verified against both binaries on
# 2026-09-17 (plan "What the live Borg binaries print").
_VERDICT_LINE = re.compile(
    r"^(?:Keeping archive \(rule: (?P<rule>[^)]+)\)|Would prune):\s+"
    r"(?P<name>.+?)\s+"
    r"\w{3}, \d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?: [+-]\d{4})?\s+"
    r"\[(?P<id>[0-9a-f]{64})\]\s*$"
)
_STREAM_PREFIX = re.compile(r"^\[(?:stdout|stderr)\] ")


@dataclass(frozen=True)
class Verdict:
    borg_id: str
    name: str
    verdict: str  # "kept" | "deleted"
    rule: Optional[str]


def parse_prune_verdicts(output: str) -> list[Verdict]:
    """The verdict lines of a `prune --list` run, in Borg's order. Raw
    lines, `--log-json` records and the `[stderr] {...}` form the Borg 1
    service stores all parse the same."""
    verdicts: list[Verdict] = []
    for raw in (output or "").splitlines():
        line = _log_message(_STREAM_PREFIX.sub("", raw.strip(), count=1))
        m = _VERDICT_LINE.match(line.strip())
        if not m:
            continue
        rule = m.group("rule")
        verdicts.append(
            Verdict(
                borg_id=m.group("id"),
                name=m.group("name"),
                verdict="kept" if rule is not None else "deleted",
                rule=rule,
            )
        )
    return verdicts
```

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_prune_preview.py -q`
Expected: 5 passed.

---

### Task 2: Share the inline dry run, and let a dry run keep every line

**Files:**
- Modify: `app/api/repositories.py:5595-5700` (the `prune_repository` route)
- Modify: `app/services/prune_preview.py`
- Modify: `app/services/prune_service.py:198-240` (the log buffer cap)
- Test: `tests/unit/test_api_repositories.py` (existing dry-run tests must
  stay green unchanged), `tests/unit/test_prune_service.py`

**Interfaces:**
- Consumes: `start_inline_maintenance`, `fail_inline_maintenance`,
  `finish_inline_maintenance`, `MaintenanceJobFacade`, `read_job_logs`,
  `BorgRouter`, all as the route imports them today.
- Produces:
  ```python
  @dataclass(frozen=True)
  class Retention:
      keep_hourly: int = 0
      keep_daily: int = 7
      keep_weekly: int = 4
      keep_monthly: int = 6
      keep_quarterly: int = 0
      keep_yearly: int = 1
      keep_within: Optional[str] = None   # already normalised

      def as_params(self) -> dict          # the prune operation's params keys

  async def run_prune_dry_run(
      db: Session, repository: Repository, retention: Retention, *, user_id: Optional[int]
  ) -> tuple[Operation, str]
  ```
  Runs the dry run inline exactly as the route did (operation created
  `running`, closed on failure, finished with `enqueue_followups=False`),
  and returns the finished operation and its log text.

- [x] **Step 1: Write the failing test for the uncapped dry-run log**

Append to `tests/unit/test_prune_service.py`, next to the existing dry-run
test that patches `create_subprocess_exec` (around line 60; reuse its
`FakeProcess`, `LinesAsyncStream`, `_log_record` helpers and the
`testing_session_local` setup, copying the arrangement of the test above
it):

```python
@pytest.mark.asyncio
async def test_dry_run_log_keeps_every_verdict_line(testing_session_local, seeded_prune_job):
    """A dry run prints one line per archive and the preview parses all of
    them; the 1000-line cap that protects a real prune's buffer would drop
    the oldest verdicts of a large repository."""
    job_id, repo_id = seeded_prune_job
    lines = [
        _log_record(
            f"Would prune:  a{i}  Thu, 2026-09-17 15:07:55 [{i:064x}]"
        ).encode() + b"\n"
        for i in range(1200)
    ]
    process = FakeProcess(0, stdout=LinesAsyncStream([]), stderr=LinesAsyncStream(lines))
    service = PruneService()
    with (
        patch("app.services.prune_service.SessionLocal", testing_session_local),
        patch("app.services.prune_service.build_repository_borg_env", return_value=({}, None)),
        patch("app.services.prune_service.asyncio.create_subprocess_exec", new=AsyncMock(return_value=process)),
    ):
        await service.execute_prune(job_id, repo_id, 0, 7, 4, 6, 0, 1, dry_run=True)
    session = testing_session_local()
    job = session.get(Operation, job_id)
    text = Path(job.log_file_path).read_text()
    assert text.count("Would prune") == 1200
```

If the file has no `seeded_prune_job` fixture, build the job inline the way
the neighbouring dry-run test does (repository row, `Operation` row of kind
`prune`, `status="running"`), and give `FakeProcess` `stdout`/`stderr`
keyword arguments if it does not take them yet (it must expose them as
attributes, which is what `read_stream` iterates).

- [x] **Step 2: Run it to verify it fails**

Run: `pytest tests/unit/test_prune_service.py -q -k keeps_every_verdict_line`
Expected: FAIL, the count is 1000.

- [x] **Step 3: Lift the cap for dry runs**

In `app/services/prune_service.py`, inside `read_stream`:

```python
                                    # A dry run's output is one verdict line per
                                    # archive and the preview (spec 4.4) reads
                                    # every one of them; only a real prune's
                                    # chatter is capped.
                                    if not dry_run and len(log_buffer) > MAX_BUFFER_SIZE:
                                        log_buffer.pop(0)
```

- [x] **Step 4: Run it to verify it passes**

Run: `pytest tests/unit/test_prune_service.py -q`
Expected: all pass.

- [x] **Step 5: Move the dry-run branch into the service**

Add to `app/services/prune_preview.py`:

```python
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.database.models import Operation, Repository


@dataclass(frozen=True)
class Retention:
    keep_hourly: int = 0
    keep_daily: int = 7
    keep_weekly: int = 4
    keep_monthly: int = 6
    keep_quarterly: int = 0
    keep_yearly: int = 1
    keep_within: Optional[str] = None

    def as_params(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def has_rule(self) -> bool:
        """Borg refuses a prune with no keep rule at all."""
        return any(
            getattr(self, k) > 0
            for k in ("keep_hourly", "keep_daily", "keep_weekly",
                      "keep_monthly", "keep_quarterly", "keep_yearly")
        ) or bool(self.keep_within)


async def run_prune_dry_run(
    db: Session,
    repository: Repository,
    retention: Retention,
    *,
    user_id: Optional[int],
) -> tuple[Operation, str]:
    """Borg's own dry run, inline, on an operation row created `running`
    and closed here (the path the prune route has always taken). Returns
    the finished row and its log text."""
    from app.api.maintenance_jobs import MaintenanceJobFacade, read_job_logs
    from app.core.borg_router import BorgRouter
    from app.services.operations.maintenance_start import (
        fail_inline_maintenance,
        finish_inline_maintenance,
        start_inline_maintenance,
    )

    operation = start_inline_maintenance(
        db,
        repository,
        "prune",
        params={**retention.as_params(), "dry_run": True, "scheduled_prune": False},
        user_id=user_id,
    )
    prune_kwargs = (
        {"keep_within": retention.keep_within} if retention.keep_within is not None else {}
    )
    try:
        await BorgRouter(repository).prune(
            operation.id,
            retention.keep_hourly,
            retention.keep_daily,
            retention.keep_weekly,
            retention.keep_monthly,
            retention.keep_quarterly,
            retention.keep_yearly,
            True,
            **prune_kwargs,
        )
    except Exception as exc:
        # The row was created `running`; a step that raised never closed it.
        await fail_inline_maintenance(db, operation, exc)
        raise
    db.refresh(operation)
    # A dry run changed nothing, so it gets no follow-up chain.
    finish_inline_maintenance(db, operation, enqueue_followups=False)
    view = MaintenanceJobFacade(db, operation)
    log = read_job_logs(view, fallback_to_logs=True, log_save_policy="all_jobs")
    return operation, log
```

Check the exact import locations of `MaintenanceJobFacade`,
`finish_inline_maintenance` and `read_job_logs` against the top of
`app/api/repositories.py` (they are imported there today) and use the same
modules. Local imports keep `prune_preview` importable from the runner
without pulling the API package at module load.

Then in `app/api/repositories.py`, replace the `dry_run` branch of
`prune_repository` (from `prune_job = start_inline_maintenance(` down to
the `return {...}` of the dry-run result) with:

```python
        from app.services.prune_preview import Retention, run_prune_dry_run

        prune_job, stdout_output = await run_prune_dry_run(
            db,
            repository,
            Retention(
                keep_hourly=keep_hourly,
                keep_daily=keep_daily,
                keep_weekly=keep_weekly,
                keep_monthly=keep_monthly,
                keep_quarterly=keep_quarterly,
                keep_yearly=keep_yearly,
                keep_within=keep_within,
            ),
            user_id=current_user.id,
        )
        logger.info(
            "Prune dry run finished",
            job_id=prune_job.id,
            repository_id=repo_id,
            user=current_user.username,
        )
        return {
            "job_id": prune_job.id,
            "status": prune_job.status,
            "dry_run": True,
            "prune_result": {
                "success": prune_job.status == "completed",
                "stdout": stdout_output,
                "stderr": prune_job.error_message or "",
            },
        }
```

Keep the response shape identical (`PruneRepositoryDialog` and
`Repositories.test.tsx` read `prune_result.stdout`). Remove imports the
route no longer uses only if nothing else in the file uses them.

- [x] **Step 6: Run the existing route tests**

Run: `pytest tests/unit/test_api_repositories.py -q -k "prune"`
Expected: all pass, including
`test_prune_dry_run_closes_its_operation_when_the_router_raises` and
`test_prune_dry_run_on_an_agent_repository_records_the_refusal` (they patch
`BorgRouter.prune` on the class, which the moved code still calls).

---

### Task 3: Join, re-measure, freed space

**Files:**
- Modify: `app/services/prune_preview.py`
- Test: `tests/unit/test_prune_preview.py`

**Interfaces:**
- Consumes: `Verdict`, `parse_prune_verdicts` (Task 1);
  `app.services.operations.executors.index.fill_archive_info(db, repository,
  archives, env, *, limit) -> int` (re-measures, commits, sets
  `stats_measured_at`); `_prepare_repository_borg_env(repository, db) ->
  (env, temp_key_file)` from the same module and
  `app.utils.borg_env.cleanup_temp_key_file`;
  `app.services.operations.repository_status.storage_summaries(db, [repo],
  archives=False)[repo.id].size_bytes`;
  `app.services.operations.repository_status.pending_removed_ids`.
- Produces:
  ```python
  MEASURE_CAP = 50

  @dataclass
  class PreviewArchive:
      id: Optional[int]          # None when the index has no row for the id
      borg_id: str
      name: str
      series: Optional[str]
      start: Optional[datetime]
      verdict: str
      rule: Optional[str]
      deduplicated_size: Optional[int]
      stats_measured_at: Optional[datetime]

  def join_verdicts(db, repository, verdicts) -> list[PreviewArchive]
  async def remeasure_candidates(db, repository, candidates: list[Archive]) -> bool   # True when partial
  def freed_at_least(candidates: list[Archive]) -> int
  def footprint(db, repository) -> Optional[int]
  ```

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_prune_preview.py` (import `_repo`, `_archive`
from `tests.unit.test_api_archive_index`, and `Archive`, `Repository`,
`RepositoryStorage` from `app.database.models` as needed):

```python
from datetime import datetime
from unittest.mock import AsyncMock, patch

import pytest

from app.database.models import Archive
from app.services import prune_preview
from app.services.prune_preview import (
    MEASURE_CAP,
    freed_at_least,
    join_verdicts,
    remeasure_candidates,
)
from tests.unit.test_api_archive_index import _archive, _repo

HEX = lambda n: f"{n:064x}"  # noqa: E731


def _verdicts(*specs):
    return [Verdict(HEX(n), name, verdict, rule) for n, name, verdict, rule in specs]


class TestJoinVerdicts:
    def test_joins_rows_by_borg_id_in_borg_order(self, test_db):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "daily-1", 1)
        a.borg_id = HEX(1)
        b = _archive(test_db, repo, "daily-2", 2)
        b.borg_id = HEX(2)
        test_db.commit()
        out = join_verdicts(
            test_db, repo, _verdicts((2, "daily-2", "kept", "daily #1"), (1, "daily-1", "deleted", None))
        )
        assert [(p.id, p.verdict, p.rule) for p in out] == [(b.id, "kept", "daily #1"), (a.id, "deleted", None)]
        assert out[1].series == "nas" and out[1].deduplicated_size == 100

    def test_unknown_id_keeps_the_line_without_a_row(self, test_db):
        repo = _repo(test_db)
        out = join_verdicts(test_db, repo, _verdicts((9, "ghost", "deleted", None)))
        assert out[0].id is None and out[0].deduplicated_size is None and out[0].name == "ghost"

    def test_a_row_the_last_listing_reported_removed_is_not_joined(self, test_db, monkeypatch):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "gone", 1)
        a.borg_id = HEX(1)
        test_db.commit()
        monkeypatch.setattr(prune_preview, "pending_removed_ids", lambda db, rid: {a.id})
        out = join_verdicts(test_db, repo, _verdicts((1, "gone", "deleted", None)))
        assert out[0].id is None


class TestFreedAtLeast:
    def test_sums_measured_candidates_and_skips_unmeasured(self, test_db):
        repo = _repo(test_db)
        a = _archive(test_db, repo, "a", 1, size=100)
        b = _archive(test_db, repo, "b", 2, size=250)
        c = _archive(test_db, repo, "c", 3)
        c.deduplicated_size = None
        test_db.commit()
        assert freed_at_least([a, b, c]) == 350


class TestRemeasureCandidates:
    @pytest.mark.asyncio
    async def test_measures_up_to_the_cap_and_reports_partial(self, test_db):
        repo = _repo(test_db)
        rows = [_archive(test_db, repo, f"a{i}", 1 + i % 28) for i in range(MEASURE_CAP + 1)]
        with (
            patch.object(prune_preview, "_prepare_repository_borg_env", return_value=({}, None)),
            patch.object(prune_preview, "fill_archive_info", new=AsyncMock(return_value=MEASURE_CAP)) as fill,
        ):
            partial = await remeasure_candidates(test_db, repo, rows)
        assert partial is True
        assert fill.await_args.kwargs["limit"] == MEASURE_CAP
        assert len(fill.await_args.args[2]) == MEASURE_CAP + 1

    @pytest.mark.asyncio
    async def test_not_partial_within_the_cap(self, test_db):
        repo = _repo(test_db)
        rows = [_archive(test_db, repo, "a", 1)]
        with (
            patch.object(prune_preview, "_prepare_repository_borg_env", return_value=({}, None)),
            patch.object(prune_preview, "fill_archive_info", new=AsyncMock(return_value=1)),
        ):
            assert await remeasure_candidates(test_db, repo, rows) is False
```

- [x] **Step 2: Run them to verify they fail**

Run: `pytest tests/unit/test_prune_preview.py -q`
Expected: FAIL on import of `join_verdicts`.

- [x] **Step 3: Implement**

Append to `app/services/prune_preview.py`:

```python
from datetime import datetime

from app.database.models import Archive
from app.services.operations.executors.index import (
    _prepare_repository_borg_env,
    fill_archive_info,
)
from app.services.operations.repository_status import (
    pending_removed_ids,
    storage_summaries,
)
from app.utils.borg_env import cleanup_temp_key_file

# Candidates re-measured synchronously before the preview answers (spec
# 4.4 step 3). Beyond it the stored values stand and `partial_measure` is
# reported.
MEASURE_CAP = 50


@dataclass
class PreviewArchive:
    id: Optional[int]
    borg_id: str
    name: str
    series: Optional[str]
    start: Optional[datetime]
    verdict: str
    rule: Optional[str]
    deduplicated_size: Optional[int]
    stats_measured_at: Optional[datetime]


def join_verdicts(
    db: Session, repository: Repository, verdicts: list[Verdict]
) -> list[PreviewArchive]:
    """Each verdict line joined to its `archives` row by Borg id (Borg 2
    series share a name). A line whose id the index does not hold, or whose
    row the newest listing reported removed, keeps Borg's name and verdict
    with no row behind it."""
    ids = [v.borg_id for v in verdicts]
    rows: dict[str, Archive] = {}
    removed = pending_removed_ids(db, repository.id)
    for i in range(0, len(ids), 500):
        for row in (
            db.query(Archive)
            .filter(Archive.repository_id == repository.id, Archive.borg_id.in_(ids[i : i + 500]))
            .all()
        ):
            if row.id not in removed:
                rows[row.borg_id] = row
    out: list[PreviewArchive] = []
    for v in verdicts:
        row = rows.get(v.borg_id)
        out.append(
            PreviewArchive(
                id=row.id if row else None,
                borg_id=v.borg_id,
                name=row.name if row else v.name,
                series=row.series if row else None,
                start=row.start if row else None,
                verdict=v.verdict,
                rule=v.rule,
                deduplicated_size=row.deduplicated_size if row else None,
                stats_measured_at=row.stats_measured_at if row else None,
            )
        )
    return out


async def remeasure_candidates(
    db: Session, repository: Repository, candidates: list[Archive]
) -> bool:
    """Fresh `deduplicated_size` for the deletion candidates, oldest first,
    up to MEASURE_CAP (spec 4.1: the preview re-measures synchronously).
    Returns True when the cap left some candidates on their stored value.
    `fill_archive_info` commits and stamps `stats_measured_at` itself."""
    if not candidates:
        return False
    env, temp_key_file = _prepare_repository_borg_env(repository, db)
    try:
        await fill_archive_info(db, repository, candidates, env, limit=MEASURE_CAP)
    finally:
        cleanup_temp_key_file(temp_key_file)
    return len(candidates) > MEASURE_CAP


def freed_at_least(candidates: list[Archive]) -> int:
    """Lower bound: chunks shared only among the candidates are in nobody's
    deduplicated_size (Appendix B)."""
    return sum(a.deduplicated_size for a in candidates if a.deduplicated_size is not None)


def footprint(db: Session, repository: Repository) -> Optional[int]:
    """The repository's stored size (the `storage` payload of #1030)."""
    summary = storage_summaries(db, [repository], archives=False).get(repository.id)
    return summary.size_bytes if summary else None
```

Check `cleanup_temp_key_file`'s signature in `app/utils/borg_env.py` (it
may take the path only, or accept None) and match it. `_prepare_repository_borg_env`
is private to the index executor; importing it is the same reuse the phase
1 code made, and it stays the one place a Borg env for the index is built.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_prune_preview.py -q`
Expected: all pass.

---

### Task 4: Files lost forever (Pro)

**Files:**
- Modify: `app/services/prune_preview.py`
- Test: `tests/unit/test_prune_preview.py`

The implementer may ask for Fable 5.1 for this task (spec 4.8).

**Interfaces:**
- Consumes: `Archive`, `ArchiveChange` rows; `SIZE_LOOKUP_CHUNK` from
  `app.services.operations.executors.history`.
- Produces:
  ```python
  TOP_LOST = 200
  TOP_FOLDERS = 20

  def lost_files(
      db, repository, archives_by_series: dict[str, list[Archive]], deleted_ids: set[int]
  ) -> dict
  # {
  #   "incomplete": bool, "unindexed_archive_ids": [int],
  #   "total_count": int, "total_size": int,
  #   "top": [{"path", "size", "series", "last_held_archive_id", "last_held_archive_name"}],
  #   "by_folder": [{"folder", "count", "size"}],
  # }
  ```
  `archives_by_series` holds every archive of the repository the index has
  (not only the ones Borg listed), ordered by `(start, id)` per series.

**The rule (spec 4.4 step 5) and one refinement.** A path is lost when at
every surviving archive of its series, its last change at or before that
archive is `removed` or absent. The spec takes the candidates to be paths
with a `removed` row somewhere in the series, on the ground that a path
never removed is present at the newest archive, which Borg always keeps.
That holds per repository, not per series: Borg 1 prunes the repository as
one set, so an older series (a plan that stopped) can lose every archive to
a newer series' keeps. Refinement: when the newest archive of a series is
itself deleted, every path with any row in the series is a candidate, and
the same evaluator decides. The evaluator is a single ordered walk over the
series' rows, and it only ever holds the candidates in memory:

1. Candidates: `SELECT DISTINCT path` of `removed` rows in the series
   (spec case), or of all non-summary rows (refinement case).
2. Walk the rows of the series ordered by `(Archive.start, Archive.id)`,
   grouped per archive, applying `added`/`modified` as present (with
   `size_after`) and `removed` as absent (remember `size_before` and the
   removing archive). `summary` rows are skipped: they stand for rows the
   per-archive cap dropped, and are what `incomplete` covers.
3. After the rows of a *surviving* archive are applied, any candidate whose
   state is present is saved (dropped from the candidate map). Only paths
   touched since the last survivor sweep can have changed, so the sweep
   checks the dirty set, not the map (the first survivor sweeps everything).
4. What remains is lost. Its size is the `size_before` of its latest
   removing row (None counts 0 in totals); "last held by" is the archive
   before the removing one in series order.

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_prune_preview.py`:

```python
from app.database.models import ArchiveChange
from app.services.prune_preview import lost_files


def _change(test_db, archive, path, change, size_before=None, size_after=None):
    test_db.add(
        ArchiveChange(
            archive_id=archive.id, path=path, change=change,
            size_before=size_before, size_after=size_after,
        )
    )
    test_db.commit()


def _series(test_db, repo, *names_days, series="nas"):
    rows = [_archive(test_db, repo, n, d, series=series) for n, d in names_days]
    return {series: rows}


class TestLostFiles:
    def test_path_removed_before_every_survivor_is_lost(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        _change(test_db, a1, "docs/x.txt", "added", size_after=10)
        _change(test_db, a2, "docs/x.txt", "removed", size_before=10)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id})
        assert out["total_count"] == 1 and out["total_size"] == 10
        assert out["top"][0]["path"] == "docs/x.txt"
        assert out["top"][0]["last_held_archive_id"] == a1.id
        assert out["top"][0]["last_held_archive_name"] == "a1"
        assert out["by_folder"] == [{"folder": "docs", "count": 1, "size": 10}]
        assert out["incomplete"] is False and out["unindexed_archive_ids"] == []

    def test_path_still_present_at_a_survivor_is_not_lost(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        _change(test_db, a1, "docs/x.txt", "added", size_after=10)
        _change(test_db, a3, "docs/x.txt", "removed", size_before=10)
        # a2 survives and still holds the path (no row: state carries over)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a3.id})
        assert out["total_count"] == 0

    def test_re_added_then_removed_again_uses_the_latest_removal(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3), ("a4", 4))
        a1, a2, a3, a4 = by["nas"]
        _change(test_db, a1, "p", "added", size_after=1)
        _change(test_db, a2, "p", "removed", size_before=1)
        _change(test_db, a3, "p", "added", size_after=5)
        _change(test_db, a4, "p", "removed", size_before=5)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id, a3.id})
        assert out["total_size"] == 5
        assert out["top"][0]["last_held_archive_id"] == a3.id

    def test_never_removed_path_is_lost_when_the_whole_series_goes(self, test_db):
        """Borg 1 prunes the repository as one set: an old series can lose
        every archive to a newer series' keeps."""
        repo = _repo(test_db)
        by = _series(test_db, repo, ("old-1", 1), ("old-2", 2), series="old")
        o1, o2 = by["old"]
        _change(test_db, o1, "keep/me", "added", size_after=7)
        out = lost_files(test_db, repo, by, deleted_ids={o1.id, o2.id})
        assert out["total_count"] == 1 and out["top"][0]["last_held_archive_id"] == o2.id

    def test_series_are_independent(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), ("n2", 2), series="nas"))
        by.update(_series(test_db, repo, ("d1", 1), ("d2", 2), series="docs"))
        n1, n2 = by["nas"]
        d1, d2 = by["docs"]
        _change(test_db, n1, "shared", "added", size_after=3)
        _change(test_db, n2, "shared", "removed", size_before=3)
        _change(test_db, d1, "shared", "added", size_after=3)
        # docs still holds "shared" in d2; the nas copy is lost anyway (cross-series not checked)
        out = lost_files(test_db, repo, by, deleted_ids={n1.id})
        assert out["total_count"] == 1 and out["top"][0]["series"] == "nas"

    def test_unindexed_archive_of_a_touched_series_marks_incomplete(self, test_db):
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2))
        a1, a2 = by["nas"]
        a2.history_state = "pending"
        test_db.commit()
        out = lost_files(test_db, repo, by, deleted_ids={a1.id})
        assert out["incomplete"] is True and out["unindexed_archive_ids"] == [a2.id]

    def test_untouched_series_is_not_walked(self, test_db):
        repo = _repo(test_db)
        by = {}
        by.update(_series(test_db, repo, ("n1", 1), ("n2", 2), series="nas"))
        by.update(_series(test_db, repo, ("d1", 1), series="docs"))
        d1 = by["docs"][0]
        d1.history_state = "pending"
        test_db.commit()
        out = lost_files(test_db, repo, by, deleted_ids={by["nas"][0].id})
        assert out["incomplete"] is False

    def test_top_is_largest_first_and_capped(self, test_db, monkeypatch):
        monkeypatch.setattr(prune_preview, "TOP_LOST", 2)
        repo = _repo(test_db)
        by = _series(test_db, repo, ("a1", 1), ("a2", 2), ("a3", 3))
        a1, a2, a3 = by["nas"]
        for i, size in enumerate((5, 50, 500)):
            _change(test_db, a1, f"f{i}", "added", size_after=size)
            _change(test_db, a2, f"f{i}", "removed", size_before=size)
        out = lost_files(test_db, repo, by, deleted_ids={a1.id, a2.id})
        assert out["total_count"] == 3 and [t["size"] for t in out["top"]] == [500, 50]
```

- [x] **Step 2: Run them to verify they fail**

Run: `pytest tests/unit/test_prune_preview.py -q -k TestLostFiles`
Expected: FAIL on import of `lost_files`.

- [x] **Step 3: Implement**

Append to `app/services/prune_preview.py`:

```python
from collections import defaultdict

from sqlalchemy import distinct

from app.database.models import ArchiveChange

TOP_LOST = 200
TOP_FOLDERS = 20
_FOLDER_DEPTH = 3


def _folder_of(path: str) -> str:
    """The rollup key: the parent directory, at most _FOLDER_DEPTH deep.
    Borg paths have no leading slash."""
    parts = path.split("/")[:-1]
    return "/".join(parts[:_FOLDER_DEPTH]) or "/"


def _candidate_paths(db: Session, ids: list[int], removed_only: bool) -> set[str]:
    paths: set[str] = set()
    for i in range(0, len(ids), SIZE_LOOKUP_CHUNK):
        q = db.query(distinct(ArchiveChange.path)).filter(
            ArchiveChange.archive_id.in_(ids[i : i + SIZE_LOOKUP_CHUNK])
        )
        q = q.filter(
            ArchiveChange.change == "removed"
            if removed_only
            else ArchiveChange.change != "summary"
        )
        paths.update(p for (p,) in q.all())
    return paths


def _lost_in_series(
    db: Session, archives: list[Archive], deleted_ids: set[int]
) -> list[dict]:
    """The walk described in the phase 3 plan, Task 4. `archives` are the
    series' rows ordered by (start, id)."""
    ids = [a.id for a in archives]
    newest_deleted = archives[-1].id in deleted_ids
    candidates = _candidate_paths(db, ids, removed_only=not newest_deleted)
    if not candidates:
        return []
    # ponytail: the candidate map is bounded by the paths ever removed in
    # the series (or every path, when the whole series goes). If that ever
    # fails on memory, page the candidates and repeat the walk per page.
    # state: path -> (present, size, last_present_archive, removing_archive)
    state: dict[str, tuple[bool, Optional[int], Optional[Archive], Optional[Archive]]] = {}
    dirty: set[str] = set()
    first_sweep = True
    previous: Optional[Archive] = None
    for archive in archives:
        rows = (
            db.query(ArchiveChange.path, ArchiveChange.change,
                     ArchiveChange.size_before, ArchiveChange.size_after)
            .filter(ArchiveChange.archive_id == archive.id,
                    ArchiveChange.change != "summary")
            .yield_per(1000)
        )
        for path, change, size_before, size_after in rows:
            if path not in candidates:
                continue
            dirty.add(path)
            if change == "removed":
                # "Last held by": the archive before the removing one in
                # series order (state carries across archives without rows).
                state[path] = (False, size_before, previous, archive)
            else:
                state[path] = (True, size_after, archive, None)
        if archive.id not in deleted_ids:
            for path in (candidates if first_sweep else dirty):
                present = state.get(path, (False,))[0]
                if present:
                    candidates.discard(path)
                    state.pop(path, None)
            first_sweep = False
            dirty.clear()
        previous = archive
    lost = []
    for path in candidates:
        present, size, held, _ = state.get(path, (False, None, None, None))
        if present:
            # Only reachable when no archive of the series survives: a path
            # still present at the end was held by every archive since it
            # was written, so the newest one is the honest "last held by".
            held = archives[-1]
        lost.append({"path": path, "size": size, "held": held})
    return lost


def lost_files(
    db: Session,
    repository: Repository,
    archives_by_series: dict[str, list[Archive]],
    deleted_ids: set[int],
) -> dict:
    """Spec 4.4 step 5, per series, from the history index only."""
    unindexed: list[int] = []
    found: list[dict] = []
    for series, archives in archives_by_series.items():
        if not any(a.id in deleted_ids for a in archives):
            continue
        unindexed.extend(a.id for a in archives if a.history_state != "indexed")
        for item in _lost_in_series(db, archives, deleted_ids):
            held = item["held"]
            found.append(
                {
                    "path": item["path"],
                    "size": item["size"],
                    "series": series,
                    "last_held_archive_id": held.id if held else None,
                    "last_held_archive_name": held.name if held else None,
                }
            )
    found.sort(key=lambda f: (-(f["size"] or 0), f["path"]))
    folders: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for f in found:
        entry = folders[_folder_of(f["path"])]
        entry[0] += 1
        entry[1] += f["size"] or 0
    by_folder = sorted(
        ({"folder": k, "count": v[0], "size": v[1]} for k, v in folders.items()),
        key=lambda x: (-x["size"], x["folder"]),
    )[:TOP_FOLDERS]
    return {
        "incomplete": bool(unindexed),
        "unindexed_archive_ids": sorted(unindexed),
        "total_count": len(found),
        "total_size": sum(f["size"] or 0 for f in found),
        "top": found[:TOP_LOST],
        "by_folder": by_folder,
    }
```

Note on the whole-series case: with no survivor the sweep never runs, so
every candidate is still in the map, and a path still present at the end
is lost with the series' newest archive as "last held by" (the test
`test_never_removed_path_is_lost_when_the_whole_series_goes` expects
`o2`). Make the tests in Step 1 pass exactly.

- [x] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_prune_preview.py -q`
Expected: all pass.

---

### Task 5: The two routes

**Files:**
- Modify: `app/api/archive_index.py` (new routes after `archives_growth`,
  before `_archive_or_404`, so `prune` never reaches the `{archive_id}`
  route)
- Modify: `app/services/prune_preview.py` (one assembler function)
- Test: `tests/unit/test_api_archive_index.py` (new classes
  `TestPrunePreview`, `TestPruneRetentionDefaults`)

**Interfaces:**
- Consumes: everything from Tasks 1 to 4; `history_enabled(db)`,
  `history_capability(db, repository)`, `HISTORY_AVAILABLE`;
  `_normalize_prune_keep_within` from `app.api.repositories`; `_plans_for`
  from `app.services.operations.series`; `Operation`.
- Produces:
  - `POST /api/repositories/{repo_id}/prune/preview`, body
    `{keep_hourly, keep_daily, keep_weekly, keep_monthly, keep_quarterly,
    keep_yearly, keep_within}` (ints ≥ 0, `keep_within` optional string),
    role `operator`, response:
    ```json
    {
      "operation_id": 12,
      "archives": [{"id": 1, "borg_id": "…", "name": "a1", "series": "nas",
                    "start": "2026-09-01T02:00:00", "verdict": "deleted",
                    "rule": null, "deduplicated_size": 100,
                    "stats_measured_at": "2026-09-17T09:00:00", "stale": false}],
      "deleted_count": 1, "kept_count": 2,
      "freed_at_least": 100, "partial_measure": false,
      "footprint_before": 1000, "footprint_after_at_most": 900,
      "lost_files": {"available": true, "capability": "available",
                     "incomplete": false, "unindexed_archive_ids": [],
                     "total_count": 0, "total_size": 0, "top": [], "by_folder": []},
      "log": "…"
    }
    ```
    `lost_files.available` is false with `capability` set to the
    `history_capability` value (`plan_locked`, `agent_unsupported`, …) and
    the counts absent when the walk did not run. 400 with key
    `backend.errors.prune.noKeepRule` when no keep rule is set. 502 with
    key `backend.errors.prune.dryRunFailed` when the dry-run operation did
    not complete (the log is still returned under `log`).
  - `GET /api/repositories/{repo_id}/prune/retention-defaults`, role
    `viewer`, response `{"source": "plan"|"last_prune"|"default",
    "plan_name": str|null, "keep_hourly", …, "keep_within"}`: the first
    enabled plan linked to the repository with `run_prune_after` (by name),
    else the params of the newest manual `prune` operation that was not a
    dry run, else the dialog defaults (0, 7, 4, 6, 0, 1, null).

- [x] **Step 1: Write the failing tests**

Append to `tests/unit/test_api_archive_index.py`:

```python
from unittest.mock import AsyncMock, patch

from app.services import prune_preview as pp
from app.services.prune_preview import Verdict


def _hex(n):
    return f"{n:064x}"


def _fake_dry_run(status="completed", log="borg said"):
    async def run(db, repository, retention, *, user_id):
        op = Operation(kind="prune", repository_id=repository.id, status=status,
                       trigger="manual", params={**retention.as_params(), "dry_run": True})
        db.add(op)
        db.commit()
        return op, log
    return run


class TestPrunePreview:
    def _setup(self, test_db):
        repo = _repo(test_db)
        a1 = _archive(test_db, repo, "a1", 1, size=100)
        a2 = _archive(test_db, repo, "a2", 2, size=200)
        a3 = _archive(test_db, repo, "a3", 3, size=300)
        for n, a in enumerate((a1, a2, a3), start=1):
            a.borg_id = _hex(n)
        test_db.commit()
        verdicts = [Verdict(_hex(3), "a3", "kept", "daily #1"),
                    Verdict(_hex(2), "a2", "deleted", None),
                    Verdict(_hex(1), "a1", "deleted", None)]
        return repo, (a1, a2, a3), verdicts

    def test_preview_joins_measures_and_sums(self, test_client, test_db, admin_headers):
        repo, (a1, a2, a3), verdicts = self._setup(test_db)
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run()),
            patch.object(pp, "parse_prune_verdicts", return_value=verdicts),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)) as remeasure,
            patch.object(pp, "footprint", return_value=1000),
        ):
            r = test_client.post(f"/api/repositories/{repo.id}/prune/preview",
                                 json={"keep_daily": 1}, headers=admin_headers)
        assert r.status_code == 200, r.text
        body = r.json()
        assert [(a["name"], a["verdict"]) for a in body["archives"]] == [("a1", "deleted"), ("a2", "deleted"), ("a3", "kept")]
        assert body["deleted_count"] == 2 and body["kept_count"] == 1
        assert body["freed_at_least"] == 300
        assert body["footprint_before"] == 1000 and body["footprint_after_at_most"] == 700
        assert body["partial_measure"] is False and body["log"] == "borg said"
        assert {a.id for a in remeasure.await_args.args[2]} == {a1.id, a2.id}
        assert body["lost_files"] == {"available": False, "capability": "plan_locked"}

    def test_preview_on_pro_walks_lost_files(self, test_client, test_db, admin_headers):
        _pro(test_db)
        repo, (a1, a2, a3), verdicts = self._setup(test_db)
        with (
            patch.object(pp, "run_prune_dry_run", new=_fake_dry_run()),
            patch.object(pp, "parse_prune_verdicts", return_value=verdicts),
            patch.object(pp, "remeasure_candidates", new=AsyncMock(return_value=False)),
            patch.object(pp, "lost_files", return_value={"incomplete": False, "unindexed_archive_ids": [],
                                                         "total_count": 0, "total_size": 0, "top": [], "by_folder": []}) as lost,
        ):
            r = test_client.post(f"/api/repositories/{repo.id}/prune/preview",
                                 json={"keep_daily": 1}, headers=admin_headers)
        assert r.status_code == 200
        assert r.json()["lost_files"]["available"] is True
        assert lost.call_args.kwargs["deleted_ids"] == {a1.id, a2.id}
        assert list(lost.call_args.args[2]) == ["nas"]

    def test_no_keep_rule_is_400(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.post(f"/api/repositories/{repo.id}/prune/preview",
                             json={"keep_daily": 0}, headers=admin_headers)
        assert r.status_code == 400
        assert r.json()["detail"]["key"] == "backend.errors.prune.noKeepRule"

    def test_failed_dry_run_is_502_with_the_log(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        with patch.object(pp, "run_prune_dry_run", new=_fake_dry_run(status="failed", log="boom")):
            r = test_client.post(f"/api/repositories/{repo.id}/prune/preview",
                                 json={"keep_daily": 1}, headers=admin_headers)
        assert r.status_code == 502
        assert r.json()["detail"]["key"] == "backend.errors.prune.dryRunFailed"
        assert r.json()["detail"]["params"]["log"] == "boom"

    def test_viewer_cannot_preview(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        r = test_client.post(f"/api/repositories/{repo.id}/prune/preview",
                             json={"keep_daily": 1}, headers=auth_headers)
        assert r.status_code == 403


class TestPruneRetentionDefaults:
    def test_defaults_without_plan_or_prune(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        r = test_client.get(f"/api/repositories/{repo.id}/prune/retention-defaults", headers=admin_headers)
        assert r.status_code == 200
        assert r.json() == {"source": "default", "plan_name": None, "keep_hourly": 0, "keep_daily": 7,
                            "keep_weekly": 4, "keep_monthly": 6, "keep_quarterly": 0, "keep_yearly": 1,
                            "keep_within": None}

    def test_last_manual_prune_wins_over_defaults(self, test_client, test_db, admin_headers):
        repo = _repo(test_db)
        _op(test_db, repo, "prune", params={"keep_daily": 3, "keep_within": "2d", "dry_run": True})
        _op(test_db, repo, "prune", params={"keep_daily": 9, "keep_weekly": 2})
        r = test_client.get(f"/api/repositories/{repo.id}/prune/retention-defaults", headers=admin_headers)
        body = r.json()
        assert body["source"] == "last_prune" and body["keep_daily"] == 9 and body["keep_weekly"] == 2

    def test_plan_wins_over_last_prune(self, test_client, test_db, admin_headers):
        from app.database.models import BackupPlan, BackupPlanRepository
        repo = _repo(test_db)
        _op(test_db, repo, "prune", params={"keep_daily": 9})
        plan = BackupPlan(name="Nightly", run_prune_after=True, enabled=True, prune_keep_daily=14,
                          prune_keep_within="1d")
        test_db.add(plan)
        test_db.flush()
        test_db.add(BackupPlanRepository(backup_plan_id=plan.id, repository_id=repo.id, enabled=True))
        test_db.commit()
        r = test_client.get(f"/api/repositories/{repo.id}/prune/retention-defaults", headers=admin_headers)
        body = r.json()
        assert body["source"] == "plan" and body["plan_name"] == "Nightly"
        assert body["keep_daily"] == 14 and body["keep_within"] == "1d"
```

Check the `_op` helper's signature in the file (it takes `params`) and the
required columns of `BackupPlan` / `BackupPlanRepository` (fill any
NOT NULL column the constructor needs, as other tests in `tests/unit` that
create plans do; grep `BackupPlan(` there).

- [x] **Step 2: Run them to verify they fail**

Run: `pytest tests/unit/test_api_archive_index.py -q -k "PrunePreview or RetentionDefaults"`
Expected: FAIL, 404 or 405 on the routes.

- [x] **Step 3: Add the assembler to the service**

Append to `app/services/prune_preview.py`:

```python
from app.services.operations.followups import (
    HISTORY_AVAILABLE,
    history_capability,
    history_enabled,
)


def archives_by_series(db: Session, repository: Repository) -> dict[str, list[Archive]]:
    removed = pending_removed_ids(db, repository.id)
    q = db.query(Archive).filter(Archive.repository_id == repository.id)
    if removed:
        q = q.filter(Archive.id.notin_(removed))
    out: dict[str, list[Archive]] = {}
    for a in q.order_by(Archive.series.asc(), Archive.start.asc(), Archive.id.asc()).all():
        out.setdefault(a.series, []).append(a)
    return out


async def build_preview(
    db: Session, repository: Repository, retention: Retention, *, user_id: Optional[int]
) -> dict:
    """Spec 4.4 steps 1 to 5 in order. Raises DryRunFailed when Borg's dry
    run did not complete, with the log attached."""
    pro = history_enabled(db)  # commits; before the archive rows load
    operation, log = await run_prune_dry_run(db, repository, retention, user_id=user_id)
    if operation.status not in ("completed", "completed_with_warnings"):
        raise DryRunFailed(log)
    joined = join_verdicts(db, repository, parse_prune_verdicts(log))
    by_id = {a.id: a for rows in archives_by_series(db, repository).values() for a in rows}
    candidates = [by_id[p.id] for p in joined if p.verdict == "deleted" and p.id in by_id]
    partial = await remeasure_candidates(db, repository, candidates)
    for p in joined:
        row = by_id.get(p.id) if p.id is not None else None
        if row is not None:
            p.deduplicated_size = row.deduplicated_size
            p.stats_measured_at = row.stats_measured_at
    freed = freed_at_least(candidates)
    before = footprint(db, repository)
    deleted_ids = {a.id for a in candidates}
    capability = history_capability(db, repository)
    lost: dict = {"available": False, "capability": capability}
    if pro and capability == HISTORY_AVAILABLE:
        lost = {
            "available": True,
            "capability": capability,
            **lost_files(db, repository, archives_by_series(db, repository), deleted_ids=deleted_ids),
        }
    joined.sort(key=lambda p: (p.start is None, p.start or datetime.min, p.id or 0))
    return {
        "operation_id": operation.id,
        "archives": [
            {
                "id": p.id, "borg_id": p.borg_id, "name": p.name, "series": p.series,
                "start": p.start, "verdict": p.verdict, "rule": p.rule,
                "deduplicated_size": p.deduplicated_size,
                "stats_measured_at": p.stats_measured_at,
                "stale": p.id is not None and p.stats_measured_at is None,
            }
            for p in joined
        ],
        "deleted_count": sum(1 for p in joined if p.verdict == "deleted"),
        "kept_count": sum(1 for p in joined if p.verdict == "kept"),
        "freed_at_least": freed,
        "partial_measure": partial,
        "footprint_before": before,
        "footprint_after_at_most": max(before - freed, 0) if before is not None else None,
        "lost_files": lost,
        "log": log,
    }


class DryRunFailed(Exception):
    def __init__(self, log: str):
        super().__init__("prune dry run failed")
        self.log = log


def retention_defaults(db: Session, repository: Repository) -> dict:
    """What the preview page prefills: the plan's retention, else the last
    real manual prune's, else the dialog's defaults."""
    from app.services.operations.series import _plans_for

    plans = sorted(
        (p for p in _plans_for(db, repository, active_links_only=True)
         if p.enabled and p.run_prune_after),
        key=lambda p: p.name or "",
    )
    if plans:
        p = plans[0]
        return {
            "source": "plan", "plan_name": p.name,
            "keep_hourly": p.prune_keep_hourly or 0, "keep_daily": p.prune_keep_daily or 0,
            "keep_weekly": p.prune_keep_weekly or 0, "keep_monthly": p.prune_keep_monthly or 0,
            "keep_quarterly": p.prune_keep_quarterly or 0, "keep_yearly": p.prune_keep_yearly or 0,
            "keep_within": p.prune_keep_within or None,
        }
    last = (
        db.query(Operation)
        .filter(Operation.repository_id == repository.id, Operation.kind == "prune",
                Operation.trigger == "manual")
        .order_by(Operation.id.desc())
        .all()
    )
    for op in last:
        params = op.params or {}
        if params.get("dry_run"):
            continue
        base = Retention().as_params()
        base.update({k: params[k] for k in base if k in params and params[k] is not None})
        return {"source": "last_prune", "plan_name": None, **base}
    return {"source": "default", "plan_name": None, **Retention().as_params()}
```

The Verdict/PreviewArchive `name` for an unknown id and `series=None` is
carried through; `start` None sorts last.

- [x] **Step 4: Add the routes**

In `app/api/archive_index.py`, after `archives_growth`:

```python
class PrunePreviewRequest(BaseModel):
    keep_hourly: int = Field(default=0, ge=0)
    keep_daily: int = Field(default=0, ge=0)
    keep_weekly: int = Field(default=0, ge=0)
    keep_monthly: int = Field(default=0, ge=0)
    keep_quarterly: int = Field(default=0, ge=0)
    keep_yearly: int = Field(default=0, ge=0)
    keep_within: Optional[str] = None


@router.post("/{repo_id}/prune/preview")
async def prune_preview(
    repo_id: int,
    body: PrunePreviewRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Spec 4.4: Borg's dry run joined to the index, candidates re-measured,
    freed space as a lower bound, and (Pro) the files no surviving archive
    of the series would hold. Declared before the `{archive_id}` routes on
    purpose, as `archives_growth` is."""
    from app.api.repositories import _normalize_prune_keep_within
    from app.services import prune_preview as service

    repository = _repo(db, current_user, repo_id, role="operator")
    retention = service.Retention(
        keep_hourly=body.keep_hourly, keep_daily=body.keep_daily,
        keep_weekly=body.keep_weekly, keep_monthly=body.keep_monthly,
        keep_quarterly=body.keep_quarterly, keep_yearly=body.keep_yearly,
        keep_within=_normalize_prune_keep_within(body.keep_within),
    )
    if not retention.has_rule:
        raise HTTPException(status_code=400, detail={"key": "backend.errors.prune.noKeepRule"})
    try:
        return await service.build_preview(db, repository, retention, user_id=current_user.id)
    except service.DryRunFailed as exc:
        raise HTTPException(
            status_code=502,
            detail={"key": "backend.errors.prune.dryRunFailed", "params": {"log": exc.log}},
        )


@router.get("/{repo_id}/prune/retention-defaults")
async def prune_retention_defaults(
    repo_id: int,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    from app.services.prune_preview import retention_defaults

    return retention_defaults(db, _repo(db, current_user, repo_id))
```

Note the tests patch `run_prune_dry_run` and friends on the
`app.services.prune_preview` module, so `build_preview` must call them
through module globals (plain calls inside the same module do), and the
route must import the module, not the names.

- [x] **Step 5: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_archive_index.py -q -k "PrunePreview or RetentionDefaults"` then `pytest tests/unit -q`
Expected: all pass. The full run covers the moved dry-run branch (Task 2).

---

### Task 6: Frontend API, types, and the retention fields extraction

**Files:**
- Modify: `frontend/src/services/api.ts` (in `repositoriesAPI`, next to
  `pruneRepository` at line 974)
- Modify: `frontend/src/types/archives.ts` (append)
- Create: `frontend/src/components/prune/PruneRetentionFields.tsx`
- Modify: `frontend/src/components/PruneRepositoryDialog.tsx` (use the
  extracted fields; the dialog's behaviour is unchanged in this task)
- Test: `frontend/src/components/prune/__tests__/PruneRetentionFields.test.tsx`,
  the existing `frontend/src/components/__tests__/PruneRepositoryDialog.test.tsx`
  must stay green.

**Interfaces:**
- Produces:
  ```ts
  // types/archives.ts
  export interface PruneRetention {
    keep_within: string; keep_hourly: number; keep_daily: number; keep_weekly: number
    keep_monthly: number; keep_quarterly: number; keep_yearly: number
  }
  export interface PrunePreviewArchive {
    id: number | null; borg_id: string; name: string; series: string | null; start: string | null
    verdict: 'kept' | 'deleted'; rule: string | null; deduplicated_size: number | null
    stats_measured_at: string | null; stale: boolean
  }
  export interface PruneLostFile {
    path: string; size: number | null; series: string
    last_held_archive_id: number | null; last_held_archive_name: string | null
  }
  export interface PruneLostFiles {
    available: boolean; capability: string
    incomplete?: boolean; unindexed_archive_ids?: number[]
    total_count?: number; total_size?: number
    top?: PruneLostFile[]; by_folder?: { folder: string; count: number; size: number }[]
  }
  export interface PrunePreviewResponse {
    operation_id: number; archives: PrunePreviewArchive[]
    deleted_count: number; kept_count: number
    freed_at_least: number; partial_measure: boolean
    footprint_before: number | null; footprint_after_at_most: number | null
    lost_files: PruneLostFiles; log: string
  }
  export interface PruneRetentionDefaults extends Omit<PruneRetention, 'keep_within'> {
    source: 'plan' | 'last_prune' | 'default'; plan_name: string | null; keep_within: string | null
  }
  ```
  ```ts
  // services/api.ts, in repositoriesAPI
  prunePreview: (id: number, data: PruneRetention) =>
    api.post<PrunePreviewResponse>(`/repositories/${id}/prune/preview`, data),
  pruneRetentionDefaults: (id: number) =>
    api.get<PruneRetentionDefaults>(`/repositories/${id}/prune/retention-defaults`),
  ```
  ```tsx
  // components/prune/PruneRetentionFields.tsx
  export interface PruneRetentionFieldsProps {
    value: PruneRetention
    onChange: (next: PruneRetention) => void
    disabled?: boolean
  }
  export const DEFAULT_RETENTION: PruneRetention  // 0, 7, 4, 6, 0, 1, ''
  export default function PruneRetentionFields(props): JSX.Element
  ```
  The `PruneForm` interface in the dialog becomes a re-export of
  `PruneRetention` (same field names, so nothing else changes).

- [x] **Step 1: Write the failing test**

```tsx
// frontend/src/components/prune/__tests__/PruneRetentionFields.test.tsx
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test-utils'   // the helper the other component tests import; match their path
import PruneRetentionFields, { DEFAULT_RETENTION } from '../PruneRetentionFields'

describe('PruneRetentionFields', () => {
  it('renders the seven fields with the given values and reports changes', () => {
    const onChange = vi.fn()
    renderWithProviders(<PruneRetentionFields value={{ ...DEFAULT_RETENTION, keep_daily: 3 }} onChange={onChange} />)
    const daily = screen.getByLabelText(/keep daily/i) as HTMLInputElement
    expect(daily.value).toBe('3')
    fireEvent.change(daily, { target: { value: '5' } })
    expect(onChange).toHaveBeenCalledWith({ ...DEFAULT_RETENTION, keep_daily: 5 })
    fireEvent.change(screen.getByLabelText(/keep within/i), { target: { value: '2d' } })
    expect(onChange).toHaveBeenLastCalledWith({ ...DEFAULT_RETENTION, keep_daily: 3, keep_within: '2d' })
  })

  it('disables every field when disabled', () => {
    renderWithProviders(<PruneRetentionFields value={DEFAULT_RETENTION} onChange={() => {}} disabled />)
    expect(screen.getByLabelText(/keep daily/i)).toBeDisabled()
  })
})
```

Use the label texts the dialog already has in `en.json` under
`dialogs.prune` (grep `keepDaily` there) so the accessible names match.

- [x] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/prune`
Expected: FAIL, module not found.

- [x] **Step 3: Extract the fields**

Move the retention inputs of `PruneRepositoryDialog.tsx` (the `keep_within`
`TextField` and the six numeric fields built from the array at lines
646-690, with their labels, helper texts and `inputProps`) into
`PruneRetentionFields.tsx`, rendered from `value` and calling `onChange({
...value, [key]: next })`. Keep the exact i18n keys the dialog uses. The
dialog then renders `<PruneRetentionFields value={pruneForm}
onChange={setPruneForm} disabled={isLoading} />` in place of the moved
markup and keeps everything else (tip text, results dialog, actions).
Export `DEFAULT_RETENTION` from the new file and make the dialog's
`defaultPruneForm` equal to it.

- [x] **Step 4: Add the types and API entries** as listed under Produces.

- [x] **Step 5: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/prune src/components/__tests__/PruneRepositoryDialog.test.tsx src/pages/__tests__/Repositories.test.tsx && npm run typecheck`
Expected: all pass.

---

### Task 7: Heatmap verdict props

**Files:**
- Modify: `frontend/src/components/archives/ArchiveSeriesHeatmap.tsx:26-32`
  (props) and `:236-300` (cell rendering)
- Test: `frontend/src/components/archives/__tests__/ArchiveSeriesHeatmap.test.tsx`

**Interfaces:**
- Produces, on `ArchiveSeriesHeatmapProps`:
  ```ts
  // Optional overrides for a day that has archives. Absent, the cell keeps
  // its count-scaled primary color and count tooltip.
  cellColor?: (day: HeatmapDay) => string | undefined
  cellLabel?: (day: HeatmapDay) => string | undefined
  ```
  Passed through `Band` to the cell: when `cellColor(day)` returns a
  string it replaces `bgcolor` for a day with archives; when
  `cellLabel(day)` returns a string it replaces the `aria-label` (which is
  also what the tooltip shows).

- [x] **Step 1: Write the failing test**

Append to the heatmap test file, using the fixture data and render helper
the file already has for the repository band:

```tsx
it('lets the caller color and label a day', () => {
  const data = buildHeatmap([{ date: '2026-09-10', archive_ids: [1] }])  // reuse the file's builder; match its name
  renderWithProviders(
    <ArchiveSeriesHeatmap
      data={data}
      onSelectDay={() => {}}
      cellColor={(day) => (day.archive_ids.includes(1) ? 'rgb(220, 38, 38)' : undefined)}
      cellLabel={(day) => `deleted on ${day.date}`}
    />,
  )
  const cell = screen.getByTestId('heatmap-day-repository-2026-09-10')
  expect(cell).toHaveStyle({ backgroundColor: 'rgb(220, 38, 38)' })
  expect(cell).toHaveAttribute('aria-label', 'deleted on 2026-09-10')
})
```

- [x] **Step 2: Run it to verify it fails**

Run: `cd frontend && npx vitest run src/components/archives/__tests__/ArchiveSeriesHeatmap.test.tsx`
Expected: FAIL (type error or style mismatch).

- [x] **Step 3: Implement**

Add the two props to `ArchiveSeriesHeatmapProps` and to `Band`'s props,
thread them through the `Band` calls at lines 383 and 394, and in the cell:

```tsx
const override = hasArchives && day ? cellColor?.(day) : undefined
const labelOverride = hasArchives && day ? cellLabel?.(day) : undefined
...
aria-label={
  hasArchives
    ? labelOverride ?? t('archives.heatmap.tooltip', { ... })
    : undefined
}
...
bgcolor: override ?? (hasArchives ? alpha(...) : isMissed ? ... : ...),
```

- [x] **Step 4: Run the heatmap tests**

Run: `cd frontend && npx vitest run src/components/archives`
Expected: all pass.

---

### Task 8: The prune preview page

**Files:**
- Create: `frontend/src/pages/PrunePreview.tsx`
- Create: `frontend/src/components/prune/PrunePreviewNumbers.tsx`
- Create: `frontend/src/components/prune/PruneCandidatesRanked.tsx`
- Create: `frontend/src/components/prune/PruneLostFilesPanel.tsx`
- Create: `frontend/src/components/prune/previewHeatmap.ts`
- Create: stories `PrunePreviewNumbers.stories.tsx`,
  `PruneCandidatesRanked.stories.tsx`, `PruneLostFilesPanel.stories.tsx`
  next to the components
- Modify: `frontend/src/App.tsx:181` (route)
- Modify: `frontend/src/locales/{en,de,es,it}.json` (namespace
  `prunePreview`)
- Test: `frontend/src/pages/__tests__/PrunePreview.test.tsx`,
  `frontend/src/components/prune/__tests__/previewHeatmap.test.ts`,
  `frontend/src/components/prune/__tests__/PruneLostFilesPanel.test.tsx`

Use `ui-ux-pro-max` for this task. Mockup screen 3 is the layout:
retention card on the left (300px, stacks on top under 900px), the stack on
the right.

**Interfaces:**
- Consumes: `repositoriesAPI.prunePreview`, `repositoriesAPI.pruneRetentionDefaults`,
  `repositoriesAPI.pruneRepository` (Task 6), `ArchiveSeriesHeatmap` with
  `cellColor` / `cellLabel` (Task 7), `PruneRetentionFields`,
  `PlanGate` (`feature="archive_history"`), `formatBytes` from
  `utils/dateUtils`, `parseBackendDate`.
- Produces:
  ```ts
  // previewHeatmap.ts
  export function previewToHeatmap(archives: PrunePreviewArchive[], today?: Date): HeatmapResponse
  //   repository band = every archive with a start; one series band per series;
  //   missed_days []; cadence_known false; retention_since null; flags all false.
  export function dayVerdict(archives: PrunePreviewArchive[]): (day: HeatmapDay) => 'kept' | 'deleted' | 'mixed' | undefined
  export function sizeIntensity(archives: PrunePreviewArchive[]): (day: HeatmapDay) => number  // 0.45 .. 1
  ```
  ```tsx
  // PrunePreviewNumbers: props { deletedCount, keptCount, freedAtLeast, footprintBefore, footprintAfterAtMost, measuredAt?: string | null }
  // PruneCandidatesRanked: props { archives: PrunePreviewArchive[]; partialMeasure: boolean; onOpen: (archiveId: number) => void }
  //   deleted archives sorted by deduplicated_size desc, bar width relative to the max, stale ones marked, unmeasured at the end.
  // PruneLostFilesPanel: props { lost: PruneLostFiles; repositoryId: number; onIndexNow?: () => void }
  //   wrapped in PlanGate(feature="archive_history") by the page; shows the summary line,
  //   folder rollup, top list (path, size, last held by, link to /archives/{repositoryId}/{archiveId}),
  //   and when capability !== 'available' one line saying why (agent-executed repositories have no history index).
  ```
  Route: `/repositories/:repositoryId/prune-preview` inside
  `ProtectedRoute requiredTab="repositories"`. The page reads
  `location.state?.retention` (set by the dialog in Task 9) and otherwise
  loads `pruneRetentionDefaults`; it runs the preview on mount once
  retention is known and on "Refresh preview" after edits (not on every
  keystroke: a dry run takes seconds and holds the repository). "Run prune
  now" posts to `pruneRepository` with the same fields and `dry_run:
  false`, then navigates to `/activity?repository_id=<id>`.

- [x] **Step 1: Write the failing tests**

```ts
// frontend/src/components/prune/__tests__/previewHeatmap.test.ts
import { describe, expect, it } from 'vitest'
import { dayVerdict, previewToHeatmap, sizeIntensity } from '../previewHeatmap'
import type { PrunePreviewArchive } from '../../../types/archives'

const a = (id: number, series: string, start: string, verdict: 'kept' | 'deleted', size: number | null): PrunePreviewArchive => ({
  id, borg_id: `${id}`, name: `a${id}`, series, start, verdict, rule: verdict === 'kept' ? 'daily #1' : null,
  deduplicated_size: size, stats_measured_at: null, stale: false,
})

describe('previewToHeatmap', () => {
  it('groups archives into a repository band and one band per series', () => {
    const data = previewToHeatmap([a(1, 'nas', '2026-09-10T02:00:00', 'kept', 10), a(2, 'docs', '2026-09-10T03:00:00', 'deleted', 20)])
    expect(data.repository.days.map((d) => d.archive_ids)).toEqual([[1, 2]])
    expect(data.series.map((s) => s.series)).toEqual(['docs', 'nas'])
    expect(data.repository.count).toBe(2)
  })
  it('skips archives without a start', () => {
    expect(previewToHeatmap([a(1, 'nas', null as unknown as string, 'kept', 1)]).repository.count).toBe(0)
  })
})

describe('dayVerdict', () => {
  it('is kept, deleted or mixed', () => {
    const list = [a(1, 'nas', '2026-09-10T02:00:00', 'kept', 1), a(2, 'nas', '2026-09-10T03:00:00', 'deleted', 1), a(3, 'nas', '2026-09-11T02:00:00', 'deleted', 1)]
    const verdict = dayVerdict(list)
    expect(verdict({ date: '2026-09-10', archive_ids: [1, 2], count: 2, deduplicated_size: 0, duration_seconds: 0, anomalies: [] })).toBe('mixed')
    expect(verdict({ date: '2026-09-11', archive_ids: [3], count: 1, deduplicated_size: 0, duration_seconds: 0, anomalies: [] })).toBe('deleted')
  })
})

describe('sizeIntensity', () => {
  it('scales the largest day to 1 and the smallest to 0.45, unmeasured to 0.45', () => {
    const list = [a(1, 'nas', '2026-09-10T02:00:00', 'kept', 100), a(2, 'nas', '2026-09-11T02:00:00', 'kept', 0), a(3, 'nas', '2026-09-12T02:00:00', 'kept', null)]
    const f = sizeIntensity(list)
    const day = (date: string, ids: number[]) => ({ date, archive_ids: ids, count: ids.length, deduplicated_size: 0, duration_seconds: 0, anomalies: [] })
    expect(f(day('2026-09-10', [1]))).toBe(1)
    expect(f(day('2026-09-11', [2]))).toBe(0.45)
    expect(f(day('2026-09-12', [3]))).toBe(0.45)
  })
})
```

```tsx
// frontend/src/pages/__tests__/PrunePreview.test.tsx
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../test-utils'
import PrunePreview from '../PrunePreview'
import { repositoriesAPI } from '../../services/api'
import type { PrunePreviewResponse } from '../../types/archives'

vi.mock('../../services/api', async (importOriginal) => {
  const mod = await importOriginal<typeof import('../../services/api')>()
  return { ...mod, repositoriesAPI: { ...mod.repositoriesAPI, prunePreview: vi.fn(), pruneRetentionDefaults: vi.fn(), pruneRepository: vi.fn() } }
})

const preview: PrunePreviewResponse = {
  operation_id: 5,
  archives: [
    { id: 1, borg_id: '1', name: 'a1', series: 'nas', start: '2026-09-01T02:00:00', verdict: 'deleted', rule: null, deduplicated_size: 300, stats_measured_at: '2026-09-17T09:00:00', stale: false },
    { id: 2, borg_id: '2', name: 'a2', series: 'nas', start: '2026-09-02T02:00:00', verdict: 'kept', rule: 'daily #1', deduplicated_size: 100, stats_measured_at: '2026-09-17T09:00:00', stale: false },
  ],
  deleted_count: 1, kept_count: 1, freed_at_least: 300, partial_measure: false,
  footprint_before: 1000, footprint_after_at_most: 700,
  lost_files: { available: false, capability: 'plan_locked' },
  log: 'Would prune: a1',
}

describe('PrunePreview page', () => {
  beforeEach(() => {
    vi.mocked(repositoriesAPI.pruneRetentionDefaults).mockResolvedValue({ data: { source: 'plan', plan_name: 'Nightly', keep_hourly: 0, keep_daily: 7, keep_weekly: 4, keep_monthly: 6, keep_quarterly: 0, keep_yearly: 1, keep_within: null } } as never)
    vi.mocked(repositoriesAPI.prunePreview).mockResolvedValue({ data: preview } as never)
  })

  it('prefills from the plan, runs the preview and shows the numbers', async () => {
    renderWithProviders(<PrunePreview />, { route: '/repositories/7/prune-preview', path: '/repositories/:repositoryId/prune-preview' })
    await waitFor(() => expect(repositoriesAPI.prunePreview).toHaveBeenCalledWith(7, expect.objectContaining({ keep_daily: 7 })))
    expect(await screen.findByText(/Nightly/)).toBeInTheDocument()
    expect(screen.getByTestId('prune-preview-deleted').textContent).toContain('1')
    expect(screen.getByTestId('prune-preview-freed').textContent).toMatch(/300 B/)
    expect(screen.getByTestId('prune-preview-after').textContent).toMatch(/700 B/)
  })

  it('re-runs only on refresh and runs the prune with the edited retention', async () => {
    vi.mocked(repositoriesAPI.pruneRepository).mockResolvedValue({ data: { job_id: 9 } } as never)
    renderWithProviders(<PrunePreview />, { route: '/repositories/7/prune-preview', path: '/repositories/:repositoryId/prune-preview' })
    await screen.findByTestId('prune-preview-deleted')
    fireEvent.change(screen.getByLabelText(/keep daily/i), { target: { value: '2' } })
    expect(repositoriesAPI.prunePreview).toHaveBeenCalledTimes(1)
    fireEvent.click(screen.getByRole('button', { name: /refresh preview/i }))
    await waitFor(() => expect(repositoriesAPI.prunePreview).toHaveBeenLastCalledWith(7, expect.objectContaining({ keep_daily: 2 })))
    fireEvent.click(screen.getByRole('button', { name: /run prune now/i }))
    fireEvent.click(await screen.findByRole('button', { name: /confirm/i }))
    await waitFor(() => expect(repositoriesAPI.pruneRepository).toHaveBeenCalledWith(7, expect.objectContaining({ keep_daily: 2, dry_run: false })))
  })

  it('shows the lower-bound and cross-series notes', async () => {
    renderWithProviders(<PrunePreview />, { route: '/repositories/7/prune-preview', path: '/repositories/:repositoryId/prune-preview' })
    expect(await screen.findByText(/lower bound/i)).toBeInTheDocument()
    expect(screen.getByText(/another series/i)).toBeInTheDocument()
  })
})
```

Match `renderWithProviders`'s router options to what the helper in
`frontend/src/test-utils` actually accepts (other page tests such as
`ArchiveDetail.test.tsx` show the pattern); if it takes `initialEntries`,
wrap in `<Routes><Route path=… element=…/></Routes>` the way that test does.

```tsx
// frontend/src/components/prune/__tests__/PruneLostFilesPanel.test.tsx
import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test-utils'
import PruneLostFilesPanel from '../PruneLostFilesPanel'

describe('PruneLostFilesPanel', () => {
  it('lists totals, folders and the top files with a link to the archive', () => {
    renderWithProviders(
      <PruneLostFilesPanel repositoryId={7} lost={{
        available: true, capability: 'available', incomplete: false, unindexed_archive_ids: [],
        total_count: 2, total_size: 30,
        top: [{ path: 'docs/x', size: 20, series: 'nas', last_held_archive_id: 4, last_held_archive_name: 'a4' },
              { path: 'docs/y', size: 10, series: 'nas', last_held_archive_id: 4, last_held_archive_name: 'a4' }],
        by_folder: [{ folder: 'docs', count: 2, size: 30 }],
      }} />,
    )
    expect(screen.getByText(/2 files/)).toBeInTheDocument()
    expect(screen.getByText('docs/x')).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /a4/ })).toHaveAttribute('href', '/archives/7/4')
  })

  it('says why when the history index is unavailable', () => {
    renderWithProviders(<PruneLostFilesPanel repositoryId={7} lost={{ available: false, capability: 'agent_unsupported' }} />)
    expect(screen.getByText(/agent/i)).toBeInTheDocument()
  })

  it('warns when the index is incomplete', () => {
    renderWithProviders(<PruneLostFilesPanel repositoryId={7} lost={{ available: true, capability: 'available', incomplete: true, unindexed_archive_ids: [3, 4], total_count: 0, total_size: 0, top: [], by_folder: [] }} />)
    expect(screen.getByText(/index incomplete/i)).toBeInTheDocument()
  })
})
```

- [x] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/components/prune src/pages/__tests__/PrunePreview.test.tsx`
Expected: FAIL, modules not found.

- [x] **Step 3: Build `previewHeatmap.ts`**

```ts
import type { HeatmapDay, HeatmapResponse, HeatmapSeries, PrunePreviewArchive } from '../../types/archives'

const isoDay = (start: string) => start.slice(0, 10)

function band(archives: PrunePreviewArchive[]) {
  const days = new Map<string, HeatmapDay>()
  for (const a of archives) {
    if (!a.start) continue
    const key = isoDay(a.start)
    const day = days.get(key) ?? { date: key, count: 0, deduplicated_size: 0, duration_seconds: 0, archive_ids: [], anomalies: [] }
    day.count += 1
    day.deduplicated_size += a.deduplicated_size ?? 0
    day.archive_ids.push(a.id ?? -1)
    days.set(key, day)
  }
  const dated = archives.filter((a) => a.start).sort((x, y) => x.start!.localeCompare(y.start!))
  return { days: [...days.values()], first: dated[0]?.start ?? null, last: dated.at(-1)?.start ?? null, count: dated.length }
}

export function previewToHeatmap(archives: PrunePreviewArchive[]): HeatmapResponse {
  const bySeries = new Map<string, PrunePreviewArchive[]>()
  for (const a of archives) {
    if (!a.start || !a.series) continue
    bySeries.set(a.series, [...(bySeries.get(a.series) ?? []), a])
  }
  const series: HeatmapSeries[] = [...bySeries.entries()]
    .sort(([x], [y]) => x.localeCompare(y))
    .map(([name, list]) => ({ series: name, ...band(list) }))
  return {
    since: null, until: null,
    repository: { ...band(archives), missed_days: [] },
    series, cadence_known: false, retention_since: null,
    flags_available: { missed_run: false, size_outlier: false, duration_outlier: false },
  }
}

export function dayVerdict(archives: PrunePreviewArchive[]) {
  const byId = new Map(archives.filter((a) => a.id !== null).map((a) => [a.id as number, a.verdict]))
  return (day: HeatmapDay): 'kept' | 'deleted' | 'mixed' | undefined => {
    const verdicts = new Set(day.archive_ids.map((id) => byId.get(id)).filter(Boolean))
    if (verdicts.size === 0) return undefined
    if (verdicts.size > 1) return 'mixed'
    return verdicts.has('deleted') ? 'deleted' : 'kept'
  }
}

const MIN_INTENSITY = 0.45

export function sizeIntensity(archives: PrunePreviewArchive[]) {
  const byId = new Map(archives.filter((a) => a.id !== null).map((a) => [a.id as number, a.deduplicated_size]))
  const sizes = archives.map((a) => a.deduplicated_size ?? 0)
  const max = Math.max(0, ...sizes)
  return (day: HeatmapDay): number => {
    if (max === 0) return MIN_INTENSITY
    const total = day.archive_ids.reduce((sum, id) => sum + (byId.get(id) ?? 0), 0)
    return MIN_INTENSITY + (total / max) * (1 - MIN_INTENSITY)
  }
}
```

Check `HeatmapResponse`'s full shape in `types/archives.ts` (there may be
fields beyond those shown at lines 74-86) and fill every required one.

- [x] **Step 4: Build the three components and the page**

Page structure (`PrunePreview.tsx`), with `data-testid`s the tests use:

- Header: breadcrumb "Repositories › {name} › Prune preview" (repository
  name from `repositoriesAPI.getRepository` or the list query the app
  already caches; use whichever `ArchiveDetail.tsx` uses for its crumb).
- Left card: `PruneRetentionFields`, a source line ("Prefilled from the
  plan {plan_name}" / "Prefilled from the last manual prune" / "Default
  retention"), "Reset" (back to the loaded defaults), "Refresh preview"
  (primary, disabled while the preview runs), and "Preview refreshed
  {relative time}".
- Right stack:
  1. `PrunePreviewNumbers`: four tiles (`prune-preview-deleted`,
     `prune-preview-freed`, `prune-preview-before`, `prune-preview-after`).
     Freed reads "at least {bytes}", after reads "≤ {bytes}" with sub-line
     "at most"; before/after show "not measured" when null.
  2. Heatmap card "What stays, what goes": `ArchiveSeriesHeatmap` with
     `data={previewToHeatmap(archives)}`, `cellColor` mapping `dayVerdict`
     to `alpha(theme.palette.success.main, intensity)` for kept,
     `alpha(theme.palette.error.main, intensity)` for deleted,
     `theme.palette.warning.main` for mixed; `cellLabel` giving
     "{name}: kept, rule {rule}" / "{name}: would be deleted" joined for
     the day's archives; `onSelectDay` / `onSelectArchive` navigate to
     `/archives/{repositoryId}/{archiveId}`. Legend: kept, deleted, mixed
     day.
  3. `PruneCandidatesRanked` (title "Deleted archives ranked by what they
     free", sub-line "Re-measured just now for {n} candidates" or, when
     `partial_measure`, "Re-measured the oldest 50 of {n}; the rest use
     their stored value").
  4. `<PlanGate feature="archive_history">` around `PruneLostFilesPanel`.
  5. Warnings list: index incomplete (only when `lost_files.incomplete`,
     with the archive count and a link to `/archives?repository=…`), the
     lower-bound note (always, contains the words "lower bound"), the
     cross-series note (always, contains "another series"), partial measure
     (when set).
  6. Footer: a disclosure "Show Borg output ({deleted} would prune, {kept}
     keeping)" rendering `log` in a `<pre>`; "Cancel" (navigate back) and
     "Run prune now, delete {n} archives" (error color) which opens a MUI
     confirm dialog whose confirm button is labelled "Confirm"; on success
     `toast.success(t('repositories.toasts.pruneStarted'))` and navigate to
     `/activity?repository_id={id}`.
- Error state: a 502 from the preview shows an `Alert` with
  `t('prunePreview.dryRunFailed')` and the returned log in the disclosure;
  a 400 `noKeepRule` shows the message inline under the fields.
- Loading: skeleton tiles on first run; while refreshing, the stack keeps
  its last result at reduced opacity.

`PruneCandidatesRanked` rows: name (mono, ellipsis, click calls `onOpen`),
bar (`error.main` at 0.85 opacity on `error` soft track, width relative
to the largest candidate), size (bold, tabular), a "re-measuring" chip
when `stale`, "not measured" text when size is null; more than 25 rows
collapse behind "Show all {n}".

`PruneLostFilesPanel`: title "Files lost forever" with a "PRO" chip (the
same chip `ArchiveChangesTab` renders, if it has one; otherwise
`PLAN_LABEL` from `core/features`), summary "{count} files, {bytes}, no
surviving archive holds them", folder rollup as chips or a two-column grid,
a table Path / Size / Last held by (link `/archives/{repositoryId}/{last_held_archive_id}`),
a trailing row "… {n} more, largest first" when `total_count > top.length`,
an "Index incomplete for {n} archives" alert when `incomplete`, and a
one-line reason when `available` is false (`capability` `agent_unsupported`:
"Agent-executed repositories have no history index"; any other: "The
history index is not available for this repository").

Route in `App.tsx`, after the `/archives/:repositoryId/:archiveId` route:

```tsx
<Route
  path="/repositories/:repositoryId/prune-preview"
  element={
    <ProtectedRoute requiredTab="repositories">
      <PrunePreview />
    </ProtectedRoute>
  }
/>
```

Locale keys, namespace `prunePreview` in all four files (English shown;
translate the other three in the same register the files already use):
`title` "Prune preview", `crumbRepositories` (reuse the existing
repositories nav key if there is one), `retention` "Retention",
`prefilledPlan` "Prefilled from the plan {{name}}. Changes here are a
preview until you run the prune.", `prefilledLastPrune` "Prefilled from
the last manual prune.", `prefilledDefault` "Default retention.",
`reset` "Reset", `refresh` "Refresh preview", `refreshedAt` "Preview
refreshed {{when}}", `deleted` "Archives deleted", `ofTotal` "of
{{total}}", `kept` "{{count}} kept", `freed` "Space freed", `atLeast` "at
least {{size}}", `freedSub` "exact figure after the prune and compact",
`before` "Footprint before", `after` "Footprint after", `atMost` "at
most", `notMeasured` "not measured", `heatmapTitle` "What stays, what
goes", `legendKept` "Kept", `legendDeleted` "Deleted", `legendMixed`
"Mixed day", `cellKept` "{{name}}: kept, rule {{rule}}", `cellDeleted`
"{{name}}: would be deleted", `rankedTitle` "Deleted archives ranked by
what they free", `remeasured` "Re-measured just now for {{count}}
candidates", `remeasuredPartial` "Re-measured the oldest {{cap}} of
{{count}}; the rest use their stored value", `remeasuring`
"re-measuring", `showAll` "Show all {{count}}", `lostTitle` "Files lost
forever", `lostSummary` "{{count}} files, {{size}}, no surviving archive
holds them", `lostNone` "No file is lost: every path a deleted archive
holds survives in a kept archive of its series.", `lostPath` "Path",
`lostSize` "Size", `lostHeldBy` "Last held by", `lostMore` "{{count}}
more, largest first", `lostAgent` "Agent-executed repositories have no
history index, so lost files cannot be computed.", `lostUnavailable` "The
history index is not available for this repository.", `warnIncomplete`
"Index incomplete for {{count}} archives. Files that only those archives
held may be missing from the list.", `warnIndexNow` "Open the archives",
`warnLowerBound` "Space freed is a lower bound. Borg reports no per-set
statistics before a prune; chunks shared only among deleted archives are
freed too and are not counted here.", `warnCrossSeries` "Lost files are
checked within each series. A copy in another series of this repository
is not considered.", `showLog` "Show Borg output ({{deleted}} would
prune, {{kept}} keeping)", `cancel` "Cancel", `runNow` "Run prune now,
delete {{count}} archives", `confirmTitle` "Delete {{count}} archives?",
`confirmBody` "This runs the prune with the retention shown. Deleted
archives cannot be recovered.", `confirm` "Confirm", `dryRunFailed`
"Borg's dry run failed. The output is below.", `noKeepRule` "Set at least
one keep rule."

Backend error keys `backend.errors.prune.noKeepRule` and
`backend.errors.prune.dryRunFailed` go in the same four files under the
existing `backend.errors` tree.

- [x] **Step 5: Stories**

One story file per component with a default story and, for the numbers, a
"not measured" variant; for the ranked list, a "partial and stale"
variant; for the lost-files panel, "available", "incomplete", "agent
unsupported" and "empty" variants. Follow `ArchiveStatsHeader.stories.tsx`
for the decorator and theme setup.

- [x] **Step 6: Run the tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/prune src/pages/__tests__/PrunePreview.test.tsx && npm run typecheck && npm run lint && npm run check:locales`
Expected: all pass.

---

### Task 9: Entry points: dialog "Preview" and the repository card

**Files:**
- Modify: `frontend/src/components/PruneRepositoryDialog.tsx:985-1010`
- Modify: `frontend/src/pages/Repositories.tsx` (the `handlePruneDryRun`
  handler and `pruneRepositoryMutation.onSuccess`'s dry-run branch)
- Modify: `frontend/src/components/RepositoryCard.tsx:1064-1082`,
  `frontend/src/pages/repositories-page/RepositoryGroups.tsx:27,58,188`
- Modify: `frontend/src/locales/{en,de,es,it}.json`
- Test: `frontend/src/components/__tests__/PruneRepositoryDialog.test.tsx`,
  `frontend/src/components/__tests__/RepositoryCard.test.tsx`,
  `frontend/src/pages/__tests__/Repositories.test.tsx`

**Interfaces:**
- `PruneRepositoryDialogProps.onDryRun` becomes `onPreview: (form:
  PruneRetention) => void` (the dialog no longer awaits a result for it;
  the `results` prop and the results dialog stay for the real prune's
  outcome). The button label key `dialogs.prune.dryRunButton` becomes
  "Preview" in English and the equivalent in the other three files;
  `dialogs.prune.dryRunTip` becomes "Tip: preview first to see which
  archives would be deleted and what that frees."
- `RepositoryCard` gains `onPrunePreview: () => void`, an `Eye` icon button
  next to Prune (same `canDo('maintenance') && capabilities.canPrune`
  guard, not disabled while maintenance runs, `aria-label`
  `t('repositoryCard.buttons.prunePreview')` "Prune preview").
  `RepositoryGroups` threads it as it threads `onPrune`.
- `Repositories.tsx`: `onPreview` and `onPrunePreview` both call
  `navigate(\`/repositories/${repo.id}/prune-preview\`, { state: { retention: form } })`
  (the card passes no state). The `dry_run` branch of the mutation's
  `onSuccess` and `handlePruneDryRun` are removed; the mutation is only
  called with `dry_run: false` now.

- [x] **Step 1: Update the tests first**

In `PruneRepositoryDialog.test.tsx`, replace the assertions on the dry-run
callback with: clicking the button named /preview/i calls `onPreview` with
the current form. In `RepositoryCard.test.tsx`, add: the button named
/prune preview/i calls `onPrunePreview`. In `Repositories.test.tsx`,
replace the dry-run flow test (the one asserting
`repositories.toasts.dryRunCompleted` or `prune_result.stdout`) with one
that clicks the card's "Prune preview" and asserts `navigate` was called
with `/repositories/<id>/prune-preview` (mock `useNavigate` the way the
file already does for other navigations, or assert on
`window.location.pathname` under the test router).

- [x] **Step 2: Run them to verify they fail**

Run: `cd frontend && npx vitest run src/components/__tests__/PruneRepositoryDialog.test.tsx src/components/__tests__/RepositoryCard.test.tsx src/pages/__tests__/Repositories.test.tsx`
Expected: FAIL on the new names.

- [x] **Step 3: Implement** the three changes listed under Interfaces.
Delete the now-unused `dryRunCompleted` toast key only if nothing else
references it (grep all four locales and `src`). Keep the results dialog's
`isDryRun` branches: the backend route still accepts `dry_run: true` for
API users, and the type stays.

- [x] **Step 4: Run the tests and the locale check**

Run: `cd frontend && npx vitest run src/components/__tests__/PruneRepositoryDialog.test.tsx src/components/__tests__/RepositoryCard.test.tsx src/pages/__tests__/Repositories.test.tsx && npm run check:locales`
Expected: all pass.

---

### Task 10: Visual check and full verification

**Files:** none new.

- [x] **Step 1: Storybook, light and dark, 400px**

Start Storybook per the memory note (`fnm use 24`; `.claude/launch.json`
has the entry) and open, in the browser pane, the three new component
stories and the heatmap story with verdict colors if one was added. Check
in light and dark: kept green and deleted red are distinguishable from
each other and from the mixed-day warning at every intensity; the ranked
bars read on the paper surface; the lost-files table does not overflow at
400px (path column ellipsises, "Last held by" column hides under 900px as
in the mockup). Fix what fails; note anything deliberately left in the 5.1
Notes column.

- [x] **Step 2: Run the app against the dev container once**

With the backend and frontend of the worktree running (or the dev
container if the worktree's ports clash), open
`/repositories/<id>/prune-preview` for a Borg 1 and a Borg 2 repository
that the dev container holds, run the preview with a retention that
deletes something, and confirm: every archive in the heatmap has a
verdict, the ranked list matches the "Would prune" lines in the Borg
output disclosure, and "Run prune now" is not clicked. Record the two
operation ids in the Notes column.

- [x] **Step 3: Full suites**

Run:
```bash
pytest tests/unit -q
```
```bash
cd frontend && npm run typecheck && npm run lint && npm run test && npm run check:locales && npm run format:check
```
Expected: all green. Paste the summary lines into the G2 report.

- [x] **Step 4: Stop at gate G2** (nothing is committed before the answer).

---

## Self-review against the spec

- 4.4 step 1 (inline dry run): Task 2. Step 2 (parse `--list`, join by
  what Borg prints): Task 1, join by id in Task 3; the Borg 2 naming
  question is answered in "What the live Borg binaries print" and recorded
  in the spec. Step 3 (re-measure, cap 50, `partial_measure`): Task 3.
  Step 4 (`freed_at_least`): Task 3. Step 5 (lost files, per series,
  `incomplete`, top 200, folder rollup, cross-series limitation stated):
  Task 4 and Task 8. Response shape: Task 5 (`stale` and the two counts
  added for the UI; `footprint_before` from the `storage` payload).
  UI: page, retention editor prefilled from plan or last manual prune
  (Task 5 defaults route, Task 8), heatmap with verdicts (Tasks 7, 8),
  numbers row, ranking, lost-files panel behind `PlanGate`, warnings, raw
  log disclosure, "Run prune now" to the existing route (Task 8), reached
  from the dialog's renamed button and the card (Task 9).
- 4.1: the preview re-measures candidates synchronously (Task 3), through
  `fill_archive_info`, which stamps `stats_measured_at`.
- 4.6: `archive_history` gates only `lost_files` (server: `history_enabled`;
  client: `PlanGate`).
- 4.7: fixtures from real Borg 1.4 and Borg 2 (Task 1), unit tests in the
  named files, Vitest per component and page, a story per component,
  light and dark screenshots (Task 10).
- Appendix B: lower bound (Task 3, wording in Task 8); per-series lost
  files from the index only (Task 4); page not dialog, dialog keeps its
  form and gains Preview (Task 9); no new feature key.

## Open questions

1. **Lost files when a whole series is deleted** (Task 4 refinement). The
   spec's candidate rule assumes the newest archive of every series
   survives, which Borg 1 does not guarantee across series. The plan
   widens the candidates to every path of the series in that case. Agree,
   or keep the spec's rule and report "series fully deleted" without a
   file list?
2. **Folder rollup depth.** The plan groups lost files by the parent
   directory cut to three components (`srv/media/raw`). The mockup shows
   four-deep folders. Three keeps a home directory's users apart
   (`home/karan/tmp-exports`); is that the right depth, or should it be
   the deepest common parent per source path?
3. **Preview on agent repositories.** The dry run goes through the agent
   (as today); the re-measure runs up to 50 `repository.archive_info`
   agent jobs in sequence, each under the info timeout. That can take
   minutes. Cap agent repositories lower (10?), or accept and show a
   progress line?
4. **Card entry point.** The card has icon buttons, not a menu; the plan
   adds an `Eye` icon next to Prune. Fine, or fold it into the Prune
   button (dialog first, then Preview) and drop the extra icon?
5. **Retention-defaults precedence** when several enabled plans prune the
   repository: the plan takes the first by name. Should it prefer the plan
   that ran most recently (`last_prune`)?
