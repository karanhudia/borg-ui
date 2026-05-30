---
target: frontend/src/pages/DashboardV3.tsx
total_score: 29
p0_count: 0
p1_count: 3
timestamp: 2026-05-30T15-52-18Z
slug: frontend-src-pages-dashboardv3-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Banner, status dot, refresh, schedule pills all communicate state. Still no "last refreshed Xs ago" indicator next to the 30s polling. |
| 2 | Match System / Real World | 3 | Section headings are real sentence-case labels now (Recent activity, System resources). `BACKUP / CHECK / COMPACT / RESTORE` still arrive uppercase from i18n (RepositoryHealthPanel meta + health.tsx:213), but they read as labels not eyebrows. Borg paths and repo IDs still absent on this surface. |
| 3 | User Control and Freedom | 3 | Refresh, full log, repo click-through present. Repo card click goes to `/repositories` not the specific repo (RepositoryHealthPanel.tsx:113). |
| 4 | Consistency and Standards | 3 | The page now visually rhymes with the rest of the app. Card fills are still `rgba(255,255,255,0.05) / rgba(0,0,0,0.03)` from tokens.tsx:4 (not the standard `#ffffff` / `#27272a` paper used elsewhere); borders are hairline alpha rather than `theme.divider`. Mono on numbers is consistent. |
| 5 | Error Prevention | 3 | Read-only surface; low blast radius. |
| 6 | Recognition Rather Than Recall | 3 | `c` (cores), `G` (GB), `Xh/Xd/Xw/Xmo`, `arx` shorthand still used. Tooltips now carry full timestamps in DimStatusGrid (health.tsx:217). |
| 7 | Flexibility and Efficiency | 2 | Still no keyboard shortcuts, no filter on activity timeline, no sort/filter on repo cards, no bulk actions. Unchanged from prior pass. |
| 8 | Aesthetic and Minimalist Design | 3 | Glass blur, glow drop-shadows, pulse rings, and badge-pulse animation are gone (PulseDot is now a static dot at health.tsx:22-34; donut strokes have no filter; imminent schedules use a static ring at health.tsx:392). Borders carry status; type sizes floor at 0.6875rem. Two donuts still dominate the left column. |
| 9 | Error Recovery | 2 | Page-level Alert with retry (DashboardV3.tsx:77-97) is calm. Current failures block (DashboardV3.tsx:463-524) is now neutral: a thin top border, a normal-weight section heading, body-text mono on the error line, and the red is carried only by the `XCircle` icon plus repo name color is `T.textPrimary`. Per-tile failure isolation still missing: one React Query covers the whole page (DashboardV3.tsx:69-73). |
| 10 | Help and Documentation | 1 | Still no inline help for "dedup ratio", "1.23x", critical-vs-warning thresholds. Unchanged. |
| **Total** | | **29/40** | **Good — solid foundation, address weak areas** |

## Anti-Patterns Verdict

**LLM assessment**: The "AI ops command center" reading is gone. The quieter pass landed cleanly: surfaces are flat tinted panels with hairline borders, numbers do not glow, status dots do not pulse, and section headings sit at 0.8125rem / weight 600 in sentence case instead of 0.58rem tracked all-caps. The page now reads as an operations panel rather than a Dribbble shot. The two structural anti-patterns flagged previously as out of scope are still present (the two hero donuts, single-query failure isolation, no DE/ES growth audit), but they are visible now as architectural decisions, not as decorative slop. The header comment at the top of DashboardV3.tsx no longer markets the file as a "command center" surface, which matches the new register.

**Deterministic scan**: `detect.mjs` returned `[]` (exit 0) on `DashboardV3.tsx` and the `dashboard-v3/` directory. Same as prior run; detector did not catch the original textural slop and would not catch this either. The improvements here are not detectable by the bundled regex rules.

**Visual overlays**: Not available in this agent surface. Fallback signal: source-only review.

## Overall Impression

