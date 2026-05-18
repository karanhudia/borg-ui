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
- Instruct Codex to keep a single `## Codex Workpad` comment on the Linear
  issue.
- Move validated PR work to `Human Review`.
- Land approved work only after a human moves the issue to `Merging`.

## Borg UI Validation Policy

The workflow prompt tells agents to choose validation by change scope:

- Backend changes: `ruff check app tests`, `ruff format --check app tests`, and
  relevant `pytest` tests.
- Frontend changes: `npm run check:locales`, `npm run typecheck`,
  `npm run lint`, `npm run build`, and relevant Vitest tests from `frontend/`.
- User-facing runtime changes: validate with `./scripts/dev.sh`,
  `docker compose up -d --build`, or smoke runners under `tests/smoke/` when
  the ticket warrants end-to-end proof.

## Performance Planning

The current Borg UI Symphony workflow prioritizes auditability and broad local
validation. On resource-constrained local runners, that can make issue-to-PR
latency and token usage much higher than necessary. The current reduction
proposal is tracked in:

- `docs/engineering/specs/2026-05-17-symphony-issue-pr-latency-reduction.md`
- `docs/engineering/plans/2026-05-17-symphony-issue-pr-latency-reduction.md`

The proposal keeps quality gates explicit while recommending lazy dependency
setup, selector-based validation manifests, code-level validation guidance, CI
sharding, and compact retry context. Host concurrency should be tuned only after
those code-level reductions are measured.

## Notes

- Keep the Symphony runtime checkout separate from Borg UI.
- Do not commit Linear API keys, Codex auth files, `.env` files, logs, local
  data, dependency directories, build output, or coverage artifacts.
- If the GitHub SSH clone hook fails, verify that the host running Symphony can
  access `git@github.com:karanhudia/borg-ui.git`.
