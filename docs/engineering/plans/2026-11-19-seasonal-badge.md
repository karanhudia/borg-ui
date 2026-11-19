# Seasonal Badge Implementation Plan

**Goal:** Festive emoji on the sidebar logo tile, driven by a `seasonal_badge` announcement entry, with a sale link for `cta_plans`.

**Architecture:** Extend the announcement type and validator; `selectAnnouncement` skips badges, `selectSeasonalBadge` picks one. A `useSeasonalBadge` hook reuses the manifest query; a presentational `SeasonalBadge` renders inside the sidebar `Toolbar`.

**Spec:** `docs/engineering/specs/2026-11-19-seasonal-badge.md`

## Global Constraints

- No em dashes in copy or comments. Reduced motion disables every animation.
- Sale link only when `systemInfo.plan` is in `cta_plans`.
- Old installs must still ignore the entry (unknown type rejected by their validator).

## Review Focus

- Badge entry never reaches the modal (test in Task 1).
- `seasonal_badge` without `emoji` is invalid (test in Task 1).
- Unknown `effect` renders like `none` (Task 2, component).
- sessionStorage throwing must not break the sidebar (Task 2, try/catch).
- Badge must not nest an anchor inside the logo `Link` (Task 2, sibling placement).

### Task 1: Types, validation, selection

Files: `types/announcements.ts`, `utils/announcements.ts`, `utils/__tests__/announcements.test.ts`

- Add `'seasonal_badge'` to `AnnouncementType`; fields `emoji?: string`, `effect?: 'chunks' | 'none'`, `cta_plans?: Plan[]`.
- Validator: `seasonal_badge` requires non-empty `emoji`; `cta_plans` like `target_plans`; `effect` any optional string.
- `selectAnnouncement` ignores `seasonal_badge`. New `selectSeasonalBadge(announcements: unknown[], context): Announcement | null`.
- Tests: badge never selected by `selectAnnouncement`; `selectSeasonalBadge` honours window and `target_plans`; missing emoji rejected.

### Task 2: Hook and component

Files: `hooks/useAnnouncementsManifest.ts` (extracted query), `hooks/useSeasonalBadge.ts`, `components/SeasonalBadge.tsx`, `components/SeasonalBadge.stories.tsx`, `components/AppSidebar.tsx`

- `useSeasonalBadge(): { badge: Announcement | null; showSale: boolean; trackSaleClick(): void }`.
- `SeasonalBadge({ badge, showSale, onSaleClick })`: emoji at the tile corner, tooltip, link when `showSale`, chunk burst once per session.
- Stories: Community sale, Pro, no effect.

### Task 3: Feed, docs, verify

- Entry `badge-black-friday-2026` in `docs/announcements.json` and `frontend/src/data/announcements.json`.
- `docs/announcements.md` section. Run vitest, tsc, lint, Storybook screenshots light and dark.
