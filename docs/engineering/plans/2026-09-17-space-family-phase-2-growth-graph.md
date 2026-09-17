# Space Family Phase 2: Repository Growth Graph Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans
> to implement this plan task-by-task in this session (no subagents). Use
> superpowers:test-driven-development inside every task, and `ui-ux-pro-max`
> for the UI tasks. Steps use checkbox (`- [ ]`) syntax for tracking. Do not
> commit at the end of a task; the phase has one commit gate (G2) at the end,
> per section 5.4 of the spec and `.claude/instructions.md`.

**Goal:** Add a third view to the Archives page, next to Heatmap and List,
that draws every measured archive of a repository as a bar (what that backup
added to the repository) with a line for the running total (the repository
footprint over time), an optional line for the source size, and a series
filter when the repository holds more than one series (spec 4.3).

**Architecture:** One new read-only endpoint, `GET
/repositories/{id}/archives/growth?series=`, computes the points and the
running total server side from the `archives` rows that already carry the
four Borg figures, and flags points whose measurement is stale
(`stats_measured_at` null, spec 4.1). One new component,
`ArchiveGrowthChart`, owns the chart, its legend, the source-size toggle and
the series select; `Archives.tsx` only gains the third toggle value, the
query and the render branch. Recharts is already a dependency of the
frontend (installed, not yet imported anywhere), so no new package.

**Tech Stack:** FastAPI, SQLAlchemy, pytest with the `_repo` / `_archive`
helpers and the `test_client` / `admin_headers` / `auth_headers` fixtures of
`tests/unit/test_api_archive_index.py`; React, MUI, Recharts 3
(`ComposedChart`), `react-i18next`, TanStack Query, Vitest with
`renderWithProviders`, Storybook. No new dependencies. No migration.

**Spec:** `docs/engineering/specs/2026-09-16-pro-roadmap-search-space-source-guard.md`,
sections 4.1 (what stale means), 4.3, 4.6, 4.7, 4.8 (phase 2 row), 5,
Appendix B. Mockup, screen 2: https://claude.ai/artifact/LsvMba2GFJLzgXytxZumbP

## Model

Section 4.8 names Sonnet 5 to implement phase 2 and Fable 5.1 to review it.
Plans are written on Fable 5.1; this one was drafted on Fable 5.1 on
2026-09-17, so G0 passed for the plan step. The implement step must check G0
against Sonnet 5 and record any deviation in the 5.1 Notes column.

## Global Constraints

- No em dashes anywhere: not in code comments, not in i18n strings, not in
  documentation. Use periods, commas or parentheses.
- Every user-visible string goes through `react-i18next`, with the key added
  to all four locale files (`frontend/src/locales/{en,de,es,it}.json`); the
  pre-push `check:locales` script enforces parity.
- All work happens in the worktree `../borg-ui-space-family` on branch
  `feat/space-family-phase-2` (created 2026-09-17 from `origin/main` at
  07de1106), never in the main checkout.
- Every task adds or updates a test. The full backend unit suite and the
  frontend `typecheck`, `lint`, `test`, `check:locales` and `format:check`
  run before G2.
- UI changes are verified visually in Storybook, light and dark, before push
  (repository rule). Storybook needs Node 20.19+ via `fnm use 24`.
- The growth view is ungated (spec 4.6, Appendix B). Do not add a plan check.
- Chart colors were validated with the dataviz palette checker on
  2026-09-17 against both paper surfaces (`#ffffff`, `#27272a`): bars
  `theme.palette.primary.main`; footprint line `theme.palette.info.main` in
  light and `theme.palette.info.light` in dark (the dark `info.main` is too
  close to the dark primary, ΔE 12.3 normal vision, below the 15 floor);
  source line `theme.palette.text.secondary`, dashed (a reference line, not
  a series color). Do not swap these for other palette slots without
  re-running the checker.

---

### Task 1: Growth endpoint

**Files:**
- Modify: `app/api/archive_index.py` (new route between `archives_heatmap`
  and `_archive_or_404`, roughly line 320)
- Test: `tests/unit/test_api_archive_index.py` (new class `TestArchiveGrowth`
  after `TestHeatmap`)

**Interfaces:**
- Consumes: `_repo`, `_archives_query`, `Archive` (all already in the
  module).
- Produces: `GET /api/repositories/{repo_id}/archives/growth?series=<name>`
  returning

```json
{
  "points": [
    {
      "archive_id": 1, "name": "a1", "series": "nas",
      "start": "2026-09-01T02:00:00", "deduplicated_size": 100,
      "original_size": 100, "running_total": 100, "stale": false
    }
  ],
  "series": ["nas", "old"],
  "stale_count": 0,
  "unmeasured_count": 1
}
```

  sorted by `start` ascending. `running_total` is the cumulative
  `deduplicated_size` over the returned points: per series when `series` is
  given, over the whole repository otherwise (spec 4.3). Archives with a null
  `deduplicated_size` are skipped and counted in `unmeasured_count`. A point
  is `stale` when its `stats_measured_at` is null (sizes present, measurement
  cleared by a listing that saw removals, spec 4.1). `stale_count` counts
  those points.

