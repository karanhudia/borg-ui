---
target: frontend/src/pages/DashboardV3.tsx
total_score: 31
p0_count: 0
p1_count: 2
timestamp: 2026-05-30T16-10-25Z
slug: frontend-src-pages-dashboardv3-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Banner, status dot, refresh, schedule pills communicate state. No "last refreshed Xs ago" stamp next to the 30s polling cycle. |
| 2 | Match System / Real World | 3 | Sentence-case section headings everywhere. `BACKUP / CHECK / COMPACT / RESTORE` still arrive uppercase from i18n (used at DimStatusGrid label row, health.tsx:213) but read as labels, not eyebrows. Borg paths / repo IDs still absent. |
| 3 | User Control and Freedom | 3 | Refresh, full log, repo click-through all present. Repo card click still routes to `/repositories` (RepositoryHealthPanel.tsx:118) not the specific repo. |
| 4 | Consistency and Standards | 3 | Page visually rhymes with rest of app. Card fill is still the dashboard-specific `rgba(255,255,255,0.05) / rgba(0,0,0,0.03)` token (tokens.tsx:4) rather than MUI `background.paper`. Mono on numbers consistent. |
| 5 | Error Prevention | 3 | Read-only surface; low blast radius. n/a. |
| 6 | Recognition Rather Than Recall | 3 | `c` (cores), `G` (GB), `Xd/Xw/Xmo` shorthand still in use. Tooltips on DimStatusGrid carry the full timestamp via `formatDateTimeFull`. |
| 7 | Flexibility and Efficiency | 2 | No keyboard shortcuts, no filter on activity timeline, no sort/filter on repo cards, no bulk actions. Unchanged across all three runs. |
| 8 | Aesthetic and Minimalist Design | 4 | Donuts shrunk 148 to 96 (charts.tsx:10, :79); the headline % and total size now sit in panel headers, not as centered hero numbers. PulseDot is a static dot with a faint 2px ring (health.tsx:22-34). Glass blur, glow drop-shadows, pulse rings, and badge-pulse animation are all gone. Every element earns its pixel. |
| 9 | Error Recovery | 2 | Page-level Alert with retry is calm. Current failures block (DashboardV3.tsx:494-555) reads neutral (thin top border, sentence-case heading, muted mono on error string). Per-tile failure isolation still missing: single React Query (DashboardV3.tsx:69-73) covers the whole page. Deferred. |
| 10 | Help and Documentation | 1 | Still no inline help for "dedup ratio", "1.23x", critical-vs-warning thresholds. Unchanged across three runs. |
| **Total** | | **31/40** | **Good. Solid foundation, two structural P1s remain.** |

## Anti-Patterns Verdict

**LLM assessment**: The dashboard now reads as an operations panel, not a Dribbble shot. The donut distillation lands cleanly: at 96px with the % in the header and the centerpiece carrying only "good/total" or the archives count, neither ring competes with the repo health grid for hierarchy. The storage card's total size moved into the header beside the icon (DashboardV3.tsx:374-384), removing the second hero number. The dead `T.greenGlow` and `STATUS.glow` tokens are gone from tokens.tsx, which means the cinematic vocabulary is no longer even available in code. The `gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))'` change at RepositoryHealthPanel.tsx:100 is the right move for i18n string growth: there is no hard 3-col cap anymore, so DE/ES locales reflow to 2 columns instead of crushing chips. The plan chip uses i18n `planCount` with `count` interpolation (line 213-215), removing the hardcoded `'plan'/'plans'` pluralization.

**Deterministic scan**: `detect.mjs` returned `[]` (exit 0) on `DashboardV3.tsx` and the `dashboard-v3/` directory in prior runs. Detector did not catch the original textural slop and would not catch the structural items that remain. Improvements here are not detectable by the bundled regex rules.

**Visual overlays**: Not available in this agent surface. Fallback signal: source-only review.

## Overall Impression

Third pass moves the dashboard from 29/40 to 31/40. The two P1s flagged in run 2 that were addressable as design work (donut framing, repo grid layout / plan chip i18n) are both resolved cleanly. What remains is one architectural P1 (single React Query, deferred as a real refactor), one i18n hygiene P1 (`repo.type.toUpperCase()` plus the hand-rolled hex-alpha pattern), and the perennial low-impact items (no keyboard shortcuts, no inline help). Aesthetic + Minimalist climbs to a 4 because nothing on the page is decorative anymore. The dashboard is no longer the loudest screen in the app, which is exactly what PRODUCT.md asks for.

## What's Working

- SuccessDonut and StorageDonut at 96px with headline data in the panel header (charts.tsx:5-63, :65-201, DashboardV3.tsx:254-279, :362-385). The ring is a supporting glanceable shape, not a centerpiece. Good/total and the archives count are the only labels inside the ring, both in muted text.
- `gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))'` at RepositoryHealthPanel.tsx:100 with the 300px floor sized for the DE worst case. Comment on line 97-99 documents the reasoning. This is the layout decision that survives every locale.
- Plan chip i18n via `planCount` with `count` interpolation (RepositoryHealthPanel.tsx:213-215). The hardcoded English pluralization is gone.
- Token surface is now genuinely minimal: only `bgCard / border / borderHover / textPrimary / textMuted / textDim / 5 status colors / 3 dim variants / mono / radius / 6 internal SVG tokens`. No `glow`, no `greenGlow`, no decorative tokens left.
- Section header pattern (icon + sentence-case 0.8125rem weight 600) is consistent across all four card types: Success (line 260), Resources (line 324), Storage (line 370), Repository health (RepositoryHealthPanel.tsx:36), Upcoming (UpcomingBackupsPanel.tsx:37), Activity (line 452). Six instances, one pattern.

