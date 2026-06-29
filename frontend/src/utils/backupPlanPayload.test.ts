import { describe, expect, it } from 'vitest'

import { createInitialState, planToState } from '../pages/backup-plans/state'
import { buildBackupPlanPayload } from './backupPlanPayload'
import type { BackupPlan } from '../types'

describe('backupPlanPayload prune keep-within', () => {
  it('includes a trimmed keep-within interval in backup plan payloads', () => {
    const payload = buildBackupPlanPayload({
      ...createInitialState(),
      name: 'Frequent backup',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      runPruneAfter: true,
      pruneKeepWithin: ' 1d ',
    })

    expect(payload.prune_keep_within).toBe('1d')
  })

  it('normalizes a cleared keep-within interval to null in backup plan payloads', () => {
    const payload = buildBackupPlanPayload({
      ...createInitialState(),
      name: 'Frequent backup',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      runPruneAfter: true,
      pruneKeepWithin: '   ',
    })

    expect(payload.prune_keep_within).toBeNull()
  })

  it('hydrates keep-within from an existing backup plan', () => {
    const state = planToState({
      id: 1,
      name: 'Frequent backup',
      enabled: true,
      source_type: 'local',
      source_directories: ['/data'],
      source_locations: [],
      exclude_patterns: [],
      repository_run_mode: 'series',
      max_parallel_repositories: 1,
      failure_behavior: 'continue',
      schedule_enabled: false,
      timezone: 'UTC',
      archive_name_template: '{plan_name}-{repo_name}-{now}',
      compression: 'lz4',
      run_repository_scripts: true,
      run_prune_after: true,
      run_compact_after: false,
      run_check_after: false,
      repository_count: 1,
      check_max_duration: 3600,
      prune_keep_hourly: 0,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_quarterly: 0,
      prune_keep_yearly: 1,
      prune_keep_within: '1d',
      repositories: [{ repository_id: 10, enabled: true, execution_order: 1 }],
    } as BackupPlan)

    expect(state.pruneKeepWithin).toBe('1d')
  })
})