Route order matters: `/{repo_id}/archives/{archive_id}` declares
`archive_id: int` in the signature only, so Starlette matches `growth` as a
path segment and FastAPI answers 422. The new route must be declared before
`get_archive`, the way `archives_heatmap` is.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_api_archive_index.py` after the `TestHeatmap`
class. The `_archive` helper never sets `stats_measured_at`, so a helper row
is stale unless the test stamps it.

```python
@pytest.mark.unit
class TestArchiveGrowth:
    def _measured(self, test_db, repo, name, day, **kw):
        a = _archive(test_db, repo, name, day, **kw)
        a.stats_measured_at = utc_now().replace(tzinfo=None)
        test_db.commit()
        return a

    def test_points_carry_a_running_total_and_skip_unmeasured_archives(
        self, test_client, test_db, admin_headers
    ):
        """One point per measured archive, oldest first; the running total
        is the repository footprint after that archive (spec 4.3). A row the
        info fill has not reached yet has no size and is not a point."""
        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        stale = _archive(test_db, repo, "a2", 2, size=50)  # sizes, no date
        unmeasured = _archive(test_db, repo, "a3", 3)
        unmeasured.original_size = None
        unmeasured.deduplicated_size = None
        test_db.commit()
        self._measured(test_db, repo, "old-a4", 4, series="old", size=30)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=admin_headers
        )
        assert r.status_code == 200
        body = r.json()
        assert [p["name"] for p in body["points"]] == ["a1", "a2", "old-a4"]
        assert [p["running_total"] for p in body["points"]] == [100, 150, 180]
        assert [p["stale"] for p in body["points"]] == [False, True, False]
        assert body["points"][1]["archive_id"] == stale.id
        assert body["points"][0]["original_size"] == 100
        assert body["points"][0]["start"].startswith("2026-09-01T02:00:00")
        assert body["series"] == ["nas", "old"]
        assert body["stale_count"] == 1
        assert body["unmeasured_count"] == 1

    def test_series_filter_restarts_the_running_total(
        self, test_client, test_db, admin_headers
    ):
        """Filtered to one series, the total is that series' footprint, and
        the series list still names every series so the select can switch."""
        repo = _repo(test_db)
        self._measured(test_db, repo, "a1", 1, size=100)
        self._measured(test_db, repo, "old-a2", 2, series="old", size=30)
        self._measured(test_db, repo, "old-a3", 3, series="old", size=20)

        r = test_client.get(
            f"/api/repositories/{repo.id}/archives/growth",
            params={"series": "old"},
            headers=admin_headers,
        )
        assert r.status_code == 200
        body = r.json()
        assert [p["name"] for p in body["points"]] == ["old-a2", "old-a3"]
        assert [p["running_total"] for p in body["points"]] == [30, 50]
        assert body["series"] == ["nas", "old"]

    def test_requires_repository_access(self, test_client, test_db, auth_headers):
        repo = _repo(test_db)
        assert test_client.get(
            f"/api/repositories/{repo.id}/archives/growth", headers=auth_headers
        ).status_code in (403, 404)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_api_archive_index.py::TestArchiveGrowth -q`
Expected: the first two FAIL with status 422 (the `{archive_id}` route
swallows `growth`); the access test passes already (the detail route also
refuses the other user), which is fine.

- [ ] **Step 3: Write the route**

In `app/api/archive_index.py`, directly after `archives_heatmap` and before
`_archive_or_404`:

```python
@router.get("/{repo_id}/archives/growth")
async def archives_growth(
    repo_id: int,
    series: Optional[str] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """The archive index as a growth curve (spec 4.3).

    One point per measured archive, oldest first: what the archive added to
    the repository (deduplicated_size) and the running total of those
    additions, which is the repository footprint after that backup. Filtered
    to a series the total restarts, so the curve is that series' footprint.
    Archives the info fill has not measured have no point. A stale point
    (measured once, then a listing saw archives removed) keeps its value
    and is flagged, per spec 4.1.

    Declared before the `{archive_id}` route on purpose: that route's path
    parameter matches any segment, so `growth` would otherwise reach it and
    fail validation.
    """
    repository = _repo(db, current_user, repo_id)
    rows = (
        _archives_query(db, repository, series, None, None)
        .order_by(Archive.start.asc(), Archive.id.asc())
        .all()
    )
    all_series = [
        s
        for (s,) in db.query(Archive.series)
        .filter(Archive.repository_id == repository.id)
        .distinct()
        .order_by(Archive.series.asc())
        .all()
    ]
    points: list[dict] = []
    running = 0
    unmeasured = 0
    for a in rows:
        if a.deduplicated_size is None:
            unmeasured += 1
            continue
        running += a.deduplicated_size
        points.append(
            {
                "archive_id": a.id,
                "name": a.name,
                "series": a.series,
                "start": a.start,
                "deduplicated_size": a.deduplicated_size,
                "original_size": a.original_size,
                "running_total": running,
                "stale": a.stats_measured_at is None,
            }
        )
    return {
        "points": points,
        "series": all_series,
        "stale_count": sum(1 for p in points if p["stale"]),
        "unmeasured_count": unmeasured,
    }
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `pytest tests/unit/test_api_archive_index.py -q`
Expected: PASS, including every pre-existing class in the file (the new
route must not shadow `/archives/heatmap` or `/archives/{archive_id}`).

### Task 2: Frontend types, API client and strings

**Files:**
- Modify: `frontend/src/types/archives.ts` (after `HeatmapResponse`)
- Modify: `frontend/src/services/api.ts` (`archivesAPI`, after `getHeatmap`)
- Modify: `frontend/src/locales/en.json`, `de.json`, `es.json`, `it.json`
  (under `archives.view`, and a new `archives.growth` block after
  `archives.heatmap`)

**Interfaces:**
- Produces:

```ts
export interface GrowthPoint {
  archive_id: number
  name: string
  series: string
  start: string
  deduplicated_size: number
  original_size: number | null
  running_total: number
  stale: boolean
}

export interface GrowthResponse {
  points: GrowthPoint[]
  series: string[]
  stale_count: number
  unmeasured_count: number
}

archivesAPI.getGrowth(repositoryId: number, params?: { series?: string })
  => Promise<AxiosResponse<GrowthResponse>>
```

- [ ] **Step 1: Add the types**

In `frontend/src/types/archives.ts`, after the `HeatmapResponse` interface:

```ts
// Mirrors GET /repositories/{id}/archives/growth (spec 4.3). Points are the
// measured archives oldest first; running_total is the footprint after each
// one, restarted per series when the request was filtered.
export interface GrowthPoint {
  archive_id: number
  name: string
  series: string
  start: string
  deduplicated_size: number
  original_size: number | null
  running_total: number
  // Sizes present but the measurement date was cleared by a listing that saw
  // removed archives (spec 4.1). Drawn lighter.
  stale: boolean
}

export interface GrowthResponse {
  points: GrowthPoint[]
  series: string[]
  stale_count: number
  unmeasured_count: number
}
```

- [ ] **Step 2: Add the client method**

In `frontend/src/services/api.ts`, extend the import from
`'../types/archives'` with `GrowthResponse`, and add after `getHeatmap` in
`archivesAPI`:

```ts
  getGrowth: (repositoryId: number, params?: { series?: string }) =>
    api.get<GrowthResponse>(`/repositories/${repositoryId}/archives/growth`, { params }),
```

- [ ] **Step 3: Add the strings**

`frontend/src/locales/en.json`: in `archives.view` add `"growth": "Growth"`
after `"list"`, and after the `archives.heatmap` block add:

```json
    "growth": {
      "title": "Repository growth",
      "seriesLabel": "Series",
      "allSeries": "All series",
      "showSource": "Show source size",
      "legendAdded": "Added per archive",
      "legendFootprint": "Repository footprint (running total)",
      "legendSource": "Source size (original)",
      "legendStale": "Stale, re-measuring",
      "staleNote_one": "{{count}} archive is being re-measured after archives were removed. Its bar shows the last measurement.",
      "staleNote_other": "{{count}} archives are being re-measured after archives were removed. Their bars show the last measurement.",
      "unmeasuredNote_one": "{{count}} archive is not measured yet and is not drawn.",
      "unmeasuredNote_other": "{{count}} archives are not measured yet and are not drawn.",
      "empty": "The growth graph needs at least two measured archives.",
      "tooltipAdded": "Added",
      "tooltipFootprint": "Footprint after",
      "tooltipSource": "Source size",
      "tooltipStale": "Stale measurement",
      "openArchive": "Open archive"
    },
```

`de.json`, same places:

```json
      "growth": "Wachstum"
```

```json
    "growth": {
      "title": "Wachstum des Repositorys",
      "seriesLabel": "Serie",
      "allSeries": "Alle Serien",
      "showSource": "Quellgröße anzeigen",
      "legendAdded": "Pro Archiv hinzugefügt",
      "legendFootprint": "Belegter Speicher (laufende Summe)",
      "legendSource": "Quellgröße (Original)",
      "legendStale": "Veraltet, wird neu gemessen",
      "staleNote_one": "{{count}} Archiv wird nach dem Entfernen von Archiven neu gemessen. Sein Balken zeigt die letzte Messung.",
      "staleNote_other": "{{count}} Archive werden nach dem Entfernen von Archiven neu gemessen. Ihre Balken zeigen die letzte Messung.",
      "unmeasuredNote_one": "{{count}} Archiv ist noch nicht gemessen und wird nicht gezeichnet.",
      "unmeasuredNote_other": "{{count}} Archive sind noch nicht gemessen und werden nicht gezeichnet.",
      "empty": "Das Wachstumsdiagramm braucht mindestens zwei gemessene Archive.",
      "tooltipAdded": "Hinzugefügt",
      "tooltipFootprint": "Belegt danach",
      "tooltipSource": "Quellgröße",
      "tooltipStale": "Veraltete Messung",
      "openArchive": "Archiv öffnen"
    },
```

`es.json`:

```json
      "growth": "Crecimiento"
```

```json
    "growth": {
      "title": "Crecimiento del repositorio",
      "seriesLabel": "Serie",
      "allSeries": "Todas las series",
      "showSource": "Mostrar tamaño de origen",
      "legendAdded": "Añadido por archivo",
      "legendFootprint": "Espacio ocupado (total acumulado)",
      "legendSource": "Tamaño de origen (original)",
      "legendStale": "Obsoleto, midiendo de nuevo",
      "staleNote_one": "{{count}} archivo se está midiendo de nuevo tras eliminar archivos. Su barra muestra la última medición.",
      "staleNote_other": "{{count}} archivos se están midiendo de nuevo tras eliminar archivos. Sus barras muestran la última medición.",
      "unmeasuredNote_one": "{{count}} archivo aún no se ha medido y no se dibuja.",
      "unmeasuredNote_other": "{{count}} archivos aún no se han medido y no se dibujan.",
      "empty": "El gráfico de crecimiento necesita al menos dos archivos medidos.",
      "tooltipAdded": "Añadido",
      "tooltipFootprint": "Ocupado después",
      "tooltipSource": "Tamaño de origen",
      "tooltipStale": "Medición obsoleta",
      "openArchive": "Abrir archivo"
    },
```

`it.json`:

```json
      "growth": "Crescita"
```

```json
    "growth": {
      "title": "Crescita del repository",
      "seriesLabel": "Serie",
      "allSeries": "Tutte le serie",
      "showSource": "Mostra dimensione sorgente",
      "legendAdded": "Aggiunto per archivio",
      "legendFootprint": "Spazio occupato (totale progressivo)",
      "legendSource": "Dimensione sorgente (originale)",
      "legendStale": "Obsoleto, nuova misurazione in corso",
      "staleNote_one": "{{count}} archivio viene misurato di nuovo dopo la rimozione di archivi. La sua barra mostra l'ultima misurazione.",
      "staleNote_other": "{{count}} archivi vengono misurati di nuovo dopo la rimozione di archivi. Le loro barre mostrano l'ultima misurazione.",
      "unmeasuredNote_one": "{{count}} archivio non è ancora misurato e non viene disegnato.",
      "unmeasuredNote_other": "{{count}} archivi non sono ancora misurati e non vengono disegnati.",
      "empty": "Il grafico della crescita richiede almeno due archivi misurati.",
      "tooltipAdded": "Aggiunto",
      "tooltipFootprint": "Occupato dopo",
      "tooltipSource": "Dimensione sorgente",
      "tooltipStale": "Misurazione obsoleta",
      "openArchive": "Apri archivio"
    },
```

- [ ] **Step 4: Types and locales**

Run: `cd frontend && npm run typecheck && npm run check:locales`
Expected: both pass. Nothing consumes the new types yet.

### Task 3: `ArchiveGrowthChart` component, test, story

**Files:**
- Create: `frontend/src/components/archives/ArchiveGrowthChart.tsx`
- Create: `frontend/src/components/archives/__tests__/ArchiveGrowthChart.test.tsx`
- Create: `frontend/src/components/archives/ArchiveGrowthChart.stories.tsx`

**Interfaces:**
- Consumes: `GrowthResponse`, `GrowthPoint` from Task 2; `formatBytes`,
  `formatDateShort`, `formatDateCompact` from `utils/dateUtils`;
  `RichSelect` from `components/shared/RichSelect` (props: `value`,
  `onChange(value: string)`, `options: {value, primary}[]`, `label`);
  Recharts 3 (`ResponsiveContainer`, `ComposedChart`, `Bar`, `Cell`, `Line`,
  `XAxis`, `YAxis`, `CartesianGrid`, `Tooltip`).
- Produces:

```ts
export interface ArchiveGrowthChartProps {
  data: GrowthResponse
  // '' means every series (the whole repository).
  series: string
  onSeriesChange: (series: string) => void
  onSelectArchive: (archiveId: number) => void
}
export default function ArchiveGrowthChart(props: ArchiveGrowthChartProps)
```

Design notes the implementer follows (spec 4.3 and the mockup, screen 2):

- Bars: `deduplicated_size`, `primary.main`, 2 px rounded top, at most
  18 px wide, stale bars at 35% opacity, measured bars at 90%.
- Footprint line: `running_total`, 2 px, no dots, `info.main` in light,
  `info.light` in dark (see Global Constraints).
- Source line: `original_size`, only when the toggle is on, 1.5 px dashed
  `4 4`, `text.secondary`, no dots.
- Two Y axes, both in bytes: left for the bars, right for the two lines,
  because a year of daily archives makes the total hundreds of times the
  typical bar and a shared axis flattens every bar. Both axes use
  `formatBytes`. See Open questions for the alternative.
- X axis: `start`, ticks through `formatDateShort`, `minTickGap` 40.
- Legend: our own row under the chart (a Recharts `Legend` cannot show the
  stale swatch or take i18n copy), one entry per drawn mark plus the stale
  swatch when `stale_count > 0`.
- Notes under the legend: the stale note when `stale_count > 0`, the
  unmeasured note when `unmeasured_count > 0`.
- Empty state when `points.length < 2`, still showing the series select if
  there are several series (a filtered series can be empty while another is
  not).
- Series select: a `RichSelect` shown only when `data.series.length > 1`,
  with an "All series" option (value `''`) first.
- Tooltip: archive name, `formatDateCompact(start)`, added, footprint after,
  source size (when the toggle is on), a stale line when stale, and the hint
  that a click opens the archive.
- Animation off (`isAnimationActive={false}`) on every mark so tests and
  Storybook snapshots are deterministic.

- [ ] **Step 1: Write the failing component test**

`frontend/src/components/archives/__tests__/ArchiveGrowthChart.test.tsx`:

```tsx
import { describe, it, expect, vi } from 'vitest'
import { screen, fireEvent } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import ArchiveGrowthChart from '../ArchiveGrowthChart'
import type { GrowthPoint, GrowthResponse } from '../../../types/archives'

const point = (id: number, day: number, overrides: Partial<GrowthPoint> = {}): GrowthPoint => ({
  archive_id: id,
  name: `nas-2026-09-0${day}`,
  series: 'nas',
  start: `2026-09-0${day}T02:00:00`,
  deduplicated_size: 1_000_000_000,
  original_size: 90_000_000_000,
  running_total: id * 1_000_000_000,
  stale: false,
  ...overrides,
})

const response = (overrides: Partial<GrowthResponse> = {}): GrowthResponse => ({
  points: [point(1, 1), point(2, 2), point(3, 3)],
  series: ['nas'],
  stale_count: 0,
  unmeasured_count: 0,
  ...overrides,
})

const render = (data: GrowthResponse, series = '') => {
  const onSeriesChange = vi.fn()
  const onSelectArchive = vi.fn()
  renderWithProviders(
    <ArchiveGrowthChart
      data={data}
      series={series}
      onSeriesChange={onSeriesChange}
      onSelectArchive={onSelectArchive}
    />
  )
  return { onSeriesChange, onSelectArchive }
}

describe('ArchiveGrowthChart', () => {
  it('names the bars and the footprint line, and hides the source line by default', () => {
    render(response())
    expect(screen.getByText('Added per archive')).toBeInTheDocument()
    expect(screen.getByText('Repository footprint (running total)')).toBeInTheDocument()
    expect(screen.queryByText('Source size (original)')).not.toBeInTheDocument()
    expect(screen.queryByText('Stale, re-measuring')).not.toBeInTheDocument()
  })

  it('adds the source line when asked', () => {
    render(response())
    fireEvent.click(screen.getByRole('checkbox', { name: 'Show source size' }))
    expect(screen.getByText('Source size (original)')).toBeInTheDocument()
  })

  it('explains stale and unmeasured archives', () => {
    render(
      response({
        points: [point(1, 1), point(2, 2, { stale: true }), point(3, 3)],
        stale_count: 1,
        unmeasured_count: 2,
      })
    )
    expect(screen.getByText('Stale, re-measuring')).toBeInTheDocument()
    expect(screen.getByText(/1 archive is being re-measured/)).toBeInTheDocument()
    expect(screen.getByText(/2 archives are not measured yet/)).toBeInTheDocument()
  })

  it('offers the series select only when the repository has several series', () => {
    render(response())
    expect(screen.queryByLabelText('Series')).not.toBeInTheDocument()
  })

  it('switches series through the select', () => {
    const { onSeriesChange } = render(response({ series: ['nas', 'docs'] }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /Series/ }))
    fireEvent.click(screen.getByRole('option', { name: /docs/ }))
    expect(onSeriesChange).toHaveBeenCalledWith('docs')
  })

  it('says so when fewer than two archives are measured', () => {
    render(response({ points: [point(1, 1)] }))
    expect(
      screen.getByText('The growth graph needs at least two measured archives.')
    ).toBeInTheDocument()
    expect(screen.queryByText('Added per archive')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/components/archives/__tests__/ArchiveGrowthChart.test.tsx`
Expected: FAIL, module `../ArchiveGrowthChart` not found.

- [ ] **Step 3: Write the component**

`frontend/src/components/archives/ArchiveGrowthChart.tsx`:

```tsx
import { useState } from 'react'
import {
  Box,
  Checkbox,
  FormControlLabel,
  Paper,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  Bar,
  CartesianGrid,
  Cell,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'
import RichSelect from '../shared/RichSelect'
import { formatBytes, formatDateCompact, formatDateShort } from '../../utils/dateUtils'
import type { GrowthPoint, GrowthResponse } from '../../types/archives'

export interface ArchiveGrowthChartProps {
  data: GrowthResponse
  // '' means every series (the whole repository).
  series: string
  onSeriesChange: (series: string) => void
  onSelectArchive: (archiveId: number) => void
}

const HEIGHT = 320
const STALE_OPACITY = 0.35
const MEASURED_OPACITY = 0.9

// Recharts hands the bar's data entry to onClick under `payload`.
type BarClick = { payload?: GrowthPoint }

interface TooltipProps {
  active?: boolean
  payload?: { payload: GrowthPoint }[]
  showSource: boolean
}

function GrowthTooltip({ active, payload, showSource }: TooltipProps) {
  const { t } = useTranslation()
  const point = payload?.[0]?.payload
  if (!active || !point) return null
  const row = (label: string, value: string) => (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', gap: 2 }}>
      <Typography variant="caption" sx={{ color: 'text.secondary' }}>
        {label}
      </Typography>
      <Typography variant="caption" sx={{ fontVariantNumeric: 'tabular-nums' }}>
        {value}
      </Typography>
    </Box>
  )
  return (
    <Paper elevation={3} sx={{ p: 1.25, minWidth: 220 }}>
      <Typography variant="subtitle2" sx={{ wordBreak: 'break-all' }}>
        {point.name}
      </Typography>
      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 0.5 }}>
        {formatDateCompact(point.start)}
      </Typography>
      {row(t('archives.growth.tooltipAdded'), formatBytes(point.deduplicated_size))}
      {row(t('archives.growth.tooltipFootprint'), formatBytes(point.running_total))}
      {showSource && row(t('archives.growth.tooltipSource'), formatBytes(point.original_size))}
      {point.stale && (
        <Typography variant="caption" sx={{ color: 'warning.main', display: 'block', mt: 0.5 }}>
          {t('archives.growth.tooltipStale')}
        </Typography>
      )}
      <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mt: 0.5 }}>
        {t('archives.growth.openArchive')}
      </Typography>
    </Paper>
  )
}

function Swatch({ color, line, dashed, opacity = 1 }: {
  color: string
  line?: boolean
  dashed?: boolean
  opacity?: number
}) {
  return (
    <Box
      component="span"
      sx={{
        display: 'inline-block',
        width: 14,
        height: line ? 0 : 12,
        borderRadius: line ? 0 : 0.5,
        bgcolor: line ? 'transparent' : color,
        borderTop: line ? `2px ${dashed ? 'dashed' : 'solid'} ${color}` : 'none',
        opacity,
        mr: 0.75,
        verticalAlign: line ? 'middle' : '-2px',
      }}
    />
  )
}

export default function ArchiveGrowthChart({
  data,
  series,
  onSeriesChange,
  onSelectArchive,
}: ArchiveGrowthChartProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const [showSource, setShowSource] = useState(false)

  const barColor = theme.palette.primary.main
  // The dark info.main sits too close to the dark primary for two marks to
  // read apart (palette check 2026-09-17); the lighter step passes.
  const footprintColor =
    theme.palette.mode === 'dark' ? theme.palette.info.light : theme.palette.info.main
  const sourceColor = theme.palette.text.secondary
  const gridColor = alpha(theme.palette.text.primary, 0.08)
  const tickStyle = { fill: theme.palette.text.secondary, fontSize: 11 }

  const seriesOptions = [
    { value: '', primary: t('archives.growth.allSeries') },
    ...data.series.map((name) => ({ value: name, primary: name })),
  ]
  const hasSeriesChoice = data.series.length > 1
  const enough = data.points.length >= 2

  return (
    <Box data-testid="archive-growth-chart">
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        alignItems={{ xs: 'stretch', sm: 'center' }}
        sx={{ mb: 2 }}
      >
        <Typography variant="subtitle1" sx={{ fontWeight: 600, flexGrow: 1 }}>
          {t('archives.growth.title')}
        </Typography>
        {hasSeriesChoice && (
          <RichSelect
            value={series}
            onChange={onSeriesChange}
            options={seriesOptions}
            label={t('archives.growth.seriesLabel')}
            sx={{ minWidth: 200 }}
          />
        )}
        {enough && (
          <FormControlLabel
            control={
              <Checkbox
                size="small"
                checked={showSource}
                onChange={(event) => setShowSource(event.target.checked)}
              />
            }
            label={t('archives.growth.showSource')}
          />
        )}
      </Stack>

      {!enough ? (
        <Typography variant="body2" sx={{ color: 'text.secondary', py: 6, textAlign: 'center' }}>
          {t('archives.growth.empty')}
        </Typography>
      ) : (
        <>
          <ResponsiveContainer
            width="100%"
            height={HEIGHT}
            initialDimension={{ width: 800, height: HEIGHT }}
          >
            <ComposedChart data={data.points} margin={{ top: 8, right: 8, bottom: 0, left: 8 }}>
              <CartesianGrid vertical={false} stroke={gridColor} />
              <XAxis
                dataKey="start"
                tickFormatter={(value: string) => formatDateShort(value)}
                minTickGap={40}
                tick={tickStyle}
                tickLine={false}
                axisLine={{ stroke: gridColor }}
              />
              <YAxis
                yAxisId="added"
                tickFormatter={(value: number) => formatBytes(value)}
                width={84}
                tick={tickStyle}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                yAxisId="total"
                orientation="right"
                tickFormatter={(value: number) => formatBytes(value)}
                width={84}
                tick={tickStyle}
                tickLine={false}
                axisLine={false}
              />
              <Tooltip
                cursor={{ fill: alpha(theme.palette.text.primary, 0.06) }}
                content={<GrowthTooltip showSource={showSource} />}
              />
              <Bar
                yAxisId="added"
                dataKey="deduplicated_size"
                fill={barColor}
                radius={[2, 2, 0, 0]}
                maxBarSize={18}
                isAnimationActive={false}
                cursor="pointer"
                onClick={(entry: BarClick) => {
                  const id = entry.payload?.archive_id
                  if (id != null) onSelectArchive(id)
                }}
              >
                {data.points.map((point) => (
                  <Cell
                    key={point.archive_id}
                    fillOpacity={point.stale ? STALE_OPACITY : MEASURED_OPACITY}
                  />
                ))}
              </Bar>
              <Line
                yAxisId="total"
                type="monotone"
                dataKey="running_total"
                stroke={footprintColor}
                strokeWidth={2}
                dot={false}
                activeDot={{ r: 4 }}
                isAnimationActive={false}
              />
              {showSource && (
                <Line
                  yAxisId="total"
                  type="monotone"
                  dataKey="original_size"
                  stroke={sourceColor}
                  strokeWidth={1.5}
                  strokeDasharray="4 4"
                  dot={false}
                  activeDot={{ r: 3 }}
                  isAnimationActive={false}
                />
              )}
            </ComposedChart>
          </ResponsiveContainer>

          <Stack
            direction="row"
            spacing={2}
            useFlexGap
            flexWrap="wrap"
            sx={{ mt: 1.5, color: 'text.secondary', typography: 'caption' }}
          >
            <span>
              <Swatch color={barColor} opacity={MEASURED_OPACITY} />
              {t('archives.growth.legendAdded')}
            </span>
            <span>
              <Swatch color={footprintColor} line />
              {t('archives.growth.legendFootprint')}
            </span>
            {showSource && (
              <span>
                <Swatch color={sourceColor} line dashed />
                {t('archives.growth.legendSource')}
              </span>
            )}
            {data.stale_count > 0 && (
              <span>
                <Swatch color={barColor} opacity={STALE_OPACITY} />
                {t('archives.growth.legendStale')}
              </span>
            )}
          </Stack>

          {(data.stale_count > 0 || data.unmeasured_count > 0) && (
            <Box sx={{ mt: 1 }}>
              {data.stale_count > 0 && (
                <Typography variant="caption" sx={{ color: 'warning.main', display: 'block' }}>
                  {t('archives.growth.staleNote', { count: data.stale_count })}
                </Typography>
              )}
              {data.unmeasured_count > 0 && (
                <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
                  {t('archives.growth.unmeasuredNote', { count: data.unmeasured_count })}
                </Typography>
              )}
            </Box>
          )}
        </>
      )}
    </Box>
  )
}
```

If the typecheck rejects the `onClick` handler type on `Bar`, cast at the
call site (`onClick={(entry) => ... (entry as BarClick).payload ...}`)
rather than loosening the interface. If `RichSelect` renders its combobox
without the label in its accessible name, pass `labelId` and `selectId`
explicitly so the test's `getByRole('combobox', { name: /Series/ })` finds
it.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd frontend && npx vitest run src/components/archives/__tests__/ArchiveGrowthChart.test.tsx`
Expected: PASS, six tests.

- [ ] **Step 5: Write the story**

`frontend/src/components/archives/ArchiveGrowthChart.stories.tsx`. The
`Dark` story wraps itself in the dark theme so the visual check covers both
modes (the global decorator renders light only).

```tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { ThemeProvider } from '@mui/material/styles'
import { Box, CssBaseline } from '@mui/material'
import ArchiveGrowthChart from './ArchiveGrowthChart'
import { getTheme } from '../../theme'
import type { GrowthPoint, GrowthResponse } from '../../types/archives'

// Ninety nightly archives: a slowly growing source, two large days, three
// stale measurements near the end, as in the spec mockup (screen 2).
function nightly(): GrowthPoint[] {
  const points: GrowthPoint[] = []
  let total = 197_000_000_000
  let seed = 7
  const rnd = () => {
    seed = (seed * 9301 + 49297) % 233280
    return seed / 233280
  }
  for (let i = 0; i < 90; i += 1) {
    const day = new Date(Date.UTC(2026, 5, 19 + i, 2))
    const spike = i === 30 || i === 67 ? 4.5 : 1
    const added = Math.round((0.3 + rnd() * 0.9 * spike) * 1_000_000_000)
    total += added
    points.push({
      archive_id: i + 1,
      name: `nas-${day.toISOString().slice(0, 10)}T02:00:00`,
      series: 'nightly',
      start: day.toISOString().replace('Z', ''),
      deduplicated_size: added,
      original_size: Math.round((371 + i * 0.46) * 1_000_000_000),
      running_total: total,
      stale: i === 85 || i === 87 || i === 88,
    })
  }
  return points
}

const data: GrowthResponse = {
  points: nightly(),
  series: ['nightly', 'docs'],
  stale_count: 3,
  unmeasured_count: 1,
}

const meta = {
  title: 'Components/Archives/ArchiveGrowthChart',
  component: ArchiveGrowthChart,
  args: {
    data,
    series: '',
    onSeriesChange: () => {},
    onSelectArchive: () => {},
  },
} satisfies Meta<typeof ArchiveGrowthChart>

export default meta
type Story = StoryObj<typeof meta>

export const Repository: Story = {}

export const OneSeries: Story = {
  args: { data: { ...data, series: ['nightly'], stale_count: 0, unmeasured_count: 0 } },
}

export const Empty: Story = {
  args: { data: { points: data.points.slice(0, 1), series: ['nightly'], stale_count: 0, unmeasured_count: 3 } },
}

export const Dark: Story = {
  decorators: [
    (Story) => (
      <ThemeProvider theme={getTheme('dark')}>
        <CssBaseline />
        <Box sx={{ p: 2, bgcolor: 'background.paper' }}>
          <Story />
        </Box>
      </ThemeProvider>
    ),
  ],
}
```

- [ ] **Step 6: Lint, types, format**

Run: `cd frontend && npm run typecheck && npm run lint && npm run format:check`
Expected: all pass. Run `npx prettier --write` on the three new files if
`format:check` complains.

### Task 4: Wire the growth view into the Archives page

**Files:**
- Modify: `frontend/src/pages/Archives.tsx` (`ArchivesViewMode`,
  `getInitialViewMode`, the queries near line 180, the toggle near line 770,
  the render branch near line 784)
- Modify: `frontend/src/utils/archiveResync.ts` (`storedArchiveKeys`)
- Test: `frontend/src/pages/__tests__/Archives.view.test.tsx`

**Interfaces:**
- Consumes: `ArchiveGrowthChart` from Task 3, `archivesAPI.getGrowth` from
  Task 2.
- Produces: the `growth` value of the `archives-view-mode` localStorage key,
  and the query key `['repository-archives-growth', repositoryId, series]`.

- [ ] **Step 1: Write the failing page test**

In `frontend/src/pages/__tests__/Archives.view.test.tsx`:

Add to the mocks, next to the heatmap component mocks:

```tsx
vi.mock('../../components/archives/ArchiveGrowthChart', () => ({
  default: ({ data }: { data: { points: unknown[] } }) => (
    <div data-testid="archive-growth-chart">{data.points.length}</div>
  ),
}))
```

Add `getGrowth: vi.fn(),` to the `archivesAPI` mock object, and a
`const getGrowthMock = vi.fn()` next to `getHeatmapMock`. In `beforeEach`:

```tsx
    getGrowthMock.mockResolvedValue({
      data: { points: [{ archive_id: 1 }, { archive_id: 2 }], series: ['default'], stale_count: 0, unmeasured_count: 0 },
    })
    vi.mocked(apiModule.archivesAPI.getGrowth).mockImplementation(getGrowthMock)
```

Add two tests at the end of the `describe`:

```tsx
  it('switches to the growth view and persists the choice', async () => {
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))
    await waitFor(() => {
      expect(screen.getByTestId('archive-series-heatmap')).toBeInTheDocument()
    })
    expect(getGrowthMock).not.toHaveBeenCalled()

    await user.click(screen.getByRole('button', { name: 'Growth' }))

    await waitFor(() => {
      expect(screen.getByTestId('archive-growth-chart')).toHaveTextContent('2')
    })
    expect(getGrowthMock).toHaveBeenCalledWith(1, { series: undefined })
    expect(screen.queryByTestId('archive-series-heatmap')).not.toBeInTheDocument()
    expect(localStorage.getItem('archives-view-mode')).toBe('growth')
  })

  it('honours a persisted growth view preference on mount', async () => {
    localStorage.setItem('archives-view-mode', 'growth')
    renderWithProviders(<Archives />, { queryClient })
    const user = userEvent.setup()

    await user.click(screen.getByText('Select Repo'))

    await waitFor(() => {
      expect(screen.getByTestId('archive-growth-chart')).toBeInTheDocument()
    })
    expect(getHeatmapMock).not.toHaveBeenCalled()
  })
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd frontend && npx vitest run src/pages/__tests__/Archives.view.test.tsx`
Expected: the two new tests FAIL (no `Growth` button); the existing ones
still pass.

- [ ] **Step 3: Add the view**

In `frontend/src/pages/Archives.tsx`:

Import the component next to the heatmap imports:

```tsx
import ArchiveGrowthChart from '../components/archives/ArchiveGrowthChart'
```

Replace the view mode type and initialiser:

```tsx
type ArchivesViewMode = 'heatmap' | 'list' | 'growth'

