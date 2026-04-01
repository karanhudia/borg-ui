---
layout: default
title: Announcements
nav_order: 99
---

# Announcements Manifest

The production announcement feed is published from:

`https://karanhudia.github.io/borg-ui/announcements.json`

This file is sourced from [docs/announcements.json](/Users/karanhudia/Documents/Redundancy/borg-ui/docs/announcements.json) because GitHub Pages in this repository publishes the `docs/` site.

## Update Flow

1. Edit [docs/announcements.json](/Users/karanhudia/Documents/Redundancy/borg-ui/docs/announcements.json).
2. Commit and push to `main`.
3. Wait for GitHub Pages to rebuild.
4. Verify the live manifest URL returns JSON.

## Local Development

Local frontend development still uses [frontend/public/announcements.json](/Users/karanhudia/Documents/Redundancy/borg-ui/frontend/public/announcements.json) as a dev-only fallback.

If you change one of these files, update the other to keep local testing aligned with production.
