# Phase 3: Background Work Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. UI tasks use the `ui-ux-pro-max` skill and add Storybook stories per `AGENTS.md`.

**Goal:** Ship the Background work tab (spec 10.1), the per-repository
`OperationStatusStrip` (spec 10.2), the shared `CategoryToken`, the settings
nav entry, and the doc updates that make the operations pipeline (already
running server-side since phase 1) visible and controllable in the UI.

**Architecture:** This phase is frontend-only. Every backend route it needs
already exists and is exercised by tests: `GET/POST /api/operations*`
(list, queue, pause, resume, limits, cancel, logs) from phase 1, and
`GET /api/repositories/{id}/status-strip` plus
`POST /api/repositories/{id}/rebuild` from phase 2
(`app/api/archive_index.py:273-379`). New frontend code: a typed API client
layer over those routes, an SSE hook that turns `operation.updated` /
`operation.progress` events (spec 9.4, emitted by
`app/services/operations/events.py`) into React Query cache updates, a
`CategoryToken` primitive, the pipeline board component tree under
`frontend/src/components/background-work/`, the status strip on
`RepositoryCard`, and the Settings tab/sidebar wiring.

**Tech Stack:** React 18, TypeScript, MUI, `@tanstack/react-query`,
`react-i18next`, `lucide-react` icons, Vitest + Testing Library, Storybook.

**Spec:** `docs/engineering/specs/2026-09-03-repository-operations-and-archive-history.md`
sections 5, 6.3, 9.1, 9.2, 9.4, 9.5, 10.1, 10.2, and Appendix B. Review
focus per 19.3 is 10.1 and 10.2.

## Global Constraints

- All new strings go through `react-i18next`; add matching keys to
  `frontend/src/locales/en.json`, `de.json`, `es.json`, and `it.json` in the
  same task that introduces the string (spec section 10 preamble).
- Dialogs use `ResponsiveDialog`; rich dropdowns use `RichSelect` (spec 10
  preamble, `AGENTS.md`).
- No heavy left accent borders for cards, panels, alerts, or status surfaces
  (`AGENTS.md` UI Preferences).
- Every new or changed component ships a Storybook story (`AGENTS.md` UI
  Workflow).
- Types live in `frontend/src/types/operations.ts` (spec section 10
  preamble); this phase creates that file.
- The Background work tab is Community-tier — no `PlanGate`, no feature-key
  check. Only the `overdue` anomaly flag inside the status strip is
  Pro-gated, and the backend already returns `overdue: null` for
  Community installs (`app/api/archive_index.py:322`); the frontend renders
  that as "no data" rather than a warning.
- `docs/navigation.md` is updated in the same change that adds the sidebar
  entry (`AGENTS.md` Feature Planning).

---

## Task 1: Operations types and API client

**Files:**

- Create: `frontend/src/types/operations.ts`
- Modify: `frontend/src/services/api.ts` (add `operationsAPI`, extend
  `archivesAPI` — see Interfaces below for the exact insertion points)
- Test: `frontend/src/services/__tests__/api.test.ts`

**Interfaces:**

- Produces: `OperationCategory`, `OperationKind`, `OperationStatus`,
  `OperationTrigger` string unions; `OperationItem`, `QueueLimits`,
  `QueueRepository`, `QueueResponse`, `StatusStripCell`,
  `StatusStripResponse`, `RebuildStage` (`'stats' | 'archives' | 'history'`)
  types; `operationsAPI.{getQueue, pause, resume, updateLimits, cancel}` and
  `archivesAPI.{getStatusStrip, rebuild}` functions. Every later task
  imports types from `frontend/src/types/operations.ts` and calls these
  API functions — do not re-declare the shapes elsewhere.

The backend's `OperationItem` (`app/api/operations.py:43-84`),
`QueueResponse` (`:111-114`), `QueueLimits` (`:96-102`), and the
`status-strip` route's ad hoc dict (`app/api/archive_index.py:313-327`) are
the source of truth for field names below.

- [ ] **Step 1: Write the type file (no test needed for a pure type file;
      TypeScript's own compiler is the check — `npm run typecheck` covers
      this and runs in Task 12)**

```typescript
// frontend/src/types/operations.ts
// Mirrors app/services/operations/vocab.py (spec 6.3) and the response
// shapes in app/api/operations.py and app/api/archive_index.py.

export type OperationCategory =
  | 'import'
  | 'backup'
  | 'restore'
  | 'maintenance'
  | 'index'
  | 'mirror'
  | 'system'

export type OperationKind =
  | 'import_connect'
  | 'backup'
  | 'restore'
  | 'restore_check'
  | 'check'
  | 'prune'
  | 'compact'
  | 'delete_archive'
  | 'wipe'
  | 'rclone_sync'
  | 'package_install'
  | 'stats'
  | 'archive_sync'
  | 'history_index'
  | 'history_merge'

export type OperationStatus =
  | 'queued'
  | 'running'
  | 'completed'
  | 'completed_with_warnings'
  | 'failed'
  | 'cancelled'
  | 'skipped'

export type OperationTrigger =
  | 'manual'
  | 'schedule'
  | 'plan'
  | 'import'
  | 'followup'
  | 'reconcile'
  | 'retry'

export interface OperationItem {
  activity_key: string | null
  id: number
  type: string
  kind: OperationKind
  category: OperationCategory
  status: OperationStatus
  trigger: OperationTrigger
  priority: number
  run_id: string
  depends_on_id: number | null
  repository_id: number | null
  repository: string | null
  repository_path: string | null
  started_at: string | null
  completed_at: string | null
  created_at: string | null
  error_message: string | null
  skip_reason: string | null
  log_file_path: string | null
  triggered_by: string
  schedule_id: number | null
  schedule_name: string | null
  backup_plan_id: number | null
  backup_plan_run_id: number | null
  backup_plan_name: string | null
  archive_name: string | null
  package_name: string | null
  has_logs: boolean
  progress_percent: number | null
  progress_current: number | null
  progress_total: number | null
  progress_message: string | null
  execution_mode: string | null
  params: Record<string, unknown> | null
  result: Record<string, unknown> | null
  followups: OperationItem[]
}

export interface QueueLimits {
  index_workers: number
  index_running: number
  max_concurrent_backups: number
  max_concurrent_scheduled_backups: number
  max_concurrent_scheduled_checks: number
}

export interface QueueRepository {
  repository_id: number | null
  repository_name: string
  lane_busy: boolean
  operations: OperationItem[]
}

export interface QueueResponse {
  repositories: QueueRepository[]
  limits: QueueLimits
  paused: boolean
}

export type StatusStripCellKey = 'backup' | 'check' | 'prune' | 'compact' | 'index' | 'mirror'

export interface StatusStripCell {
  cell: StatusStripCellKey
  status: OperationStatus | null
  completed_at: string | null
  age_seconds: number | null
  threshold_days: number
  overdue: boolean | null
  running: boolean
  source: 'operations' | 'legacy' | null
}

export interface StatusStripResponse {
  cells: StatusStripCell[]
  overdue_available: boolean
}

export type RebuildStage = 'stats' | 'archives' | 'history'

export interface RebuildResponse {
  run_id: string | null
  operations: number[]
}

export interface OperationUpdatedEvent {
  type: 'operation.updated'
  data: OperationItem
  timestamp: string
}

export interface OperationProgressEvent {
  type: 'operation.progress'
  data: {
    id: number
    progress_percent: number | null
    progress_current: number | null
    progress_total: number | null
    progress_message: string | null
  }
  timestamp: string
}
```

- [ ] **Step 2: Write the failing API-shape tests**

Add to `frontend/src/services/__tests__/api.test.ts`, in a new
`describe` block (this file already imports `api` and uses
`axios-mock-adapter`; follow the existing pattern at the top of the file):

```typescript
import { operationsAPI } from '../api'
import { archivesAPI as archivesApiClient } from '../api'

describe('operationsAPI', () => {
  it('requests the queue view', async () => {
    const mock = new MockAdapter(api)
    mock.onGet('/operations/queue').reply(200, { repositories: [], limits: {}, paused: false })
    const response = await operationsAPI.getQueue()
    expect(response.data.paused).toBe(false)
    mock.restore()
  })

  it('pauses and resumes background work', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/operations/pause').reply(200, { paused: true })
    mock.onPost('/operations/resume').reply(200, { paused: false })
    await operationsAPI.pause()
    await operationsAPI.resume()
    expect(mock.history.post).toHaveLength(2)
    mock.restore()
  })

  it('updates index worker limits', async () => {
    const mock = new MockAdapter(api)
    mock.onPut('/operations/limits').reply(200, {})
    await operationsAPI.updateLimits(4)
    expect(JSON.parse(mock.history.put[0].data)).toEqual({ index_workers: 4 })
    mock.restore()
  })

  it('cancels an operation', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/operations/9/cancel').reply(200, {})
    await operationsAPI.cancel(9)
    expect(mock.history.post[0].url).toBe('/operations/9/cancel')
    mock.restore()
  })
})

describe('archivesAPI status strip and rebuild', () => {
  it('requests the status strip for a repository', async () => {
    const mock = new MockAdapter(api)
    mock.onGet('/repositories/3/status-strip').reply(200, { cells: [], overdue_available: false })
    const response = await archivesApiClient.getStatusStrip(3)
    expect(response.data.overdue_available).toBe(false)
    mock.restore()
  })

  it('requests a rebuild from a given stage', async () => {
    const mock = new MockAdapter(api)
    mock.onPost('/repositories/3/rebuild').reply(200, { run_id: 'r1', operations: [1, 2] })
    const response = await archivesApiClient.rebuild(3, 'archives')
    expect(JSON.parse(mock.history.post[0].data)).toEqual({ from: 'archives' })
    expect(response.data.run_id).toBe('r1')
    mock.restore()
  })
})
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/services/__tests__/api.test.ts`
Expected: FAIL — `operationsAPI` is not exported, `archivesAPI.getStatusStrip`
and `.rebuild` do not exist.

- [ ] **Step 4: Implement the client additions**

