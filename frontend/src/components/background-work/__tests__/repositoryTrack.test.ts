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

const repo = (operations: OperationItem[], lane_busy = false): QueueRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  lane_busy,
  operations,
})

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
      ['stats', 'done'],
      ['archives', 'running'],
      ['history', 'waiting'],
    ])
    expect(track.stages[3].reason).toBe('queued')
  })

  it('explains a queued stage with the paused state first', () => {
    const track = deriveTrack(repo([op({ kind: 'stats', status: 'queued' })], true), limits, true)
    expect(track.stages[1].reason).toBe('paused')
  })

  it('explains a queued stage with the busy lane', () => {
    const track = deriveTrack(repo([op({ kind: 'stats', status: 'queued' })], true), limits, false)
    expect(track.stages[1].reason).toBe('lane_busy')
  })

  it('explains a queued history stage with the worker limit', () => {
    const track = deriveTrack(
      repo([op({ kind: 'history_index', status: 'queued' })]),
      { ...limits, index_running: 2 },
      false
    )
    expect(track.stages[3].reason).toBe('workers')
  })

  it('treats history_merge as the history stage and failed as retryable', () => {
    const track = deriveTrack(
      repo([op({ id: 4, kind: 'history_merge', status: 'failed' })]),
      limits,
      false
    )
    expect(track.stages[3].status).toBe('failed')
    expect(track.stages[3].operation?.id).toBe(4)
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
    expect(track.stages[1].status).toBe('done')
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
