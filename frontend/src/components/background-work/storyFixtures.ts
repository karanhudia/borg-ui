// Shared fixtures for the Background work stories: a queue with every kind
// of track state, and the hub rows those repositories would have at rest.
import type {
  HubRepository,
  HubRepositoryDetail,
  HubResponse,
  OperationItem,
  QueueResponse,
} from '../../types/operations'

const minutesAgo = (minutes: number) => new Date(Date.now() - minutes * 60 * 1000).toISOString()

export const op = (overrides: Partial<OperationItem>): OperationItem => ({
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

export const hubRepository = (overrides: Partial<HubRepository> = {}): HubRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  repository_type: 'local',
  sync_state: 'fresh',
  last_synced_at: minutesAgo(12),
  last_stats_at: minutesAgo(11),
  last_history_at: minutesAgo(12),
  archives: 18,
  history: { indexed: 18, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 16219 },
  ...overrides,
})

export const hubRepositories: HubRepository[] = [
  hubRepository({
    repository_id: 1,
    repository_name: 'offsite',
    sync_state: 'never',
    last_synced_at: null,
    last_stats_at: null,
    archives: 0,
    history: { indexed: 0, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 0 },
  }),
  hubRepository({ repository_id: 2, repository_name: 'nas' }),
  hubRepository({
    repository_id: 3,
    repository_name: 'photos',
    sync_state: 'syncing',
    archives: 38,
    history: { indexed: 14, pending: 24, failed: 0, skipped: 0, truncated: 0, rows: 8501 },
  }),
  hubRepository({
    repository_id: 4,
    repository_name: 'laptop',
    sync_state: 'stale',
    last_synced_at: minutesAgo(60 * 30),
    last_stats_at: minutesAgo(60 * 30),
    archives: 40,
    history: { indexed: 36, pending: 0, failed: 3, skipped: 0, truncated: 1, rows: 2611 },
  }),
  hubRepository({
    repository_id: 5,
    repository_name: 'documents',
    archives: 15,
    history: { indexed: 15, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 62 },
  }),
]

export const hubResponse: HubResponse = {
  repositories: hubRepositories,
  totals: {
    repositories: hubRepositories.length,
    archives: hubRepositories.reduce((sum, r) => sum + r.archives, 0),
    history_rows: hubRepositories.reduce((sum, r) => sum + r.history.rows, 0),
    history_bytes: 4_300_000,
  },
  last_reconcile_at: minutesAgo(12),
  reconcile_interval_minutes: 60,
  history_available: true,
}

export const hubDetail: HubRepositoryDetail = {
  repository_id: 4,
  failed_archives: [
    {
      id: 41,
      name: 'laptop-2026-09-04T02:00',
      start: '2026-09-04T02:00:00',
      history_attempts: 3,
      history_rows: null,
    },
    {
      id: 42,
      name: 'laptop-2026-09-03T02:00',
      start: '2026-09-03T02:00:00',
      history_attempts: 3,
      history_rows: null,
    },
  ],
  truncated_archives: [
    {
      id: 30,
      name: 'laptop-2026-08-20T02:00',
      start: '2026-08-20T02:00:00',
      history_attempts: 0,
      history_rows: 200000,
    },
  ],
}

export const busyQueue: QueueResponse = {
  repositories: [
    {
      repository_id: 1,
      repository_name: 'offsite',
      lane_busy: false,
      operations: [
        op({ id: 1, kind: 'import_connect', category: 'import', repository: 'offsite' }),
      ],
    },
    {
      repository_id: 2,
      repository_name: 'nas',
      lane_busy: true,
      operations: [
        op({
          id: 2,
          kind: 'stats',
          status: 'running',
          repository: 'nas',
          repository_id: 2,
          started_at: minutesAgo(41),
        }),
        op({
          id: 3,
          kind: 'backup',
          category: 'backup',
          status: 'running',
          repository: 'nas',
          repository_id: 2,
          backup_plan_name: 'nightly',
          started_at: minutesAgo(41),
        }),
      ],
    },
    {
      repository_id: 3,
      repository_name: 'photos',
      lane_busy: false,
      operations: [
        op({
          id: 4,
          kind: 'history_index',
          status: 'running',
          repository: 'photos',
          repository_id: 3,
          progress_percent: 37,
          progress_current: 14,
          progress_total: 38,
          started_at: minutesAgo(6),
        }),
      ],
    },
    {
      repository_id: 4,
      repository_name: 'laptop',
      lane_busy: false,
      operations: [
        op({ id: 5, status: 'completed', repository: 'laptop', repository_id: 4 }),
        op({
          id: 6,
          kind: 'archive_sync',
          status: 'failed',
          repository: 'laptop',
          repository_id: 4,
          error_message: 'borg list timed out',
        }),
      ],
    },
  ],
  limits: {
    index_workers: 2,
    index_running: 1,
    max_concurrent_backups: 1,
    max_concurrent_scheduled_backups: 2,
    max_concurrent_scheduled_checks: 4,
  },
  paused: false,
}

export const emptyQueue: QueueResponse = {
  repositories: [],
  limits: {
    index_workers: 2,
    index_running: 0,
    max_concurrent_backups: 1,
    max_concurrent_scheduled_backups: 2,
    max_concurrent_scheduled_checks: 4,
  },
  paused: false,
}