In `frontend/src/services/api.ts`, extend the existing `archivesAPI` block
(around line 677) by adding two methods, and add a new `operationsAPI`
export near it (follow the file's existing convention of one `export const
xAPI = {...}` block per resource, e.g. `settingsAPI` at line 725):

```typescript
// added inside the existing archivesAPI = { ... } block
getStatusStrip: (repositoryId: number) =>
  api.get<StatusStripResponse>(`/repositories/${repositoryId}/status-strip`),
rebuild: (repositoryId: number, from: RebuildStage) =>
  api.post<RebuildResponse>(`/repositories/${repositoryId}/rebuild`, { from }),
```

```typescript
// new export, placed after archivesAPI
export const operationsAPI = {
  getQueue: () => api.get<QueueResponse>('/operations/queue'),
  list: (params?: {
    repository_id?: number
    category?: string[]
    kind?: string[]
    status?: string[]
    trigger?: string[]
    run_id?: string
    since?: string
    limit?: number
    cursor?: number
  }) => api.get<{ items: OperationItem[]; next_cursor: number | null }>('/operations/', { params }),
  pause: () => api.post('/operations/pause'),
  resume: () => api.post('/operations/resume'),
  updateLimits: (indexWorkers: number) =>
    api.put<QueueLimits>('/operations/limits', { index_workers: indexWorkers }),
  cancel: (operationId: number) => api.post(`/operations/${operationId}/cancel`),
}
```

Add the needed type imports at the top of `api.ts`:

```typescript
import type {
  OperationItem,
  QueueResponse,
  QueueLimits,
  StatusStripResponse,
  RebuildStage,
  RebuildResponse,
} from '../types/operations'
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/services/__tests__/api.test.ts`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/types/operations.ts frontend/src/services/api.ts frontend/src/services/__tests__/api.test.ts
git commit -m "feat(operations): add operations/status-strip types and API client"
```

---

## Task 2: `useOperationEvents` SSE hook

**Files:**

- Create: `frontend/src/hooks/useOperationEvents.ts`
- Test: `frontend/src/hooks/__tests__/useOperationEvents.test.tsx`

**Interfaces:**

- Consumes: `OperationUpdatedEvent`, `OperationProgressEvent` from
  `frontend/src/types/operations.ts` (Task 1). The existing SSE stream is
  `GET /api/events/stream?token=...` (`app/api/events.py:139`, mounted at
  `/events`), which sends every event as a default `message` with a JSON
  body shaped `{type, data, timestamp}` — there is no per-type SSE `event:`
  line, so the hook must switch on `parsed.type` after `JSON.parse`.
- Produces: `useOperationEvents(onUpdated: (op: OperationItem) => void,
  onProgress: (progress: OperationProgressEvent['data']) => void): void`.
  Later tasks (3-6, 9) call this once each from the component that owns the
  relevant React Query cache (the pipeline board and the status strip), not
  globally, so a page without the board does not open a stream.

There is no existing shared SSE hook in the codebase (verified — searching
`frontend/src` for `EventSource` matches only an unrelated i18n key
`authEventSources`). This hook is the first one, per spec Appendix A.3's
phase-3 note. Auth token retrieval follows the pattern in
`frontend/src/services/authHeaders.ts` (`EventSource` cannot send custom
headers, hence the `?token=` query parameter the backend already accepts).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/hooks/__tests__/useOperationEvents.test.tsx
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useOperationEvents } from '../useOperationEvents'

class FakeEventSource {
  static instances: FakeEventSource[] = []
  onmessage: ((ev: MessageEvent) => void) | null = null
  onerror: (() => void) | null = null
  closed = false
  constructor(public url: string) {
    FakeEventSource.instances.push(this)
  }
  close() {
    this.closed = true
  }
  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) } as MessageEvent)
  }
}

vi.mock('../../services/authHeaders', () => ({
  getAccessToken: () => 'test-token',
}))

