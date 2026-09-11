import { describe, it, expect } from 'vitest'
import { deriveTrack } from '../repositoryTrack'
import type { OperationItem, QueueLimits, QueueRepository } from '../../../types/operations'

const op = (overrides: Partial<OperationItem>): OperationItem =>
  ({
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
    created_at: null,
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
  }) as OperationItem

const limits: QueueLimits = {
  index_workers: 2,
  index_running: 0,
  max_concurrent_backups: 1,
  max_concurrent_scheduled_backups: 2,
  max_concurrent_scheduled_checks: 4,
}

const repo = (
  operations: OperationItem[],
  lane_busy = false,
  lane_holder: QueueRepository['lane_holder'] = null
): QueueRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  lane_busy,
  lane_holder,
  operations,
})

// A busy lane and the operation holding it, as the queue sends the pair:
// the holder is one of the repository's own running rows.
const held = (
  kind: 'backup' | 'prune' | 'compact' | 'check',
  queued: OperationItem[]
): QueueRepository => {
  const holder = op({
    id: 99,
    kind,
    category: kind === 'backup' ? 'backup' : 'maintenance',
    status: 'running',
  })
  return repo([...queued, holder], true, { kind, id: holder.id })
}

describe('deriveTrack', () => {
  it('maps each stage to its latest operation status', () => {
    const track = deriveTrack(
      repo([
        op({ id: 1, kind: 'stats', status: 'completed' }),
        op({ id: 2, kind: 'archive_sync', status: 'running', started_at: '2026-09-05T10:00:00' }),
        op({ id: 3, kind: 'history_index', status: 'queued' }),
      ]),
      limits,
      false
    )
    expect(track.stages.map((s) => [s.key, s.status])).toEqual([
      ['connect', 'idle'],
      ['archives', 'running'],
      ['history', 'waiting'],
      ['stats', 'done'],
    ])
    expect(track.stages[2].reason).toBe('queued')
  })

  it('explains a queued stage with the paused state first', () => {
    const track = deriveTrack(
      held('backup', [op({ kind: 'stats', status: 'queued' })]),
      limits,
      true
    )
    expect(track.stages[3].reason).toBe('paused')
  })

  it('explains a queued stage with the busy lane', () => {
    const track = deriveTrack(
      held('backup', [op({ kind: 'stats', status: 'queued' })]),
      limits,
      false
    )
    expect(track.stages[3].reason).toBe('lane_busy')
    expect(track.stages[3].reasonKind).toBe('backup')
  })

  it('names whichever exclusive operation holds the lane', () => {
    // a prune, a compact or a check hold it as much as a backup does
    for (const kind of ['prune', 'compact', 'check'] as const) {
      const track = deriveTrack(
        held(kind, [op({ kind: 'stats', status: 'queued' })]),
        limits,
        false
      )
      expect(track.stages[3].reason).toBe('lane_busy')
      expect(track.stages[3].reasonKind).toBe(kind)
    }
  })

  it('falls back to the unnamed wording when the payload carries no holder', () => {
    // a page loaded before the server sent the holder: the lane is busy,
    // something runs, but nothing names it, and "the backup" would be a guess
    const track = deriveTrack(
      repo(
        [
          op({ kind: 'stats', status: 'queued' }),
          op({ id: 99, kind: 'backup', category: 'backup', status: 'running' }),
        ],
        true,
        null
      ),
      limits,
      false
    )
    expect(track.stages[3].reason).toBe('lane_busy_unnamed')
    expect(track.stages[3].reasonKind).toBeNull()
  })

  it('stops naming a holder the same payload shows as finished', () => {
    // an event marked the holder completed in the cache before the queue
    // was refetched, while another operation still runs: the stage waits,
    // but for something it can no longer name
    const track = deriveTrack(
      repo(
        [
          op({ kind: 'stats', status: 'queued' }),
          op({ id: 99, kind: 'prune', category: 'maintenance', status: 'completed' }),
          op({ id: 100, kind: 'backup', category: 'backup', status: 'running' }),
        ],
        true,
        { kind: 'prune', id: 99 }
      ),
      limits,
      false
    )
    expect(track.stages[3].reason).toBe('lane_busy_unnamed')
    expect(track.stages[3].reasonKind).toBeNull()
  })

  it('leaves the worker limit to explain a stage once the holder is gone', () => {
    // bypass_lock lets index work run beside a lane holder; when that
    // holder finishes in the cache, an archive_sync still running is not
    // evidence of a taken lane, and the real answer is the worker pool
    const track = deriveTrack(
      repo(
        [
          op({ id: 10, kind: 'history_index', status: 'queued' }),
          op({ id: 99, kind: 'prune', category: 'maintenance', status: 'completed' }),
          op({ id: 9, kind: 'archive_sync', category: 'index', status: 'running' }),
        ],
        true,
        { kind: 'prune', id: 99 }
      ),
      { ...limits, index_running: 2 },
      false
    )
    expect(track.stages[2].reason).toBe('workers')
    expect(track.stages[2].reasonKind).toBeNull()
  })

  it('does not let a kind it cannot place keep the lane busy', () => {
    // an operation from a newer build carries a category all the same; the
    // server refuses it the lane, and so does the track rather than
    // reporting a holder it cannot name
    const track = deriveTrack(
      repo(
        [
          op({ id: 10, kind: 'history_index', status: 'queued' }),
          op({ id: 99, kind: 'prune', category: 'maintenance', status: 'completed' }),
          op({
            id: 11,
            kind: 'teleport' as OperationItem['kind'],
            category: 'maintenance',
            status: 'running',
          }),
        ],
        true,
        { kind: 'prune', id: 99 }
      ),
      { ...limits, index_running: 2 },
      false
    )
    expect(track.stages[2].reason).toBe('workers')
    expect(track.stages[2].reasonKind).toBeNull()
  })

  it('does not claim a busy lane while the payload shows nothing running', () => {
    // the lane flag is the server's word and the rows are this payload's;
    // with every operation finished in the cache the stage is simply next
    // in line, not waiting for a phantom
    const track = deriveTrack(
      repo(
        [
          op({ kind: 'stats', status: 'queued' }),
          op({ id: 99, kind: 'prune', category: 'maintenance', status: 'completed' }),
        ],
        true,
        { kind: 'prune', id: 99 }
      ),
      limits,
      false
    )
    expect(track.stages[3].reason).toBe('queued')
    expect(track.stages[3].reasonKind).toBeNull()
  })

  it('explains a queued history stage with the worker limit', () => {
    const track = deriveTrack(
      repo([op({ kind: 'history_index', status: 'queued' })]),
      { ...limits, index_running: 2 },
      false
    )
    expect(track.stages[2].reason).toBe('workers')
  })

  it('treats history_merge as the history stage and failed as retryable', () => {
    const track = deriveTrack(
      repo([op({ id: 4, kind: 'history_merge', status: 'failed' })]),
      limits,
      false
    )
    expect(track.stages[2].status).toBe('failed')
    expect(track.stages[2].operation?.id).toBe(4)
  })

  it('prefers the newest operation when a stage ran twice', () => {
    const track = deriveTrack(
      repo([
        op({ id: 4, kind: 'stats', status: 'failed' }),
        op({ id: 9, kind: 'stats', status: 'completed' }),
      ]),
      limits,
      false
    )
    expect(track.stages[3].status).toBe('done')
  })

  it('describes only the newest run when an older one is still in the queue window', () => {
    const track = deriveTrack(
      repo([
        op({ id: 1, kind: 'archive_sync', status: 'completed', run_id: 'reconcile' }),
        op({ id: 2, kind: 'history_index', status: 'completed', run_id: 'reconcile' }),
        op({ id: 3, kind: 'stats', status: 'completed', run_id: 'reconcile' }),
        op({ id: 4, kind: 'stats', status: 'queued', run_id: 'rebuild', trigger: 'manual' }),
      ]),
      limits,
      false
    )
    expect(track.stages.map((s) => [s.key, s.status])).toEqual([
      ['connect', 'idle'],
      ['archives', 'idle'],
      ['history', 'idle'],
      ['stats', 'waiting'],
    ])
  })

  it('prefers the run with work in progress over a newer finished one', () => {
    const track = deriveTrack(
      repo([
        op({ id: 1, kind: 'archive_sync', status: 'completed', run_id: 'reconcile' }),
        op({ id: 2, kind: 'history_index', status: 'running', run_id: 'reconcile' }),
        op({ id: 5, kind: 'stats', status: 'completed', run_id: 'rebuild', trigger: 'manual' }),
      ]),
      limits,
      false
    )
    expect(track.stages.map((s) => [s.key, s.status])).toEqual([
      ['connect', 'idle'],
      ['archives', 'done'],
      ['history', 'running'],
      ['stats', 'idle'],
    ])
  })

  it('marks a stage skipped after its dependency failed instead of done', () => {
    const track = deriveTrack(
      repo([
        op({ id: 1, kind: 'archive_sync', status: 'failed' }),
        op({ id: 2, kind: 'history_index', status: 'skipped', skip_reason: 'dependency_failed' }),
      ]),
      limits,
      false
    )
    expect(track.stages[1].status).toBe('failed')
    expect(track.stages[2].status).toBe('skipped')
  })

  it('surfaces a running foreground operation separately from the stages', () => {
    const track = deriveTrack(
      repo([op({ id: 7, kind: 'backup', category: 'backup', status: 'running' })], true),
      limits,
      false
    )
    expect(track.foreground?.id).toBe(7)
    expect(track.stages.every((s) => s.status === 'idle')).toBe(true)
  })
})
