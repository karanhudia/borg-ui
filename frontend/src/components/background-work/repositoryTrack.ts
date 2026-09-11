import type {
  OperationItem,
  OperationKind,
  QueueLimits,
  QueueRepository,
  RebuildStage,
} from '../../types/operations'

// The four derivation stages a repository moves through (spec 10.1), in
// the order the runner executes them: the archive list, then the file
// history built from it, then stats, which totals up whatever the other
// stages produced. An import is the one run that starts with stats,
// because there it doubles as the connection check. Every stage maps to
// one or two operation kinds; the board never shows kinds directly.
export type StageKey = 'connect' | 'archives' | 'history' | 'stats'

export const STAGE_ORDER: StageKey[] = ['connect', 'archives', 'history', 'stats']

const STAGE_FOR_KIND: Partial<Record<OperationItem['kind'], StageKey>> = {
  import_connect: 'connect',
  stats: 'stats',
  archive_sync: 'archives',
  history_index: 'history',
  history_merge: 'history',
}

// The stages a rebuild can start from, in run order: starting at one
// rebuilds it and every stage after it, so the archive list means
// everything and stats means the totals alone.
export const REBUILD_STAGES: RebuildStage[] = ['archives', 'history', 'stats']

// `connect` is the synchronous import request and has no rebuild stage.
export const REBUILD_STAGE_FOR: Partial<Record<StageKey, RebuildStage>> = {
  archives: 'archives',
  history: 'history',
  stats: 'stats',
}

// Width of each stage's column in the hub table. The rebuild stages are
// the columns; `connect` is a one-off import step with nothing at rest to
// show, so it has no column. Adding a stage means adding a width here and
// a cell in the row; the header and grid follow from this table.
const HUB_STAGE_COLUMN_WIDTH: Record<RebuildStage, string> = {
  archives: 'minmax(170px, 1.2fr)',
  history: 'minmax(190px, 1.4fr)',
  stats: 'minmax(130px, 1fr)',
}

// One grid shared by the hub header and every repository row: name, then
// one column per stage in the order the runner builds them, then the row
// menu. On small screens the name and the row menu share the first line
// and every data cell spans the full width beneath them.
export const HUB_GRID_COLUMNS = {
  xs: 'minmax(0, 1fr) auto',
  md: `minmax(180px, 1.4fr) ${REBUILD_STAGES.map((s) => HUB_STAGE_COLUMN_WIDTH[s]).join(' ')} 40px`,
}

export type StageStatus = 'idle' | 'done' | 'running' | 'waiting' | 'failed' | 'skipped'

// Why a queued stage has not started, in the order a person would want to
// hear it: the whole queue is paused, a foreground job owns this
// repository, every index worker is busy, or it is simply next in line.
// `lane_busy` names the server-reported holder while it is still running.
export type WaitReason = 'paused' | 'lane_busy' | 'index_busy' | 'workers' | 'queued'
// The index kinds that share a repository's index slot; `history_index`
// holds the lane instead. A copy of what lanes.py derives (INDEX_KINDS
// minus the exclusive one): keep the two in step when a kind is added.
const SHARED_INDEX_KINDS = new Set<OperationItem['kind']>([
  'archive_sync',
  'history_merge',
  'stats',
])

// Whether one of `operations` is running index work of the shared kind. The
// track reads the server's `index_busy` against the operations it holds: an
// SSE update that finishes that work clears the wait reason before the next
// fetch, the same way the lane's holder is checked against them.
export function indexBusyFrom(operations: OperationItem[]): boolean {
  return operations.some((op) => op.status === 'running' && SHARED_INDEX_KINDS.has(op.kind))
}

export interface StageState {
  key: StageKey
  status: StageStatus
  operation: OperationItem | null
  reason: WaitReason | null
  // The lane holder's kind, for the `lane_busy` wording. Any exclusive
  // kind can hold a lane: a backup, but also a prune, a compact, a check
  // or the file-history index. Optional so the partial stage literals in
  // tests and stories stay valid; `deriveTrack` always sets it.
  reasonKind?: OperationKind | null
}

