---
target: frontend/src/pages/DashboardV3.tsx
total_score: 20
p0_count: 2
p1_count: 3
timestamp: 2026-05-30T15-16-33Z
slug: frontend-src-pages-dashboardv3-tsx
---
## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 3 | Health banner, pulse dots, refresh button, schedule pills all communicate state clearly. Polling is silent though (no "last refreshed Xs ago"). |
| 2 | Match System / Real World | 2 | Real borg vocab is mostly hidden by abbreviations. `arx` (archive), `MEM`, `DISK`, `0.49rem` all-caps `FRESH / ARCHIVES / COMPACT / RESTORE` labels read as cryptic, not precise. Borg paths, repo IDs, encryption modes are absent on this surface. |
| 3 | User Control and Freedom | 3 | Refresh, full-log link, repo click-through all present. No way to pin the polling, hide a noisy card, or jump from a failed activity row to that job's run page. |
| 4 | Consistency and Standards | 2 | The dashboard reads as its own visual product separate from the rest of the app. JetBrains Mono everywhere, `radius: 14px`, glass + blur, glow drop-shadows, pulse animations, and 0.58–0.62rem uppercase eyebrows are not shared primitives anywhere else in the codebase (PRODUCT.md principle 4 violated). |
| 5 | Error Prevention | 3 | n/a — read-only surface, low blast radius. |
| 6 | Recognition Rather Than Recall | 2 | Cryptic abbreviations (`arx`, `c` for cores, `5h`, `4d`), all-caps tiny labels, and color-coded gauges with no inline thresholds force users to recall "what does amber CPU mean?". The legend for the activity timeline is good. |
| 7 | Flexibility and Efficiency | 1 | No keyboard shortcuts, no filtering of the activity timeline, no sort or filter on repo health cards, no bulk action. Power-user surface, novice-user affordances. |
| 8 | Aesthetic and Minimalist Design | 1 | Decorative `drop-shadow(0 0 8px ...)` on every SVG circle, `backdropFilter: blur(12px)` on every card, pulsing dots, glow halos, animated `badge-pulse` radial ring, indigo "today" highlight column in the timeline, gradient inset shadow on the banner. Every element earned its glow; none of them needed it. |
| 9 | Error Recovery | 2 | Top-level fetch error shows a generic `Dashboard unavailable` Alert with Retry. Per-tile failure (e.g. activity feed 500) has no isolated recovery. Currently a single React Query covers the whole page, so any partial failure blanks the dashboard. |
| 10 | Help and Documentation | 1 | No inline help for "what is `dedup ratio`", "what does `1.23×` mean", "what counts as critical vs warning". For a borg-literate user this is fine, but newcomers (a stated audience in PRODUCT.md) get nothing. |
| **Total** | | **20/40** | **Acceptable — significant improvements needed before users are happy** |

## Anti-Patterns Verdict

**LLM assessment**: This dashboard fails its own brief in a very specific way: it is the "AI ops command center" template applied at high fidelity. Every PRODUCT.md anti-reference is present somewhere on the page. The file's top comment literally names it: `"Void" ops command center — Real-Time Monitoring × Modern Cinema (ui-ux-pro-max) — Glass surface · Hairline border — Bento grid (asymmetric) + full-width activity timeline SVG`. That is the cliche, written down. Concretely: glassmorphism on every card (`backdropFilter: 'blur(12px)'`, `DashboardV3.tsx:64`), tiny tracked all-caps eyebrows above every section (DashboardV3.tsx:147–153, :202–208, :261–268, :317–323, :356–363, :433–440, :479–485, plus matching ones in RepositoryHealthPanel, UpcomingBackupsPanel, ArcGauge), pulse rings + glow drop-shadows on every SVG circle (health.tsx:21–33, charts.tsx:34, :122, :243), JetBrains Mono on numbers and labels, indigo "today" highlight column with the lowercase "today" label drifting into Linear/Vercel-clone territory, animated radial-gradient `badge-pulse` ring (health.tsx:402–408). The page does not look like Plex / Linear / Tailscale / Proxmox; it looks like a Dribbble shot of "what if Linear made an ops dashboard."

**Deterministic scan**: `detect.mjs` returned `[]` (clean, exit 0) on `DashboardV3.tsx` and the `dashboard-v3/` directory. No regex matches for the bundled AI-slop patterns. That is not exoneration. The detector targets specific lexical patterns (cream backgrounds, "supercharge", `01 / 02 / 03` scaffolding); the failures here are textural and compositional, which the deterministic scan does not see.

