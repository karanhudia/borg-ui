# Phase 4: Archive Experience Implementation Plan

> **For agentic workers:** This plan is executed with
> `superpowers:executing-plans` and `superpowers:test-driven-development`,
> in the session the user opened, on the model section 13 names. **No
> subagents** (spec Appendix B, owner's decision). Steps use checkbox
> (`- [ ]`) syntax for tracking.

**Goal:** Replace the Archives page with a database-backed series heatmap,
add a full archive route with Changes, Files and Info tabs, add search and
per-path history, and gate every Pro surface behind `archive_history`.

**Architecture:** Frontend only. Every route this phase consumes already
exists and is tested from phases 1 and 2 (`app/api/archive_index.py`), and
`archive_history` is already registered in both feature registries and in
`docs/plan-content.json`. The work is types, an API client, components under
`frontend/src/components/archives/`, one new page, and `PlanGate` wrappers.
The one behavioural switch is that the Archives page stops calling
`BorgApiClient.listArchives()` (live `borg list`) and reads the `archives`
table instead.

**Tech Stack:** React 18, TypeScript, MUI 9, TanStack Query v5,
react-i18next, Vitest + Testing Library, Storybook 9, `react-window` for
virtualisation (already a dependency - verify before Task 6; if absent, use
the windowing approach in `BackupJobsTable.tsx` instead of adding a
dependency).

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
sections 10.3, 10.4, 10.5, 10.6, 11.1, 11.3, 11.4, and 9.2. Appendix B is
binding: never re-open a decision recorded there.

## Global Constraints

Copied verbatim from spec section 10 and AGENTS.md. Every task's
requirements implicitly include this section.

- All new components ship a Storybook story.
- Dialogs use `ResponsiveDialog` (`frontend/src/components/shared/ResponsiveDialog.tsx`).
- Selects that need rich rows use `RichSelect`
  (`frontend/src/components/shared/RichSelect.tsx`). Its real prop shape is
  `value: string`, `onChange: (value: string) => void`, `label: string`
  (required), `options: {value, primary, secondary?, icon?, group?}[]`.
- No left accent borders.
- Every string goes through `react-i18next` with keys added to **all four**
  of `frontend/src/locales/{en,de,es,it}.json`. The four files must stay
  key-parallel; CI enforces this.
- Types live in `frontend/src/types/operations.ts` and
  `frontend/src/types/archives.ts`.
- **No em dashes** anywhere: not in UI copy, i18n strings, or code comments.
  Use periods, commas or parentheses.
- Never build a user-visible string by transforming a translated value (for
  example `t(key).replace(...)`). Add a separate key instead.
- Backend datetimes can arrive without a UTC offset. Parse them with
  `parseBackendDate` from `frontend/src/utils/dateUtils.ts`, never bare
  `new Date(value)`.
- MUI 9 rejects `alignItems`, `flexWrap` and `fontWeight` as direct props on
  `Stack`/`Typography` in some overloads. Put layout and weight in `sx`.
- Do not write to a ref during render; the `react-hooks/refs` lint rule
  fails the build. Sync refs inside an effect.
- A component whose story renders a hook calling `useAuth` needs an
  `AuthProvider` in the story, or the Storybook Visual Report job times out.
  `build-storybook` does not render stories, so this only shows up in CI.
  Follow `frontend/src/components/BackgroundWorkTab.stories.tsx`.
- Verification before any commit: `npx vitest run`, `npm run lint`,
  `npm run typecheck`, and `npm run build-storybook` under Node 20.19+.

---

## File Structure

**Created**

| File | Responsibility |
| --- | --- |
| `frontend/src/types/archives.ts` | Response types for every `archive_index.py` route |
| `frontend/src/components/archives/ArchiveSeriesHeatmap.tsx` | One block per series, weeks as rows, days as columns |
| `frontend/src/components/archives/HeatmapLegend.tsx` | Count scale plus the Pro chip on outlier entries |
| `frontend/src/components/archives/SyncStateChip.tsx` | `sync_state` chip with rebuild link |
| `frontend/src/components/archives/ArchiveSearchField.tsx` | Search input plus results dialog |
| `frontend/src/pages/ArchiveDetail.tsx` | The `/archives/:repositoryId/:archiveId` route |
| `frontend/src/components/archives/ArchiveChangesTab.tsx` | Compare picker, filter chips, virtualised rows |
| `frontend/src/components/archives/ArchiveChangesPreview.tsx` | Inert fixture-rendered preview behind the Pro gate |
| `frontend/src/components/archives/ArchiveFilesTab.tsx` | Two-pane browse plus details layout |
| `frontend/src/components/archives/ArchiveFileDetailsPane.tsx` | Metadata, Restore, Download, history |
| `frontend/src/components/archives/FileHistoryPanel.tsx` | Per-path history from `/history` |
| `frontend/src/components/archives/ArchiveInfoTab.tsx` | Archive metadata in `RepositoryInfo` style |
| `frontend/src/components/activity/RunChainRow.tsx` | Follow-up chain beneath a parent operation row |

**Modified**

| File | Change |
| --- | --- |
| `frontend/src/services/api.ts:685-707` | Add the DB-backed archive methods to `archivesAPI` |
| `frontend/src/pages/Archives.tsx:120-128` | Read the DB route instead of `BorgApiClient.listArchives()`; add heatmap/list toggle, sync chip, search |
| `frontend/src/App.tsx:172-179` | Register the archive detail route |
| `frontend/src/components/ArchiveContentsDialog.tsx` | Add "Open full page" action |
| `frontend/src/pages/activity/ActivityFilters.tsx` | Category chips and trigger select |
| `frontend/src/components/BackupJobsTable.tsx` | Render `RunChainRow` under parent operations |
| `frontend/src/components/RepositoryCard.tsx` | "Operations" action linking to Activity with the repository pinned |
| `frontend/src/components/background-work/RebuildMenu.tsx` | Wrap the `history` option in `PlanGate disabled` |
| `frontend/src/locales/{en,de,es,it}.json` | Keys for all of the above |
| `docs/navigation.md` | Document the archive detail route |

---

## Task 1: Archive types and API client

**Files:**
- Create: `frontend/src/types/archives.ts`
- Modify: `frontend/src/services/api.ts:685-707`
- Test: `frontend/src/services/__tests__/api.test.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: every type below, plus `archivesAPI.listStored`,
  `archivesAPI.getHeatmap`, `archivesAPI.getArchive`, `archivesAPI.getChanges`,
  `archivesAPI.getPathHistory`, `archivesAPI.search`. Tasks 2 to 11 depend on
  these exact names.

Field names come from `app/api/archive_index.py`: `serialize_archive` at
line 56, `_serialize_change` at line 388, and the route returns at lines
141, 173, 407, 529, 634. Do not invent fields.

- [ ] **Step 1: Write `frontend/src/types/archives.ts`**

```typescript
// Mirrors the response shapes in app/api/archive_index.py (spec 9.2).

export type HistoryState = 'pending' | 'indexed' | 'skipped'
export type SyncState = 'fresh' | 'syncing' | 'stale' | 'never'
export type ChangeType = 'added' | 'removed' | 'modified' | 'summary'

export interface ArchiveRow {
  id: number
  repository_id: number
  borg_id: string
  name: string
  series: string
  start: string
  end: string | null
  duration_seconds: number | null
  nfiles: number | null
  original_size: number | null
  compressed_size: number | null
  deduplicated_size: number | null
  hostname: string | null
  username: string | null
  comment: string | null
  backup_operation_id: number | null
  history_state: HistoryState
  history_indexed_at: string | null
  history_rows: number | null
  history_truncated: boolean
  first_seen_at: string | null
  last_seen_at: string | null
}

export interface ArchiveListResponse {
  archives: ArchiveRow[]
  series: string[]
  sync_state: SyncState
  last_synced_at: string | null
  history_available: boolean
}

export interface HeatmapDay {
  date: string
  count: number
  deduplicated_size: number
  duration_seconds: number
  archive_ids: number[]
  anomalies: string[]
}

export interface HeatmapSeries {
  series: string
  days: HeatmapDay[]
  missed_days: string[]
  first: string | null
  last: string | null
}

export interface HeatmapResponse {
  since: string | null
  until: string | null
  series: HeatmapSeries[]
  flags_available: {
    missed_run: boolean
    size_outlier: boolean
    duration_outlier: boolean
  }
}

export interface ArchiveDetailResponse extends ArchiveRow {
  predecessor_id: number | null
  successor_id: number | null
  history_available: boolean
}

export interface ChangeRow {
  path: string
  change: ChangeType
  size_before: number | null
  size_after: number | null
  mode_changed: boolean
  owner_changed: boolean
  summary_count: number | null
}

export interface ChangeTotals {
  added: number
  removed: number
  modified: number
  summary: number
}

export interface ChangesResponse {
  archive_id: number
  compare_to_id: number | null
  changes: ChangeRow[]
  totals: ChangeTotals
  next_cursor: string | null
  incomplete: boolean
  unindexed_archive_ids: number[]
  history_state?: HistoryState
  history_truncated?: boolean
}

export interface HistoryEntry {
  archive_id: number
  archive_name: string
  series: string
  start: string
  change: ChangeType
  size_before: number | null
  size_after: number | null
  mode_changed: boolean
  owner_changed: boolean
}

export interface PresentRange {
  series: string
  from_archive_id: number
  to_archive_id: number | null
}

export interface PathHistoryResponse {
  path: string
  entries: HistoryEntry[]
  present: PresentRange[]
  present_in_latest: boolean
}

export interface SearchResult {
  path: string
  first_seen_archive_id: number
  first_seen: string
  last_seen_archive_id: number
  last_seen: string
  archive_count: number
  series: string
  last_change: ChangeType
}

export interface SearchResponse {
  query: string
  results: SearchResult[]
  truncated: boolean
}
```

- [ ] **Step 2: Write the failing API client test**

Append to `frontend/src/services/__tests__/api.test.ts`, matching the
existing describe-block style in that file:

```typescript
describe('archivesAPI stored-archive methods', () => {
  it('reads the database-backed archive list', async () => {
    await archivesAPI.listStored(7, { series: 'nightly' })
    expect(mockGet).toHaveBeenCalledWith('/repositories/7/archives', {
      params: { series: 'nightly' },
    })
  })

  it('requests changes with a compare target and change filters', async () => {
    await archivesAPI.getChanges(7, 12, { compare_to: 11, change: ['added', 'removed'] })
    expect(mockGet).toHaveBeenCalledWith(
      '/repositories/7/archives/12/changes',
      expect.objectContaining({
        params: { compare_to: 11, change: ['added', 'removed'] },
        paramsSerializer: { indexes: null },
      })
    )
  })

  it('reads history for one path', async () => {
    await archivesAPI.getPathHistory(7, 'home/karan/docs/invoices.xlsx')
    expect(mockGet).toHaveBeenCalledWith('/repositories/7/history', {
      params: { path: 'home/karan/docs/invoices.xlsx' },
    })
  })
})
```

- [ ] **Step 3: Run the test and confirm it fails**

Run: `npx vitest run src/services/__tests__/api.test.ts -t "stored-archive"`
Expected: FAIL, `archivesAPI.listStored is not a function`.

- [ ] **Step 4: Add the methods to `archivesAPI`**

Insert before the closing brace at `frontend/src/services/api.ts:707`.
`paramsSerializer: { indexes: null }` is required on `getChanges`: FastAPI's
`Query(list[str])` reads repeated keys, and axios would otherwise emit
`change[]=added`, which the route ignores.

```typescript
  listStored: (repositoryId: number, params?: { series?: string; since?: string; until?: string }) =>
    api.get<ArchiveListResponse>(`/repositories/${repositoryId}/archives`, { params }),
  getHeatmap: (repositoryId: number, params?: { since?: string; until?: string }) =>
    api.get<HeatmapResponse>(`/repositories/${repositoryId}/archives/heatmap`, { params }),
  getArchive: (repositoryId: number, archiveId: number) =>
    api.get<ArchiveDetailResponse>(`/repositories/${repositoryId}/archives/${archiveId}`),
  getChanges: (
    repositoryId: number,
    archiveId: number,
    params?: {
      compare_to?: number
      path_prefix?: string
      change?: ChangeType[]
      limit?: number
      cursor?: string
    }
  ) =>
    api.get<ChangesResponse>(`/repositories/${repositoryId}/archives/${archiveId}/changes`, {
      params,
      paramsSerializer: { indexes: null },
    }),
  getPathHistory: (repositoryId: number, path: string) =>
    api.get<PathHistoryResponse>(`/repositories/${repositoryId}/history`, { params: { path } }),
  search: (repositoryId: number, q: string, limit?: number) =>
    api.get<SearchResponse>(`/repositories/${repositoryId}/search`, { params: { q, limit } }),
```

Add the type imports alongside the existing `types/operations` import block
at `frontend/src/services/api.ts:25`.

- [ ] **Step 5: Run the tests and confirm they pass**

Run: `npx vitest run src/services/__tests__/api.test.ts`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/archives.ts frontend/src/services/api.ts \
        frontend/src/services/__tests__/api.test.ts
git commit -m "feat(archives): add stored-archive types and API client"
```

---

## Task 2: SyncStateChip

**Files:**
- Create: `frontend/src/components/archives/SyncStateChip.tsx`
- Create: `frontend/src/components/archives/SyncStateChip.stories.tsx`
- Test: `frontend/src/components/archives/__tests__/SyncStateChip.test.tsx`
- Modify: `frontend/src/locales/{en,de,es,it}.json`

**Interfaces:**
- Consumes: `SyncState`, `parseBackendDate` from Task 1 and `dateUtils`.
- Produces: `<SyncStateChip state={SyncState} lastSyncedAt={string | null}
  onRebuild={() => void} />`. Task 9 mounts it.

Spec 10.3: "Synced 2 min ago", "Syncing", or "Not indexed yet" with a
rebuild link.

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import SyncStateChip from '../SyncStateChip'

describe('SyncStateChip', () => {
  it('shows how long ago a fresh sync completed', () => {
    render(
      <SyncStateChip
        state="fresh"
        lastSyncedAt={new Date(Date.now() - 120_000).toISOString()}
        onRebuild={vi.fn()}
      />
    )
    expect(screen.getByText(/synced/i)).toBeInTheDocument()
  })

  it('offers a rebuild action when the repository was never indexed', () => {
    const onRebuild = vi.fn()
    render(<SyncStateChip state="never" lastSyncedAt={null} onRebuild={onRebuild} />)
    expect(screen.getByText(/not indexed yet/i)).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    expect(onRebuild).toHaveBeenCalled()
  })

  it('shows no rebuild action while a sync is running', () => {
    render(<SyncStateChip state="syncing" lastSyncedAt={null} onRebuild={vi.fn()} />)
    expect(screen.getByText(/syncing/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /rebuild/i })).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/archives/__tests__/SyncStateChip.test.tsx`
Expected: FAIL, cannot resolve `../SyncStateChip`.

- [ ] **Step 3: Add the locale keys**

Add to each of the four locale files under `archives.sync`. English:

```json
"sync": {
  "fresh": "Synced {{ago}}",
  "syncing": "Syncing",
  "stale": "Sync is out of date",
  "never": "Not indexed yet",
  "rebuild": "Rebuild"
}
```

German: `"Synchronisiert {{ago}}"`, `"Wird synchronisiert"`,
`"Synchronisierung ist veraltet"`, `"Noch nicht indiziert"`,
`"Neu aufbauen"`.
Spanish: `"Sincronizado {{ago}}"`, `"Sincronizando"`,
`"La sincronización está desactualizada"`, `"Aún no indexado"`,
`"Reconstruir"`.
Italian: `"Sincronizzato {{ago}}"`, `"Sincronizzazione in corso"`,
`"La sincronizzazione non è aggiornata"`, `"Non ancora indicizzato"`,
`"Ricostruisci"`.

- [ ] **Step 4: Write the component**

```typescript
import { Box, Chip, Link as MuiLink } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { parseBackendDate } from '../../utils/dateUtils'
import type { SyncState } from '../../types/archives'

interface SyncStateChipProps {
  state: SyncState
  lastSyncedAt: string | null
  onRebuild: () => void
}

export default function SyncStateChip({ state, lastSyncedAt, onRebuild }: SyncStateChipProps) {
  const { t } = useTranslation()
  const label =
    state === 'fresh' && lastSyncedAt
      ? t('archives.sync.fresh', {
          ago: formatDistanceToNow(parseBackendDate(lastSyncedAt), { addSuffix: true }),
        })
      : t(`archives.sync.${state}`)

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Chip size="small" label={label} />
      {state !== 'syncing' && (
        <MuiLink component="button" type="button" variant="caption" onClick={onRebuild}>
          {t('archives.sync.rebuild')}
        </MuiLink>
      )}
    </Box>
  )
}
```

- [ ] **Step 5: Run the test and confirm it passes**

Run: `npx vitest run src/components/archives/__tests__/SyncStateChip.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 6: Write the story**

One story per state: `Fresh`, `Syncing`, `Stale`, `Never`. No providers are
needed; the component uses only `useTranslation`.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/archives/SyncStateChip.tsx \
        frontend/src/components/archives/SyncStateChip.stories.tsx \
        frontend/src/components/archives/__tests__/SyncStateChip.test.tsx \
        frontend/src/locales
git commit -m "feat(archives): add SyncStateChip"
```

---

## Task 3: ArchiveSeriesHeatmap and HeatmapLegend

**Files:**
- Create: `frontend/src/components/archives/ArchiveSeriesHeatmap.tsx`
- Create: `frontend/src/components/archives/HeatmapLegend.tsx`
- Create: stories for both
- Test: `frontend/src/components/archives/__tests__/ArchiveSeriesHeatmap.test.tsx`

**Interfaces:**
- Consumes: `HeatmapResponse`, `HeatmapSeries`, `HeatmapDay` (Task 1).
- Produces: `<ArchiveSeriesHeatmap data={HeatmapResponse}
  onSelectDay={(day: HeatmapDay) => void} />` and `<HeatmapLegend
  flagsAvailable={HeatmapResponse['flags_available']} />`. Task 9 mounts both.

Spec 10.3: one block per series, weeks as rows, days as columns, cells
coloured by count and outlined for anomalies, hover shows size and duration,
click opens the archive route. Spec 11.3: outlier legend entries carry a
small Pro chip using `PLAN_LABEL` and `PLAN_COLOR`; the flags themselves are
not gated in the UI because the API omits them.

- [ ] **Step 1: Write the failing test**

```typescript
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import ArchiveSeriesHeatmap from '../ArchiveSeriesHeatmap'
import type { HeatmapResponse } from '../../../types/archives'

const day = (date: string, overrides = {}) => ({
  date,
  count: 1,
  deduplicated_size: 41_200_000_000,
  duration_seconds: 7860,
  archive_ids: [12],
  anomalies: [],
  ...overrides,
})

const data: HeatmapResponse = {
  since: '2026-08-01',
  until: '2026-09-04',
  series: [
    {
      series: 'nightly',
      days: [day('2026-09-01'), day('2026-09-02', { count: 0, archive_ids: [] })],
      missed_days: ['2026-09-02'],
      first: '2026-08-01T02:00:00Z',
      last: '2026-09-01T02:00:00Z',
    },
  ],
  flags_available: { missed_run: true, size_outlier: false, duration_outlier: false },
}

describe('ArchiveSeriesHeatmap', () => {
  it('renders one block per series', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByText('nightly')).toBeInTheDocument()
  })

  it('opens the archive for a day that has one', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-01'))
    expect(onSelectDay).toHaveBeenCalledWith(expect.objectContaining({ archive_ids: [12] }))
  })

  it('does not select an empty day', () => {
    const onSelectDay = vi.fn()
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={onSelectDay} />)
    fireEvent.click(screen.getByTestId('heatmap-day-nightly-2026-09-02'))
    expect(onSelectDay).not.toHaveBeenCalled()
  })

  it('marks a missed day so it reads as a gap rather than an empty cell', () => {
    render(<ArchiveSeriesHeatmap data={data} onSelectDay={vi.fn()} />)
    expect(screen.getByTestId('heatmap-day-nightly-2026-09-02')).toHaveAttribute(
      'data-missed',
      'true'
    )
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `npx vitest run src/components/archives/__tests__/ArchiveSeriesHeatmap.test.tsx`
Expected: FAIL, cannot resolve `../ArchiveSeriesHeatmap`.

- [ ] **Step 3: Add the locale keys**

Under `archives.heatmap` in all four files. English:

```json
"heatmap": {
  "none": "No archives",
  "archives_one": "{{count}} archive",
  "archives_other": "{{count}} archives",
  "missed": "Expected a run, none found",
  "sizeOutlier": "Unusually small",
  "durationOutlier": "Unusually slow",
  "legendLess": "Less",
  "legendMore": "More",
  "tooltip": "{{count}} on {{date}} · {{size}} · {{duration}}"
}
```

Translate each into de, es and it. Keep the `_one`/`_other` plural suffixes;
i18next resolves them by count.

- [ ] **Step 4: Write `HeatmapLegend`**

Renders the count scale swatches from `legendLess` to `legendMore`, then one
row per anomaly kind: `missed` always, `sizeOutlier` and `durationOutlier`
each followed by a Pro chip when the matching `flags_available` entry is
false. Import `PLAN_LABEL` and `PLAN_COLOR` from wherever
`frontend/src/core/plan.ts` (or the module `PlanGate.tsx` imports them from)
exports them; grep for `PLAN_LABEL` before writing this and use the real
path.

- [ ] **Step 5: Write `ArchiveSeriesHeatmap`**

Structure per series: a `Typography` with the series name, then a grid.
Group `days` into ISO weeks (Monday first), one row per week, seven columns.
Each cell is a `Box` with:

- `data-testid={`heatmap-day-${series}-${day.date}`}`
- `data-missed={missed_days.includes(day.date)}`
- background from a five-step count scale using `alpha(theme.palette.primary.main, n)`
- `outline` when `day.anomalies.length > 0`
- `role="button"` and `tabIndex={0}` only when `day.archive_ids.length > 0`,
  calling `onSelectDay(day)` on click and on Enter or Space
- a `Tooltip` with `archives.heatmap.tooltip`, formatting size with the
  existing `formatBytes` from `utils/dateUtils.ts` and duration with the
  existing duration helper in that file

Cells with no archive get no `role`, no `tabIndex` and no click handler, so
the third test passes.

- [ ] **Step 6: Run the tests and confirm they pass**

Run: `npx vitest run src/components/archives/__tests__/ArchiveSeriesHeatmap.test.tsx`
Expected: PASS, 4 tests.

- [ ] **Step 7: Write the stories**

`ArchiveSeriesHeatmap`: `Default` (two series, a gap, an outlier),
`SingleSeries`, `Empty`. `HeatmapLegend`: `Community`
(`size_outlier: false`, showing the Pro chips) and `Pro` (all true).

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/archives frontend/src/locales
git commit -m "feat(archives): add series heatmap and legend"
```

---

## Task 4: ArchiveSearchField with the Pro gate

**Files:**
- Create: `frontend/src/components/archives/ArchiveSearchField.tsx`
- Create: `frontend/src/components/archives/ArchiveSearchField.stories.tsx`
- Test: `frontend/src/components/archives/__tests__/ArchiveSearchField.test.tsx`

**Interfaces:**
- Consumes: `archivesAPI.search`, `SearchResponse` (Task 1).
- Produces: `<ArchiveSearchField repositoryId={number} />`. Task 9 mounts it.

Spec 10.3: results in a `ResponsiveDialog` list with "present in latest" and
"last seen" columns. Spec 11.3: `PlanGate` with `disabled`,
`surface="archives"`, `operation="search"`.

- [ ] **Step 1: Write the failing test**

Mock `archivesAPI` and `usePlan`. The global test setup at
`frontend/src/test/setup.ts` already mocks `usePlan` with `can: () => true`,
so the unlocked path is the default; override the mock in the locked test.

```typescript
describe('ArchiveSearchField', () => {
  it('opens a dialog listing matches with their last seen archive', async () => {
    ;(archivesAPI.search as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        query: 'invoices',
        results: [
          {
            path: 'home/karan/docs/invoices.xlsx',
            first_seen_archive_id: 3,
            first_seen: '2026-08-24T02:00:00Z',
            last_seen_archive_id: 12,
            last_seen: '2026-09-02T02:00:00Z',
            archive_count: 7,
            series: 'nightly',
            last_change: 'modified',
          },
        ],
        truncated: false,
      },
    })
    renderField()
    fireEvent.change(screen.getByRole('textbox'), { target: { value: 'invoices' } })
    fireEvent.submit(screen.getByRole('search'))
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.getByText('home/karan/docs/invoices.xlsx')).toBeInTheDocument()
  })

  it('disables the field on a plan without the history feature', () => {
    renderField({ can: () => false })
    expect(screen.getByRole('textbox')).toBeDisabled()
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Expected: FAIL, cannot resolve `../ArchiveSearchField`.

- [ ] **Step 3: Add the locale keys**

Under `archives.search`: `placeholder` ("Search files in this repository"),
`title` ("Search results"), `columnPath`, `columnLastSeen`,
`columnPresent`, `present` ("In latest"), `absent` ("Not in latest"),
`empty` ("No matching files"), `truncated` ("Showing the first
{{count}} matches"). Translate into de, es and it.

- [ ] **Step 4: Write the component**

A `<form role="search">` wrapping a `TextField`, wrapped in `PlanGate` with
`feature="archive_history"`, `disabled`, `surface="archives"`,
`operation="search"`. Submitting runs a `useQuery` with
`enabled: submitted.length > 0` and opens a `ResponsiveDialog` holding a
`Table` with the three columns. `present_in_latest` per result is
`result.last_seen_archive_id === newestArchiveId`; the response has no such
boolean per row, so pass the newest archive id in as a prop from Task 9
rather than inventing a field.

Revise the produced interface to
`<ArchiveSearchField repositoryId={number} newestArchiveId={number | null} />`
and use that signature in Task 9.

- [ ] **Step 5: Run the tests and confirm they pass**

Expected: PASS, 2 tests.

- [ ] **Step 6: Write the story**

`Unlocked` and `Locked`, following `PlanGate.stories.tsx` for how the plan
is stubbed.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/archives frontend/src/locales
git commit -m "feat(archives): add gated archive search field"
```

---

## Task 5: Archive detail route shell and Info tab

**Files:**
- Create: `frontend/src/pages/ArchiveDetail.tsx`
- Create: `frontend/src/components/archives/ArchiveInfoTab.tsx`
- Create: stories for both
- Test: `frontend/src/pages/__tests__/ArchiveDetail.test.tsx`
- Modify: `frontend/src/App.tsx:172-179`, `docs/navigation.md`

**Interfaces:**
- Consumes: `archivesAPI.getArchive`, `ArchiveDetailResponse` (Task 1).
- Produces: the route `/archives/:repositoryId/:archiveId`, and
  `<ArchiveInfoTab archive={ArchiveDetailResponse} />`. Tasks 6 and 7 fill
  the other two tabs.

Spec 10.4: header with name, series, start, duration, sizes, and
`[Restore] [Mount] [Delete]` using the existing dialogs
(`RestoreWizard.tsx`, `MountArchiveDialog.tsx`, `DeleteArchiveDialog.tsx`).
Tabs: Changes, Files, Info.

- [ ] **Step 1: Write the failing test**

```typescript
describe('ArchiveDetail', () => {
  it('shows the archive header and defaults to the Changes tab', async () => {
    renderRoute('/archives/7/12')
    expect(await screen.findByText('nas-2026-09-02T02:00')).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /changes/i })).toHaveAttribute('aria-selected', 'true')
  })

  it('switches to the Info tab', async () => {
    renderRoute('/archives/7/12')
    fireEvent.click(await screen.findByRole('tab', { name: /info/i }))
    expect(await screen.findByText(/nightly/)).toBeInTheDocument()
  })

  it('reports an archive that cannot be loaded', async () => {
    ;(archivesAPI.getArchive as ReturnType<typeof vi.fn>).mockRejectedValue(new Error('nope'))
    renderRoute('/archives/7/999')
    expect(await screen.findByText(/could not be loaded/i)).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run it and confirm it fails**

Expected: FAIL, cannot resolve `../ArchiveDetail`.

- [ ] **Step 3: Add the locale keys**

Under `archives.detail`: `tabChanges`, `tabFiles`, `tabInfo`, `series`,
`started`, `duration`, `originalSize`, `compressedSize`,
`deduplicatedSize`, `files`, `hostname`, `username`, `comment`,
`loadFailed` ("This archive could not be loaded."). The Changes tab label
carries counts, so add `tabChangesWithCounts`: `"Changes (+{{added}}
−{{removed}} ~{{modified}})"`. Translate into de, es and it.

- [ ] **Step 4: Write `ArchiveInfoTab`**

A definition list of the `ArchiveRow` fields, formatted with `formatBytes`
and `parseBackendDate`. Follow the metadata layout already used in
`RepositoryInfo`; grep for that component and match its markup rather than
inventing one.

- [ ] **Step 5: Write `ArchiveDetail`**

Reads `repositoryId` and `archiveId` from `useParams`, coerces both with
`Number(...)`, and guards against `NaN` by rendering the load-failure alert.
`useQuery` on `['archive', repositoryId, archiveId]`. Renders the header,
the three action buttons wired to the existing dialogs, and an MUI `Tabs`
with the tab held in a `?tab=` search param so the tab survives a reload.
Changes and Files render placeholders in this task; Tasks 6 and 7 replace
them.

- [ ] **Step 6: Register the route**

In `frontend/src/App.tsx`, directly after the `/archives` route that ends at
line 179:

```tsx
        <Route
          path="/archives/:repositoryId/:archiveId"
          element={
            <ProtectedRoute requiredTab="archives">
              <ArchiveDetail />
            </ProtectedRoute>
          }
        />
```

- [ ] **Step 7: Run the tests and confirm they pass**

Run: `npx vitest run src/pages/__tests__/ArchiveDetail.test.tsx`
Expected: PASS, 3 tests.

- [ ] **Step 8: Document the route**

Add the archive detail route to `docs/navigation.md` beside the existing
`/archives` entry.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/pages/ArchiveDetail.tsx frontend/src/components/archives \
        frontend/src/App.tsx docs/navigation.md frontend/src/locales \
        frontend/src/pages/__tests__/ArchiveDetail.test.tsx
git commit -m "feat(archives): add archive detail route with Info tab"
```

---

## Task 6: ArchiveChangesTab behind the Pro gate

**Files:**
- Create: `frontend/src/components/archives/ArchiveChangesTab.tsx`
- Create: `frontend/src/components/archives/ArchiveChangesPreview.tsx`
- Create: stories for both
- Test: `frontend/src/components/archives/__tests__/ArchiveChangesTab.test.tsx`
- Modify: `frontend/src/pages/ArchiveDetail.tsx`

**Interfaces:**
- Consumes: `archivesAPI.getChanges`, `ChangesResponse`, `ChangeRow`,
  `ChangeTotals`, `ArchiveDetailResponse` (Tasks 1 and 5).
- Produces: `<ArchiveChangesTab repositoryId={number}
  archive={ArchiveDetailResponse} />`.

Spec 10.4: `RichSelect` compare picker, change-type filter chips,
virtualised rows grouped by top-level directory, truncated banner when
`history_truncated`, and an explanatory empty state with a rebuild link when
`history_state` is `pending` or `skipped`. Spec 11.3: `PlanGate` with
`preview` set to a static inert sample rendered from fixture data,
`surface="archive_detail"`, `operation="view_changes"`.

- [ ] **Step 1: Write the failing test**

```typescript
describe('ArchiveChangesTab', () => {
  it('lists changes with their size transition', async () => { /* modified row shows 374 KB -> 412 KB */ })
  it('filters to a single change type when its chip is toggled', async () => { /* expects change: ['added'] in the request params */ })
  it('re-requests changes against the chosen compare target', async () => { /* expects compare_to: 9 */ })
  it('explains a pending archive instead of showing an empty list', async () => { /* history_state pending -> rebuild link, no table */ })
  it('warns when the index was truncated', async () => { /* history_truncated -> banner */ })
  it('shows the inert preview to a plan without the feature', () => { /* can: () => false */ })
})
```

Write each body out in full following the mocking style established in
Task 4; do not leave the comment placeholders in the committed test.

- [ ] **Step 2: Run it and confirm it fails**

Expected: FAIL, cannot resolve `../ArchiveChangesTab`.

- [ ] **Step 3: Add the locale keys**

Under `archives.changes`: `compareWith`, `previous` ("previous"), `net`,
`added`, `removed`, `modified`, `summaryRow` ("{{count}} more in
{{path}}"), `truncated` ("This archive's index was truncated at the row
cap, so some paths are summarised."), `pending` ("This archive has not been
indexed yet."), `skipped` ("History indexing was skipped for this
archive."), `rebuildLink` ("Rebuild the history index"), `empty` ("No
changes between these archives."). Translate into de, es and it.

- [ ] **Step 4: Write `ArchiveChangesPreview`**

A module-level fixture array of six `ChangeRow` values and a render of the
same row markup with every interactive element removed. It takes no props
and issues no requests, so it is safe behind the gate.

- [ ] **Step 5: Write `ArchiveChangesTab`**

- Compare picker: `RichSelect` whose options are the archives in the same
  series older than this one, fetched with `archivesAPI.listStored`. The
  default is `archive.predecessor_id`, labelled with `previous`.
- Filter chips: one per `ChangeType` except `summary`, toggling entries in a
  `change[]` array passed to `getChanges`.
- Rows: group by first path segment, virtualising with the same approach
  `BackupJobsTable.tsx` already uses. A `summary` row renders `summaryRow`
  with its `summary_count`.
- Banners: `truncated` when `history_truncated`; the `pending` or `skipped`
  empty state, with a rebuild link calling `archivesAPI.rebuild(repositoryId,
  'history')`, when `history_state` is not `indexed`.
- Wrap the whole tab in `PlanGate` with `feature="archive_history"`,
  `preview={<ArchiveChangesPreview />}`, `surface="archive_detail"`,
  `operation="view_changes"`.

- [ ] **Step 6: Run the tests and confirm they pass**

Expected: PASS, 6 tests.

- [ ] **Step 7: Mount it in `ArchiveDetail`**

Replace the Changes placeholder from Task 5. Feed the tab label from the
`totals` in the response using `tabChangesWithCounts`.

- [ ] **Step 8: Write the stories**

`Default`, `Truncated`, `Pending`, `Locked`.

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/archives frontend/src/pages/ArchiveDetail.tsx \
        frontend/src/locales
git commit -m "feat(archives): add gated Changes tab with compare picker"
```

---

## Task 7: Files tab, details pane and file history

**Files:**
- Create: `frontend/src/components/archives/ArchiveFilesTab.tsx`
- Create: `frontend/src/components/archives/ArchiveFileDetailsPane.tsx`
- Create: `frontend/src/components/archives/FileHistoryPanel.tsx`
- Create: stories for all three
- Test: one `__tests__` file per component
- Modify: `frontend/src/pages/ArchiveDetail.tsx`

**Interfaces:**
- Consumes: `archivesAPI.getPathHistory`, `PathHistoryResponse`,
  `HistoryEntry` (Task 1); the existing `ArchivePathSelector.tsx` and
  `RestoreWizard.tsx`.
- Produces: `<ArchiveFilesTab repositoryId={number}
  archive={ArchiveDetailResponse} />`.

Spec 10.4: `ArchivePathSelector` browsing on the left, a new details pane on
the right with metadata, `[Restore]`, `[Download]` and a `FileHistoryPanel`.
Below the `md` breakpoint the pane becomes a `ResponsiveDialog` bottom
sheet. Nothing is selected on open; the pane shows folder metadata for the
current path. Multi-select keeps the pane on the last clicked file and the
footer shows the selection count with a restore action opening
`RestoreWizard` preselected. Spec 11.3: the history panel uses `PlanGate`
with `disabled`, `surface="archive_files"`, `operation="view_history"`.

- [ ] **Step 1: Write the three failing tests**

`FileHistoryPanel`: renders one row per entry with its size and change,
renders "Not present in {{count}} older archives" from the `present`
ranges, renders a "Restore this" action per entry, and renders disabled
when the plan lacks the feature.

`ArchiveFileDetailsPane`: shows folder metadata when `selectedPath` is
null, shows file metadata when set, and calls `onRestore` and `onDownload`.

`ArchiveFilesTab`: shows the footer only when there is a selection, and the
footer count reflects the number selected.

- [ ] **Step 2: Run them and confirm they fail**

Expected: FAIL, unresolved imports for all three.

- [ ] **Step 3: Add the locale keys**

Under `archives.files`: `size`, `modified`, `owner`, `permissions`,
`restore`, `download`, `history`, `firstSeen`, `unchanged`, `changed`,
`restoreThis`, `notPresent` ("Not present in {{count}} older archives"),
`selected` ("{{count}} selected ({{size}})"), `restoreSelection`,
`searchInArchive`. Translate into de, es and it.

- [ ] **Step 4: Write `FileHistoryPanel`**

`useQuery` on `['path-history', repositoryId, path]`, enabled only when
`path` is set. One row per entry, newest first, showing date, size and the
change word. `changed` rows show the signed delta between `size_before` and
`size_after`. The oldest entry with `change === 'added'` renders
`firstSeen`. Wrap in `PlanGate` with `disabled`,
`surface="archive_files"`, `operation="view_history"`.

- [ ] **Step 5: Write `ArchiveFileDetailsPane`**

Props: `repositoryId`, `archive`, `selectedPath: string | null`,
`selectedEntry` (the row object `ArchivePathSelector` already yields; grep
that file for its item type and reuse it rather than declaring a new one),
`onRestore`, `onDownload`. Renders metadata, the two buttons, and
`FileHistoryPanel`.

- [ ] **Step 6: Write `ArchiveFilesTab`**

Two-column `Box` layout above `md`, collapsing to browse-only with the pane
in a `ResponsiveDialog` below it (`useMediaQuery(theme.breakpoints.down('md'))`).
Holds `selectedPaths: string[]` and `lastClickedPath: string | null`.
The footer appears when `selectedPaths.length > 0` and opens `RestoreWizard`
preselected to those paths.

- [ ] **Step 7: Run the tests and confirm they pass**

Expected: PASS across the three files.

- [ ] **Step 8: Mount it in `ArchiveDetail`**

Replace the Files placeholder from Task 5.

- [ ] **Step 9: Write the stories**

`FileHistoryPanel`: `Unlocked`, `Locked`. `ArchiveFileDetailsPane`:
`Folder`, `File`. `ArchiveFilesTab`: `Default`, `MultiSelect`.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/archives frontend/src/pages/ArchiveDetail.tsx \
        frontend/src/locales
git commit -m "feat(archives): add Files tab with details pane and file history"
```

---

## Task 8: Files tab keyboard navigation

**Files:**
- Modify: `frontend/src/components/archives/ArchiveFilesTab.tsx`
- Test: `frontend/src/components/archives/__tests__/ArchiveFilesTab.test.tsx`

**Interfaces:**
- Consumes: Task 7's component.
- Produces: no new exports.

Spec 10.6: arrow keys move selection, Enter opens a folder, Backspace goes
up, `/` focuses search, `r` opens restore for the selection.

- [ ] **Step 1: Write the failing tests**

One test per binding: ArrowDown moves the active row, Enter on a folder
descends, Backspace on a nested path ascends, `/` moves focus to the search
input, and `r` with a selection opens the restore wizard. Assert that `/`
and `r` do nothing while focus is inside a text input, so typing a path
containing a slash is not hijacked.

- [ ] **Step 2: Run them and confirm they fail**

Expected: FAIL, the key handlers do not exist.

- [ ] **Step 3: Implement the handler**

A single `onKeyDown` on the browse pane container. Guard every binding with
a check that `document.activeElement` is not an `input` or `textarea` before
treating a printable key as a shortcut. `preventDefault()` on Backspace so
the browser does not navigate back.

- [ ] **Step 4: Run the tests and confirm they pass**

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/archives
git commit -m "feat(archives): add keyboard navigation to the Files tab"
```

---

## Task 9: Archives page switches to the database

**Files:**
- Modify: `frontend/src/pages/Archives.tsx:120-128`
- Modify: `frontend/src/components/ArchiveContentsDialog.tsx`
- Test: `frontend/src/pages/__tests__/Archives.test.tsx`

**Interfaces:**
- Consumes: Tasks 1 to 4.
- Produces: no new exports.

Spec 10.3 and 9.2. Appendix B, phase 2 entry: the live `borg list` route
already moved to `/repositories/{id}/archives/live`, and
`repositoriesAPI.listRepositoryArchives` at `frontend/src/services/api.ts:937`
already points there. This task changes which of the two the page calls.

- [ ] **Step 1: Write the failing tests**

The page reads `archivesAPI.listStored` rather than
`BorgApiClient.listArchives`; the heatmap renders by default; the List
toggle switches to `ArchivesList` and persists to `localStorage` under
`archives-view-mode`; the persisted preference is honoured on mount; the
sync chip renders with the response's `sync_state`.

- [ ] **Step 2: Run them and confirm they fail**

Expected: FAIL, the page still calls the live route.

- [ ] **Step 3: Add the locale keys**

Under `archives.view`: `heatmap` ("Heatmap"), `list` ("List"). Translate
into de, es and it.

- [ ] **Step 4: Rewrite the archives query**

Replace the `useQuery` at `frontend/src/pages/Archives.tsx:120-128` with one
keyed `['repository-archives-stored', selectedRepositoryId]` calling
`archivesAPI.listStored`. Keep the existing 423 lock-error effect below it
working: that effect reads `error.response.status`, which the axios client
still provides.

- [ ] **Step 5: Add the view toggle, sync chip and search**

A `ToggleButtonGroup` with the two modes, initialised from
`localStorage.getItem('archives-view-mode')` and written on change,
following the persistence pattern already in `ArchivesList.tsx:62-90`.
Mount `SyncStateChip` beside the selector, `ArchiveSearchField` above the
heatmap with `newestArchiveId` from the first row of `archives`, and
`ArchiveSeriesHeatmap` with `onSelectDay` navigating to
`/archives/{repositoryId}/{day.archive_ids[0]}`.

- [ ] **Step 6: Add "Open full page" to `ArchiveContentsDialog`**

A button in the dialog actions navigating to the archive route and closing
the dialog. The dialog currently identifies archives by name; it needs the
numeric id. Look up the row by `borg_id` from the stored list already in the
page's query cache, and hide the action when no match is found rather than
guessing an id.

- [ ] **Step 7: Run the tests and confirm they pass**

Expected: PASS. Also run the full suite here, since this task changes a page
many other tests render: `npx vitest run`.

- [ ] **Step 8: Commit**

```bash
git add frontend/src/pages/Archives.tsx frontend/src/components/ArchiveContentsDialog.tsx \
        frontend/src/locales frontend/src/pages/__tests__/Archives.test.tsx
git commit -m "feat(archives): read the archive list from the database"
```

---

## Task 10: Activity filters and run chains

**Files:**
- Create: `frontend/src/components/activity/RunChainRow.tsx`
- Create: `frontend/src/components/activity/RunChainRow.stories.tsx`
- Test: `frontend/src/components/activity/__tests__/RunChainRow.test.tsx`
- Modify: `frontend/src/pages/activity/ActivityFilters.tsx`
- Modify: `frontend/src/components/BackupJobsTable.tsx`
- Modify: `frontend/src/components/RepositoryCard.tsx`

**Interfaces:**
- Consumes: `OperationItem` and `CategoryToken` from phase 3.
- Produces: `<RunChainRow operation={OperationItem} />`.

Spec 10.5: category chips using `CategoryToken` and a trigger select;
`RunChainRow` beneath a parent row, expandable; index rows only when the
Index chip is on; no action buttons for index work; a `RepositoryCard`
"Operations" action opening Activity with `?repository_id=`.

- [ ] **Step 1: Write the failing tests**

`RunChainRow`: renders one entry per follow-up with its status, collapses
to "{{count}} follow-ups" past three, and renders no action buttons.
`ActivityFilters`: toggling a category chip and choosing a trigger both
reach `onChange`; the Index chip is off by default.
`RepositoryCard`: the Operations action links to
`/activity?repository_id={id}`.

- [ ] **Step 2: Run them and confirm they fail**

Expected: FAIL.

- [ ] **Step 3: Add the locale keys**

Under `activity`: `filterCategory`, `filterTrigger`, `allTriggers`,
`followupsCollapsed` ("{{count}} follow-ups"), `operations`
("Operations"). Reuse the existing `operations.category.*` and
`operations.kind.*` keys from phase 3 for the chip and follow-up labels
rather than adding duplicates. Translate the new keys into de, es and it.

- [ ] **Step 4: Write `RunChainRow`**

Reads `operation.followups`. Renders up to three inline with a status tick
per kind and a progress fragment for a running one; past three, renders
`followupsCollapsed` with an expand toggle. No action buttons.

- [ ] **Step 5: Extend `ActivityFilters`**

Category chips built from the `OperationCategory` union, each rendering a
`CategoryToken`, and a trigger `RichSelect` from the `OperationTrigger`
union. Index starts unselected, matching the backend default that excludes
index rows unless asked for.

- [ ] **Step 6: Mount `RunChainRow` in `BackupJobsTable`**

Render it beneath a row whose operation has a non-empty `followups`.

- [ ] **Step 7: Add the `RepositoryCard` action**

A menu item linking to `/activity?repository_id={repository.id}`.

- [ ] **Step 8: Run the tests and confirm they pass**

Expected: PASS.

- [ ] **Step 9: Write the story**

`RunChainRow`: `TwoFollowups`, `Collapsed`, `WithRunning`.

- [ ] **Step 10: Commit**

```bash
git add frontend/src/components/activity frontend/src/pages/activity/ActivityFilters.tsx \
        frontend/src/components/BackupJobsTable.tsx frontend/src/components/RepositoryCard.tsx \
        frontend/src/locales
git commit -m "feat(activity): add category filters and run chains"
```

---

## Task 11: Gate the rebuild history option and verify the feature registry

**Files:**
- Modify: `frontend/src/components/background-work/RebuildMenu.tsx`
- Test: `frontend/src/components/background-work/__tests__/RebuildMenu.test.tsx`
- Test: `frontend/src/core/__tests__/features.test.ts`

**Interfaces:**
- Consumes: `PlanGate`, phase 3's `RebuildMenu`.
- Produces: no new exports.

Spec 11.3: the `history` option is rendered through `PlanGate` with
`disabled`. Spec 11.4: the frontend features test asserts the same key and
plan as the backend.

- [ ] **Step 1: Write the failing tests**

`RebuildMenu`: the history item is disabled without the feature and
selectable with it; stats and archives are never gated.
`features.test.ts`: `FEATURES.archive_history === 'pro'`. Check whether that
assertion already exists before adding it; the key was registered in phase
2 and the test may already cover it. If it does, skip this half and say so
in the commit message.

- [ ] **Step 2: Run them and confirm they fail**

Expected: FAIL on the RebuildMenu assertions.

- [ ] **Step 3: Wrap the history option**

Wrap only the `history` `MenuItem` in `PlanGate` with
`feature="archive_history"`, `disabled`, `surface="background_work"`,
`operation="rebuild_history"`.

- [ ] **Step 4: Run the tests and confirm they pass**

Expected: PASS.

- [ ] **Step 5: Update the RebuildMenu story**

Add a `Locked` story alongside the existing `Default`.

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/background-work frontend/src/core
git commit -m "feat(operations): gate the history rebuild option behind the plan"
```

---

## Task 12: Full verification

**Files:** none. This task only runs checks and fixes what they surface.

- [ ] **Step 1: Run the whole frontend suite**

Run: `npx vitest run`
Expected: every file passes. The phase 3 baseline was 2362 tests across 204
files; this phase adds to both numbers.

- [ ] **Step 2: Lint and typecheck**

Run: `npm run lint && npm run typecheck`
Expected: both clean, no warnings.

- [ ] **Step 3: Build Storybook**

Run: `npm run build-storybook` under Node 20.19+ (`fnm use 20.19.4`).
Expected: success.

- [ ] **Step 4: Render every story**

Run: `npm run visual:screenshots`
Expected: no "Retrying ... after load failure" and no timeout. Step 3
passing does not imply this one does: `build-storybook` never renders a
story, so a story that throws only fails here and in CI. If Playwright
browsers are missing, install them with
`PLAYWRIGHT_BROWSERS_PATH=0 npx playwright install chromium`.

- [ ] **Step 5: Confirm locale parity**

Run the key-comparison the pre-commit hook uses, or compare the flattened
key sets of the four locale files directly. Expected: de, es and it each
report zero missing and zero extra against en.

- [ ] **Step 6: Check for em dashes**

Run: `git diff main --name-only | xargs grep -l "—"`
Expected: no file introduced or modified by this phase appears.

- [ ] **Step 7: Stop at gate G2**

Present the verification output and ask whether to commit and push. Per
`.claude/instructions.md`, nothing is committed or pushed without that
answer. Do not ask about a release: phases 1 to 4 ship together, and the
release prompt was removed from the instructions on 2026-09-04.

---

## Open questions

- **`present_in_latest` per search result.** Spec 10.3 asks the results
  dialog for a "present in latest" column, but `GET /repositories/{id}/search`
  returns `last_seen_archive_id` per row and no such boolean
  (`app/api/archive_index.py:634`). Task 4 derives it by comparing that id
  against the newest archive id passed in from the page. That is correct
  only when the newest archive is indexed. Confirm at G1 whether deriving it
  client-side is acceptable, or whether the route should gain the field.

- **Virtualisation dependency.** Task 6 needs virtualised change rows and
  Task 7 a virtualised file list. If `react-window` is not already a
  dependency, adding one is a decision rather than an implementation detail.
  The alternative is reusing whatever windowing `BackupJobsTable.tsx` does
  today. Confirm at G1 which way to go, since it affects both tasks.

- **`ArchiveContentsDialog` "Open full page" needs a numeric archive id.**
  The dialog is opened from the list with a Borg archive name, not a row id
  (`frontend/src/components/ArchiveContentsDialog.tsx`). Task 9 looks the id
  up from the stored list in the query cache and hides the action when there
  is no match, which means the action is missing for an archive Borg has but
  the index does not. Confirm that degrading quietly is right, rather than
  showing a disabled button with an explanation.

- **Heatmap date range.** Spec 10.3 does not say what window the heatmap
  covers, and the route takes optional `since` and `until`
  (`app/api/archive_index.py:173`). This plan requests the default (no
  bounds) and renders whatever comes back. Confirm whether a bounded default
  such as the last 12 weeks, with a range control, is wanted in this phase
  or is a later addition.
