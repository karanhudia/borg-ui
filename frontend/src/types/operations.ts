// Mirrors app/services/operations/vocab.py (spec 6.3) and the response
// shapes in app/api/operations.py and app/api/archive_index.py.

export type OperationCategory =
  'import' | 'backup' | 'restore' | 'maintenance' | 'index' | 'mirror' | 'system'

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
  'manual' | 'schedule' | 'plan' | 'import' | 'followup' | 'reconcile' | 'retry'

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