**Visual overlays**: Not available. Browser automation (Chrome DevTools / live-server injection) is not present in this agent's tool surface, so no `[Human]` tab overlay was produced. Fallback signal: source-only review.

## Overall Impression

The dashboard is the most striking surface in the app, and that is its problem. PRODUCT.md asks for "operational over aspirational" and "calm under failure"; what shipped is closer to "aspirational ops aesthetic." Density without rhythm, decoration without restraint. The single biggest opportunity is to strip the cinematic layer (glass, blur, glow, pulse, drop-shadow on numbers) and let the data carry the page. Everything else — copy, IA, error states — flows from that decision.

## What's Working

- The repository health cards (RepositoryHealthPanel.tsx:111–258) carry a lot of real information per row: status dot, type chip, observe-only chip, schedule badge, plan count, dimension grid. This is the most operational thing on the page and it earns its space.
- The `DashboardSkeleton` (DashboardSkeleton.tsx) is faithful to the real layout, including the staggered fade-in for repo cards. Loading state genuinely matches what's coming.
- The `ScheduleBadge` (health.tsx:263–425) is a quietly excellent component: four distinct states (manual / paused / scheduled / countdown) with a justified pulse for imminent runs. This is the kind of primitive PRODUCT.md asks for.

## Priority Issues

- **[P0] The dashboard violates almost every anti-reference in PRODUCT.md simultaneously.** The header comment literally calls it "Void ops command center" with "Glass surface" and "Modern Cinema." Glassmorphism (DashboardV3.tsx:60–67, UpcomingBackupsPanel.tsx:25–34), tiny tracked all-caps eyebrows (9+ instances cited above), glow drop-shadows on every SVG stroke (charts.tsx:34, :122, :243, health.tsx:32), pulse rings (health.tsx:21–45), animated radial pulse on imminent badges (health.tsx:402–408). **Why it matters**: First surface after login. Sets the brand promise for every screen that follows. **Fix**: Strip glass, blur, glow, drop-shadows on numeric values, and pulse-by-default. Keep one pulse, on the system-status dot only, and only when state is non-healthy. Replace tiny uppercase eyebrows with normal-case section headings at the body type scale. **Command**: `/impeccable quieter`.

- **[P0] Type is too small to read.** Section labels at 0.58rem (~9.3px) and 0.62rem in DashboardV3.tsx:147–151, :203, :264, :356, :436, dimension labels at 0.49rem (~7.8px) in health.tsx:214, dimension values at 0.58rem in health.tsx:234. WCAG 2.1 AA requires 4.5:1 contrast for body text; `T.textMuted` at 7.8px does not survive that target in either mode. **Why it matters**: PRODUCT.md commits to WCAG 2.1 AA. The repo dimension grid is unreadable for anyone over 35 without zoom. **Fix**: Floor section labels at 0.75rem / 12px and body labels at 0.875rem / 14px. Drop the all-caps treatment; sentence case at a real size reads better and survives DE/ES/IT growth. **Command**: `/impeccable typeset`.

- **[P1] Repository health cards become unreadable as repo count grows and as i18n strings expand.** 3-column grid at `lg` (RepositoryHealthPanel.tsx:96–98), each card crammed with status dot + type chip + observe chip + schedule pill + name (one line, ellipsis) + archive count + size + plan chip + plan name + 4-column dimension grid with vertical dividers. In German, `BACKUP / CHECK / COMPACT / RESTORE` stay (Englishisms in DE locale, lines 6–9 of the localized strings), but `AKTUELL` (FRESH) and `ARCHIVE` are longer; the 4-up grid at `lg` will start ellipsing dimension values in DE/ES. The dimension labels are already at 0.49rem; there is no headroom. **Why it matters**: Operators with 8+ repos hit a wall of 24+ tiny chips. PRODUCT.md principle: tolerate 30% string growth. **Fix**: Two layouts — a compact grid for ≤6 repos, a table view above that. Dimension labels need a real size or to live on hover. **Command**: `/impeccable layout`.

- **[P1] Calm-under-failure is partially broken.** The full-page Alert at DashboardV3.tsx:81–102 is fine, but `currentFailures` (DashboardV3.tsx:475–537) appended below the activity timeline mixes severity with chrome: red eyebrow, red XCircle icons, red error text wrapping with `wordBreak: 'break-all'`. The "borderTop" divider plus red typography stack reads alarmist for a dashboard that may show 1 transient failure overnight. There is no per-tile error state if `activity_feed` is the only field that failed. **Why it matters**: PRODUCT.md principle 3 (Calm under failure) is the most important screen archetype. **Fix**: Move "Recent failures" out of the timeline card into its own neutral panel. Replace red wall-of-text with a single status line per failure plus a "View run" action that routes to the job. Make per-tile error boundaries possible by splitting the React Query. **Command**: `/impeccable harden`.

