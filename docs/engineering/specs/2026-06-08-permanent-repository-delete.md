# Permanent Repository Delete

## Problem

The repository card has a delete action that removes the repository configuration from Borg UI, but it does not remove the repository directory from disk. Users need a separate, clearly destructive action for permanently deleting a server-local repository from the filesystem.

## Desired outcome

Add a permanent delete action beside the existing repository delete action. The new action deletes the local Borg repository directory and then removes the Borg UI repository record. The existing delete action remains a metadata-only removal path.

## Scope

- Applies to server-local repositories only.
- SSH, managed-agent, and direct rclone repositories keep the existing metadata delete action and do not expose server-side filesystem deletion.
- Permanent deletion requires typed confirmation using the repository name.
- Backend rejects non-local paths, missing paths, non-directory paths, symlink paths, and paths that do not look like Borg repositories.
- Backend keeps the repository record when filesystem deletion fails.
- Frontend updates the repository list immediately after successful permanent deletion and shows a failure toast when deletion fails.

## UX

Repository cards keep the current compact icon action style. The existing `Delete` action continues to use the trash icon and metadata-only semantics. The new permanent delete action uses a distinct destructive icon and tooltip label, opens a `ResponsiveDialog`, shows the repository name and path, and requires typing the repository name before enabling the confirm button.

## Backend API

Add `POST /api/repositories/{repo_id}/permanent-delete`.

Request:

```json
{
  "confirmation_phrase": "Repository name",
  "understood": true
}
```

Success response:

```json
{
  "success": true,
  "message": "backend.success.repo.repositoryPermanentlyDeleted"
}
```

Failure behavior:

- `400` for unsupported repository types or unsafe filesystem targets.
- `404` for missing repository records or missing filesystem paths.
- `409` for running repository operations.
- `500` for filesystem removal failures.

## Acceptance Criteria

- Users can distinguish metadata-only repository deletion from permanent filesystem deletion.
- Permanent deletion requires explicit typed confirmation before files are removed.
- Confirming permanent deletion removes the local repository directory through the backend.
- Successful permanent deletion removes the repository from the UI without requiring a page refresh.
- Filesystem failures leave the repository visible and show a useful failure message.
- Permanent filesystem deletion is not exposed for SSH, managed-agent, or direct rclone repositories.

## Validation

- Backend unit tests cover successful filesystem deletion and filesystem deletion failure.
- Frontend tests cover the permanent delete confirmation flow, success removal, and failure messaging.
- Repository card Storybook coverage shows the new permanent delete action.
- Local walkthrough verifies the repository list flow: open repositories, trigger permanent delete, type the repository name, confirm, and observe repository removal or failure feedback.