describe('useOperationEvents', () => {
  beforeEach(() => {
    FakeEventSource.instances = []
    vi.stubGlobal('EventSource', FakeEventSource)
  })
  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('opens a stream carrying the auth token', () => {
    renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    expect(FakeEventSource.instances).toHaveLength(1)
    expect(FakeEventSource.instances[0].url).toContain('token=test-token')
  })

  it('routes operation.updated events to onUpdated', () => {
    const onUpdated = vi.fn()
    renderHook(() => useOperationEvents(onUpdated, vi.fn()))
    const op = { id: 1, status: 'running' }
    FakeEventSource.instances[0].emit({ type: 'operation.updated', data: op, timestamp: 't' })
    expect(onUpdated).toHaveBeenCalledWith(op)
  })

  it('routes operation.progress events to onProgress', () => {
    const onProgress = vi.fn()
    renderHook(() => useOperationEvents(vi.fn(), onProgress))
    const progress = { id: 1, progress_percent: 50, progress_current: 5, progress_total: 10, progress_message: null }
    FakeEventSource.instances[0].emit({ type: 'operation.progress', data: progress, timestamp: 't' })
    expect(onProgress).toHaveBeenCalledWith(progress)
  })

  it('ignores unrelated event types', () => {
    const onUpdated = vi.fn()
    const onProgress = vi.fn()
    renderHook(() => useOperationEvents(onUpdated, onProgress))
    FakeEventSource.instances[0].emit({ type: 'connection_established', data: {}, timestamp: 't' })
    expect(onUpdated).not.toHaveBeenCalled()
    expect(onProgress).not.toHaveBeenCalled()
  })

  it('closes the stream on unmount', () => {
    const { unmount } = renderHook(() => useOperationEvents(vi.fn(), vi.fn()))
    unmount()
    expect(FakeEventSource.instances[0].closed).toBe(true)
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useOperationEvents.test.tsx`
Expected: FAIL — module `../useOperationEvents` does not exist.

- [ ] **Step 3: Check `authHeaders.ts` for the real token getter name**

Run: `grep -n "^export function get\|^export const get" frontend/src/services/authHeaders.ts`
If the exported name differs from `getAccessToken`, use the real name in
both the hook and the test's `vi.mock` call — do not invent a wrapper.

- [ ] **Step 4: Write the implementation**

```typescript
// frontend/src/hooks/useOperationEvents.ts
import { useEffect, useRef } from 'react'
import { BASE_PATH } from '../utils/basePath'
import { getAccessToken } from '../services/authHeaders'
import type { OperationItem, OperationProgressEvent } from '../types/operations'

type RawEvent = {
  type: string
  data: unknown
  timestamp: string
}

/**
 * Subscribes to the shared SSE stream (spec 9.4) and routes
 * `operation.updated` / `operation.progress` events to the caller. Opens
 * one connection per mounted consumer; callers should mount this once per
 * page (the pipeline board, the status strip), not globally.
 */
export function useOperationEvents(
  onUpdated: (op: OperationItem) => void,
  onProgress: (progress: OperationProgressEvent['data']) => void
): void {
  const onUpdatedRef = useRef(onUpdated)
  const onProgressRef = useRef(onProgress)
  onUpdatedRef.current = onUpdated
  onProgressRef.current = onProgress

  useEffect(() => {
    const token = getAccessToken()
    const url = `${BASE_PATH}/api/events/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`
    const source = new EventSource(url)

    source.onmessage = (event: MessageEvent) => {
      let parsed: RawEvent
      try {
        parsed = JSON.parse(event.data)
      } catch {
        return
      }
      if (parsed.type === 'operation.updated') {
        onUpdatedRef.current(parsed.data as OperationItem)
      } else if (parsed.type === 'operation.progress') {
        onProgressRef.current(parsed.data as OperationProgressEvent['data'])
      }
    }

    return () => {
      source.close()
    }
  }, [])
}
```

If `getAccessToken` is not the real exported name from
`authHeaders.ts` (Step 3), substitute it here and keep the `vi.mock` path
in the test aligned.

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/hooks/__tests__/useOperationEvents.test.tsx`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add frontend/src/hooks/useOperationEvents.ts frontend/src/hooks/__tests__/useOperationEvents.test.tsx
git commit -m "feat(operations): add SSE hook for operation.updated and operation.progress"
```

---

## Task 3: `CategoryToken`

**Files:**

- Create: `frontend/src/components/CategoryToken.tsx`
- Create: `frontend/src/components/CategoryToken.stories.tsx`
- Test: `frontend/src/components/__tests__/CategoryToken.test.tsx`

**Interfaces:**

- Consumes: `OperationCategory` from `frontend/src/types/operations.ts`.
- Produces: `<CategoryToken category={OperationCategory} size?: 'small' |
  'medium' />` rendering an icon plus label `Chip`-like token. Tasks 4-10
  (pipeline cards, status strip cells, and — in phase 4/5, out of this
  plan's scope — Activity) import this component; the prop name is
  `category`, not `kind` or `type`.

Category to icon/color mapping (spec 6.3 category list: `import`, `backup`,
`restore`, `maintenance`, `index`, `mirror`, `system`). Reuse
`lucide-react`, already the icon library in `RepositoryCard.tsx`, and MUI
theme palette keys so dark mode is automatic (no hardcoded hex per
`AGENTS.md`'s "no left accent borders" spirit — this file sets the pattern
other 10.1/10.2 components copy).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/__tests__/CategoryToken.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import CategoryToken from '../CategoryToken'

describe('CategoryToken', () => {
  it('renders the label for each known category', () => {
    const categories: Array<[string, string]> = [
      ['backup', 'Backup'],
      ['maintenance', 'Maintenance'],
      ['index', 'Index'],
      ['mirror', 'Mirror'],
      ['restore', 'Restore'],
      ['import', 'Import'],
      ['system', 'System'],
    ]
    categories.forEach(([category, label]) => {
      const { unmount } = render(<CategoryToken category={category as never} />)
      expect(screen.getByText(label)).toBeInTheDocument()
      unmount()
    })
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/CategoryToken.test.tsx`
Expected: FAIL — module `../CategoryToken` does not exist.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/CategoryToken.tsx
import { Box, Chip, useTheme, alpha } from '@mui/material'
import {
  Download,
  Save,
  RotateCcw,
  Wrench,
  Database,
  Cloud,
  Package,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { OperationCategory } from '../types/operations'

const ICONS: Record<OperationCategory, React.ComponentType<{ size?: number }>> = {
  import: Download,
  backup: Save,
  restore: RotateCcw,
  maintenance: Wrench,
  index: Database,
  mirror: Cloud,
  system: Package,
}

const PALETTE_KEYS: Record<OperationCategory, 'primary' | 'success' | 'warning' | 'info' | 'secondary'> = {
  import: 'info',
  backup: 'success',
  restore: 'primary',
  maintenance: 'warning',
  index: 'secondary',
  mirror: 'info',
  system: 'secondary',
}

interface CategoryTokenProps {
  category: OperationCategory
  size?: 'small' | 'medium'
}

export default function CategoryToken({ category, size = 'small' }: CategoryTokenProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const Icon = ICONS[category]
  const colorKey = PALETTE_KEYS[category]
  const color = (theme.palette[colorKey] as { main: string }).main
  return (
    <Chip
      size={size}
      icon={
        <Box sx={{ display: 'flex', alignItems: 'center', pl: 0.5 }}>
          <Icon size={size === 'small' ? 12 : 14} />
        </Box>
      }
      label={t(`operations.category.${category}`)}
      sx={{
        bgcolor: alpha(color, 0.12),
        color,
        fontWeight: 600,
        '& .MuiChip-icon': { color },
      }}
    />
  )
}
```

- [ ] **Step 4: Add i18n keys**

Add to `frontend/src/locales/en.json` (new top-level `"operations"` key,
placed alphabetically near `"notifications"`/`"preferences"`; mirror the
same key structure into `de.json`, `es.json`, `it.json` with translated
values — do not leave non-English locales with English fallback strings):

```json
"operations": {
  "category": {
    "import": "Import",
    "backup": "Backup",
    "restore": "Restore",
    "maintenance": "Maintenance",
    "index": "Index",
    "mirror": "Mirror",
    "system": "System"
  }
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/__tests__/CategoryToken.test.tsx`
Expected: PASS

- [ ] **Step 6: Write the Storybook story**

```typescript
// frontend/src/components/CategoryToken.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack } from '@mui/material'
import CategoryToken from './CategoryToken'
import type { OperationCategory } from '../types/operations'

const CATEGORIES: OperationCategory[] = [
  'import',
  'backup',
  'restore',
  'maintenance',
  'index',
  'mirror',
  'system',
]

const meta = {
  title: 'Components/CategoryToken',
} satisfies Meta<typeof CategoryToken>

export default meta

type Story = StoryObj<typeof meta>

export const AllCategories: Story = {
  render: () => (
    <Stack direction="row" spacing={1} flexWrap="wrap">
      {CATEGORIES.map((category) => (
        <CategoryToken key={category} category={category} />
      ))}
    </Stack>
  ),
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/CategoryToken.tsx frontend/src/components/CategoryToken.stories.tsx frontend/src/components/__tests__/CategoryToken.test.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add CategoryToken shared component"
```

---

## Task 4: `PipelineStageColumn` and `PipelineRepositoryCard`

**Files:**

- Create: `frontend/src/components/background-work/PipelineStageColumn.tsx`
- Create: `frontend/src/components/background-work/PipelineRepositoryCard.tsx`
- Create: `frontend/src/components/background-work/PipelineStageColumn.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/PipelineStageColumn.test.tsx`
- Test: `frontend/src/components/background-work/__tests__/PipelineRepositoryCard.test.tsx`

**Interfaces:**

- Consumes: `OperationItem`, `QueueRepository` from
  `frontend/src/types/operations.ts` (Task 1).
- Produces: `<PipelineRepositoryCard operation={OperationItem} onRetry?:
  (operationId: number) => void />` and `<PipelineStageColumn stage={{
  key: string; label: string; operations: OperationItem[] }} workerControl?:
  ReactNode />`. Task 6 (`PipelineBoard`) renders one `PipelineStageColumn`
  per stage and passes it the operations bucketed for that stage; it also
  passes `workerControl` only to the "History index" column (the mock at
  spec 10.1 shows `workers: index 2` under that column).

Stage bucketing (from the spec 10.1 mock's five columns "Connect, Stats,
Archives, History index, Ready") maps directly onto `OperationItem.kind`:
`import_connect` → Connect, `stats` → Stats, `archive_sync` → Archives,
`history_index` → History index. "Ready" is not a `kind` — it is the set of
operations whose `status` is `completed` / `completed_with_warnings`
that finished within the queue route's 60-second recent window
(`app/api/operations.py:38,278-281` — the backend already only returns
these, so "Ready" is simply every queue item whose status is terminal).
`history_merge` is pure SQL and typically finishes within the same request
cycle; it renders in the "Ready" column like any other terminal kind rather
than getting a sixth column, since the spec's mock only shows five.

- [ ] **Step 1: Write the failing tests**

```typescript
// frontend/src/components/background-work/__tests__/PipelineRepositoryCard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import PipelineRepositoryCard from '../PipelineRepositoryCard'
import type { OperationItem } from '../../../types/operations'

const baseOp: OperationItem = {
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'archive_sync',
  category: 'index',
  status: 'running',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 5,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: null,
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: 40,
  progress_current: 14,
  progress_total: 38,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
}

describe('PipelineRepositoryCard', () => {
  it('shows the repository name and a progress bar while running', () => {
    render(<PipelineRepositoryCard operation={baseOp} />)
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByRole('progressbar')).toBeInTheDocument()
  })

  it('shows a retry action for a failed operation and calls onRetry', () => {
    const onRetry = vi.fn()
    render(
      <PipelineRepositoryCard
        operation={{ ...baseOp, status: 'failed', progress_percent: null }}
        onRetry={onRetry}
      />
    )
    fireEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledWith(1)
  })

  it('renders no retry action for a running operation', () => {
    render(<PipelineRepositoryCard operation={baseOp} onRetry={vi.fn()} />)
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })
})
```

```typescript
// frontend/src/components/background-work/__tests__/PipelineStageColumn.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import PipelineStageColumn from '../PipelineStageColumn'
import type { OperationItem } from '../../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: overrides.id ?? 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'queued',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: null,
  completed_at: null,
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

describe('PipelineStageColumn', () => {
  it('shows the stage label and operation count', () => {
    render(
      <PipelineStageColumn stage={{ key: 'stats', label: 'Stats', operations: [op({}), op({ id: 2 })] }} />
    )
    expect(screen.getByText('Stats')).toBeInTheDocument()
    expect(screen.getByText('2')).toBeInTheDocument()
  })

  it('renders a card per operation', () => {
    render(
      <PipelineStageColumn stage={{ key: 'stats', label: 'Stats', operations: [op({}), op({ id: 2 })] }} />
    )
    expect(screen.getAllByText('nas')).toHaveLength(2)
  })

  it('renders the worker control when provided', () => {
    render(
      <PipelineStageColumn
        stage={{ key: 'history_index', label: 'History index', operations: [] }}
        workerControl={<span>workers: index 2</span>}
      />
    )
    expect(screen.getByText('workers: index 2')).toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/PipelineRepositoryCard.test.tsx src/components/background-work/__tests__/PipelineStageColumn.test.tsx`
Expected: FAIL — modules do not exist.

- [ ] **Step 3: Write `PipelineRepositoryCard`**

```typescript
// frontend/src/components/background-work/PipelineRepositoryCard.tsx
import { Box, Typography, LinearProgress, IconButton, Tooltip, alpha, useTheme } from '@mui/material'
import { RotateCw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatElapsedTime } from '../../utils/dateUtils'
import type { OperationItem } from '../../types/operations'

interface PipelineRepositoryCardProps {
  operation: OperationItem
  onRetry?: (operationId: number) => void
}

export default function PipelineRepositoryCard({ operation, onRetry }: PipelineRepositoryCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const isFailed = operation.status === 'failed'
  const isRunning = operation.status === 'running'

  return (
    <Box
      sx={{
        border: '1px solid',
        borderColor: isFailed
          ? alpha(theme.palette.error.main, 0.4)
          : isDark
            ? alpha('#fff', 0.08)
            : alpha('#000', 0.08),
        borderRadius: 1.5,
        p: 1,
        mb: 1,
        bgcolor: isDark ? alpha('#fff', 0.02) : alpha('#000', 0.015),
      }}
    >
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <Typography variant="body2" fontWeight={600} noWrap>
          {operation.repository ?? t('operations.background.systemRow')}
        </Typography>
        {isFailed && onRetry && (
          <Tooltip title={t('operations.background.retry')}>
            <IconButton
              size="small"
              aria-label={t('operations.background.retry')}
              onClick={() => onRetry(operation.id)}
            >
              <RotateCw size={14} />
            </IconButton>
          </Tooltip>
        )}
      </Box>
      <Typography variant="caption" color="text.secondary">
        {operation.status === 'queued'
          ? t('operations.background.waiting')
          : isRunning && operation.started_at
            ? formatElapsedTime(operation.started_at)
            : isFailed
              ? t('operations.background.failed')
              : t(`operations.status.${operation.status}`)}
      </Typography>
      {isRunning && operation.progress_percent != null && (
        <LinearProgress
          variant="determinate"
          value={operation.progress_percent}
          sx={{ mt: 0.5, height: 4, borderRadius: 2 }}
        />
      )}
    </Box>
  )
}
```

Check `formatElapsedTime`'s real signature before using it
(`grep -n "export function formatElapsedTime" frontend/src/utils/dateUtils.ts`)
— it is already imported this way in `RepositoryCard.tsx:32`, so match its
argument type (likely a start timestamp string or `Date`) exactly.

- [ ] **Step 4: Write `PipelineStageColumn`**

```typescript
// frontend/src/components/background-work/PipelineStageColumn.tsx
import { Box, Typography, Chip } from '@mui/material'
import type { ReactNode } from 'react'
import PipelineRepositoryCard from './PipelineRepositoryCard'
import type { OperationItem } from '../../types/operations'

interface PipelineStageColumnProps {
  stage: {
    key: string
    label: string
    operations: OperationItem[]
  }
  workerControl?: ReactNode
  onRetry?: (operationId: number) => void
}

export default function PipelineStageColumn({ stage, workerControl, onRetry }: PipelineStageColumnProps) {
  return (
    <Box sx={{ minWidth: 200, flex: 1 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
        <Typography variant="subtitle2">{stage.label}</Typography>
        <Chip size="small" label={stage.operations.length} />
      </Box>
      {stage.operations.map((op) => (
        <PipelineRepositoryCard key={op.id} operation={op} onRetry={onRetry} />
      ))}
      {workerControl}
    </Box>
  )
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/PipelineRepositoryCard.test.tsx src/components/background-work/__tests__/PipelineStageColumn.test.tsx`
Expected: PASS

- [ ] **Step 6: Add i18n keys**

Add under the `"operations"` key introduced in Task 3, in all four locale
files:

```json
"operations": {
  "background": {
    "systemRow": "System",
    "retry": "Retry",
    "waiting": "waiting",
    "failed": "failed"
  },
  "status": {
    "queued": "Queued",
    "running": "Running",
    "completed": "Completed",
    "completed_with_warnings": "Completed with warnings",
    "failed": "Failed",
    "cancelled": "Cancelled",
    "skipped": "Skipped"
  }
}
```

- [ ] **Step 7: Write the Storybook story**

```typescript
// frontend/src/components/background-work/PipelineStageColumn.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack } from '@mui/material'
import PipelineStageColumn from './PipelineStageColumn'
import type { OperationItem } from '../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'archive_sync',
  category: 'index',
  status: 'running',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: 40,
  progress_current: 14,
  progress_total: 38,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

const meta = {
  title: 'BackgroundWork/PipelineStageColumn',
} satisfies Meta<typeof PipelineStageColumn>

export default meta

type Story = StoryObj<typeof meta>

export const Mixed: Story = {
  render: () => (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" spacing={3}>
        <PipelineStageColumn stage={{ key: 'connect', label: 'Connect', operations: [op({ id: 1, kind: 'import_connect', status: 'queued', repository: 'offsite' })] }} />
        <PipelineStageColumn stage={{ key: 'stats', label: 'Stats', operations: [op({ id: 2, kind: 'stats', repository: 'nas' })] }} />
        <PipelineStageColumn
          stage={{ key: 'history_index', label: 'History index', operations: [op({ id: 3, kind: 'history_index', repository: 'photos', progress_current: 14, progress_total: 38, progress_percent: 37 })] }}
          workerControl={<Box sx={{ fontSize: 12, color: 'text.secondary', mt: 1 }}>workers: index 2</Box>}
        />
        <PipelineStageColumn
          stage={{ key: 'ready', label: 'Ready', operations: [op({ id: 4, kind: 'stats', status: 'completed', repository: 'laptop' })] }}
        />
      </Stack>
    </Box>
  ),
}

export const WithFailure: Story = {
  render: () => (
    <Box sx={{ p: 3, maxWidth: 260 }}>
      <PipelineStageColumn
        stage={{ key: 'archives', label: 'Archives', operations: [op({ id: 5, kind: 'archive_sync', status: 'failed', repository: 'offsite', progress_percent: null })] }}
        onRetry={() => {}}
      />
    </Box>
  ),
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/background-work/PipelineStageColumn.tsx frontend/src/components/background-work/PipelineRepositoryCard.tsx frontend/src/components/background-work/PipelineStageColumn.stories.tsx frontend/src/components/background-work/__tests__/PipelineStageColumn.test.tsx frontend/src/components/background-work/__tests__/PipelineRepositoryCard.test.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add pipeline stage column and repository card"
```

---

## Task 5: `ForegroundLaneRow`

**Files:**

- Create: `frontend/src/components/background-work/ForegroundLaneRow.tsx`
- Create: `frontend/src/components/background-work/ForegroundLaneRow.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/ForegroundLaneRow.test.tsx`

**Interfaces:**

- Consumes: `OperationItem`, `CategoryToken` (Task 3).
- Produces: `<ForegroundLaneRow operation={OperationItem} />`, rendering
  nothing (`null`) when there is no running exclusive foreground operation.
  Task 6 passes it the queue's lane holder, if any — an operation whose
  `category` is one of `backup`, `restore`, or `maintenance` and whose
  `status` is `running`, found across `QueueResponse.repositories[].
  operations`. Per spec 10.1, this row has "a link to Activity and no
  controls."

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/background-work/__tests__/ForegroundLaneRow.test.tsx
import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import ForegroundLaneRow from '../ForegroundLaneRow'
import type { OperationItem } from '../../../types/operations'

const op: OperationItem = {
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'backup',
  category: 'backup',
  status: 'running',
  trigger: 'schedule',
  priority: 5,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 7,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'schedule',
  schedule_id: null,
  schedule_name: 'nightly',
  backup_plan_id: 2,
  backup_plan_run_id: null,
  backup_plan_name: 'nightly',
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
}

describe('ForegroundLaneRow', () => {
  it('renders the repository, kind, and plan name with a link to Activity', () => {
    render(
      <MemoryRouter>
        <ForegroundLaneRow operation={op} />
      </MemoryRouter>
    )
    expect(screen.getByText('nas')).toBeInTheDocument()
    expect(screen.getByText(/nightly/)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /activity/i })).toHaveAttribute(
      'href',
      expect.stringContaining('repository_id=7')
    )
  })

  it('renders no action buttons', () => {
    render(
      <MemoryRouter>
        <ForegroundLaneRow operation={op} />
      </MemoryRouter>
    )
    expect(screen.queryByRole('button')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/ForegroundLaneRow.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/background-work/ForegroundLaneRow.tsx
import { Box, Typography, Link as MuiLink } from '@mui/material'
import { Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import CategoryToken from '../CategoryToken'
import { formatElapsedTime } from '../../utils/dateUtils'
import type { OperationItem } from '../../types/operations'

interface ForegroundLaneRowProps {
  operation: OperationItem
}

export default function ForegroundLaneRow({ operation }: ForegroundLaneRowProps) {
  const { t } = useTranslation()
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 1 }}>
      <CategoryToken category={operation.category} />
      <Typography variant="body2">
        {operation.repository} {t(`operations.kind.${operation.kind}`)}
        {operation.backup_plan_name ? ` (${t('operations.background.plan')}: ${operation.backup_plan_name})` : ''}
      </Typography>
      {operation.started_at && (
        <Typography variant="caption" color="text.secondary">
          {formatElapsedTime(operation.started_at)}
        </Typography>
      )}
      <Typography variant="caption" color="text.secondary">
        {t('operations.background.holdsLane')}
      </Typography>
      <MuiLink
        component={RouterLink}
        to={`/activity?repository_id=${operation.repository_id}`}
        sx={{ ml: 'auto' }}
      >
        {t('operations.background.viewActivity')}
      </MuiLink>
    </Box>
  )
}
```

- [ ] **Step 4: Add i18n keys**

Under `"operations"` in all four locale files:

```json
"kind": {
  "import_connect": "connect",
  "backup": "backup",
  "restore": "restore",
  "restore_check": "restore check",
  "check": "check",
  "prune": "prune",
  "compact": "compact",
  "delete_archive": "delete archive",
  "wipe": "wipe",
  "rclone_sync": "mirror sync",
  "package_install": "package install",
  "stats": "stats",
  "archive_sync": "archive sync",
  "history_index": "history index",
  "history_merge": "history merge"
},
"background": {
  "plan": "plan",
  "holdsLane": "→ holds the lane",
  "viewActivity": "Activity ▸"
}
```

(merge into the existing `"operations.background"` object added in Task 4
rather than duplicating the key)

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/ForegroundLaneRow.test.tsx`
Expected: PASS

- [ ] **Step 6: Write the Storybook story**

```typescript
// frontend/src/components/background-work/ForegroundLaneRow.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import ForegroundLaneRow from './ForegroundLaneRow'
import type { OperationItem } from '../../types/operations'

const op: OperationItem = {
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'backup',
  category: 'backup',
  status: 'running',
  trigger: 'schedule',
  priority: 5,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 7,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'schedule',
  schedule_id: null,
  schedule_name: 'nightly',
  backup_plan_id: 2,
  backup_plan_run_id: null,
  backup_plan_name: 'nightly',
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
}

const meta = {
  title: 'BackgroundWork/ForegroundLaneRow',
} satisfies Meta<typeof ForegroundLaneRow>

export default meta

type Story = StoryObj<typeof meta>

export const Running: Story = {
  render: () => (
    <MemoryRouter>
      <Box sx={{ p: 3, maxWidth: 480 }}>
        <ForegroundLaneRow operation={op} />
      </Box>
    </MemoryRouter>
  ),
}
```

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/background-work/ForegroundLaneRow.tsx frontend/src/components/background-work/ForegroundLaneRow.stories.tsx frontend/src/components/background-work/__tests__/ForegroundLaneRow.test.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add ForegroundLaneRow"
```

---

## Task 6: `PipelineBoard`

**Files:**

- Create: `frontend/src/components/background-work/PipelineBoard.tsx`
- Create: `frontend/src/components/background-work/PipelineBoard.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/PipelineBoard.test.tsx`

**Interfaces:**

- Consumes: `operationsAPI.getQueue` and `operationsAPI.cancel` (Task 1),
  `useOperationEvents` (Task 2), `PipelineStageColumn` (Task 4),
  `ForegroundLaneRow` (Task 5), `EmptyStateCard` (existing,
  `frontend/src/components/EmptyStateCard.tsx`).
- Produces: `<PipelineBoard />` with no required props — it owns its own
  `useQuery(['operations-queue'], operationsAPI.getQueue)` and merges live
  SSE updates into that query's cache via `queryClient.setQueryData`. Task 9
  (`BackgroundWorkTab`) renders this plus the header controls (pause/resume,
  rebuild menu, worker limit) around it; the board itself has no header.

Empty state: spec 10.1 says "an `EmptyStateCard` saying nothing is running,
with the last reconcile time." There is no "last reconcile time" field on
`QueueResponse` today — recording that requires either a new backend field
or reading it from the most recent `index`-category operation's
`completed_at` client-side. Resolve this at plan review (G1): the simplest
in-scope option is deriving it client-side from the queue response's own
`repositories[].operations` (a completed index op still shows up for 60
seconds per `RECENT_WINDOW`, but a *last* reconcile could be older). Given
no backend field exists and this phase adds no backend routes, the plan
takes the pragmatic path: show the `EmptyStateCard` with just the "nothing
running" message, and log this gap under Open Questions rather than
guessing a backend contract Opus 5's review would need to re-derive.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/background-work/__tests__/PipelineBoard.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import PipelineBoard from '../PipelineBoard'
import { operationsAPI } from '../../../services/api'

vi.mock('../../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn(),
    cancel: vi.fn(),
  },
}))

vi.mock('../../../hooks/useOperationEvents', () => ({
  useOperationEvents: vi.fn(),
}))

function renderBoard() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <PipelineBoard />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

const queueOp = (overrides: Record<string, unknown>) => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'queued',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: null,
  completed_at: null,
  created_at: new Date().toISOString(),
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

describe('PipelineBoard', () => {
  it('renders a column per stage with the right operations', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [
          { repository_id: 1, repository_name: 'nas', lane_busy: false, operations: [queueOp({})] },
        ],
        limits: { index_workers: 2, index_running: 1, max_concurrent_backups: 1, max_concurrent_scheduled_backups: 2, max_concurrent_scheduled_checks: 4 },
        paused: false,
      },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByText('nas')).toBeInTheDocument())
    expect(screen.getByText('Stats')).toBeInTheDocument()
  })

  it('renders the foreground lane row for a running exclusive operation', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        repositories: [
          {
            repository_id: 1,
            repository_name: 'nas',
            lane_busy: true,
            operations: [queueOp({ kind: 'backup', category: 'backup', status: 'running' })],
          },
        ],
        limits: { index_workers: 2, index_running: 0, max_concurrent_backups: 1, max_concurrent_scheduled_backups: 2, max_concurrent_scheduled_checks: 4 },
        paused: false,
      },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByRole('link', { name: /activity/i })).toBeInTheDocument())
  })

  it('shows the empty state when nothing is running', async () => {
    ;(operationsAPI.getQueue as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: { repositories: [], limits: { index_workers: 2, index_running: 0, max_concurrent_backups: 1, max_concurrent_scheduled_backups: 2, max_concurrent_scheduled_checks: 4 }, paused: false },
    })
    renderBoard()
    await waitFor(() => expect(screen.getByText(/nothing is running/i)).toBeInTheDocument())
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/PipelineBoard.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/background-work/PipelineBoard.tsx
import { useCallback, useMemo } from 'react'
import { Box, Stack, Typography } from '@mui/material'
import { ListChecks } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import PipelineStageColumn from './PipelineStageColumn'
import ForegroundLaneRow from './ForegroundLaneRow'
import EmptyStateCard from '../EmptyStateCard'
import { operationsAPI } from '../../services/api'
import { useOperationEvents } from '../../hooks/useOperationEvents'
import type { OperationItem, QueueResponse } from '../../types/operations'

const QUEUE_KEY = ['operations-queue'] as const

const STAGE_KINDS: Array<{ key: string; labelKey: string; kind: OperationItem['kind'] }> = [
  { key: 'connect', labelKey: 'operations.background.stage.connect', kind: 'import_connect' },
  { key: 'stats', labelKey: 'operations.background.stage.stats', kind: 'stats' },
  { key: 'archives', labelKey: 'operations.background.stage.archives', kind: 'archive_sync' },
  { key: 'history', labelKey: 'operations.background.stage.history', kind: 'history_index' },
]

const TERMINAL_STATUSES = new Set(['completed', 'completed_with_warnings', 'failed', 'cancelled', 'skipped'])
const FOREGROUND_CATEGORIES = new Set(['backup', 'restore', 'maintenance'])

export default function PipelineBoard() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data, isLoading } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
    refetchInterval: 15000,
  })

  const onUpdated = useCallback(
    (updated: OperationItem) => {
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) => {
        if (!current) return current
        return {
          ...current,
          repositories: current.repositories.map((repo) => ({
            ...repo,
            operations: repo.operations.some((op) => op.id === updated.id)
              ? repo.operations.map((op) => (op.id === updated.id ? updated : op))
              : repo.repository_id === updated.repository_id
                ? [...repo.operations, updated]
                : repo.operations,
          })),
        }
      })
    },
    [queryClient]
  )

  const onProgress = useCallback(
    (progress: { id: number; progress_percent: number | null; progress_current: number | null; progress_total: number | null; progress_message: string | null }) => {
      queryClient.setQueryData<QueueResponse | undefined>(QUEUE_KEY, (current) => {
        if (!current) return current
        return {
          ...current,
          repositories: current.repositories.map((repo) => ({
            ...repo,
            operations: repo.operations.map((op) => (op.id === progress.id ? { ...op, ...progress } : op)),
          })),
        }
      })
    },
    [queryClient]
  )

  useOperationEvents(onUpdated, onProgress)

  const allOperations = useMemo(
    () => data?.repositories.flatMap((repo) => repo.operations) ?? [],
    [data]
  )

  const foreground = allOperations.find(
    (op) => FOREGROUND_CATEGORIES.has(op.category) && op.status === 'running'
  )

  const readyOperations = allOperations.filter((op) => TERMINAL_STATUSES.has(op.status))

  const handleRetry = useCallback(
    (_operationId: number) => {
      // Retry is a rebuild-from-stage action owned by RebuildMenu (Task 8);
      // a per-card retry re-enqueues the same kind at manual priority via
      // the rebuild route, wired in Task 9 where the repository id is
      // available from the queue row.
    },
    []
  )

  if (!isLoading && allOperations.length === 0) {
    return (
      <EmptyStateCard
        icon={<ListChecks size={48} />}
        title={t('operations.background.emptyTitle')}
        description={t('operations.background.emptyDescription')}
      />
    )
  }

  return (
    <Box>
      {foreground && (
        <Box sx={{ mb: 2 }}>
          <ForegroundLaneRow operation={foreground} />
        </Box>
      )}
      <Stack direction="row" spacing={3} sx={{ overflowX: 'auto', pb: 1 }}>
        {STAGE_KINDS.map((stage) => (
          <PipelineStageColumn
            key={stage.key}
            stage={{
              key: stage.key,
              label: t(stage.labelKey),
              operations: allOperations.filter((op) => op.kind === stage.kind && !TERMINAL_STATUSES.has(op.status)),
            }}
            workerControl={
              stage.key === 'history' && data ? (
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
                  {t('operations.background.workers', { count: data.limits.index_workers })}
                </Typography>
              ) : undefined
            }
            onRetry={handleRetry}
          />
        ))}
        <PipelineStageColumn
          stage={{ key: 'ready', label: t('operations.background.stage.ready'), operations: readyOperations }}
        />
      </Stack>
    </Box>
  )
}
```

- [ ] **Step 4: Add i18n keys**

Under `"operations.background"` in all four locale files:

```json
"stage": {
  "connect": "Connect",
  "stats": "Stats",
  "archives": "Archives",
  "history": "History index",
  "ready": "Ready"
},
"workers": "workers: index {{count}}",
"emptyTitle": "Nothing is running",
"emptyDescription": "Background work will appear here the next time an import, backup, or reconcile run starts."
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/PipelineBoard.test.tsx`
Expected: PASS

- [ ] **Step 6: Write the Storybook story**

```typescript
// frontend/src/components/background-work/PipelineBoard.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import PipelineBoard from './PipelineBoard'

