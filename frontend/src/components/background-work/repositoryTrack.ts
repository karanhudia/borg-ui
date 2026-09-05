import type {
  OperationItem,
  QueueLimits,
  QueueRepository,
  RebuildStage,
} from '../../types/operations'

// The four derivation stages a repository moves through (spec 10.1), in
// the order the runner executes them. Every stage maps to one or two
// operation kinds; the board never shows kinds directly.
export type StageKey = 'connect' | 'stats' | 'archives' | 'history'

export const STAGE_ORDER: StageKey[] = ['connect', 'stats', 'archives', 'history']

const STAGE_FOR_KIND: Partial<Record<OperationItem['kind'], StageKey>> = {
  import_connect: 'connect',
  stats: 'stats',
  archive_sync: 'archives',
  history_index: 'history',
  history_merge: 'history',
}

// `connect` is the synchronous import request and has no rebuild stage.
export const REBUILD_STAGE_FOR: Partial<Record<StageKey, RebuildStage>> = {
  stats: 'stats',
  archives: 'archives',
  history: 'history',
}

// One grid shared by the header row and every repository row, so stage
// labels sit over the segments they describe.
export const TRACK_GRID_COLUMNS = {
  xs: '1fr',
  md: 'minmax(180px, 1.3fr) repeat(4, minmax(110px, 1fr)) 40px',
}

export type StageStatus = 'idle' | 'done' | 'running' | 'waiting' | 'failed'

// Why a queued stage has not started, in the order a person would want to
// hear it: the whole queue is paused, a foreground job owns this
// repository, every index worker is busy, or it is simply next in line.
export type WaitReason = 'paused' | 'lane_busy' | 'workers' | 'queued'

export interface StageState {
  key: StageKey
  status: StageStatus
  operation: OperationItem | null
  reason: WaitReason | null
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
    default:
      return 'done'
  }
}

export function deriveTrack(
  repository: QueueRepository,
  limits: QueueLimits,
  paused: boolean
): RepositoryTrack {
  const latest = new Map<StageKey, OperationItem>()
  for (const operation of repository.operations) {
    const stage = STAGE_FOR_KIND[operation.kind]
    if (!stage) continue
    const current = latest.get(stage)
    if (!current || operation.id > current.id) latest.set(stage, operation)
  }

  const foreground =
    repository.operations.find(
      (operation) => FOREGROUND_CATEGORIES.has(operation.category) && operation.status === 'running'
    ) ?? null

  const stages = STAGE_ORDER.map<StageState>((key) => {
    const operation = latest.get(key) ?? null
    if (!operation) return { key, status: 'idle', operation: null, reason: null }
    const status = stageStatus(operation.status)
    let reason: WaitReason | null = null
    if (status === 'waiting') {
      if (paused) reason = 'paused'
      else if (repository.lane_busy) reason = 'lane_busy'
      else if (key === 'history' && limits.index_running >= limits.index_workers) reason = 'workers'
      else reason = 'queued'
    }
    return { key, status, operation, reason }
  })

  return {
    repositoryId: repository.repository_id,
    repositoryName: repository.repository_name,
    foreground,
    stages,
  }
}