## Priority Issues

- **[P1] One React Query covers the whole page; any field failing collapses the dashboard.** DashboardV3.tsx:64-73 fetches a single `DashboardOverview` and renders the Alert (DashboardV3.tsx:77-97) when any part fails. If `activity_feed` 500s, `repository_health` and `system_metrics` go dark with it. PRODUCT.md principle 3 (Calm under failure) wants per-tile resilience. The user reasonably deferred this as a backend + frontend refactor; flagging it forward so the next pass picks it up. **Fix**: Split into per-section queries (summary + storage, repositories, activity_feed, upcoming_tasks, system_metrics) and degrade each tile independently. **Command**: `/impeccable harden`.

- **[P1] Cosmetic i18n / token-shape hygiene still leaks.** `repo.type.toUpperCase()` (RepositoryHealthPanel.tsx:142) forces a casing transform into the rendered string; i18n cannot rescue locales that do not uppercase the same way. The hand-rolled `cs.color + '30'`, `+ '25'`, `+ '12'` hex-alpha pattern (DashboardV3.tsx:133, RepositoryHealthPanel.tsx:121, :128, :144, :149, :222 etc.) is brittle: any token migrated to `rgb()` or `hsl()` silently turns invisible. `lastBackupDate` (DashboardV3.tsx:111-114) still drops schedule timezones when sorting. **Why it matters**: PRODUCT.md commits to ~30% string growth and a coherent token system; both are violated by hand-rolled string ops that bypass the design system. **Fix**: Move `repo.type` rendering through i18n with locale-aware casing; replace `+ '30'` with a `mix(color, transparent, n)` helper or pre-defined alpha tokens. **Command**: `/impeccable polish`.

## Persona Red Flags

**Alex (Power User)**: Still no keyboard shortcuts. No filter on the activity timeline (cannot isolate `prune` runs). The 30s polling has no visible "last refreshed Xs ago" stamp. Clicking a repo card opens `/repositories` (RepositoryHealthPanel.tsx:118), not the specific repo, so the click context is lost. Unchanged across all three runs.

**Sam (Accessibility-dependent)**: Type sizes floor at 0.6875rem on the type chip (RepositoryHealthPanel.tsx:146), still borderline at WCAG AA 3:1 large-text threshold; verify in both themes. No `prefers-reduced-motion` override is shipped, but the dashboard no longer relies on motion (PulseDot is static, donuts have no glow, badge-pulse removed); only the chart stroke transitions (charts.tsx:36, :127, :241) and DashboardSkeleton fade-in (line 219-224) remain. The activity timeline SVG still uses `<title>` only inside `<circle>` (ActivityTimeline.tsx:122); screen readers still get nothing useful for keyboard nav.

**Riley (Stress tester)**: `UpcomingBackupsPanel` still returns `null` when empty (UpcomingBackupsPanel.tsx:16), leaving a gap in the left column. With 0 repos the donuts render at full 96px with meaningless 0%. With 50+ repos the new auto-fit grid will scale columns wide but offers no virtualization. Long repo names still truncate silently with no tooltip (RepositoryHealthPanel.tsx:187-189).

## Minor Observations

- `repo.type.toUpperCase()` (RepositoryHealthPanel.tsx:142) burns casing into the rendered string; i18n cannot fix it for locales with different uppercasing.
- `cs.color + '30'` / `+ '25'` / `+ '12'` hex-alpha pattern still in use (DashboardV3.tsx:133, RepositoryHealthPanel.tsx:121, :128, :144, :149, :222, etc.); brittle if any token is moved to `rgb()` / `hsl()`.
- The dashboard's own card paper (`rgba(255,255,255,0.05)` / `rgba(0,0,0,0.03)` from tokens.tsx:4) is still not the MUI `background.paper` used elsewhere. Quieter now, but documentary register is unique to this surface.
- `lastBackupDate` computation (DashboardV3.tsx:111-114) still drops schedule timezones when sorting.
- DashboardSkeleton at line 206 still uses the old `repeat(3, 1fr)` at `lg` rather than mirroring the real `auto-fit minmax(300px, 1fr)` grid. Skeleton no longer faithful to the live layout at narrow widths.
- DashboardSkeleton fade-in animation (line 219-224) is the only remaining motion that does not respect `prefers-reduced-motion`.

## Questions to Consider

- Per-tile failure isolation is the single biggest "calm under failure" gap. Is the right move to split `getOverview` on the backend, or to compose multiple independent queries on the frontend against existing endpoints?
- Is the dashboard's surface token (`rgba(255,255,255,0.05)`) a deliberate "operational dashboard" register, or should it converge on MUI `background.paper` shared with the rest of the app?
- With donuts demoted, would removing them entirely (replacing with one-line stats in the banner) feel like progress or like a loss? The current 96px is a good middle, but the question is open.
- The DashboardSkeleton still uses the old fixed-3-col grid. Should the skeleton track the live layout exactly, or is "approximate shape" sufficient?
