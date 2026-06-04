---
title: Contributing
nav_order: 9
description: "How to contribute to Borg UI"
---

# Contributing

Keep changes small, testable, and tied to a real issue or improvement.

## Setup

```bash
git clone https://github.com/YOUR_USERNAME/borg-ui.git
cd borg-ui
git remote add upstream https://github.com/karanhudia/borg-ui.git
./scripts/dev.sh
```

## Branches

```bash
git checkout -b fix/short-description
```

Use clear prefixes:

- `fix/`
- `feat/`
- `docs/`
- `test/`
- `refactor/`

## Checks

Run the checks for the area you changed.

Docs:

```bash
cd docs
npm ci
npm run build
```

Frontend:

```bash
cd frontend
npm install
npm run typecheck
npm run lint
npm run format:check
npm test
```

Backend:

```bash
ruff check app tests
ruff format --check app tests
pytest
```

## Pull Requests

Good PRs include:

- what changed
- why it changed
- how it was tested
- screenshots for visible UI changes
- migration notes for data or config changes

Avoid mixing unrelated refactors with behavior changes.

## Docs

Docs live in `docs/` and are built with VitePress.

Rules:

- use current UI names
- use current default port `8081`
- use `ainullcode/borg-ui`
- avoid future claims unless clearly labeled roadmap
- prefer one working path over many variants
- run the docs build before opening a PR

## License

Contributions are licensed under the GNU Affero General Public License v3.0.
