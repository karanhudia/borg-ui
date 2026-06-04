---
target: frontend/src/pages/DashboardV3.tsx
total_score: 34
p0_count: 0
p1_count: 2
timestamp: 2026-05-31T04-30-05Z
slug: frontend-src-pages-dashboardv3-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Banner, status dot (now 10px with `33` alpha ring), refresh, schedule pills communicate state. Still no "last refreshed Xs ago" stamp next to the 30s polling cycle. |
| 2 | Match System / Real World | 3 | Section headings sentence case. Type chip color now distinguishes LOCAL / SSH / SFTP / RCLONE at a glance; values like "Behind" and "Unset" read better than the old "Needs backup" / "Not configured". Borg paths and repo IDs still absent on this surface. |
| 3 | User Control and Freedom | 3 | Refresh, full log, repo click-through present. Repo card click still routes to `/repositories` (RepositoryHealthPanel.tsx:215, :333), not the specific repo. |
| 4 | Consistency and Standards | 4 | The card paper is now emerald-tinted at `rgba(5,150,105,0.04)` light / `rgba(16,185,129,0.06)` dark (tokens.tsx:10), matching the brand identity captured in DESIGN.md and `theme-color`. Address bar, banner, and dashboard surfaces now share a brand-anchored hue. Mono on numbers consistent. The 31/40 critique flagged a "separate visual product" gap; that gap is now closed at the surface-token level. |
| 5 | Error Prevention | 3 | Read-only surface; low blast radius. n/a. |
| 6 | Recognition Rather Than Recall | 3 | `c` (cores), `G` (GB), `Xd/Xw/Xmo` shorthand still in use. New tooltip on the failure-strip timestamp (RepositoryHealthPanel.tsx:143-154) carries the full ISO via `formatDateTimeFull`. Type chip color reduces "what is RCLONE" recall load. |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts, no filter on activity timeline, no sort/filter on repo cards, no bulk actions. Unchanged across four runs. The "Set up a schedule" CTA now has Enter/Space keyboard handling (DashboardV3.tsx:236-263), which is a real (if narrow) keyboard win. |
| 8 | Aesthetic and Minimalist Design | 4 | Variable density on health cards (compact one-liners for healthy, full card with 2x2 inline footer for warning/critical) is the right move. The 5% status tint on warning/critical cards (RepositoryHealthPanel.tsx:339) reads as quiet differentiation, not a wall of color. ActivityTimeline as a 5-lane chart with type labels in-chart (ActivityTimeline.tsx:131-158) is more legible than the prior hour-of-day axis. Every element earns its pixel. |
| 9 | Error Recovery | 3 | Failures are now hoisted to a red-bordered strip at the top of Repository Health (RepositoryHealthPanel.tsx:98-178), adjacent to the cards they reference. Each failure is one compact line: `repo . relative-time . translated-error` with tooltips for full timestamp and full error. Raw backend keys are now translated via `translateBackendKey()`. The page-level Alert with retry remains calm. One React Query still covers the whole page; per-tile isolation deferred. |
| 10 | Help and Documentation | 2 | Tooltip coverage is broader now: failure timestamps, failure error text, dimension cells all carry `formatDateTimeFull` or full-string tooltips. Still no inline help for "dedup ratio", "1.23x", or critical-vs-warning thresholds. |
| **Total** | | **34/40** | **Good. Approaching excellent. Two structural P1s remain.** |

## Anti-Patterns Verdict

**LLM assessment**: The brand-realignment pass is the most consequential change since the file started at 20/40. The dashboard now reads as "of Borg UI" rather than "a dashboard that happens to live inside Borg UI": surface tints, `theme-color`, and card paper all share the emerald hue captured on the logo, and DESIGN.md acknowledges the framework-primary gap as a known Open Issue rather than papering over it. Type-colored destination chips (LOCAL blue, SSH indigo, SFTP violet, RCLONE cyan) carry a real piece of information that previously took a recall step, and the palette is cool enough not to compete with status (green/amber/red) or brand (emerald). The variable-density health grid is exactly what PRODUCT.md principle 3 (Calm under failure) asks for: a healthy day collapses to thin one-liners that don't shout; a bad day still gets the full 2x2 footer with mono values where they matter. Hoisting the failure strip out of the Activity panel into the Repository Health card co-locates failure context with the cards a user would act on, which is one of the original 20/40 priorities. The Activity Timeline becoming a 5-lane chart with in-chart labels removes the legend recall burden and trims the panel from roughly 340px to roughly 150px. None of these are decorative.

