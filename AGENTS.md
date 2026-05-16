# Agent Instructions

These instructions apply to the entire repository.

## Feature Planning

- For non-trivial features, meaningful behavior changes, and UI changes, use the relevant Superpowers workflow before implementation.
- Use `superpowers:brainstorming` when requirements, product behavior, or UX need shaping; use `superpowers:writing-plans` for multi-step implementation plans.
- Use `superpowers:test-driven-development` for feature and bug-fix implementation, and `superpowers:verification-before-completion` before claiming completion, committing, or pushing.
- Save durable specs and implementation plans under `docs/engineering/specs/` and `docs/engineering/plans/` with dated, slugged filenames such as `YYYY-MM-DD-feature-name.md`.
- Keep process proportional: small mechanical fixes can use a concise inline plan plus targeted tests or verification instead of a full written spec.
- Do not create generic `design.md` files by default; use feature-specific specs only when a written spec is warranted.

## UI Workflow

- All UI-related decisions, design changes, reviews, and implementations must use the `ui-ux-pro-max` skill before proceeding.

## UI Preferences

- Do not use heavy left accent borders for cards, panels, alerts, list items, or status surfaces.
- Prefer balanced borders, subtle full-outline treatments, background tinting, icons, chips, or typography for emphasis instead.