const meta = {
  title: 'BackgroundWork/PipelineBoard',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof PipelineBoard>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <PipelineBoard />
        </Box>
      </MemoryRouter>
    </QueryClientProvider>
  ),
}
```

Note in the story file (as a comment) that this story shows loading/empty
state only without a mocked `operationsAPI`; Storybook mock service worker
wiring for authenticated API responses follows whatever pattern
`RepositoryCard.stories.tsx` or similar already use — check
`grep -rln "msw\|mockServiceWorker" frontend/src/components/*.stories.tsx`
before deciding whether to add API mocking here or leave it to a `.mdx`
docs page; if no existing story mocks `useQuery` data, match that
precedent rather than introducing MSW for the first time in this task.

- [ ] **Step 7: Commit**

```bash
git add frontend/src/components/background-work/PipelineBoard.tsx frontend/src/components/background-work/PipelineBoard.stories.tsx frontend/src/components/background-work/__tests__/PipelineBoard.test.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add PipelineBoard"
```

---

## Task 7: `RepositoryTrackDialog`

**Files:**

- Create: `frontend/src/components/background-work/RepositoryTrackDialog.tsx`
- Create: `frontend/src/components/background-work/RepositoryTrackDialog.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/RepositoryTrackDialog.test.tsx`

**Interfaces:**

- Consumes: `ResponsiveDialog` (`frontend/src/components/shared/ResponsiveDialog.tsx`),
  `RichSelect` (`frontend/src/components/shared/RichSelect.tsx`),
  `archivesAPI.rebuild` (Task 1), `OperationItem`, `RebuildStage`.
- Produces: `<RepositoryTrackDialog open={boolean} onClose={() => void}
  repositoryId={number} repositoryName={string} operations={OperationItem[]}
  />`. Task 9 opens this when a `PipelineRepositoryCard` (or a future
  repository-detail entry point) is clicked; wire the click handler in
  Task 9, not here — this task only builds the dialog itself.

Before writing this component, read `ResponsiveDialog`'s and `RichSelect`'s
actual prop signatures (`sed -n '1,60p' frontend/src/components/shared/ResponsiveDialog.tsx`
and the same for `RichSelect.tsx`) so the props used below match reality —
do not guess prop names.

- [ ] **Step 1: Read the shared component signatures**

Run:
```bash
grep -n "interface.*Props\|export default function" frontend/src/components/shared/ResponsiveDialog.tsx
grep -n "interface.*Props\|export default function\|export function RichSelect" frontend/src/components/shared/RichSelect.tsx
```
Use the real prop names (likely `open`, `onClose`, `title`, `children` for
`ResponsiveDialog`, and `value`/`onChange`/`options` for `RichSelect`) in
Steps 3-4 below.

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/components/background-work/__tests__/RepositoryTrackDialog.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import RepositoryTrackDialog from '../RepositoryTrackDialog'
import { archivesAPI } from '../../../services/api'
import type { OperationItem } from '../../../types/operations'

vi.mock('../../../services/api', () => ({
  archivesAPI: { rebuild: vi.fn().mockResolvedValue({ data: { run_id: 'r1', operations: [1] } }) },
}))

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'completed',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 3,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: '2026-09-04T00:01:00Z',
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

describe('RepositoryTrackDialog', () => {
  it('renders one row per operation with its stage timing', () => {
    render(
      <RepositoryTrackDialog
        open
        onClose={vi.fn()}
        repositoryId={3}
        repositoryName="nas"
        operations={[op({ kind: 'stats' }), op({ id: 2, kind: 'archive_sync' })]}
      />
    )
    expect(screen.getByText('nas')).toBeInTheDocument()
  })

  it('triggers a rebuild for the selected stage', async () => {
    render(
      <RepositoryTrackDialog open onClose={vi.fn()} repositoryId={3} repositoryName="nas" operations={[op({})]} />
    )
    fireEvent.click(screen.getByRole('button', { name: /rebuild from/i }))
    await waitFor(() => expect(archivesAPI.rebuild).toHaveBeenCalledWith(3, 'stats'))
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/RepositoryTrackDialog.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Write the implementation**

Build using the real `ResponsiveDialog` and `RichSelect` signatures found
in Step 1. Structural shape (adjust prop names to match what Step 1 found):

```typescript
// frontend/src/components/background-work/RepositoryTrackDialog.tsx
import { useState } from 'react'
import { Box, Typography, Button, Stack } from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import RichSelect from '../shared/RichSelect'
import CategoryToken from '../CategoryToken'
import { archivesAPI } from '../../services/api'
import type { OperationItem, RebuildStage } from '../../types/operations'

interface RepositoryTrackDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  operations: OperationItem[]
}

const REBUILD_STAGES: RebuildStage[] = ['stats', 'archives', 'history']

export default function RepositoryTrackDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  operations,
}: RepositoryTrackDialogProps) {
  const { t } = useTranslation()
  const [stage, setStage] = useState<RebuildStage>('stats')
  const [submitting, setSubmitting] = useState(false)

  const handleRebuild = async () => {
    setSubmitting(true)
    try {
      await archivesAPI.rebuild(repositoryId, stage)
    } finally {
      setSubmitting(false)
      onClose()
    }
  }

  return (
    <ResponsiveDialog open={open} onClose={onClose} title={repositoryName}>
      <Stack spacing={1.5} sx={{ py: 1 }}>
        {operations.map((op) => (
          <Box key={op.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <CategoryToken category={op.category} />
            <Typography variant="body2">{t(`operations.kind.${op.kind}`)}</Typography>
            <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
              {t(`operations.status.${op.status}`)}
            </Typography>
          </Box>
        ))}
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, pt: 1 }}>
          <RichSelect
            value={stage}
            onChange={(value: string) => setStage(value as RebuildStage)}
            options={REBUILD_STAGES.map((s) => ({ value: s, label: t(`operations.background.rebuildStage.${s}`) }))}
          />
          <Button variant="outlined" disabled={submitting} onClick={handleRebuild}>
            {t('operations.background.rebuildFrom')}
          </Button>
        </Box>
      </Stack>
    </ResponsiveDialog>
  )
}
```

If `RichSelect`'s real API differs (e.g. it takes `rows` instead of
`options`, or needs a `RichSelectRow` child), adapt this block to match —
the test in Step 2 only asserts on the "Rebuild from" button and the
`archivesAPI.rebuild` call, not on `RichSelect` internals, so the fix stays
local to this file.

- [ ] **Step 5: Add i18n keys**

Under `"operations.background"` in all four locale files:

```json
"rebuildFrom": "Rebuild from",
"rebuildStage": {
  "stats": "Stats",
  "archives": "Archives",
  "history": "History"
}
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/RepositoryTrackDialog.test.tsx`
Expected: PASS

- [ ] **Step 7: Write the Storybook story**

```typescript
// frontend/src/components/background-work/RepositoryTrackDialog.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { Button } from '@mui/material'
import RepositoryTrackDialog from './RepositoryTrackDialog'
import type { OperationItem } from '../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: overrides.id ?? 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'completed',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 3,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: '2026-09-04T00:00:00Z',
  completed_at: '2026-09-04T00:01:00Z',
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

const meta = {
  title: 'BackgroundWork/RepositoryTrackDialog',
} satisfies Meta<typeof RepositoryTrackDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => {
    const Wrapper = () => {
      const [open, setOpen] = useState(true)
      return (
        <>
          <Button onClick={() => setOpen(true)}>Open</Button>
          <RepositoryTrackDialog
            open={open}
            onClose={() => setOpen(false)}
            repositoryId={3}
            repositoryName="nas"
            operations={[op({ kind: 'stats' }), op({ id: 2, kind: 'archive_sync', status: 'running' })]}
          />
        </>
      )
    }
    return <Wrapper />
  },
}
```

- [ ] **Step 8: Commit**

```bash
git add frontend/src/components/background-work/RepositoryTrackDialog.tsx frontend/src/components/background-work/RepositoryTrackDialog.stories.tsx frontend/src/components/background-work/__tests__/RepositoryTrackDialog.test.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add RepositoryTrackDialog"
```

---

## Task 8: `RebuildMenu`

**Files:**

- Create: `frontend/src/components/background-work/RebuildMenu.tsx`
- Create: `frontend/src/components/background-work/RebuildMenu.stories.tsx`
- Test: `frontend/src/components/background-work/__tests__/RebuildMenu.test.tsx`

**Interfaces:**

- Consumes: nothing from earlier tasks beyond `RebuildStage`.
- Produces: `<RebuildMenu onSelect={(stage: RebuildStage) => void} />`, a
  header-level MUI `Menu` button labeled "Rebuild…" per the spec 10.1 mock's
  header row (`[⏸ Pause] [Rebuild… ▾]`). Task 9 wires `onSelect` to a
  repository picker plus `archivesAPI.rebuild` — this component only emits
  the chosen stage, since the header action needs a repository selection
  step the mock does not fully specify (Open Questions covers this).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/background-work/__tests__/RebuildMenu.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import RebuildMenu from '../RebuildMenu'

describe('RebuildMenu', () => {
  it('opens the menu and calls onSelect with the chosen stage', () => {
    const onSelect = vi.fn()
    render(<RebuildMenu onSelect={onSelect} />)
    fireEvent.click(screen.getByRole('button', { name: /rebuild/i }))
    fireEvent.click(screen.getByRole('menuitem', { name: /archives/i }))
    expect(onSelect).toHaveBeenCalledWith('archives')
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/RebuildMenu.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/background-work/RebuildMenu.tsx
import { useState } from 'react'
import { Button, Menu, MenuItem } from '@mui/material'
import { ChevronDown } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RebuildStage } from '../../types/operations'

const STAGES: RebuildStage[] = ['stats', 'archives', 'history']

interface RebuildMenuProps {
  onSelect: (stage: RebuildStage) => void
}

export default function RebuildMenu({ onSelect }: RebuildMenuProps) {
  const { t } = useTranslation()
  const [anchorEl, setAnchorEl] = useState<HTMLElement | null>(null)

  return (
    <>
      <Button
        endIcon={<ChevronDown size={14} />}
        onClick={(e) => setAnchorEl(e.currentTarget)}
        variant="outlined"
        size="small"
      >
        {t('operations.background.rebuildFrom').replace(' from', '…')}
      </Button>
      <Menu anchorEl={anchorEl} open={!!anchorEl} onClose={() => setAnchorEl(null)}>
        {STAGES.map((stage) => (
          <MenuItem
            key={stage}
            onClick={() => {
              onSelect(stage)
              setAnchorEl(null)
            }}
          >
            {t(`operations.background.rebuildStage.${stage}`)}
          </MenuItem>
        ))}
      </Menu>
    </>
  )
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd frontend && npx vitest run src/components/background-work/__tests__/RebuildMenu.test.tsx`
Expected: PASS

- [ ] **Step 5: Write the Storybook story**

```typescript
// frontend/src/components/background-work/RebuildMenu.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import RebuildMenu from './RebuildMenu'

const meta = {
  title: 'BackgroundWork/RebuildMenu',
} satisfies Meta<typeof RebuildMenu>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => <RebuildMenu onSelect={() => {}} />,
}
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/components/background-work/RebuildMenu.tsx frontend/src/components/background-work/RebuildMenu.stories.tsx frontend/src/components/background-work/__tests__/RebuildMenu.test.tsx
git commit -m "feat(operations): add RebuildMenu"
```

---

## Task 9: `BackgroundWorkTab` page and Settings/sidebar wiring

**Files:**

- Create: `frontend/src/components/BackgroundWorkTab.tsx`
- Create: `frontend/src/components/BackgroundWorkTab.stories.tsx`
- Modify: `frontend/src/pages/Settings.tsx`
- Modify: `frontend/src/components/AppSidebar.tsx`
- Test: `frontend/src/components/__tests__/BackgroundWorkTab.test.tsx`

**Interfaces:**

- Consumes: `PipelineBoard` (Task 6), `RebuildMenu` (Task 8),
  `RepositoryTrackDialog` (Task 7), `operationsAPI.{pause,resume,
  updateLimits}` (Task 1), `useAuthorization` (existing,
  `frontend/src/hooks/useAuthorization.ts`).
- Produces: route `background-work` registered in `Settings.tsx`'s
  `getTabOrder()` and render block, and a sidebar entry in `AppSidebar.tsx`.

Visibility: spec 10.1 says "admin and operator visible." The codebase's
per-repository RBAC (`usePermissions`) does not carry a global operator
concept by itself, but `useAuthorization()` already exposes
`globalRoleRank` built from `authAPI.getAuthorizationModel()`'s
`global_roles` (`viewer`/`operator`/`admin` with `scope: 'global'`, see
`frontend/src/hooks/__tests__/usePermissions.test.ts:11-15`) and
`currentGlobalRole: user?.role`. Gate visibility with:

```typescript
const { globalRoleRank, currentGlobalRole } = useAuthorization()
const canViewBackgroundWork =
  (globalRoleRank.get(currentGlobalRole ?? '') ?? 0) >= (globalRoleRank.get('operator') ?? Infinity)
```

`useAuthorization` does not currently export `globalRoleRank` — check with
`grep -n "return {" -A 15 frontend/src/hooks/useAuthorization.ts`; if it is
still private (as read during planning, `globalRoleRank` is computed via
`useMemo` at line ~23 but only `roleHasGlobalPermission` and
`currentGlobalRole` are returned), add `globalRoleRank` to the hook's
return object in this task as a one-line addition — do not duplicate the
`buildRoleRankMap` logic in `BackgroundWorkTab.tsx`.

Pause/resume/worker-limit controls call `get_current_admin_user`-gated
routes server-side (`app/api/operations.py:313-346`); render them but
`disabled` for a non-admin `currentGlobalRole` so the UI does not offer a
control the backend will 403.

- [ ] **Step 1: Confirm and extend `useAuthorization`'s return value**

Run: `grep -n "return {" -A 15 frontend/src/hooks/useAuthorization.ts`
If `globalRoleRank` is not in the returned object, add it:

```typescript
// in the return statement of useAuthorization()
    globalRoleRank,
```

Run the existing hook's test suite to confirm nothing regresses:
`cd frontend && npx vitest run src/hooks/__tests__/useAuthorization.test.ts`
Expected: PASS (no new assertions needed — this is an additive export).

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/components/__tests__/BackgroundWorkTab.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import BackgroundWorkTab from '../BackgroundWorkTab'
import { operationsAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  operationsAPI: {
    getQueue: vi.fn().mockResolvedValue({
      data: { repositories: [], limits: { index_workers: 2, index_running: 0, max_concurrent_backups: 1, max_concurrent_scheduled_backups: 2, max_concurrent_scheduled_checks: 4 }, paused: false },
    }),
    pause: vi.fn().mockResolvedValue({ data: { paused: true } }),
    resume: vi.fn().mockResolvedValue({ data: { paused: false } }),
    updateLimits: vi.fn().mockResolvedValue({ data: {} }),
  },
  archivesAPI: { rebuild: vi.fn() },
}))

vi.mock('../../hooks/useOperationEvents', () => ({ useOperationEvents: vi.fn() }))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    globalRoleRank: new Map([['viewer', 1], ['operator', 2], ['admin', 3]]),
    currentGlobalRole: 'admin',
  }),
}))

function renderTab() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <BackgroundWorkTab />
      </MemoryRouter>
    </QueryClientProvider>
  )
}

describe('BackgroundWorkTab', () => {
  it('pauses background work from the header control', async () => {
    renderTab()
    fireEvent.click(await screen.findByRole('button', { name: /pause/i }))
    await waitFor(() => expect(operationsAPI.pause).toHaveBeenCalled())
  })

  it('renders the rebuild menu', async () => {
    renderTab()
    expect(await screen.findByRole('button', { name: /rebuild/i })).toBeInTheDocument()
  })
})
```

- [ ] **Step 3: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/BackgroundWorkTab.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 4: Write `BackgroundWorkTab`**

```typescript
// frontend/src/components/BackgroundWorkTab.tsx
import { useState } from 'react'
import { Box, Button, Stack, Typography } from '@mui/material'
import { Pause, Play } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import PipelineBoard from './background-work/PipelineBoard'
import RebuildMenu from './background-work/RebuildMenu'
import { operationsAPI } from '../services/api'
import type { RebuildStage } from '../types/operations'

const QUEUE_KEY = ['operations-queue'] as const

export default function BackgroundWorkTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { data } = useQuery({
    queryKey: QUEUE_KEY,
    queryFn: () => operationsAPI.getQueue().then((r) => r.data),
  })
  const [pendingStage, setPendingStage] = useState<RebuildStage | null>(null)

  const pauseMutation = useMutation({
    mutationFn: () => operationsAPI.pause(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })
  const resumeMutation = useMutation({
    mutationFn: () => operationsAPI.resume(),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: QUEUE_KEY }),
  })

  const paused = data?.paused ?? false

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
        <Typography variant="h6" sx={{ mr: 'auto' }}>
          {t('operations.background.title')}
        </Typography>
        <Button
          size="small"
          variant="outlined"
          startIcon={paused ? <Play size={14} /> : <Pause size={14} />}
          onClick={() => (paused ? resumeMutation.mutate() : pauseMutation.mutate())}
        >
          {paused ? t('operations.background.resume') : t('operations.background.pause')}
        </Button>
        <RebuildMenu onSelect={setPendingStage} />
      </Stack>
      <PipelineBoard />
      {pendingStage && (
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 1 }}>
          {t('operations.background.rebuildNeedsRepository')}
        </Typography>
      )}
    </Box>
  )
}
```

The header "Rebuild…" action needs a repository target the spec's mock
does not spell out (see Task 8's note and Open Questions). This step keeps
the wiring honest rather than guessing: `pendingStage` is captured but the
actual rebuild call is left to a repository-picker follow-up flagged in
Open Questions, since fabricating a picker UI not in the spec or mocks
risks contradicting Appendix B's intent at G3 review.

- [ ] **Step 5: Add i18n keys**

Under `"operations.background"` in all four locale files:

```json
"title": "Background work",
"pause": "Pause",
"resume": "Resume",
"rebuildNeedsRepository": "Choose a repository from its card to rebuild."
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/__tests__/BackgroundWorkTab.test.tsx`
Expected: PASS

- [ ] **Step 7: Wire the Settings tab**

In `frontend/src/pages/Settings.tsx`:

Add the import:
```typescript
import BackgroundWorkTab from '../components/BackgroundWorkTab'
import { useAuthorization } from '../hooks/useAuthorization'
```

Add the visibility check near the other `canManage*` constants (after line 39):
```typescript
  const { globalRoleRank, currentGlobalRole } = useAuthorization()
  const canViewBackgroundWork =
    (globalRoleRank.get(currentGlobalRole ?? '') ?? 0) >= (globalRoleRank.get('operator') ?? Infinity)
```

Add `'background-work'` to `getTabOrder()`'s return array (after the
`canManageSystem ? ['monitoring']` entry, matching the System group's
ordering) and to its dependency array:
```typescript
      ...(canManageSystem ? ['monitoring'] : []),
      ...(canViewBackgroundWork ? ['background-work'] : []),
```
```typescript
  }, [
    canManageSystem,
    canManageMqtt,
    canManageBeta,
    canManageCache,
    canManageLogs,
    canManagePackages,
    canManageUsers,
    canManageLicensing,
    canManageMounts,
    canManageScripts,
    canManageExportImport,
    mqttBetaEnabled,
    canViewBackgroundWork,
  ])
```

Add the render block after the Monitoring & Reports tab (after line 165):
```typescript
      {/* Background Work Tab - Admin/Operator */}
      {currentTabId === 'background-work' && canViewBackgroundWork && (
        <TabContentLayout>
          <BackgroundWorkTab />
        </TabContentLayout>
      )}
