import type {
  OperationItem,
  OperationKind,
  PausableStage,
  QueueLimits,
  QueueRepository,
  RebuildStage,
} from '../../types/operations'

// The stages a repository moves through (spec 2026-09-23 section 1), in run
// order: the import's connection check, the archive list, the retention
// comparison when the list changed, the file history built from it, then
// stats, which totals up whatever the other stages produced. An import is
// the one run that starts with stats, because there it doubles as the
// connection check. Every stage maps to one or two operation kinds; the board
// never shows kinds directly.
export type StageKey = 'connect' | PausableStage

export const STAGE_ORDER: StageKey[] = ['connect', 'archives', 'retention', 'history', 'stats']

// Mirrors STAGES in app/services/operations/vocab.py, plus the import's
// connect step, which is a synchronous request and never queues.
const STAGE_FOR_KIND: Partial<Record<OperationKind, StageKey>> = {
  import_connect: 'connect',
  archive_sync: 'archives',
  // Left every chain with #1168; legacy rows still belong to the listing.
  history_merge: 'archives',
  prune_compare: 'retention',
  history_index: 'history',
  stats: 'stats',
}

// The stages a rebuild can start from, in run order: starting at one
// rebuilds it and every stage after it, so the archive list means
// everything and stats means the totals alone.
export const REBUILD_STAGES: RebuildStage[] = ['archives', 'history', 'stats']

// `connect` is the synchronous import request and `retention` is refreshed
// by the listing or the prune preview page, so neither has a rebuild stage.
export const REBUILD_STAGE_FOR: Partial<Record<StageKey, RebuildStage>> = {
  archives: 'archives',
  history: 'history',
  stats: 'stats',
}

// One grid shared by the hub header and every repository row: name, the
// stage the repository is in, when its derived data last changed, then the
// row menu. Stages live in the strip above the table and what each one keeps
// in the repository's dialog, so a new stage adds neither a column nor a
// cell here. On small screens the name and the row menu share the first
// line and every data cell spans the full width beneath them.
export const HUB_GRID_COLUMNS = {
  xs: 'minmax(0, 1fr) auto',
  md: 'minmax(200px, 1.4fr) minmax(220px, 1.4fr) minmax(200px, 1.2fr) 40px',
}

export type StageStatus = 'idle' | 'done' | 'running' | 'waiting' | 'failed' | 'skipped'

// Why a queued stage has not started, in the order a person would want to
// hear it: its stage is paused, a stage it waits on is paused, a foreground
// job owns this repository, every index worker is busy, or it is simply
// next in line. `lane_busy` names the server-reported holder while it is
// still running.
export type WaitReason =
  'paused' | 'upstream_paused' | 'lane_busy' | 'index_busy' | 'workers' | 'queued'

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
  pausedStages: PausableStage[]
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

  // A kind with a stage is shown there, not as foreground: the retention
  // comparison is a maintenance kind but a step of the background chain.
  const foreground =
    repository.operations.find(
      (operation) =>
        FOREGROUND_CATEGORIES.has(operation.category) &&
        !STAGE_FOR_KIND[operation.kind] &&
        operation.status === 'running'
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
      // The server names the shared index work; each one is checked against
      // the rows at hand, so an SSE update that finishes it clears the wait
      // reason before the next fetch, the way the lane's holder is checked.
      const otherIndexRunning = (repository.index_holder_ids ?? []).some(
        (id) => !predecessors.has(id) && operationsById.get(id)?.status === 'running'
      )
      const isPaused = (stage: StageKey | undefined) =>
        stage != null && stage !== 'connect' && pausedStages.includes(stage)
      const upstreamPaused = [...predecessors].some((id) => {
        const dependency = operationsById.get(id)
        return dependency?.status === 'queued' && isPaused(STAGE_FOR_KIND[dependency.kind])
      })
      if (isPaused(key)) reason = 'paused'
      else if (upstreamPaused) reason = 'upstream_paused'
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

// The one stage a repository is "in", for the strip and the row: the running
// one, else the first waiting one in run order, else a failed one from the
// run, else none (at rest).
export function currentStage(track: RepositoryTrack | null): StageState | null {
  if (!track) return null
  return (
    track.stages.find((s) => s.status === 'running') ??
    track.stages.find((s) => s.status === 'waiting') ??
    track.stages.find((s) => s.status === 'failed') ??
    null
  )
}
