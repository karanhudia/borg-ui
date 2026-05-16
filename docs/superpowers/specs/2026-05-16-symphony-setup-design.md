# Symphony Setup Design

## Context

Borg UI will use OpenAI Symphony as an external orchestration service. The
Symphony runtime itself stays outside this repository. This repository owns the
workflow contract and optional Codex skills that Symphony agents need when they
work on Borg UI Linear tickets.

The Linear project is:

```text
https://linear.app/nullcodeai/project/borg-ui-dd36af456cf9/
```

The project slug used by Symphony is `borg-ui-dd36af456cf9`.

## Goal

Add the official Symphony-style repository setup for Borg UI so Symphony can
poll Linear, create isolated workspaces, clone Borg UI, run Codex app-server,
and hand completed work to human review through pull requests.

## Architecture

The setup will follow Symphony's Elixir reference documentation:

- Add a root `WORKFLOW.md` as the repository-owned Symphony contract.
- Use Symphony's default Linear status flow:
  `Todo`, `In Progress`, `Human Review`, `Merging`, `Rework`, and terminal
  states such as `Done`, `Closed`, `Cancelled`, `Canceled`, and `Duplicate`.
- Configure workspaces under a Borg UI-specific root such as
  `~/code/borg-ui-symphony-workspaces`.
- Use `hooks.after_create` to clone `git@github.com:karanhudia/borg-ui.git`
  into each new issue workspace.
- Launch Codex via `codex app-server` with inherited shell environment,
  `approval_policy: never`, and `workspace-write` sandboxing.
- Copy Symphony's optional `.codex/skills` into this repository and adjust only
  project-specific validation commands where the upstream skills refer to
  Symphony's Elixir test suite.
- Add concise local operator documentation explaining how to run the external
  Symphony service against Borg UI's `WORKFLOW.md`.

## Workflow Prompt

The prompt body in `WORKFLOW.md` will keep the official Symphony behavior:

- Treat Linear as the source of work.
- Keep one persistent `## Codex Workpad` comment on each issue.
- Move `Todo` issues to `In Progress` before implementation.
- Move completed and validated PRs to `Human Review`.
- Wait for a human to move approved PRs to `Merging`.
- Use the `land` skill from `Merging` to merge and finish the issue.
- Stop only for true blockers such as missing required secrets, tools, or
  permissions.

The Borg UI prompt additions will describe the repo's validation lanes:

- Backend: `ruff check app tests`, `ruff format --check app tests`, and targeted
  `pytest`.
- Frontend: `npm run check:locales`, `npm run typecheck`, `npm run lint`,
  `npm run build`, and targeted Vitest tests from `frontend/`.
- Runtime/UI changes: validate through the existing dev or production-style app
  scripts and smoke tests when the ticket changes user-facing behavior.
- PRs: use the existing `.github/PULL_REQUEST_TEMPLATE.md` and keep the PR
  linked from Linear.

## Files

- Create `WORKFLOW.md`.
- Create `.codex/skills/commit/SKILL.md`.
- Create `.codex/skills/push/SKILL.md`.
- Create `.codex/skills/pull/SKILL.md`.
- Create `.codex/skills/land/SKILL.md`.
- Create `.codex/skills/land/land_watch.py`.
- Create `.codex/skills/linear/SKILL.md`.
- Create `docs/symphony.md`.

## Error Handling

The workflow will use Symphony's official blocked-access behavior. GitHub access
problems should be investigated with available fallbacks before marking the
issue blocked. Non-GitHub blockers such as missing Linear auth, missing Codex
auth, or absent required local tools should be recorded in the workpad with the
exact missing requirement and the issue moved to `Human Review`.

## Testing

Because this setup is configuration and documentation, verification will focus
on static checks:

- Confirm the YAML front matter in `WORKFLOW.md` is syntactically valid.
- Confirm the referenced skill files exist.
- Confirm docs mention the required environment variables and Symphony startup
  command.
- Optionally run Symphony's own setup commands in the external `symphony/elixir`
  checkout if the user provides or wants a local runtime checkout.

## Scope

This change will not vendor the Symphony Elixir runtime into Borg UI, create
Linear statuses through API calls, create GitHub labels, or start long-running
background orchestration without explicit operator action.