```

- [ ] **Step 8: Wire the sidebar**

In `frontend/src/components/AppSidebar.tsx`, add a nav item to the
`System` subItems array (after the `Monitoring & Reports` entry at line
~265, before the MQTT conditional entry) gated the same way:

```typescript
                    ...(canViewBackgroundWork
                      ? [{ name: 'Background work', href: '/settings/background-work', icon: ListChecks }]
                      : []),
```

Add `canViewBackgroundWork` near the other `canManage*` consts (line ~80)
using the same `useAuthorization` hook, add `ListChecks` to the
`lucide-react` import list at the top of the file (check it is not already
imported under a different purpose), add `canViewBackgroundWork` to the
`useMemo` dependency array (line ~308-320), and extend the route-matching
`useEffect` (line ~333-341) so `path.includes('/background-work')` also
expands the `System` submenu.

Add the label translation entry alongside the other System-group entries
(near line 116, in the `labelFor`-style map):
```typescript
      'Background work': t('navigation.settings.backgroundWork'),
```
and the matching key `"navigation": {"settings": {"backgroundWork":
"Background work"}}` (merge into the existing `navigation.settings`
object) in all four locale files.

- [ ] **Step 9: Write the Storybook story**

```typescript
// frontend/src/components/BackgroundWorkTab.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import BackgroundWorkTab from './BackgroundWorkTab'

