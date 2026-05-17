# Symphony Issue-to-PR Latency Reduction Spec

## Context

Borg UI runs Symphony on a local orchestration host. The current workflow favors
correctness: every active Linear issue gets a full Codex workpad, pull
synchronization, scoped implementation plan, local validation, PR feedback sweep,
GitHub checks, and a Human Review handoff. That process has produced good
auditability, but it can be too expensive for resource-constrained local
runners.

This spec reviews the Borg UI Linear project history, the current Symphony
contract in `WORKFLOW.md`, and the repository validation layout. The goal is to
reduce time to PR and token usage without reducing review quality.

## Evidence Reviewed

- Linear project query for BOR-5 through BOR-29: 25 current or completed issues,
  including 20 completed issues, 4 other active issues, and BOR-29.
- Existing `## Codex Workpad` comments for recent issues: workpads consistently
  expand issue text into a hierarchical plan, acceptance criteria, validation
  checklist, pull evidence, notes, PR feedback sweep, and handoff state.
- `WORKFLOW.md`:
  - `after_create` clones the repo and runs `cd frontend && npm ci` for every
    workspace, even docs-only or backend-only tickets.
  - `agent.max_concurrent_agents` is 10 on the current local host profile.
  - Codex is configured globally as `gpt-5.5` with `xhigh` reasoning.
  - Validation guidance asks for all backend or all frontend gates when those
    areas are touched.
- `.codex/skills/push/SKILL.md` and `.codex/skills/land/SKILL.md`:
  - Backend changes trigger `ruff check app tests`, `ruff format --check app
    tests`, and `pytest tests/unit -v`.
  - Frontend changes trigger locale parity, typecheck, lint, and full build.
- `.github/workflows/tests.yml` already runs many CI lanes in parallel:
  backend lint, backend unit coverage, backend integration, frontend quality,
  frontend coverage tests, frontend build, and three smoke lanes.
- Primary references:
  - GitHub Actions path filters and matrix strategy:
    https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
  - Pytest test selection, marker selection, `@argfile`, and duration reporting:
    https://docs.pytest.org/en/stable/how-to/usage.html
  - pytest-xdist parallel execution:
    https://pytest-xdist.readthedocs.io/en/latest/distribution.html
  - Vitest changed-file and shard options:
    https://v4.vitest.dev/guide/cli

## Timing Findings

The biggest elapsed issues were not simple docs or triage tickets; they were
UI/runtime tickets with broad validation, Storybook snapshots, app walkthroughs,
or rework/landing loops.

| Issue | Type | First PR latency | Total elapsed signal | Notes |
| --- | --- | ---: | ---: | --- |
| BOR-17 | full-stack UI/runtime | ~1h27m | ~17h56m | Three PR attachments and large rework surface |
| BOR-14 | UI/validation | ~3h19m | ~14h35m | Storybook, snapshots, frontend gates, runtime proof |
| BOR-13 | investigation | no PR attached | ~8h33m | Long root-cause investigation path |
| BOR-22 | workflow optimization | ~17m | ~8h35m | PR was quick; landing/review loop dominated |
| BOR-18 | Storybook/snapshots | ~3h28m | ~4h18m | Snapshot setup and frontend validation dominated |
| BOR-15 | full-stack UI/runtime | ~1h21m first attempt | active >23h | Rework plus new landing feedback |
| BOR-28 | docs | ~22m | ~42m | Fast because validation surface was narrow |

Time-to-first-PR and total elapsed time point to different bottlenecks:

- Time-to-first-PR is dominated by local setup, context gathering, frontend
  build/storybook work, and broad local validation.
- Total elapsed time is dominated by rework, repeated validation during landing,
  GitHub checks, and human-review feedback loops.

## Largest Time-Cost Drivers

1. Unconditional frontend dependency installation at workspace creation.
   `npm ci` runs before the agent knows whether a ticket touches frontend code.
   This front-loads a heavy Node install for docs-only, backend-only, GitHub
   triage, and Linear triage tickets before the agent knows whether frontend
   tooling is needed.

2. Broad local validation gates.
   The current local pre-push path uses whole-area gates. That is safe, but
   `pytest tests/unit -v`, full frontend typecheck/lint/build, Storybook build,
   and snapshots are much larger than needed for many changes.

3. Repeated full-context prompting and workpad growth.
   The workflow prompt, issue body, retry context, and full workpad are repeatedly
   injected. Recent workpads are valuable but verbose. Tokens are spent restating
   already-decided plan, validation, and handoff details.