The quieter pass moved the dashboard from a 20/40 "Acceptable" to a 29/40 "Good". Glass, glow, pulse, drop-shadow, and tiny tracked uppercase eyebrows are gone, the failure block no longer reads as alarmist, and section headings are at a real type size. The biggest remaining gap is structural rather than textural: the two donut centerpieces still occupy the left column, the page is still a single React Query, and a few cosmetic frictions (the `repo.type.toUpperCase()` burned-in casing, the hand-rolled hex-alpha pattern, the dashboard's own card paper that diverges from MUI Card) read as separate visual product rather than composed primitives. None of those are P0 anymore.

## What's Working

- The new section header pattern (icon + sentence-case h6-equivalent at 0.8125rem weight 600, e.g. DashboardV3.tsx:252-261, :306-315, :420-429) is consistent across cards and exactly what PRODUCT.md's "no eyebrow" rule asks for.
- `PulseDot` (health.tsx:22-34) collapsed to a static 8px dot with a faint 2px alpha ring. Status reads at a glance without movement or glow, and color is no longer the only signal because the parent card also carries the status border.
- Current failures (DashboardV3.tsx:463-524) is now calm: thin neutral divider, sentence-case section heading, body-weight mono on the repo name, muted gray on the error string. No red wall, no red eyebrow.
- `DimStatusGrid` (health.tsx:178-241) labels at 0.75rem weight 600 with values at 0.8125rem mono is finally readable; tooltips carry the full timestamp via `formatDateTimeFull`. The 0.49rem and 0.58rem text from the prior pass is fully retired.
- `surface` is the named const now (DashboardV3.tsx:56-62), retiring the `glass` metaphor in code as well as in CSS.

## Priority Issues

- **[P1] The two donuts are still the visual centerpieces of the left column.** SuccessDonut at 148x148 with the rate in 1.5rem mono (charts.tsx:46-50) plus StorageDonut at 148x148 with the total size in 1.05rem mono (charts.tsx:132-141) still occupy the first and last cards of the left rail. PRODUCT.md anti-references include "hero metric cards with gradient accents and supporting stats"; gradients are gone, but the hero-metric template is still here. **Why it matters**: The 30-day success rate is rarely the answer to "what should I do right now"; the page promotes it above the failure list and the repo health grid. Operators with one failure overnight see "94%" before they see the failure. **Fix**: Demote both donuts to small inline figures inside the health banner (or to sparkline strips), promote `Repository health` and `Recent failures` to the visual top. **Command**: `/impeccable distill`.

- **[P1] One query covers the entire page; any field failing collapses the whole dashboard.** DashboardV3.tsx:69-73 fetches a single `DashboardOverview` and renders the error Alert (DashboardV3.tsx:77-97) when any part fails. If `activity_feed` 500s, `repository_health` and `system_metrics` go dark with it. PRODUCT.md principle 3 (Calm under failure) wants per-tile resilience. **Why it matters**: Operators open the dashboard at 3am when something is wrong; the most likely failure mode is a degraded sub-query, not a network outage. **Fix**: Split into per-section queries (summary + storage, repositories, activity_feed, upcoming_tasks, system_metrics) and degrade each tile independently. **Command**: `/impeccable harden`.

- **[P1] Repository health cards still face i18n string growth and repo-count walls.** RepositoryHealthPanel.tsx:95 still uses `repeat(3, 1fr)` at `lg`. Each card carries status dot + type chip + observe chip + schedule pill + name (truncated) + archive count + size + plan chip + plan name + 4-column DimStatusGrid. In DE/ES the dimension labels and schedule pill labels grow ~30%. `BACKUP / CHECK / COMPACT / RESTORE` come back uppercase from i18n today and still pass through `dimension-labels.*` translations; verify the longer locales fit. The hand-rolled `repo.type.toUpperCase()` at RepositoryHealthPanel.tsx:137 also forces casing that i18n cannot correct. **Why it matters**: PRODUCT.md commits to ~30% string growth tolerance; the current grid has no headroom. **Fix**: Provide a compact list/table layout above ~6 repos; move `repo.type` translation to i18n with locale-aware casing. **Command**: `/impeccable layout`.

## Persona Red Flags

**Alex (Power User)**: Still no keyboard shortcuts. No filter on the activity timeline (cannot isolate `prune` runs). The 30s polling has no visible "last refreshed Xs ago" stamp; Alex cannot tell if the data is fresh. Clicking a repo card opens `/repositories` (RepositoryHealthPanel.tsx:113), not the specific repo, so the click context is lost. Unchanged from prior critique.

**Sam (Accessibility-dependent)**: Major win on type size: the 0.49rem and 0.58rem text is gone; smallest values are now 0.6875rem on the type chip (RepositoryHealthPanel.tsx:141) and 0.75rem on most labels. The 0.6875rem chip text is still borderline at WCAG AA 3:1 large-text threshold; verify in both themes. No `prefers-reduced-motion` override is shipped, but the dashboard no longer relies on motion (pulse, badge-pulse, drop-shadow filters all removed), so the gap is much smaller than before; only the chart stroke transitions (charts.tsx:33, :118, :240) and skeleton fade-in (DashboardSkeleton.tsx:221) remain. The activity timeline SVG still uses `<title>` only inside `<circle>` (ActivityTimeline.tsx:122); screen readers still get nothing useful for keyboard nav.

**Riley (Stress tester)**: `UpcomingBackupsPanel` still returns `null` when empty (UpcomingBackupsPanel.tsx:16), leaving a gap in the left column. With 0 repos the donuts still render at full size with meaningless 0%. With 50+ repos the 3-column health grid still has no virtualization. Long repo names still truncate silently with no tooltip (RepositoryHealthPanel.tsx:184-187).

## Minor Observations

- `repo.type.toUpperCase()` (RepositoryHealthPanel.tsx:137) burns casing into the rendered string; i18n cannot fix it for languages that do not uppercase the same way.
- `cs.color + '30'` / `+ '25'` / `+ '12'` hex-alpha hack (DashboardV3.tsx:133, RepositoryHealthPanel.tsx:116, :144, etc.) is still in use; brittle if any token is moved to `rgb()`/`hsl()`.
- Plan pluralization is still hardcoded `'plan' / 'plans'` (RepositoryHealthPanel.tsx:208-210) and bypasses i18n.
- The dashboard's own card paper (`rgba(255,255,255,0.05)` / `rgba(0,0,0,0.03)` from tokens.tsx:4) is not the MUI `background.paper` used elsewhere in the product. Visually quieter now, but still a distinct surface vocabulary. Document or align.
- `lastBackupDate` computation (DashboardV3.tsx:110-114) still drops schedule timezones when sorting.
- `T.glow` is still exported in STATUS (tokens.tsx:41-44) but no consumer reads it anymore; dead token can be pruned.

## Questions to Consider

- If the two donuts were demoted to one-line stats inside the banner, would the page still feel complete?
- What does the dashboard show when `activity_feed` fails but the rest succeeds? Today: the whole page goes to an Alert. Is that the intended behavior?
- The card paper, mono numerics, and 14px radius are unique to this surface. Is that a deliberate "dashboard register" or an unintended visual fork from the rest of the app?
- With reduced motion now mostly satisfied by removal rather than by a media query, does the project still owe a global `prefers-reduced-motion` rule, or is the dashboard now compliant by construction?
