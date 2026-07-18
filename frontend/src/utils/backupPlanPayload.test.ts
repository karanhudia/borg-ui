import { describe, expect, it } from 'vitest'

import { createInitialState, planToState } from '../pages/backup-plans/state'
import { buildBackupPlanPayload } from './backupPlanPayload'
import type { BackupPlan } from '../types'

describe('backupPlanPayload agent script hooks', () => {
  it('keeps an agent-script hook and never mirrors it to legacy columns', () => {
    const payload = buildBackupPlanPayload({
      ...createInitialState(),
      name: 'Agent plan',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      scriptHooks: [
        {
          agent_script_name: 'pre-db-dump.sh',
          is_agent_script: true,
          hook_type: 'pre-backup',
          execution_order: 1,
          enabled: true,
        },
      ],
    })

    expect(payload.script_hooks).toHaveLength(1)
    expect(payload.script_hooks?.[0]).toMatchObject({
      agent_script_name: 'pre-db-dump.sh',
      script_id: null,
      hook_type: 'pre-backup',
    })
    // Library-only legacy column stays empty for agent hooks.
    expect(payload.pre_backup_script_id ?? null).toBeNull()
  })

  it('drops hooks that reference neither a library nor an agent script', () => {
    const payload = buildBackupPlanPayload({
      ...createInitialState(),
      name: 'Empty hook plan',
      sourceDirectories: ['/data'],
      repositoryIds: [10],
      scriptHooks: [
        {
          hook_type: 'pre-backup',
          execution_order: 1,
          enabled: true,
        },
      ],
    })

    expect(payload.script_hooks).toHaveLength(0)
  })
})

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