const meta = {
  title: 'Settings/BackgroundWorkTab',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof BackgroundWorkTab>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter>
        <Box sx={{ p: 3 }}>
          <BackgroundWorkTab />
        </Box>
      </MemoryRouter>
    </QueryClientProvider>
  ),
}
```

- [ ] **Step 10: Update `docs/navigation.md`**

In the `### System` table under `## Settings` (after the "Monitoring &
Reports" row), add:

```markdown
| Background work | View and control queued and running index, stats, and archive-sync work across repositories: pause, resume, adjust index workers, and rebuild derived data. Visible to admins and operators. |
```

- [ ] **Step 11: Commit**

```bash
git add frontend/src/components/BackgroundWorkTab.tsx frontend/src/components/BackgroundWorkTab.stories.tsx frontend/src/components/__tests__/BackgroundWorkTab.test.tsx frontend/src/pages/Settings.tsx frontend/src/components/AppSidebar.tsx frontend/src/hooks/useAuthorization.ts docs/navigation.md frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add Background work tab and nav entry"
```

---

## Task 10: `OperationStatusStrip` on `RepositoryCard`

**Files:**

- Create: `frontend/src/components/OperationStatusStrip.tsx`
- Create: `frontend/src/components/OperationStatusStrip.stories.tsx`
- Modify: `frontend/src/components/RepositoryCard.tsx`
- Test: `frontend/src/components/__tests__/OperationStatusStrip.test.tsx`

