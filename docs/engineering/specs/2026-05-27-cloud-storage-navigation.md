# Cloud Storage Navigation Spec

## Goal

Move reusable rclone remote management out of repository setup and into a
dedicated Cloud Storage area under the BACKUP navigation, while keeping
repository-owned cloud sync on the existing repository Location step.

## Review Signal

The BOR-66 PR review clarified that "Cloud sources" should not be a tab inside
the repository wizard. It should be a left-sidebar destination like Remote
Machines, Managed Agents, and Repositories. Cloud Storage manages reusable
rclone remotes only; repositories still own remote path, cache path, sync
policy, sync status, and hydration/sync operations.

## Product Shape

- Add a BACKUP sidebar item named `Cloud Storage` at `/cloud-storage`.
- Cloud Storage lists reusable rclone remotes and lets an administrator add a
  managed remote, test connection, browse the remote, and see repository usage
  count.
- Cloud Storage does not create repositories and does not introduce a Backup
  Plan wizard step.
- Repository Wizard keeps the existing Location step.
- Location step shows four destination cards for server local storage, SSH
  storage, managed-agent storage, and Cloud Storage.
- Selecting Cloud Storage reveals rclone repository fields below the cards:
  remote selector, relative remote path, read-only local cache path, sync
  policy, advanced flags, and route preview.
- Backup Plans continue to select repositories only. Cloud metadata appears as
  repository metadata chips when repositories are listed.

## Scope For This PR

- Implement the Cloud Storage navigation item and page.
- Reuse the existing rclone remote create dialog.
- Add usage count to rclone remote API responses.
- Replace the repository wizard's internal cloud/filesystem tabs with a fourth
  Cloud Storage card and keep existing rclone create/import payload behavior.
- Update Storybook and generated snapshots for the changed Cloud Storage and
  repository Location states.
- Update this spec and the implementation plan so future work does not re-add
  cloud choices to Backup Plan Wizard.

## Follow-Up Boundary

Enabling a cloud mirror on an existing local repository needs a separate
migration/conversion design. It must decide whether to move/copy the existing
repository into the server-owned rclone cache path, how to validate rollback,
and how to avoid violating the BOR-66 rule that cache paths are server-derived.
This PR will file that as a Backlog follow-up instead of adding an unsafe
partial conversion path.

## UI Notes

- Keep the current Borg UI operational dashboard design: dense controls,
  balanced outlines, subtle tints, lucide/MUI icons, and stable hover/focus
  states.
- Do not use heavy left accent borders for Cloud Storage cards.
- Use semantic React/MUI controls and controlled form inputs.
- Keep the page useful when rclone is unavailable or no remotes exist.

## Validation

- Frontend tests cover the sidebar route, Cloud Storage page interactions, and
  repository wizard fourth-card behavior.
- Backend tests cover rclone remote usage count serialization.
- Storybook snapshots cover Cloud Storage and revised repository Location
  states.
