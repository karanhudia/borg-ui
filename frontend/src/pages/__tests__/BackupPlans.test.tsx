import { describe, expect, it } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import api, { backupPlansAPI } from '../../services/api'
import { buildBackupPlanPayload } from '../../utils/backupPlanPayload'
import {
  applyRepositorySelectionLimit,
  isRepositorySelectionOverLimit,
} from '../../utils/backupPlanRepositorySelection'
import { getLegacySourceRepositoryReviews } from '../backup-plans/legacySourceSettings'

describe('BackupPlans API', () => {
  it('posts to the toggle endpoint for a backup plan', async () => {
    const mock = new MockAdapter(api)

    try {
      mock.onPost('/backup-plans/123/toggle').reply(200, { enabled: false })

      const response = await backupPlansAPI.toggle(123)

      expect(response.data).toEqual({ enabled: false })
      expect(mock.history.post).toHaveLength(1)
      expect(mock.history.post[0].url).toBe('/backup-plans/123/toggle')
    } finally {
      mock.restore()
    }
  })
})

describe('BackupPlans repository selection gating', () => {
  it('limits Community plans to the first selected repository', () => {
    expect(applyRepositorySelectionLimit([10, 20], false)).toEqual({
      ids: [10],
      limited: true,
    })
  })

  it('keeps multiple repositories for plans with multi-repository access', () => {
    expect(applyRepositorySelectionLimit([10, 20], true)).toEqual({
      ids: [10, 20],
      limited: false,
    })
  })

  it('detects Community over-limit selections without mutating repository ids', () => {
    const repositoryIds = [10, 20]

    expect(isRepositorySelectionOverLimit(repositoryIds, false)).toBe(true)
    expect(repositoryIds).toEqual([10, 20])
  })

  it('does not treat single Community selections as over limit', () => {
    expect(isRepositorySelectionOverLimit([10], false)).toBe(false)
  })

  it('does not treat multi-repository access selections as over limit', () => {
    expect(isRepositorySelectionOverLimit([10, 20], true)).toBe(false)
  })
})

describe('BackupPlans legacy source settings', () => {
  it('compares selected legacy repository source paths with the backup plan', () => {
    const matchingRepo = {
      id: 10,
      name: 'Matching',
      path: '/repos/matching',
      source_directories: ['/data/app', '/data/db'],
    }
    const subsetRepo = {
      id: 20,
      name: 'Subset',
      path: '/repos/subset',
      source_directories: ['/data/app'],
    }
    const extraRepo = {
      id: 30,
      name: 'Extra',
      path: '/repos/extra',
      source_directories: ['/data/app', '/data/old'],
    }
    const unselectedRepo = {
      id: 40,
      name: 'Unselected',
      path: '/repos/unselected',
      source_directories: ['/data/old'],
    }

    const reviews = getLegacySourceRepositoryReviews(
      [matchingRepo, subsetRepo, extraRepo, unselectedRepo],
      [10, 20, 30],
      ['/data/app', '/data/db']
    )

    expect(reviews).toEqual([
      expect.objectContaining({
        repository: matchingRepo,
        comparison: 'matches',
        legacyOnlySourceDirectories: [],
        planOnlySourceDirectories: [],
        defaultClear: true,
      }),
      expect.objectContaining({
        repository: subsetRepo,
        comparison: 'plan_includes_legacy',
        legacyOnlySourceDirectories: [],
        planOnlySourceDirectories: ['/data/db'],
        defaultClear: true,
      }),
      expect.objectContaining({
        repository: extraRepo,
        comparison: 'legacy_has_extra',
        legacyOnlySourceDirectories: ['/data/old'],
        planOnlySourceDirectories: ['/data/db'],
        defaultClear: false,
      }),
    ])
  })
})

