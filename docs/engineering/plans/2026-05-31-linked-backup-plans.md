# Linked Backup Plans From Repositories Implementation Plan

## Goal

Add repository-to-backup-plan navigation that lands on Backup Plans filtered to the selected repository.

## Architecture

Use a URL query parameter, `repositoryId`, as the durable deep link. The frontend reads that parameter and passes it to the existing backup plan list API. The backend applies the repository filter when present so the list endpoint remains efficient and does not require every list item to carry detailed repository links.

## Tasks

- [ ] Add failing tests for `RepositoryCard` rendering/clicking the linked backup plans action.
- [ ] Add failing backend test for `GET /api/backup-plans/?repository_id=<id>` returning only enabled plans linked to that repository.
- [ ] Update backend `list_backup_plans` to accept and apply `repository_id`.
- [ ] Update `backupPlansAPI.list` to send `repository_id` when a repository filter is active.
- [ ] Update `BackupPlans` to parse `repositoryId`, include it in the query key, and pass filter context to content.
- [ ] Update `BackupPlansContent` to show linked-repository filter context and a clear-filter action.
- [ ] Thread a new `onViewBackupPlans` action through `Repositories`, `RepositoryGroups`, and `RepositoryCard`.
- [ ] Add locale keys for the new action and filter context.
- [ ] Update `RepositoryCard.stories.tsx` so Storybook demonstrates the action.
- [ ] Update user docs for the repository-to-plan navigation flow.
- [ ] Run targeted tests and required validation.