**Interfaces:**

- Consumes: `archivesAPI.getStatusStrip` (Task 1), `CategoryToken` (Task 3),
  `useOperationEvents` (Task 2, to refresh the strip when the relevant
  category's terminal operation changes).
- Produces: `<OperationStatusStrip repositoryId={number} />`, rendered
  inside `RepositoryCard` right after the Key Stats Band
  (`frontend/src/components/RepositoryCard.tsx:786-858`, insert
  immediately after the closing `</Box>` at line 858, before whatever
  content currently follows).

Cell labels and icons reuse `CategoryToken`'s `OperationCategory` mapping
where the strip's cell key matches a category 1:1 (`backup`→`backup`,
`index`→`index`, `mirror`→`mirror`); `check`, `prune`, and `compact` are
`maintenance`-category kinds in the vocab (spec 6.3) but the strip
(`STRIP_CELLS` in `app/api/archive_index.py:42-49`) reports them as three
separate cells with their own kind filter, matching the spec 10.2 mock's
six-cell strip ("Backup, Check, Prune, Compact, Compact/Index, Mirror").
Give the `check`/`prune`/`compact` cells the `maintenance` category's icon
via `CategoryToken`, since there is no `check`/`prune`/`compact`-specific
`OperationCategory` and the spec does not ask for one — only the label
text differs.

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/components/__tests__/OperationStatusStrip.test.tsx
import { describe, it, expect, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import OperationStatusStrip from '../OperationStatusStrip'
import { archivesAPI } from '../../services/api'

vi.mock('../../services/api', () => ({
  archivesAPI: { getStatusStrip: vi.fn() },
}))

vi.mock('../../hooks/useOperationEvents', () => ({ useOperationEvents: vi.fn() }))

function renderStrip(repositoryId = 1) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={queryClient}>
      <OperationStatusStrip repositoryId={repositoryId} />
    </QueryClientProvider>
  )
}

