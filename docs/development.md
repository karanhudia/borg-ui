---
title: Development
nav_order: 10
description: "Set up a Borg UI development environment"
permalink: /development
---

# Development

Use the dev script for normal local development. It runs the backend in Docker and the frontend locally with Vite.

## Requirements

- Docker
- Docker Compose
- Node.js 20.19+
- Python 3.10+ for local test tooling

## Start

```bash
git clone https://github.com/karanhudia/borg-ui.git
cd borg-ui
./scripts/dev.sh
```

The script starts:

- backend container: `borg-web-ui-dev`
- frontend dev server: `http://localhost:7879`
- backend API: `http://localhost:8083` by default

Set `DEV_PORT` in `.env` if `8083` is already used.

## Local Cloud Storage OAuth

Google Drive and OneDrive Borg UI-owned OAuth can run against the local dev
server. Because the public URL is `localhost`, Borg UI allows HTTP for this
development case.

Set `PUBLIC_BASE_URL` in the repository root `.env` file before starting
`./scripts/dev.sh`. Provider OAuth app credentials are saved from the Cloud
Storage dialog after the app starts:

```dotenv
PUBLIC_BASE_URL=http://localhost:7879
```

Register these redirect URLs in the provider OAuth app:

```text
http://localhost:7879/api/rclone/oauth/callback/drive
http://localhost:7879/api/rclone/oauth/callback/onedrive
```

To obtain OAuth credentials, create a Google Cloud project in the
[Google Cloud Console](https://console.cloud.google.com/) and enable the Google
Drive API, or register a Microsoft Entra application in the
[Azure portal](https://portal.azure.com/#view/Microsoft_AAD_RegisteredApps/ApplicationsListBlade)
for OneDrive. If `PUBLIC_BASE_URL` is missing or the provider app credentials
have not been saved in Cloud Storage, Google Drive and OneDrive fall back to
rclone's loopback/manual authorization flow.

The callback hits Vite on port `7879`, and Vite proxies `/api` to the backend
container on `DEV_PORT` (`8083` by default). Client secrets stay in the backend
database as encrypted Borg UI settings; ordinary provider metadata only reports
whether credentials are configured.

## Production-Style Local Run

```bash
docker compose up -d --build
```

Default app URL:

```text
http://localhost:8081
```

Set `PORT` in `.env` to change it.

## Useful Files

```text
app/                    FastAPI backend
frontend/               React frontend
scripts/dev.sh          full dev environment
docker-compose.yml      production-style compose
docker-compose.dev.yml  dev backend compose
docs/                   VitePress docs
```

## Frontend Commands

```bash
cd frontend
npm install
npm run dev
npm run typecheck
npm run lint
npm run format:check
npm run build
```

`npm ci` in a fresh checkout or worktree can fail on the platform-specific
optional packages (`@rolldown/binding-*`, `@oxlint/binding-*`) because of a
long-standing npm lockfile bug. `npm install` installs them, so prefer it
locally. If a build still reports a missing binding, copy that package
directory over from another checkout of the same `frontend/package-lock.json`
on the same platform. The lockfile pins these bindings per version and per
OS/CPU, so one copied from elsewhere will not load. Do not delete
`package-lock.json` to work around it: reinstalling from scratch rewrites the
lockfile, which is a repository change, not a local fix.

## Backend Commands

Run from the repository root:

```bash
ruff check app tests
ruff format --check app tests
pytest
```

## Docs Commands

```bash
cd docs
npm ci
npm run dev
npm run build
```

## API Docs

With the app running:

```text
http://localhost:8081/api/docs
```

In dev mode, use the `DEV_PORT` backend URL.

## Container Shell

```bash
docker exec -it borg-web-ui-dev bash
```

Check Borg binaries:

```bash
borg --version
borg2 --version
```

## Pre-Commit Hooks

Install hooks if you use them locally:

```bash
pre-commit install --hook-type pre-commit --hook-type pre-push
```

Make sure frontend dependencies are installed first, otherwise pre-push hooks that call `prettier`, `tsc`, or `oxlint` will fail.

## Releases

Create releases only through the checked-in release command, from a clean local
`main` that exactly matches `origin/main`:

```bash
./scripts/release.sh v2.2.7
```

For a stable semantic-version bump, `./scripts/bump-version.sh patch` (or
`minor` / `major`) delegates to the same release command.

The command updates `VERSION`, the frontend manifest and lockfile, and the
backend/OpenAPI version metadata. It verifies that every location matches,
commits the release, and pushes an annotated tag. GitHub Actions then refuses
tags whose metadata does not match or whose commit is not reachable from `main`,
before creating the GitHub release or publishing Docker images.

Published tags are immutable. If a released version needs a correction, publish
the next patch release rather than amending or re-pointing the existing tag.

## Testing the Native Installer

`scripts/install.sh` provisions a whole host, so reading it does not tell you
much. Almost every defect found in it so far has been state left inconsistent
by a **second** run, a run with **different flags**, or a run over an
**interrupted** one, and those are only reachable by running it.

Build the tarball once, then run the matrix against it:

```bash
fnm exec --using=22 -- ./scripts/build-native-tarball.sh dist
./scripts/test-native-install.sh
```

The harness boots a throwaway Debian container with systemd as PID 1 and runs
the installer against it: a fresh install, a plain re-run, a re-run passing a
different `--data-dir` and `--port`, `--no-start` against a running service,
`--skip-borg2` over an existing Borg 2, a half-built virtualenv, and a
`--service-user` change. Each case asserts the service is still up and
answering afterwards.

Needs Docker with a Linux daemon, and Node 22 for the build. The harness never
builds on its own: `npm ci` deletes `frontend/node_modules`, and a worktree
that shares one install with another checkout through a symlink would lose that
other checkout's modules. `build-native-tarball.sh` refuses outright when it
sees such a symlink.

Run one case, or keep the container to poke at it:

```bash
./scripts/test-native-install.sh --case serviceuser
./scripts/test-native-install.sh --keep
docker exec -it borg-ui-install-test journalctl -u borg-ui -n 50 --no-pager
```

To try the installer on a real host instead, build the tarball, copy it over,
and point the installer at it:

```bash
TARBALL=$(ls -t dist/borg-ui-*.tar.gz | head -n 1)
scp "$TARBALL" scripts/install.sh root@host:/tmp/
ssh root@host "bash /tmp/install.sh --tarball /tmp/$(basename "$TARBALL")"
```

One explicit path, not a glob: with more than one build in `dist/` a glob
copies them all and hands `--tarball` several arguments.

`--tarball` skips the release download, so it also covers air-gapped installs.

## Smoke Tests

Production-critical flows are covered by smoke tests against a running app.

Example:

```bash
python3 tests/smoke/run_core_smoke.py --url http://localhost:8081
```

See [Testing](testing).