**Deterministic scan**: `detect.mjs --json` returned `[]` (exit 0) on `DashboardV3.tsx` and the `dashboard-v3/` directory. Same as all prior runs; detector did not catch the original textural slop and would not catch the structural items that remain. Improvements here are not detectable by the bundled regex rules.

**Visual overlays**: Not available in this agent surface. Fallback signal: source-only review against the four prior snapshots and DESIGN.md ground truth.

## Overall Impression

Fourth pass moves the dashboard from 31/40 to 34/40. The trend across all four runs is 20 to 29 to 31 to 34, with the biggest single-run gain in run 2 (quieter pass: glass, glow, pulse, drop-shadow stripped) and the most structurally meaningful gain here in run 4 (brand realignment + variable density + failure co-location). Aesthetic and Minimalist climbs from 4 to a held 4 because no aesthetic regressions appeared. Consistency moves from 3 to 4 because the surface-token divergence flagged at runs 2 and 3 is closed. Match System / Real World holds at 3, but the type-chip color coding and shortened locale strings ("Behind", "Unset") improve scannability meaningfully. The page now feels like part of Borg UI rather than its own visual product.

## What's Working

- Brand-anchored surface tints (tokens.tsx:10-13). The dashboard reads as one product with the rest of the app because card paper, address bar `theme-color`, and the brand identity captured in DESIGN.md now share a hue. The 4-6% alpha keeps it neutral, not "colored".
- Type-colored destination chips (tokens.tsx:66-71, RepositoryHealthPanel.tsx:251-266 and :361-377). LOCAL blue, SSH indigo, SFTP violet, RCLONE cyan. Glanceable, cool palette, doesn't collide with status (green/amber/red) or brand (emerald). Adds information rather than decoration.
- Variable-density health grid (RepositoryHealthPanel.tsx:207-328 compact branch, :330-490 full card). Healthy repos are ~60-70px one-liners (status dot, name, type chip, archive count, last-backup label, optional schedule pill). Warning/critical keep the full card with the 2x2 inline dimension footer. A 12-repo all-healthy day no longer scrolls forever; a single failure still gets full visual weight.
- Failure strip co-located with the cards (RepositoryHealthPanel.tsx:98-178). Compact one-line entries, tooltips for full timestamp and full error string, raw backend keys translated via `translateBackendKey()`. Lives inside the Repository Health panel because that's where the user will act.
- 2x2 inline dimension footer (health.tsx:177-242). Each cell is `[icon] LABEL  value` on one line instead of the prior stacked 4-row column. Footer drops from ~80px to ~40px while preserving status icon + label + monospaced value + full-timestamp tooltip per dimension.
- Activity Timeline as a 5-lane chart (ActivityTimeline.tsx:36-208). Five lanes (backup, check, compact, restore, prune) with mono job-type labels in-chart at the left axis. Per-job-type legend dropped because it's now self-documenting. Today column tint kept. Failed events still get a 5.5px ring at 55% opacity, which reads without depending on motion or glow.

## Priority Issues

- **[P1] One React Query covers the whole page; any field failing collapses the dashboard.** DashboardV3.tsx:63-72 still fetches a single `DashboardOverview` and renders the page-level Alert (DashboardV3.tsx:75-96) when any part fails. If `activity_feed` 500s, `repository_health` and `system_metrics` go dark with it. PRODUCT.md principle 3 (Calm under failure) wants per-tile resilience. Unchanged across runs 2, 3, and 4. **Fix**: Split into per-section queries (summary + storage, repositories, activity_feed, upcoming_tasks, system_metrics) and degrade each tile independently. **Command**: `/impeccable harden`.

- **[P1] `repo.type.toUpperCase()` plus the hand-rolled hex-alpha pattern still bypass the design system.** RepositoryHealthPanel.tsx:254 and :364 burn casing into the rendered string; locales that do not uppercase the same way cannot rescue this from i18n. Hex-alpha concatenation (`tColor + '15'`, `tColor + '40'`, `cs.color + '0d'`, `cs.color + '60'`, `cs.color + '80'`, `cs.color + '14'`, `T.red + '0d'`, `T.red + '33'`, etc.) appears across DashboardV3.tsx, RepositoryHealthPanel.tsx, and health.tsx; brittle if any token migrated from `#rrggbb` to `rgb()`/`hsl()` form. The brand-tinted `bgCard` in tokens.tsx is already `rgba(...)`, so the pattern is becoming inconsistent with the new tokens. **Why it matters**: PRODUCT.md commits to ~30% string growth and a coherent token system; both are violated by hand-rolled string ops. **Fix**: Route `repo.type` rendering through i18n with locale-aware casing; replace `+ '0d'` style alpha concatenation with a `mix(color, transparent, n)` helper or a small set of pre-defined alpha tokens (`status.tintWeak`, `status.tintMedium`, `status.borderSoft`). **Command**: `/impeccable polish`.