describe('OperationStatusStrip', () => {
  it('renders a cell per category with its age', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          { cell: 'backup', status: 'completed', completed_at: '2026-09-04T00:00:00Z', age_seconds: 7200, threshold_days: 2, overdue: false, running: false, source: 'operations' },
          { cell: 'index', status: null, completed_at: null, age_seconds: null, threshold_days: 2, overdue: null, running: true, source: null },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByText(/backup/i)).toBeInTheDocument())
    expect(screen.getByText(/syncing/i)).toBeInTheDocument()
  })

  it('shows an overdue indicator only when the cell is flagged and overdue data is available', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          { cell: 'compact', status: 'completed', completed_at: '2026-07-25T00:00:00Z', age_seconds: 41 * 86400, threshold_days: 30, overdue: true, running: false, source: 'legacy' },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByTestId('status-strip-cell-compact')).toHaveAttribute('data-overdue', 'true'))
  })

  it('omits the mirror cell when the backend omits it', async () => {
    ;(archivesAPI.getStatusStrip as ReturnType<typeof vi.fn>).mockResolvedValue({
      data: {
        cells: [
          { cell: 'backup', status: 'completed', completed_at: '2026-09-04T00:00:00Z', age_seconds: 7200, threshold_days: 2, overdue: false, running: false, source: 'operations' },
        ],
        overdue_available: true,
      },
    })
    renderStrip()
    await waitFor(() => expect(screen.getByText(/backup/i)).toBeInTheDocument())
    expect(screen.queryByTestId('status-strip-cell-mirror')).not.toBeInTheDocument()
  })
})
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd frontend && npx vitest run src/components/__tests__/OperationStatusStrip.test.tsx`
Expected: FAIL — module does not exist.

- [ ] **Step 3: Write the implementation**

```typescript
// frontend/src/components/OperationStatusStrip.tsx
import { useQuery } from '@tanstack/react-query'
import { Box, Typography, Tooltip, alpha, useTheme } from '@mui/material'
import { AlertTriangle, Check, Loader2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { archivesAPI } from '../services/api'
import { useOperationEvents } from '../hooks/useOperationEvents'
import type { StatusStripCellKey } from '../types/operations'
import { useQueryClient } from '@tanstack/react-query'

interface OperationStatusStripProps {
  repositoryId: number
}

const CELL_CATEGORY: Record<StatusStripCellKey, string> = {
  backup: 'backup',
  check: 'maintenance',
  prune: 'maintenance',
  compact: 'maintenance',
  index: 'index',
  mirror: 'mirror',
}

export default function OperationStatusStrip({ repositoryId }: OperationStatusStripProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const queryClient = useQueryClient()
  const queryKey = ['status-strip', repositoryId] as const

  const { data } = useQuery({
    queryKey,
    queryFn: () => archivesAPI.getStatusStrip(repositoryId).then((r) => r.data),
    refetchInterval: 30000,
  })

  useOperationEvents(
    (op) => {
      if (op.repository_id === repositoryId) {
        queryClient.invalidateQueries({ queryKey })
      }
    },
    () => {}
  )

  if (!data || data.cells.length === 0) return null

  return (
    <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: 1.5, mb: 1.5 }}>
      {data.cells.map((cell) => (
        <Tooltip
          key={cell.cell}
          title={cell.completed_at ? new Date(cell.completed_at).toLocaleString() : t('operations.background.never')}
        >
          <Box
            data-testid={`status-strip-cell-${cell.cell}`}
            data-overdue={cell.overdue === true}
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              px: 1,
              py: 0.5,
              borderRadius: 1,
              bgcolor: cell.overdue
                ? alpha(theme.palette.warning.main, 0.12)
                : isDark
                  ? alpha('#fff', 0.03)
                  : alpha('#000', 0.02),
            }}
          >
            {cell.running ? (
              <Loader2 size={12} className="animate-spin" />
            ) : cell.overdue ? (
              <AlertTriangle size={12} color={theme.palette.warning.main} />
            ) : cell.status ? (
              <Check size={12} color={theme.palette.success.main} />
            ) : null}
            <Typography variant="caption" fontWeight={600}>
              {t(`operations.category.${CELL_CATEGORY[cell.cell]}`)}
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {cell.running
                ? t('operations.background.syncing')
                : cell.completed_at
                  ? formatDistanceToNow(new Date(cell.completed_at), { addSuffix: true })
                  : t('operations.background.never')}
            </Typography>
          </Box>
        </Tooltip>
      ))}
    </Box>
  )
}
```

Check `date-fns`'s `formatDistanceToNow` is already a project dependency
(it is — `RepositoryCard.tsx:4` imports `format`, `isTomorrow`, etc. from
`date-fns`) before adding the import.

- [ ] **Step 4: Add i18n keys**

Under `"operations.background"` in all four locale files:

```json
"never": "Never",
"syncing": "Syncing"
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npx vitest run src/components/__tests__/OperationStatusStrip.test.tsx`
Expected: PASS

- [ ] **Step 6: Insert into `RepositoryCard`**

In `frontend/src/components/RepositoryCard.tsx`, add the import near the
other local component imports (after line 39's `OperationalCard` import):

```typescript
import OperationStatusStrip from './OperationStatusStrip'
```

Insert right after the Key Stats Band's closing `</Box>` (currently line
858, immediately before whatever markup follows it — re-check the line
number in the live file since earlier tasks in this plan do not touch this
file, so the number should be stable, but confirm with `grep -n
"Key Stats Band" -A 75 frontend/src/components/RepositoryCard.tsx` before
editing):

```typescript
        <OperationStatusStrip repositoryId={repository.id} />
```

- [ ] **Step 7: Run the existing `RepositoryCard` tests to confirm no regression**

Run: `cd frontend && npx vitest run src/components/__tests__/RepositoryCard.test.tsx`
(adjust the path if the existing test file lives elsewhere — check with
`find frontend/src -iname "RepositoryCard.test.tsx"` first)
Expected: PASS

- [ ] **Step 8: Write the Storybook story**

```typescript
// frontend/src/components/OperationStatusStrip.stories.tsx
import type { Meta, StoryObj } from '@storybook/react-vite'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Box } from '@mui/material'
import OperationStatusStrip from './OperationStatusStrip'

const meta = {
  title: 'Components/OperationStatusStrip',
} satisfies Meta<typeof OperationStatusStrip>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  render: () => (
    <QueryClientProvider client={new QueryClient()}>
      <Box sx={{ p: 3, maxWidth: 480 }}>
        <OperationStatusStrip repositoryId={1} />
      </Box>
    </QueryClientProvider>
  ),
}
```

(Storybook's `msw`/mocked-query precedent from Task 6 applies here too —
if no existing story mocks `useQuery` data, this story documents shape via
its render call only and the loading/empty branch is what actually
renders; do not fabricate a mocking layer this codebase does not already
use elsewhere.)

- [ ] **Step 9: Commit**

```bash
git add frontend/src/components/OperationStatusStrip.tsx frontend/src/components/OperationStatusStrip.stories.tsx frontend/src/components/__tests__/OperationStatusStrip.test.tsx frontend/src/components/RepositoryCard.tsx frontend/src/locales/en.json frontend/src/locales/de.json frontend/src/locales/es.json frontend/src/locales/it.json
git commit -m "feat(operations): add OperationStatusStrip to RepositoryCard"
```

---

## Task 11: Full verification pass

**Files:** none (verification only, per `superpowers:verification-before-completion`)

- [ ] **Step 1: Run the full frontend unit suite**

Run: `cd frontend && npm test -- --run`
Expected: all tests pass, including every test file added in Tasks 1-10.

- [ ] **Step 2: Run lint and typecheck**

Run: `cd frontend && npm run lint && npm run typecheck`
Expected: clean. Fix any type errors surfaced by the new
`frontend/src/types/operations.ts` imports before proceeding.

- [ ] **Step 3: Build Storybook**

Run: `cd frontend && npm run build-storybook`
Expected: succeeds, including the eight new/changed story files
(`CategoryToken`, `PipelineStageColumn`, `ForegroundLaneRow`,
`PipelineBoard`, `RepositoryTrackDialog`, `RebuildMenu`,
`BackgroundWorkTab`, `OperationStatusStrip`).

- [ ] **Step 4: Confirm locale files stay parallel**

Run:
```bash
python3 -c "
import json
en = json.load(open('frontend/src/locales/en.json'))
for loc in ['de', 'es', 'it']:
    other = json.load(open(f'frontend/src/locales/{loc}.json'))
    def keys(d, prefix=''):
        out = set()
        for k, v in d.items():
            path = f'{prefix}.{k}' if prefix else k
            out.add(path)
            if isinstance(v, dict):
                out |= keys(v, path)
        return out
    missing = keys(en) - keys(other)
    extra = keys(other) - keys(en)
    if missing or extra:
        print(loc, 'MISSING', sorted(missing)[:10], 'EXTRA', sorted(extra)[:10])
    else:
        print(loc, 'OK')
"
```
Expected: `OK` for `de`, `es`, `it`. Fix any drift before continuing.

- [ ] **Step 5: Manual smoke check (per spec Appendix A.3 phase-3 note)**

If a running Borg UI dev server and container are reachable (per the
`run` skill or `borg-live-debug` skill), open `/settings/background-work`
and a repository card, trigger an import or reconcile run, and confirm the
board and status strip update live via SSE without a manual refresh. If no
live container is reachable this session, record that explicitly in the
phase 3 progress notes rather than silently skipping it — phases 1 and 2
both recorded this same gap.

- [ ] **Step 6: Report verification output**

Summarize suite pass/fail counts, lint/typecheck status, and the
Storybook build result for gate G2. Do not commit until the user answers
G2.

---

## Open questions

- **Rebuild header action's repository target.** The spec 10.1 mock shows
  a header-level `[Rebuild… ▾]` button but the only backend route,
  `POST /repositories/{id}/rebuild`, is per-repository. This plan's
  `RebuildMenu` (Task 8) only emits the chosen stage; `BackgroundWorkTab`
  (Task 9) stores it in `pendingStage` and shows a hint rather than
  guessing a repository-picker UI the spec does not describe. `RebuildMenu`
  and `RepositoryTrackDialog`'s own inline rebuild action (from that
  dialog, where the repository id is already known) may be sufficient in
  practice — flag this at G1 for the owner to confirm whether the header
  action should open a repository-select dialog, default to "all
  repositories" (looping the stage across every repository, which the
  backend does not support in one call), or be dropped in favor of the
  per-repository dialog action only.
- **"Last reconcile time" in the board's empty state.** Spec 10.1 asks for
  it explicitly but no backend field carries it yet (see Task 6's note).
  This plan ships the empty state without that detail. Confirm at G1
  whether that is acceptable for phase 3 or whether a small backend
  addition (e.g. `SystemSettings.last_reconcile_at`, alongside the
  existing `history_bootstrap_at` pattern from phase 2) should be added —
  that would be a backend change this plan currently has none of.
- **`PipelineRepositoryCard`'s slide transition.** Spec 10.1 says cards
  "move between columns with a short slide transition when its stage
  changes." This plan's `PipelineStageColumn`/`PipelineBoard` re-render
  cards keyed by operation id across columns via React's normal
  reconciliation, which does not by itself animate a cross-container move.
  Adding that (e.g. with `framer-motion`'s `layoutId`, which is not
  currently a dependency) is a visual-polish addition better scoped after
  the functional board works — confirm at G1 whether it belongs in this
  phase or is acceptable as a fast-follow.
