# Fork PR Visual Reports Plan

## Goal

Publish the existing Storybook visual-regression report for pull requests from
forks without executing contributor-controlled code with repository write
permissions.

## Design

1. An unprivileged `pull_request` workflow captures snapshots for every
   eligible PR and uploads them as an artifact. It uses only `contents: read`.
2. The existing visual-regression workflow becomes a trusted publisher triggered
   by the successful capture workflow through `workflow_run`. It checks out
   `main`, downloads the snapshot artifact for the triggering run, builds the
   report, and alone writes the state branch, Pages deployment, and PR body.
3. A small `pull_request_target` closed-only job removes reports. It does not
   check out, execute, or download content from the PR.

## Non-goals

- Giving fork PR code access to repository write tokens, secrets, or Pages.
- Changing the Storybook snapshot format or report presentation.
- Replacing the existing baseline/state-branch approach.

## Proof

- Extend the workflow-configuration test to assert the trust boundary,
  cross-workflow artifact handoff, and closed-report cleanup.
- Run the focused Vitest configuration test and inspect the workflow syntax.
