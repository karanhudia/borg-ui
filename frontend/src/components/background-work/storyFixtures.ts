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
  index_mode: 'full',
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
  hubRepository({
    repository_id: 6,
    repository_name: 'media',
    archives: 22,
    history: { indexed: 22, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 3140 },
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
      index_busy: false,
      operations: [
        op({ id: 1, kind: 'import_connect', category: 'import', repository: 'offsite' }),
      ],
    },
    {
      repository_id: 2,
      repository_name: 'nas',
      lane_busy: true,
      lane_holder: { kind: 'backup', id: 3 },
      // a stats is running here too; the lane's backup is what the stage
      // names, since the lane wins over the index flag
      index_busy: true,
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
      index_busy: false,
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
      index_busy: false,
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
    {
      // a stats of the repository still running: the next listing waits
      // for it (one index operation per repository), with a worker to
      // spare. The listing is another chain's, or the flag would not apply.
      repository_id: 6,
      repository_name: 'media',
      lane_busy: false,
      index_busy: true,
      operations: [
        op({
          id: 7,
          kind: 'stats',
          status: 'running',
          repository: 'media',
          repository_id: 6,
          started_at: minutesAgo(1),
        }),
        op({
          id: 8,
          kind: 'archive_sync',
          status: 'queued',
          repository: 'media',
          repository_id: 6,
          run_id: 'r2',
          trigger: 'followup',
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

// The same queue with a prune holding the lane instead of a backup: the
// waiting stages name the prune (issue: the wording used to say "backup"
// whatever held the lane).
export const maintenanceLaneQueue: QueueResponse = {
  ...busyQueue,
  repositories: busyQueue.repositories.map((repository) =>
    repository.repository_id === 2
      ? {
          ...repository,
          lane_holder: { kind: 'prune' as const, id: 3 },
          operations: [
            // the prune that holds the lane, and an index stage queued
            // behind it: the caption under that stage names the prune
            ...repository.operations.map((operation) =>
              operation.id === 3
                ? { ...operation, kind: 'prune' as const, category: 'maintenance' as const }
                : // admission holds index work back while a prune runs, so
                  // the stats row of the busy fixture waits here too
                  { ...operation, status: 'queued' as const, started_at: null }
            ),
            op({
              id: 31,
              kind: 'archive_sync',
              status: 'queued',
              repository: 'nas',
              repository_id: 2,
              started_at: null,
            }),
          ],
        }
      : repository
  ),
}

// The lane is taken, but the payload does not say by what: a page loaded
// before the server carried the holder, or one whose holder has finished
// since. The caption falls through to next in line until the next fetch.
export const missingLaneHolderQueue: QueueResponse = {
  ...busyQueue,
  repositories: busyQueue.repositories.map((repository) =>
    repository.repository_id === 2
      ? {
          ...repository,
          lane_holder: null,
          operations: repository.operations.map((operation) =>
            operation.id === 2
              ? { ...operation, status: 'queued' as const, started_at: null }
              : operation
          ),
        }
      : repository
  ),
}
