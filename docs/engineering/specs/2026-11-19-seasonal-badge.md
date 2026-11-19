# Seasonal badge

## Why

Big apps mark holidays and sales with a small festive touch in their chrome
(VLC's hat, Google doodles). Borg UI should do the same: Black Friday first,
later Halloween, Diwali, year end, with or without a sale. The festive feel is
for everyone; when there is a sale, Community installs get a one-click path to
`borgui.com/buy`.

## Goals

- A small emoji on the corner of the sidebar logo tile while an event runs.
- A short burst of the website's "drifting chunks" animation over the sidebar
  header, so the app matches the Black Friday bar on borgui.com.
- Every event is data in the remote feed. Adding Diwali never needs a release.
- Community: tooltip shows the sale line, click opens the buy link.
  Pro and Lite: same emoji and animation, tooltip without the sale, not a link.

## Non-goals

- No new feed, no image hosting, no per-event custom code.
- No countdown or banner. The sale notice stays in the existing announcement
  modal, which takes the same optional `emoji` and `effect` so it looks festive
  too (emoji replaces the modal icon, chunks drop over its header).

## Anti-goals

- Anything that slows the sidebar, loops forever, or ignores
  `prefers-reduced-motion`.
- A badge that reads as an alert or a notification count.

## Approaches

1. **New `seasonal_badge` type in `announcements.json` (picked).** Reuses date
   windows, plan targeting, localization, bundled fallback and the
   updates-worker deploy. Old installs already drop unknown types in
   `isValidAnnouncement`, so they ignore it.
2. Separate `seasonal.json` feed like `plan-content.json`. Duplicates fetch,
   validation, fallback and deploy for no gain.
3. Hardcoded dates in the frontend. Needs a release per event.

## Design

Feed entry (lives next to the sale notice, same dates):

```json
{
  "id": "badge-black-friday-2026",
  "type": "seasonal_badge",
  "emoji": "🛍️",
  "effect": "chunks",
  "title": "Black Friday",
  "message": "Happy Black Friday from Borg UI.",
  "cta_label": "20% off Lite and Pro, lifetime included",
  "cta_url": "https://borgui.com/buy?src=app-black-friday-badge",
  "cta_plans": ["community"],
  "starts_at": "2026-11-23T00:00:00Z",
  "ends_at": "2026-12-01T23:59:59Z"
}
```

- `emoji` (required for this type): one emoji, so any future event is one line.
- `effect`: `"chunks"` or `"none"`. Unknown values fall back to `"none"`.
  Chunk colours stay the website palette (emerald, amber, violet, rose).
- `cta_plans`: plans that get the sale line and the link. Omitted means
  nobody. `target_plans` still controls who sees the badge at all.
- Text fields keep their `_localized` maps (de, es, it).

Behaviour:

- `selectAnnouncement` skips `seasonal_badge`; a new `selectSeasonalBadge`
  returns the highest-priority eligible one using the same eligibility check.
- `SeasonalBadge` component renders the emoji on the logo tile's top-right
  corner, slightly tilted, with a gentle idle wobble every few seconds.
  Tooltip: title, message, and the sale line for `cta_plans`.
- The chunk burst plays once per browser session (sessionStorage), about 4s,
  over the sidebar header only, pointer-events none. Reduced motion: no burst,
  no wobble, emoji stays.
- Click on a CTA plan opens `cta_url` in a new tab and tracks the existing
  announcement CTA analytics event.

Story: `SeasonalBadge.stories.tsx` with Community (sale), Pro (no sale), and
reduced motion states; the AppSidebar story gets a Black Friday variant.

Docs: `docs/announcements.md` gets a `seasonal_badge` section.

## Left to the builder

Exact tilt, wobble timing, chunk count, and tooltip layout, within the
`ui-ux-pro-max` review and a light and dark screenshot check.