4. Too much concurrent heavy work for some host profiles.
   `max_concurrent_agents: 10` can saturate CPU, RAM, disk, npm, Playwright, and
   Python test processes on smaller runners, making every active task slower.
   This should be measured after the code-level reductions below, not changed as
   the first rollout step.

5. CI lanes are parallel, but still broad.
   GitHub Actions already parallelizes jobs, yet unit coverage, integration, and
   smoke jobs run broad suites for every PR. The orchestrator often waits for
   checks that are unrelated to the changed subsystem.

6. PR feedback and landing loops can re-run equivalent proof.
   BOR-22 improved the green-PR landing path, but the workflow still needs
   sharper rules that prevent repeated local validation when the PR head,
   checks, and feedback state are unchanged.

## Recommendations

### 1. Make Workspace Bootstrap Lazy

Replace unconditional `npm ci` in `WORKFLOW.md` with a lazy dependency policy:

- Always clone and start Codex quickly.
- Install frontend dependencies only when:
  - changed files are under `frontend/`,
  - a frontend command is selected by the validation manifest,
  - Storybook/snapshots are required, or
  - the agent explicitly opens a frontend implementation path.
- Keep a host-level npm cache and Python wheel cache. The workspace remains
  disposable, but package downloads should not be repeated from scratch.
- Prefer a full enough git history for merges. The current `--depth 1` clone can
  force unshallow fetches when a feature branch needs `origin/main` merge
  context; a blobless clone with enough refs is usually a better tradeoff than a
  shallow clone that breaks branch ancestry.

Expected impact: docs, triage, and backend-only tickets should start minutes
faster and consume less disk I/O on local runners.

### 2. Add a Validation Manifest

Every PR should carry a short machine-readable validation manifest generated from
`git diff --name-only origin/main...HEAD`. The manifest should list:

- changed domains: `docs`, `backend`, `frontend`, `storybook`, `ci`,
  `runtime-smoke`, `dependencies`, `security`;
- selected local commands;
- selected CI lanes;
- required broadening reasons, if any.

Default local tiers:

| Change class | Local proof before push |
| --- | --- |
| Docs only | `git diff --check`; `cd docs && npm run build` when VitePress docs changed |
| Workflow/docs under `.github` or `.codex` | `git diff --check`; focused script test if a script changed |
| Backend leaf module | `ruff check app tests`; `ruff format --check app tests`; mapped pytest files or node ids |
| Backend shared API/service/database | backend leaf commands plus affected API/service tests; broaden to `tests/unit` only when shared contracts changed |
| Frontend leaf component | `npm run check:locales` only if locale files changed; focused Vitest file(s); `npm run typecheck`; `npm run lint` |
| Frontend app shell/routes/API client | frontend leaf commands plus `npm run build` |
| UI visual change | relevant Vitest; Storybook story update; `npm run snapshots` for changed stories only when supported, otherwise current snapshot command |
| Runtime/user path | one targeted smoke or `./scripts/dev.sh` walkthrough tied to the changed path |
| Dependencies/security/CI config | full affected backend/frontend/security gates |

The manifest should be recorded in the workpad before validation. Reviewers can
then see why a short local proof was sufficient while CI still provides a broad
safety net.

### 3. Build a Test Selector Instead of Relying on Agent Judgment

Add a repository-owned selector script, for example
`scripts/select_validation.py`, that maps changed files to commands. The agent
should be allowed to broaden from the selector, but not silently narrow it.

Backend selector examples:

- `app/utils/ssh_host_validation.py` -> `tests/unit/test_ssh_paths.py` and
  `tests/unit/test_ssh_utils.py` if import graph says both use the helper.
- `app/api/repositories.py` -> repository API tests plus service tests touched
  by imports.
- `app/database/migrations/**` -> migration smoke or focused database tests.
- `requirements.txt`, `pytest.ini`, `tests/conftest.py` -> full backend unit
  suite and lint/format.

Frontend selector examples:

- `frontend/src/components/Foo.tsx` -> nearby `Foo.test.tsx` and `Foo.stories.tsx`
  snapshot when present.
- `frontend/src/locales/*.json` -> `npm run check:locales` and frontend format.
- `frontend/src/services/borgApi/**` -> service tests plus typecheck.
- `frontend/package.json`, `vite.config.ts`, `tsconfig*.json` -> full frontend
  quality, unit coverage, and build.

Use pytest's documented selectors (`path`, `node::id`, `-k`, `-m`, and `@file`)
to keep Python runs precise. Use Vitest's `--changed origin/main` locally and
explicit file filters when the changed-file set is reliable.

### 4. Split Long CI Lanes Further