function getInitialViewMode(): ArchivesViewMode {
  const stored = localStorage.getItem('archives-view-mode')
  return stored === 'list' || stored === 'growth' ? stored : 'heatmap'
}
```

Add state next to `chosenScale`:

```tsx
  // '' is the whole repository; the growth endpoint restarts its running
  // total when a series is named (spec 4.3).
  const [growthSeries, setGrowthSeries] = useState('')
```

Add the query after the heatmap query:

```tsx
  const { data: growthData } = useQuery({
    queryKey: ['repository-archives-growth', selectedRepositoryId, growthSeries],
    queryFn: () =>
      archivesAPI.getGrowth(selectedRepositoryId!, { series: growthSeries || undefined }),
    enabled: !!selectedRepositoryId && !repoInfoPending && viewMode === 'growth',
    retry: false,
  })
```

Add the toggle button after the `list` one:

```tsx
              <ToggleButton value="growth">{t('archives.view.growth')}</ToggleButton>
```

Turn the render branch into three cases. The existing heatmap block and the
`ArchivesList` block stay exactly as they are; only the surrounding
conditional changes:

```tsx
          {viewMode === 'heatmap' ? (
            /* existing heatmap block, unchanged */
          ) : viewMode === 'growth' ? (
            growthData?.data ? (
              <Box sx={{ ...panelSx, p: 2.5 }}>
                <ArchiveGrowthChart
                  data={growthData.data}
                  series={growthSeries}
                  onSeriesChange={setGrowthSeries}
                  onSelectArchive={(archiveId) =>
                    navigate(`/archives/${selectedRepositoryId}/${archiveId}`)
                  }
                />
              </Box>
            ) : null
          ) : (
            /* existing ArchivesList block, unchanged */
          )}