- **[P1] Hero metric template is here, just dressed up.** The 30-day success donut (charts.tsx:5–60) with a giant 1.75rem percent in the middle and "good/total OK" sublabel beneath is exactly the consumer-SaaS hero-stat pattern PRODUCT.md calls out. Same for the storage donut showing `total_size` huge in the middle. The dashboard's job is "what's the state, what can I do"; "94%" with a glow halo is aspirational framing. **Why it matters**: Operationally, the 30-day rate is rarely actionable; the user wants to know which repo failed yesterday. **Fix**: Demote both donuts to small inline stats inside the health banner. Promote the failure list and the "needs attention" repos. **Command**: `/impeccable distill`.

## Persona Red Flags

**Alex (Power User, expert sysadmin)**: No keyboard shortcuts. No filter on activity timeline (can't isolate `prune` runs at 3am). The dashboard polls every 30s but there is no visible last-refresh timestamp, so Alex can't tell whether the data is fresh. The "Full log" button opens `/activity` and loses the dashboard context. Clicking a repo card opens `/repositories` with no deep link to the repo just clicked (RepositoryHealthPanel.tsx:114 `onClick={onOpenRepositories}`); Alex now has to find the same repo again.

**Sam (Accessibility-dependent)**: Body labels at 0.49rem (health.tsx:214) and 0.58rem section eyebrows fail WCAG AA at the project's stated target. Pulse animations (health.tsx:21–33 `pulse-ring`, :402–408 `badge-pulse`) have no `@media (prefers-reduced-motion: reduce)` fallback — PRODUCT.md explicitly requires this. Color is the primary signal on dimension status (the icon is at 9px, effectively invisible at glance). The activity timeline (ActivityTimeline.tsx:67–153) is an SVG with `aria-label`, but every dot is keyboard-unreachable; the only screen-reader content is `<title>{a.type} • {a.repository} • HH:mm</title>` inside `<circle>`, which most readers do not announce.

**Riley (Stress tester)**: Empty states are mostly absent — `UpcomingBackupsPanel` returns `null` (line 16) when empty, leaving a hole in the left column with no signal that there are no upcoming jobs. With 0 repos, the right column collapses to a tiny "No repositories" line (RepositoryHealthPanel.tsx:262–266) but the left donuts still render at full size showing meaningless 0%. With 50+ repos, the 3-column health grid scrolls forever with no pagination or virtualization. With a very long repo name in German (`postgres-replica-staging-01-frankfurt`), the name truncates silently (RepositoryHealthPanel.tsx:184–187 `ellipsis, nowrap`) and there's no tooltip to recover the full string.

## Minor Observations

- `lastBackupDate` (DashboardV3.tsx:116–119) uses `b!.getTime() - a!.getTime()` to find the most recent; that string already passes through `formatDistanceToNow` and the comparison drops the timezone the schedule lives in.
- `repo.type.toUpperCase()` (RepositoryHealthPanel.tsx:140) burns into the rendered string, which means i18n cannot fix it later.
- The `cs.color + '35'` / `+ '30'` / `+ '25'` pattern (DashboardV3.tsx:138, RepositoryHealthPanel.tsx:118 etc.) is a hex-alpha hack that only works if `cs.color` is `#rrggbb`. Robust but brittle.
- Hard-coded `'plan'` / `'plans'` pluralization at RepositoryHealthPanel.tsx:210–212 bypasses i18n entirely.
- The drawer width in Layout.tsx is `240` but the dashboard has its own `220px` left column — two values managing the same visual axis from different files.

## Questions to Consider

- What would the dashboard look like with zero gradients, zero glows, zero blurs, and Inter at real sizes? That is the version PRODUCT.md actually describes.
- Why does the dashboard's visual language exist nowhere else in the app? If the rest of the app does not use glass + JetBrains Mono + tiny eyebrows, who is this screen for?
- If you removed the success donut and the storage donut, would anyone notice? Would anyone be slower at their job?
- What would a "calm under failure" dashboard show on a day with 3 failed backups? Right now it shows red text under a red eyebrow. Is that actually calm?
