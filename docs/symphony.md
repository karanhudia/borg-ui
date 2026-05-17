# Symphony

Borg UI uses OpenAI Symphony as an external orchestration service. The
Symphony runtime is not vendored into this repository; Borg UI owns the
repository contract in `WORKFLOW.md` and the optional Codex skills in
`.codex/skills`.

## Requirements

- GitHub SSH access to `git@github.com:karanhudia/borg-ui.git`
- Codex CLI with `codex app-server`
- Linear personal API key exported as `LINEAR_API_KEY`
- `mise` for the Elixir/Erlang versions recommended by Symphony
- Linear project statuses: `Todo`, `In Progress`, `Human Review`, `Merging`,
  `Rework`, and `Done`

The Borg UI Linear project is:

```text
https://linear.app/nullcodeai/project/borg-ui-dd36af456cf9/
```

## Install Symphony

Clone and build the official Symphony reference implementation outside this
repository:

Choose local paths outside this repository:

```bash
export SYMPHONY_HOME="$HOME/code/symphony"
export BORG_UI_HOME="$HOME/code/borg-ui"

git clone https://github.com/openai/symphony "$SYMPHONY_HOME"
cd "$SYMPHONY_HOME/elixir"
mise trust
mise install
mise exec -- mix setup
mise exec -- mix build
```

## Run Symphony for Borg UI

From the Symphony Elixir directory, point the service at Borg UI's workflow
file:

```bash
export SYMPHONY_HOME="$HOME/code/symphony"
export BORG_UI_HOME="$HOME/code/borg-ui"

cd "$SYMPHONY_HOME/elixir"
read -rsp "Linear API key: " LINEAR_API_KEY
echo
export LINEAR_API_KEY
mise exec -- ./bin/symphony "$BORG_UI_HOME/WORKFLOW.md" --port 4000
```

When `--port 4000` is set, the optional Symphony dashboard is available at:

```text
http://localhost:4000
```

## What Symphony Will Do

- Poll the Borg UI Linear project for active `Todo`, `In Progress`, `Merging`,
  and `Rework` issues.
- Create an isolated workspace under `~/code/borg-ui-symphony-workspaces`.
- Clone Borg UI into the issue workspace.
- Start `codex app-server` in the workspace.
- Install frontend dependencies only after the validation selector or an active
  implementation path requires frontend work.
- Instruct Codex to keep a single `## Codex Workpad` comment on the Linear
  issue.
- Move validated PR work to `Human Review`.
- Land approved work only after a human moves the issue to `Merging`.

## Borg UI Validation Policy

The workflow prompt tells agents to choose validation by change scope. When
`scripts/select_validation.py` exists, agents must run it before local
validation and record its manifest hash, selected commands, and broadening
reasons in the Linear workpad:

```bash
python3 scripts/select_validation.py --base origin/main --format json
python3 scripts/select_validation.py --base origin/main --format text
```

Selector output is the minimum local gate. Agents may broaden from it, but may
not silently narrow ticket-provided validation, reviewer-requested validation,
or manifest broadening reasons. If the selector is unavailable or reports an
unmapped/risky change, use the conservative fallback for the affected areas:

- Backend changes: `ruff check app tests`, `ruff format --check app tests`, and
  relevant `pytest` tests.
- Frontend changes: `npm run check:locales`, `npm run typecheck`,
  `npm run lint`, `npm run build`, and relevant Vitest tests from `frontend/`.
- User-facing runtime changes: validate with `./scripts/dev.sh`,
  `docker compose up -d --build`, or smoke runners under `tests/smoke/` when
  the ticket warrants end-to-end proof.

Before moving a PR to `Human Review`, the workpad should include a compact
`### Current Digest` with branch/head, active plan item, selector manifest hash,
selected validation, blockers, and PR/check state. The handoff note includes
the manifest hash so `Merging` can detect whether landing can use the already
validated fast path or must rerun selector-selected validation.

## Performance Planning

The current Borg UI Symphony workflow prioritizes auditability and broad local
validation. On resource-constrained local runners, that can make issue-to-PR
latency and token usage much higher than necessary. The current reduction
proposal is tracked in:

- `docs/engineering/specs/2026-05-17-symphony-issue-pr-latency-reduction.md`
- `docs/engineering/plans/2026-05-17-symphony-issue-pr-latency-reduction.md`

The implementation keeps quality gates explicit while using lazy dependency
setup, selector-based validation manifests, code-level validation guidance,
path-aware CI lanes, and compact retry context. The Odroid M1 workflow profile
uses a conservative `max_concurrent_agents: 3` default so Node installs,
Python/pytest, and Storybook/snapshot work do not contend across too many
simultaneous issue workspaces.

## Notes

- Keep the Symphony runtime checkout separate from Borg UI.
- Do not commit Linear API keys, Codex auth files, `.env` files, logs, local
  data, dependency directories, build output, or coverage artifacts.
- If the GitHub SSH clone hook fails, verify that the host running Symphony can
  access `git@github.com:karanhudia/borg-ui.git`.