## Persona Red Flags

**Alex (Power User)**: Still no keyboard shortcuts. No filter on the activity timeline (cannot isolate `prune` runs at 3am). The 30s polling has no visible "last refreshed Xs ago" stamp. Clicking a repo card still opens `/repositories` (RepositoryHealthPanel.tsx:215 compact, :333 full), not the specific repo. The Activity Timeline lane chart is more scannable for "did backup run on day X" but the panel still lacks any in-page filter; a power user looking for last week's prune events still has to open the full log. The new failure strip is a real win: three most recent failures sit at the top of Repository Health with full timestamp and full error in tooltips, removing the previous click-through to find what broke.

**Sam (Accessibility-dependent)**: Type sizes floor at 0.6875rem on type/observe chips (RepositoryHealthPanel.tsx:258, :274, :368, :384), still borderline at WCAG AA 3:1 large-text threshold; verify in both themes with the new emerald-tinted surface. No global `prefers-reduced-motion` override is shipped (DESIGN.md Open Issue 4); the dashboard no longer relies on motion (PulseDot static, donut transitions are the only animation, badge-pulse removed). Activity Timeline SVG still uses `<title>` only inside `<circle>` (ActivityTimeline.tsx:176); screen readers still get nothing useful for keyboard nav across the lanes. The new failure strip is a wash for keyboard nav (no focus stop on the lines); the tooltips are mouse-only via `cursor: 'help'`.

**Riley (Stress tester)**: `UpcomingBackupsPanel` still returns `null` when empty, leaving a gap in the left column (unchanged across all four runs). With 0 repos the donuts still render at 96px with meaningless 0%. With 50+ repos the auto-fit grid scales but offers no virtualization. Long repo names still truncate silently with no tooltip in the compact card body (RepositoryHealthPanel.tsx:232-243), though the full card preserves this gap too (line 409-421). The failure strip caps at 3 entries (line 124 `.slice(0, 3)`); the 4th and subsequent failures are invisible until the user clicks through to the full log, with no "and 7 more" indicator.

## Minor Observations

- `repo.type.toUpperCase()` (RepositoryHealthPanel.tsx:254, :364) burns casing; carried forward from prior runs.
- The hex-alpha concatenation pattern is now mixed with `rgba()` tokens (e.g. `T.bgCard` is `rgba(...)`, but `cs.color + '0d'` is `#rrggbbaa`). Functional today but increasingly fragile.
- The compact-card branch and the full-card branch (RepositoryHealthPanel.tsx:207-328 vs :330-490) duplicate the type chip and observe chip render. Extract to a shared `<RepoTopChips>` to avoid drift.
- The failure strip caps at 3 (line 124) with no overflow affordance; a "+ N more" link to `/activity` filtered for failures would close the loop.
- `lastBackupDate` computation (DashboardV3.tsx:110-113) still drops schedule timezones when sorting; unchanged across all four runs.
- DashboardSkeleton still uses a fixed-3-col grid for the health section, no longer faithful to the live `auto-fit minmax(300px, 1fr)`.
- The compact card uses `T.bgCard` (line 217) but the full card uses `cs.color + '0d'` (line 339). The healthy-card surface is brand-emerald; the warning/critical surface is a 5% status tint. This is a deliberate two-token surface vocabulary; document it as intentional in tokens.tsx so future PRs do not "fix" the divergence.
- Status `dim` values in `STATUS` (tokens.tsx:45-50) are now unused at this granularity since cards mostly compose `cs.color + '0d'` directly. Either route through `STATUS[x].dim` or drop the unused tokens.

## Questions to Consider

- Is the dashboard ready for a P0-free / P1-only baseline as the "ship it" line? Two P1s remain, both flagged across multiple runs and both architectural (single React Query) or hygiene (type casing + hex alpha). At what point does "polish remaining" stop driving meaningful score movement?
- The variable-density grid solves the healthy-day problem. Does the dashboard need a third density tier (collapsed list view for fleets of 50+ repos), or is auto-fit + healthy compact card sufficient at that scale?
- The failure strip is capped at 3. Is "+ N more" the right tail affordance, or should the strip grow vertically until it hits a height ceiling?
- DESIGN.md acknowledges the framework-primary-vs-brand-emerald divergence as a known Open Issue. Is reconciling MUI primary to the emerald ramp the natural next phase, or does the dashboard's brand-anchored surface get the project far enough on its own?
