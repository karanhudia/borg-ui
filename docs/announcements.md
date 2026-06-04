---
title: Announcements
nav_order: 99
---

# Announcements Manifest

The production announcement feed is published from:

`https://updates.borgui.com/announcements.json`

This file is sourced from `docs/announcements.json`.

## Update Flow

1. Edit `docs/announcements.json`.
2. Commit and push to `main`.
3. Wait for the docs deployment to finish.
4. Verify the live manifest URL returns JSON.

## Localization

Announcement translations should live in the manifest itself, not in the app locale files.

Use the base fields as the default fallback:

- `title`
- `message`
- `highlights`
- `cta_label`

Then add optional localized overrides:

- `title_localized`
- `message_localized`
- `highlights_localized`
- `cta_label_localized`

Example:

```json
{
  "id": "release-2.0.0-whats-new",
  "type": "release_highlight",
  "title": "What's new in 2.0.0",
  "title_localized": {
    "es": "Novedades de la version 2.0.0",
    "de": "Neu in 2.0.0"
  },
  "message": "Borg UI 2.0.0 adds built-in plans and Borg 2 support.",
  "message_localized": {
    "es": "Borg UI 2.0.0 agrega planes integrados y soporte para Borg 2."
  },
  "highlights": ["Built-in plans", "Borg 2 support"],
  "highlights_localized": {
    "es": ["Planes integrados", "Soporte para Borg 2"]
  },
  "cta_label": "View release notes",
  "cta_label_localized": {
    "es": "Ver notas de la version"
  }
}
```

Resolution order is:

1. exact locale, e.g. `es-ES`
2. base language, e.g. `es`
3. `default`
4. the base field

## Local Development

Local frontend development does not use the published announcement feed automatically.

Production builds try the published updates endpoint first, then fall back to the bundled
`frontend/src/data/announcements.json` manifest. Local development uses that bundled manifest unless
`VITE_ANNOUNCEMENTS_URL` is explicitly set.

When changing announcements, keep `frontend/src/data/announcements.json` in sync with
`docs/announcements.json` so local development and the production fallback match the feed.

To test a custom manifest URL:

1. Start the frontend with `VITE_ANNOUNCEMENTS_URL=<manifest-url>`.
2. Clear any `announcement:*` localStorage keys if the modal was previously acknowledged or snoozed.