export interface RepositoryTrack {
  repositoryId: number | null
  repositoryName: string
  foreground: OperationItem | null
  stages: StageState[]
}

const FOREGROUND_CATEGORIES = new Set<OperationItem['category']>([
  'backup',
  'restore',
  'maintenance',
])

function stageStatus(status: OperationItem['status']): StageStatus {
  switch (status) {
    case 'running':
      return 'running'
    case 'queued':
      return 'waiting'
    case 'failed':
    case 'cancelled':
      return 'failed'
    case 'skipped':
      return 'skipped'
    default:
      return 'done'
  }
}

export function deriveTrack(
  repository: QueueRepository,
  limits: QueueLimits,
  paused: boolean
): RepositoryTrack {
  // The queue keeps every operation from the last minute, so a repository
  // can carry a finished reconcile next to the rebuild that was just
  // queued. The track describes one run: the one still working, or else
  // the newest.
  const runs = new Map<string, OperationItem[]>()
  for (const operation of repository.operations) {
    if (!STAGE_FOR_KIND[operation.kind]) continue
    runs.set(operation.run_id, [...(runs.get(operation.run_id) ?? []), operation])
  }
  const newestId = (ops: OperationItem[]) => Math.max(...ops.map((o) => o.id))
  const active = (ops: OperationItem[]) =>
    ops.some((o) => o.status === 'queued' || o.status === 'running')
  const byNewest = (a: OperationItem[], b: OperationItem[]) => newestId(b) - newestId(a)
  const candidates = [...runs.values()]
  const chosen = candidates.filter(active).sort(byNewest)[0] ?? candidates.sort(byNewest)[0] ?? []

  const latest = new Map<StageKey, OperationItem>()
  for (const operation of chosen) {
    const stage = STAGE_FOR_KIND[operation.kind]
    if (!stage) continue
    const current = latest.get(stage)
    if (!current || operation.id > current.id) latest.set(stage, operation)
  }

  const foreground =
    repository.operations.find(
      (operation) => FOREGROUND_CATEGORIES.has(operation.category) && operation.status === 'running'
    ) ?? null

  // The server chooses the holder. SSE may finish it before the next fetch;
  // another running row cannot establish a replacement holder on its own.
  const holder = repository.lane_holder ?? null
  const holderRunning =
    repository.lane_busy &&
    holder !== null &&
    repository.operations.some(
      (operation) => operation.id === holder.id && operation.status === 'running'
    )

  const operationsById = new Map(
    repository.operations.map((operation) => [operation.id, operation])
  )
  const stages = STAGE_ORDER.map<StageState>((key) => {
    const operation = latest.get(key) ?? null
    if (!operation) return { key, status: 'idle', operation: null, reason: null, reasonKind: null }
    const status = stageStatus(operation.status)
    let reason: WaitReason | null = null
    let reasonKind: OperationKind | null = null
    if (status === 'waiting') {
      // A running dependency is the expected predecessor, but independent
      // branches can share a run ID and still compete for the index slot.
      const predecessors = new Set<number>()
      let dependencyId = operation.depends_on_id
      while (dependencyId != null && !predecessors.has(dependencyId)) {
        predecessors.add(dependencyId)
        dependencyId = operationsById.get(dependencyId)?.depends_on_id ?? null
      }
      const otherIndexRunning =
        repository.index_busy &&
        indexBusyFrom(repository.operations.filter((candidate) => !predecessors.has(candidate.id)))
      if (paused) reason = 'paused'
      else if (holderRunning) {
        reasonKind = holder.kind
        reason = 'lane_busy'
      } else if (otherIndexRunning) reason = 'index_busy'
      else if (key === 'history' && limits.index_running >= limits.index_workers) reason = 'workers'
      else reason = 'queued'
    }
    return { key, status, operation, reason, reasonKind }
  })

  return {
    repositoryId: repository.repository_id,
    repositoryName: repository.repository_name,
    foreground,
    stages,
  }
}
