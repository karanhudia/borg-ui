# Cloud Storage Archive Browser Reuse Spec

## Problem

Cloud Storage can open a rclone remote, but the browse dialog is a flat list. A
folder row is rendered as static text and the page only calls the rclone browse
endpoint for the remote root. Archive contents already provide the expected
browser interaction: breadcrumb navigation, directory-first rows, loading and
empty states, and file metadata.

## Desired Outcome

Cloud Storage should browse rclone remotes through the same reusable file
browser UI used by archive contents. Opening a remote starts at the root,
clicking folders loads that folder path, breadcrumbs return to parent paths,
and archive contents keep their existing behavior.

## Approach

- Extract the reusable presentational browser from `ArchiveContentsDialog` into
  a shared component under `frontend/src/components/`.
- Keep data loading in each caller. Archive browsing continues to use
  `BorgApiClient.getArchiveContents`, while Cloud Storage uses
  `rcloneAPI.browseRemote(remote.id, path)`.
- Normalize paths to a root-relative string for the shared component. Archive
  items may arrive with leading slashes; Cloud Storage entries usually do not.
- Preserve archive-specific canary labels and warning banner through optional
  row badge/banner props rather than embedding rclone behavior in archive code.
- Keep the Cloud Storage page layout consistent with the existing operational
  dashboard UI: dense controls, balanced borders, lucide icons, semantic
  buttons, visible focus/hover states, and no heavy left accent borders.

## Acceptance Criteria

- Cloud Storage folder rows are keyboard-accessible buttons that load the
  selected rclone path.
- The browse dialog shows breadcrumbs from root to the current cloud path and
  can navigate back to parent/root paths.
- The Cloud Storage browser reuses the extracted archive browser component
  instead of duplicating the archive browsing rows.
- Archive contents still browse folders, show breadcrumbs, preserve canary
  labeling, and allow file downloads.
- Storybook demonstrates the Cloud Storage browser in a nested folder state.
- Frontend validation and snapshots are updated for the changed UI.

## Validation

- Add a failing Vitest test that clicks a Cloud Storage folder and expects
  `rcloneAPI.browseRemote(remote.id, folderPath)` plus the nested listing.
- Run the targeted Cloud Storage and archive contents tests.
- Run `cd frontend && npm run check:locales`.
- Run `cd frontend && npm run typecheck`.
- Run `cd frontend && npm run lint`.
- Run `cd frontend && npm run build`.
- Run `cd frontend && npm run snapshots`.
- Run a local app or Storybook walkthrough of the Cloud Storage browse path.

## Notes

The existing `docs/engineering/specs/2026-05-27-cloud-storage-navigation.md`
describes creation of the Cloud Storage page. This spec narrows BOR-81 to the
browser reuse/navigation gap on that page.
