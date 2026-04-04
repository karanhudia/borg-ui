---
layout: default
title: Testing
nav_order: 11
description: "What Borg Web UI tests before you trust it with production backups"
permalink: /testing
---

# Testing

Borg Web UI prioritizes API-driven tests for the Borg 1 workflows that can affect production backups and restores.

## API Integration Coverage

- Repository create, import, info, stats, keyfile upload, and keyfile download
- Manual backup start, job status polling, archive creation, and encrypted repository backups
- Archive list, info, contents browsing, file download, and delete-job completion
- Restore preview, archive tree browsing, selected-path restore, restore start, job status polling, and restored file verification
- Repository maintenance: check, compact, prune, break-lock, and job-history/status endpoints
- Scheduled backup creation, duplication, and `run-now` execution across one or many repositories

## Smoke Coverage

Core smoke runs against a built app and a live FastAPI server:

- App boot, routing, auth, and protected endpoint reachability
- Repository create plus repository list through the public API
- Manual backup, backup cancel, failed-backup log download, archive list, archive info, file download, selected-path restore, and archive delete
- Schedule `run-now`, permissions enforcement, and key failure-path contracts

Extended smoke covers slower Borg-heavy black-box checks:

- Encrypted repositories, keyfile upload/download, and restore
- Maintenance APIs: check, compact, prune, break-lock, restore cancel, and archive delete cancel
- Localhost SSH repository smoke when the environment provides an SSH server and Borg remotely
- Multi-source backup correctness
- Archive contents parity between Borg CLI and the API
- Deep archive directory browsing behavior

## Mount Coverage

- Archive mount and unmount are tested through the FastAPI API when the environment supports `borg mount` and FUSE
- In environments without FUSE support, mount API tests are skipped instead of producing false negatives

## Test Philosophy

- Exercise the same FastAPI endpoints the frontend uses
- Run real Borg commands against temporary repositories whenever the feature ends in a real Borg operation
- Verify both the API response and the resulting repository or filesystem state