Keep the existing parallel jobs, then split the slowest broad jobs:

- Backend unit coverage:
  - matrix by path group: API, services, database/migrations, utils/core, misc;
  - merge coverage artifacts after all shards finish.
- Backend integration:
  - matrix by Borg domain: archives, backup, repositories, restore, schedule,
    mounts;
  - keep any cross-domain test in a separate `integration-cross-domain` shard.
- Frontend unit coverage:
  - use Vitest `--shard=1/N` in a matrix and merge blob/coverage reports.
- Smoke:
  - keep core, extended, and SSH split;
  - add path-aware no-op decisions inside jobs so required checks finish green
    when a smoke lane is irrelevant.

Do not rely only on workflow-level `paths-ignore` for required PR checks. GitHub
documents that skipped required workflows can leave checks pending, which blocks
merge. Prefer a tiny always-running required check that computes changed domains,
then make individual jobs exit successfully with "not applicable" when safe.

### 5. Defer Host Concurrency Tuning

Do not make concurrency reduction the first implementation step. First reduce
avoidable code-level work with lazy bootstrap, validation selection, and compact
retry context. Then use recorded command durations and host metrics to tune
concurrency per profile.

Host-profile guidance after measurement:

- Start from the selector/lazy-bootstrap baseline before changing
  `max_concurrent_agents`.
- Cap Node-heavy, Playwright, Storybook snapshot, and Python test worker
  concurrency only when measurements show contention.
- Keep workstation and CI profiles free to use higher concurrency when they have
  enough CPU, RAM, and disk I/O.
- Record the reason for any host-specific cap so it remains operational tuning,
  not a blanket workflow rule.

### 6. Reduce Prompt and Workpad Token Load

Keep the current workpad as the audit trail, but stop replaying the whole trail
to every new turn:

- Add a compact `### Current Digest` section near the top of the workpad:
  current branch/head, active plan item, selected validation, blockers, PR state.
- On retries, inject only:
  - issue title/body,
  - current digest,
  - unchecked checklist items,
  - latest validation/handoff notes.
- Move older notes under `### Log` and summarize them once they are no longer
  active decision inputs.
- Use durable spec/plan file paths instead of pasting full plans into every
  workpad update once the plan exists in the repo.
- Use lower reasoning effort for status routing, PR polling, and comment
  reconciliation; reserve `xhigh` for the first design pass and hard debugging.

Expected impact: fewer repeated tokens per retry and less Linear comment editing
time, while preserving a complete audit trail in the single workpad.

### 7. Preserve Quality With Explicit Broadening Rules

Shorter validation is safe only when broadening is deterministic. Always broaden
to full affected-suite validation when:

- changed files include package/dependency files, test config, lint config,
  workflow files, Dockerfiles, database migrations, auth/security code, or shared
  fixtures;
- the selector cannot map a file confidently;
- a focused test fails for a reason outside the touched area;
- a PR receives review feedback that changes scope;
- the branch is rebased/merged after Human Review and the head changes;
- smoke coverage is the only proof of a user-visible runtime path.

Nightly scheduled CI should continue running the full broad suite so short local
validation does not hide slow cross-domain regressions.

## Suggested Rollout

1. Immediate workflow tuning:
   - remove unconditional `npm ci` from workspace bootstrap;
   - add the workpad digest convention;
   - require a validation manifest in the workpad before push.
   - add code-level validation guidance so agents select meaningful tests before
     broadening to full local suites.

2. Selector implementation:
   - add a tested `scripts/select_validation.py`;
   - update `push` and `land` skills to use selector output;
   - keep broad validation as the fallback.

3. CI sharding:
   - split backend unit/integration and frontend Vitest coverage into matrices;
   - keep required checks green with in-job no-op decisions instead of skipped
     required workflows.

4. Measurement:
   - record command duration, time-to-first-PR, time-in-review, time-in-merge,
     and token usage per issue;
   - publish a weekly summary from Linear/workpad data so future changes are
     judged by measured latency, not impressions.
   - use those measurements to decide whether host-profile concurrency caps are
     warranted.

## Expected Impact

The largest win is not one command; it is removing avoidable work before the
agent knows the ticket shape. Lazy dependency setup and selector-based local
validation should cut UI/backend implementation loops from "run the whole area"
to "run the affected proof first, broaden only on risk." CI sharding should
reduce time waiting after PR creation without weakening the final merge gate.
Host-profile concurrency tuning remains available after measurements show it is
needed.

Quality is preserved because every shortcut has an explicit broadening rule, the
workpad records the validation rationale, and full scheduled CI remains the
backstop for cross-domain regressions.