describe('BackupPlans payload', () => {
  it('preserves a disabled plan in the payload', () => {
    const payload = buildBackupPlanPayload({
      name: 'Disabled Plan',
      description: '',
      enabled: false,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/data'],
      excludePatterns: [],
      repositoryIds: [10],
      compression: 'lz4',
      archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
      customFlags: '',
      uploadRatelimitMb: '',
      repositoryRunMode: 'series',
      maxParallelRepositories: 1,
      failureBehavior: 'continue',
      scheduleEnabled: false,
      cronExpression: '0 21 * * *',
      timezone: 'UTC',
      preBackupScriptId: null,
      postBackupScriptId: null,
      preBackupScriptParameters: {},
      postBackupScriptParameters: {},
      runRepositoryScripts: true,
      runPruneAfter: false,
      runCompactAfter: false,
      runCheckAfter: false,
      checkMaxDuration: 3600,
      checkExtraFlags: '',
      pruneKeepHourly: 0,
      pruneKeepDaily: 7,
      pruneKeepWeekly: 4,
      pruneKeepMonthly: 6,
      pruneKeepQuarterly: 0,
      pruneKeepYearly: 1,
    })

    expect(payload.enabled).toBe(false)
  })

  it('uses the plan compression for every selected repository', () => {
    const payload = buildBackupPlanPayload({
      name: 'Daily Plan',
      description: '',
      enabled: true,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/data'],
      excludePatterns: ['*.tmp'],
      repositoryIds: [10, 20],
      compression: 'zstd,10',
      archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
      customFlags: '--stats',
      uploadRatelimitMb: '5',
      repositoryRunMode: 'series',
      maxParallelRepositories: 1,
      failureBehavior: 'continue',
      scheduleEnabled: false,
      cronExpression: '0 21 * * *',
      timezone: 'UTC',
      preBackupScriptId: null,
      postBackupScriptId: null,
      preBackupScriptParameters: {},
      postBackupScriptParameters: {},
      runRepositoryScripts: true,
      runPruneAfter: true,
      runCompactAfter: true,
      runCheckAfter: true,
      checkMaxDuration: 7200,
      checkExtraFlags: '  --repair --verify-data  ',
      pruneKeepHourly: 2,
      pruneKeepDaily: 14,
      pruneKeepWeekly: 8,
      pruneKeepMonthly: 12,
      pruneKeepQuarterly: 4,
      pruneKeepYearly: 3,
    })

    expect(payload.compression).toBe('zstd,10')
    expect(payload.source_type).toBe('local')
    expect(payload.source_ssh_connection_id).toBeNull()
    expect(payload.run_repository_scripts).toBe(true)
    expect(payload).toMatchObject({
      run_prune_after: true,
      run_compact_after: true,
      run_check_after: true,
      check_max_duration: 7200,
      check_extra_flags: '--repair --verify-data',
      prune_keep_hourly: 2,
      prune_keep_daily: 14,
      prune_keep_weekly: 8,
      prune_keep_monthly: 12,
      prune_keep_quarterly: 4,
      prune_keep_yearly: 3,
    })
    expect(payload.repositories).toEqual([
      expect.objectContaining({
        repository_id: 10,
        execution_order: 1,
        compression_source: 'plan',
        compression_override: null,
      }),
      expect.objectContaining({
        repository_id: 20,
        execution_order: 2,
        compression_source: 'plan',
        compression_override: null,
      }),
    ])
  })

  it('keeps remote source connection details in the payload', () => {
    const payload = buildBackupPlanPayload({
      name: 'Remote Plan',
      description: '',
      enabled: true,
      sourceType: 'remote',
      sourceSshConnectionId: 42,
      sourceDirectories: ['/srv/data'],
      excludePatterns: [],
      repositoryIds: [10],
      compression: 'lz4',
      archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
      customFlags: '',
      uploadRatelimitMb: '',
      repositoryRunMode: 'series',
      maxParallelRepositories: 1,
      failureBehavior: 'continue',
      scheduleEnabled: false,
      cronExpression: '0 21 * * *',
      timezone: 'UTC',
      preBackupScriptId: null,
      postBackupScriptId: null,
      preBackupScriptParameters: {},
      postBackupScriptParameters: {},
      runRepositoryScripts: true,
      runPruneAfter: false,
      runCompactAfter: false,
      runCheckAfter: false,
      checkMaxDuration: 3600,
      checkExtraFlags: '',
      pruneKeepHourly: 0,
      pruneKeepDaily: 7,
      pruneKeepWeekly: 4,
      pruneKeepMonthly: 6,
      pruneKeepQuarterly: 0,
      pruneKeepYearly: 1,
    })

    expect(payload.source_type).toBe('remote')
    expect(payload.source_ssh_connection_id).toBe(42)
  })

  it('includes repository ids whose legacy source settings should be cleared', () => {
    const payload = buildBackupPlanPayload(
      {
        name: 'Migrated Plan',
        description: '',
        enabled: true,
        sourceType: 'local',
        sourceSshConnectionId: '',
        sourceDirectories: ['/data'],
        excludePatterns: [],
        repositoryIds: [10, 20],
        compression: 'lz4',
        archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
        customFlags: '',
        uploadRatelimitMb: '',
        repositoryRunMode: 'series',
        maxParallelRepositories: 1,
        failureBehavior: 'continue',
        scheduleEnabled: false,
        cronExpression: '0 21 * * *',
        timezone: 'UTC',
        preBackupScriptId: null,
        postBackupScriptId: null,
        preBackupScriptParameters: {},
        postBackupScriptParameters: {},
        runRepositoryScripts: true,
        runPruneAfter: false,
        runCompactAfter: false,
        runCheckAfter: false,
        checkMaxDuration: 3600,
        checkExtraFlags: '',
        pruneKeepHourly: 0,
        pruneKeepDaily: 7,
        pruneKeepWeekly: 4,
        pruneKeepMonthly: 6,
        pruneKeepQuarterly: 0,
        pruneKeepYearly: 1,
      },
      [20]
    )

    expect(payload.clear_legacy_source_repository_ids).toEqual([20])
  })

  it('includes plan-level scripts and parameters in the payload', () => {
    const payload = buildBackupPlanPayload({
      name: 'Scripted Plan',
      description: '',
      enabled: true,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/data'],
      excludePatterns: [],
      repositoryIds: [10],
      compression: 'lz4',
      archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
      customFlags: '',
      uploadRatelimitMb: '',
      repositoryRunMode: 'series',
      maxParallelRepositories: 1,
      failureBehavior: 'continue',
      scheduleEnabled: false,
      cronExpression: '0 21 * * *',
      timezone: 'UTC',
      preBackupScriptId: 1,
      postBackupScriptId: 2,
      preBackupScriptParameters: { TARGET: 'database' },
      postBackupScriptParameters: { STATUS_FILE: '/tmp/status' },
      runRepositoryScripts: false,
      runPruneAfter: false,
      runCompactAfter: false,
      runCheckAfter: false,
      checkMaxDuration: 3600,
      checkExtraFlags: '',
      pruneKeepHourly: 0,
      pruneKeepDaily: 7,
      pruneKeepWeekly: 4,
      pruneKeepMonthly: 6,
      pruneKeepQuarterly: 0,
      pruneKeepYearly: 1,
    })

    expect(payload.pre_backup_script_id).toBe(1)
    expect(payload.post_backup_script_id).toBe(2)
    expect(payload.pre_backup_script_parameters).toEqual({ TARGET: 'database' })
    expect(payload.post_backup_script_parameters).toEqual({ STATUS_FILE: '/tmp/status' })
    expect(payload.run_repository_scripts).toBe(false)
  })
})