```

In `frontend/src/utils/archiveResync.ts`, add the growth key so a finished
`archive_sync` (which is also what re-measures stale archives) refreshes the
graph. A prefix key invalidates every series variant:

```ts
    ['repository-archives-growth', repositoryId],
```

- [ ] **Step 4: Run the page tests to verify they pass**

Run: `cd frontend && npx vitest run src/pages/__tests__/Archives.view.test.tsx src/utils`
Expected: PASS. If a test of `archiveResync` asserts the exact key list,
add the new key to its expectation.

- [ ] **Step 5: Visual check in Storybook, light and dark**

Run (worktree, Node via fnm):

```bash
cd frontend && fnm use 24 && npm run storybook -- --ci --port 6007
```

Open `Components/Archives/ArchiveGrowthChart` and screenshot `Repository`,
`Empty` and `Dark` (the repository rule: verify UI visually before push).
Check: the bars are readable against the left axis and the footprint line
against the right one; the two stale bars near the right edge are visibly
lighter; the legend wraps without overlapping at 400 px width; the dark
story's footprint line is distinguishable from the bars; no label collides
on the X axis. Fix spacing in the component, not in the page.

### Task 5: Verification before G2

- [ ] **Step 1: Backend suite**

Run: `pytest tests/unit -q -x`
Expected: PASS. If `tests/unit/test_api_auth.py` fails on
`PUBLIC_BASE_URL`, that is the main checkout's `.env` leaking (known); rerun
with `env -u PUBLIC_BASE_URL`.

- [ ] **Step 2: Frontend suite**

Run: `cd frontend && npm run typecheck && npm run lint && npm run test -- --run && npm run check:locales && npm run format:check`
Expected: all pass.

- [ ] **Step 3: Update the spec's progress table**

Set phase 2 to `in review` in section 5.1 of the spec with the verification
output summarised in Notes, then stop at gate G2 and ask whether to commit.
Commit message convention: `feat(archives): repository growth graph (space family phase 2)`.

## Open questions

- **Two Y axes.** The mockup (screen 2) and this plan put the bars on a left
  byte axis and the two lines on a right byte axis, because a daily series
  makes the running total hundreds of times a typical bar. The dataviz
  guidance in this repository's toolchain rejects dual axes outright and
  would draw two stacked panels sharing the X axis (bars above, lines
  below). Same data, same component, one more `ComposedChart` with a
  `syncId`. Decide at G1; the plan as written follows the mockup.
- **KPI row.** The mockup shows four tiles above the chart (footprint,
  source, growth over 90 days, archive count). Spec 4.3 does not list them
  and the repository footprint already sits in the stats grid on the same
  page, so they are not planned. Add a task if wanted.
- **Source toggle persistence.** The toggle is component state and resets on
  navigation. The heatmap scale is persisted in localStorage; the toggle
  could follow the same pattern if users ask.
- **Series filter and the heatmap.** The growth series select is independent
  of the heatmap's "group by series". Sharing one selection across views was
  not discussed and is not planned.
