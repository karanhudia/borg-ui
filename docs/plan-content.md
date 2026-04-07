---
layout: default
title: Plan Content Manifest
nav_order: 100
---

# Plan Content Manifest

The production plan-content feed is published from:

`https://docs.borgui.com/plan-content.json`

This feed controls the text shown in the plan drawer for:

- currently available plan features
- upcoming plan features
- roadmap labels such as `available_in`

## Update Flow

1. Edit [docs/plan-content.json](/Users/karanhudia/Documents/Projects/borg-ui/docs/plan-content.json).
2. Commit and push to `main`.
3. Wait for GitHub Pages to rebuild.
4. Verify the live manifest URL returns JSON.

## Format

Each entry describes one feature:

```json
{
  "id": "backup_reports",
  "plan": "pro",
  "label": "Scheduled backup reports",
  "description": "Generate daily, weekly, and monthly backup summaries with status, size, and job insights",
  "available_in": "2.0.1"
}
```

Optional localization fields can be provided directly in the manifest:

- `label_localized`
- `description_localized`

Example:

```json
{
  "id": "backup_reports",
  "plan": "pro",
  "label": "Scheduled backup reports",
  "label_localized": {
    "es": "Informes programados de copias de seguridad"
  },
  "description": "Generate daily, weekly, and monthly backup summaries.",
  "description_localized": {
    "es": "Genera resúmenes diarios, semanales y mensuales de copias de seguridad."
  },
  "available_in": "2.0.1"
}
```

Resolution order is:

1. exact locale, e.g. `es-ES`
2. base language, e.g. `es`
3. `default`
4. the base field
