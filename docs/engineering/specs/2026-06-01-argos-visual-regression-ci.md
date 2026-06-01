# Argos Visual Regression CI Spec

## Problem

Storybook screenshots are currently generated into `frontend/storybook-snapshots/`
and tracked in git. The files are noisy across operating systems and slow to
regenerate on smaller machines, which makes Symphony-created PRs slower and
harder to review.

## Desired Outcome

GitHub pull request CI captures Storybook screenshots and uploads them to Argos.
Developers and agents still add or update Storybook stories for UI changes, but
they no longer maintain generated PNG snapshots in the repository.

## Design

- Keep the existing Storybook build and Playwright capture script so Borg UI
  keeps its fixed date, viewport, and render-wait behavior.
- Change the screenshot output directory to an ignored Argos upload directory.
- Add the Argos CLI as a frontend dev dependency and package scripts for local
  capture and CI upload.
- Add a dedicated GitHub Actions workflow that runs on pull requests and main
  pushes when Storybook-relevant frontend files change.
- Use GitHub tokenless authentication by default: the workflow passes
  `GITHUB_TOKEN` for PR metadata and also forwards `ARGOS_TOKEN` from repository
  secrets when the Argos project requires token authentication.
- Remove committed PNG snapshots and update repository/docs guidance so
  `frontend/storybook-snapshots/` is no longer a maintained artifact.

## Acceptance Criteria

- Pull request CI runs an Argos visual regression job for frontend
  Storybook/story-relevant changes.
- The Argos job builds Storybook, captures browser screenshots, and uploads the
  screenshot directory through Argos.
- `frontend/storybook-snapshots/` PNGs are removed from git and ignored for
  future local runs.
- Documentation explains the new workflow and required Argos repository setup.
- Existing frontend validation remains green.

## Validation

- Red/green focused Vitest checks for Argos workflow and snapshot output wiring.
- `cd frontend && npm run check:locales`
- `cd frontend && npm run typecheck`
- `cd frontend && npm run lint`
- `cd frontend && npm run build`

## External References

- Argos Storybook quickstart: https://argos-ci.com/docs/quickstart/storybook
- Argos CLI documentation: https://argos-ci.com/docs/argos-cli
- Argos GitHub tokenless authentication:
  https://argos-ci.com/docs/github-tokenless
