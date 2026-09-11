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
// `lane_busy` names the operation that holds the lane; `lane_busy_unnamed`
// is the same state from a payload that did not carry it.
export type WaitReason = 'paused' | 'lane_busy' | 'lane_busy_unnamed' | 'workers' | 'queued'

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

// The kinds the server admits one at a time (its exclusive set). The track
// only needs them to tell "the lane is taken" apart from "the index workers
// are busy", so it names them rather than reading a category: a kind this
// build does not know carries a category all the same, and the server
// already refuses it the lane. A drift against the server's table costs
// wording, never a stage.
const LANE_KINDS = new Set<OperationItem['kind']>([
  'backup',
  'check',
  'prune',
  'compact',
  'delete_archive',
  'wipe',
  'history_index',
])

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

  const holdingLane = repository.operations.filter(
    (operation) => operation.status === 'running' && LANE_KINDS.has(operation.kind)
  )

  const stages = STAGE_ORDER.map<StageState>((key) => {
    const operation = latest.get(key) ?? null
    if (!operation) return { key, status: 'idle', operation: null, reason: null, reasonKind: null }
    const status = stageStatus(operation.status)
    let reason: WaitReason | null = null
    let reasonKind: OperationKind | null = null
    if (status === 'waiting') {
      if (paused) reason = 'paused'
      else if (repository.lane_busy && holdingLane.length > 0) {
        // The lane is the server's word, the operations are this payload's:
        // an event can mark the holder finished in the cache before the
        // queue is refetched. Only name a holder this payload still shows
        // running, and only claim the lane is taken while it shows
        // something running at all, or the caption contradicts the row it
        // sits in.
        const holder = repository.lane_holder ?? null
        reasonKind = holdingLane.some((o) => o.id === holder?.id) ? (holder?.kind ?? null) : null
        reason = reasonKind ? 'lane_busy' : 'lane_busy_unnamed'
      } else if (key === 'history' && limits.index_running >= limits.index_workers)
        reason = 'workers'
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
