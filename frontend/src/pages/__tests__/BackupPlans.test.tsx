import { describe, expect, it } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import api, { backupPlansAPI } from '../../services/api'
import { buildBackupPlanPayload, type BackupPlanPayloadState } from '../../utils/backupPlanPayload'
import { createInitialState, planToState } from '../backup-plans/state'
import {
  applyRepositorySelectionLimit,
  isRepositorySelectionOverLimit,
} from '../../utils/backupPlanRepositorySelection'
import { getLegacySourceRepositoryReviews } from '../backup-plans/legacySourceSettings'
import { buildRoutePreviews } from '../backup-plans/routePreview'

function createPayloadState(
  overrides: Partial<BackupPlanPayloadState> = {}
): BackupPlanPayloadState {
  return {
    ...createInitialState(),
    name: 'Policy Plan',
    sourceDirectories: ['/data'],
    repositoryIds: [10],
    timezone: 'UTC',
    ...overrides,
  }
}

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
  it('converts scheduled upload policies to KiB per second', () => {
    const payload = buildBackupPlanPayload(
      createPayloadState({
        uploadRatelimitSchedulePolicies: [
          {
            label: 'Daytime cap',
            startTime: '08:00',
            endTime: '18:00',
            uploadRatelimitMb: '0.5',
          },
          {
            label: 'Overnight unlimited',
            startTime: '18:00',
            endTime: '08:00',
            uploadRatelimitMb: '',
          },
        ],
      })
    )

    expect(payload.upload_ratelimit_schedule_policies).toEqual([
      {
        label: 'Daytime cap',
        start_time: '08:00',
        end_time: '18:00',
        upload_ratelimit_kib: 512,
      },
      {
        label: 'Overnight unlimited',
        start_time: '18:00',
        end_time: '08:00',
        upload_ratelimit_kib: null,
      },
    ])
  })

  it('hydrates scheduled upload policies from backup plan details', () => {
    const state = planToState({
      id: 5,
      name: 'Policy Plan',
      enabled: true,
      source_type: 'local',
      source_directories: ['/data'],
      source_locations: [],
      exclude_patterns: [],
      archive_name_template: '{plan_name}-{repo_name}-{now}',
      compression: 'lz4',
      repository_run_mode: 'series',
      max_parallel_repositories: 1,
      failure_behavior: 'continue',
      schedule_enabled: false,
      timezone: 'UTC',
      repository_count: 1,
      repositories: [],
      upload_ratelimit_schedule_policies: [
        {
          label: 'Daytime cap',
          start_time: '08:00',
          end_time: '18:00',
          upload_ratelimit_kib: 512,
        },
        {
          label: 'Overnight unlimited',
          start_time: '18:00',
          end_time: '08:00',
          upload_ratelimit_kib: null,
        },
      ],
    })

    expect(state.uploadRatelimitSchedulePolicies).toEqual([
      {
        label: 'Daytime cap',
        startTime: '08:00',
        endTime: '18:00',
        uploadRatelimitMb: '0.5',
      },
      {
        label: 'Overnight unlimited',
        startTime: '18:00',
        endTime: '08:00',
        uploadRatelimitMb: '',
      },
    ])
  })

  it('builds grouped source location payloads with legacy mirrors', () => {
    const sourceLocations = [
      {
        source_type: 'local' as const,
        source_ssh_connection_id: null,
        paths: ['/srv/app'],
      },
      {
        source_type: 'remote' as const,
        source_ssh_connection_id: 11,
        paths: ['/home/app/data'],
      },
      {
        source_type: 'remote' as const,
        source_ssh_connection_id: 12,
        paths: ['/var/lib/service'],
      },
    ]

    const payload = buildBackupPlanPayload({
      name: 'Grouped Sources',
      description: '',
      enabled: true,
      sourceType: 'mixed',
      sourceSshConnectionId: '',
      sourceDirectories: ['/srv/app', '/home/app/data', '/var/lib/service'],
      sourceLocations,
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

    expect(payload.source_type).toBe('mixed')
    expect(payload.source_ssh_connection_id).toBeNull()
    expect(payload.source_directories).toEqual(['/srv/app', '/home/app/data', '/var/lib/service'])
    expect(payload.source_locations).toEqual(
      sourceLocations.map((location) => ({ ...location, agent_machine_id: null }))
    )
  })

  it('preserves local filesystem snapshot metadata in source locations', () => {
    const payload = buildBackupPlanPayload({
      name: 'Snapshot Plan',
      description: '',
      enabled: true,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/srv/app'],
      sourceLocations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/srv/app'],
          snapshot: {
            provider: 'btrfs',
            staging_path: '/var/tmp/borg-ui/snapshots',
            recursive: false,
          },
        },
      ],
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

    expect(payload.source_locations).toEqual([
      {
        source_type: 'local',
        source_ssh_connection_id: null,
        agent_machine_id: null,
        paths: ['/srv/app'],
        snapshot: {
          provider: 'btrfs',
          staging_path: '/var/tmp/borg-ui/snapshots',
          recursive: false,
        },
      },
    ])
  })

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

  it('keeps managed-agent source endpoint details in the payload', () => {
    const payload = buildBackupPlanPayload({
      name: 'Agent Plan',
      description: '',
      enabled: true,
      sourceType: 'agent',
      sourceSshConnectionId: '',
      sourceDirectories: ['/srv/project'],
      sourceLocations: [
        {
          source_type: 'agent',
          source_ssh_connection_id: null,
          agent_machine_id: 7,
          paths: ['/srv/project'],
        },
      ],
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

    expect(payload.source_type).toBe('agent')
    expect(payload.source_ssh_connection_id).toBeNull()
    expect(payload.source_locations).toEqual([
      {
        source_type: 'agent',
        source_ssh_connection_id: null,
        agent_machine_id: 7,
        paths: ['/srv/project'],
      },
    ])
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

  it('includes ordered plan script hooks in the payload and mirrors legacy fields', () => {
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
      preBackupScriptId: null,
      postBackupScriptId: null,
      preBackupScriptParameters: {},
      postBackupScriptParameters: {},
      scriptHooks: [
        {
          script_id: 2,
          hook_type: 'pre-backup',
          execution_order: 2,
          enabled: true,
          continue_on_error: true,
          skip_on_failure: false,
          parameter_values: { TARGET: 'database' },
        },
        {
          script_id: 3,
          hook_type: 'post-backup',
          execution_order: 1,
          enabled: true,
          custom_run_on: 'failure',
          parameter_values: {},
        },
      ],
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

    expect(payload.script_hooks).toEqual([
      expect.objectContaining({
        script_id: 2,
        hook_type: 'pre-backup',
        execution_order: 2,
        continue_on_error: true,
        parameter_values: { TARGET: 'database' },
      }),
      expect.objectContaining({
        script_id: 3,
        hook_type: 'post-backup',
        execution_order: 1,
        custom_run_on: 'failure',
      }),
    ])
    expect(payload.pre_backup_script_id).toBe(2)
    expect(payload.pre_backup_script_parameters).toEqual({ TARGET: 'database' })
    expect(payload.post_backup_script_id).toBe(3)
  })

  it('hydrates script hooks from the API and falls back to legacy plan script fields', () => {
    const stateWithHooks = planToState({
      id: 1,
      name: 'Scripted Plan',
      enabled: true,
      source_type: 'local',
      source_directories: ['/data'],
      source_locations: [],
      exclude_patterns: [],
      archive_name_template: '{plan_name}-{repo_name}-{now}',
      compression: 'lz4',
      repository_run_mode: 'series',
      max_parallel_repositories: 1,
      failure_behavior: 'continue',
      schedule_enabled: false,
      timezone: 'UTC',
      repository_count: 1,
      repositories: [],
      script_hooks: [
        {
          script_id: 9,
          hook_type: 'post-backup',
          execution_order: 1,
          enabled: true,
          custom_run_on: 'warning',
          parameter_values: { STATUS_FILE: '/tmp/status' },
        },
      ],
    })

    expect(stateWithHooks.scriptHooks).toEqual([
      expect.objectContaining({
        script_id: 9,
        hook_type: 'post-backup',
        custom_run_on: 'warning',
        parameter_values: { STATUS_FILE: '/tmp/status' },
      }),
    ])

    const legacyState = planToState({
      id: 2,
      name: 'Legacy Plan',
      enabled: true,
      source_type: 'local',
      source_directories: ['/data'],
      source_locations: [],
      exclude_patterns: [],
      archive_name_template: '{plan_name}-{repo_name}-{now}',
      compression: 'lz4',
      repository_run_mode: 'series',
      max_parallel_repositories: 1,
      failure_behavior: 'continue',
      schedule_enabled: false,
      timezone: 'UTC',
      repository_count: 1,
      repositories: [],
      pre_backup_script_id: 4,
      pre_backup_script_parameters: { TARGET: 'database' },
    })

    expect(legacyState.scriptHooks).toEqual([
      expect.objectContaining({
        script_id: 4,
        hook_type: 'pre-backup',
        parameter_values: { TARGET: 'database' },
      }),
    ])
  })

  it('keeps database source script assignments separate from plan scripts', () => {
    const payload = buildBackupPlanPayload({
      name: 'Database Sources',
      description: '',
      enabled: true,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
      sourceLocations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
          database: {
            template_id: 'sqlite',
            engine: 'SQLite',
            display_name: 'SQLite database',
            backup_strategy: 'online_backup',
            detected_source_path: '/home/app/state.sqlite',
            detection_label: 'Borg UI server',
            capture_mode: 'dump',
            dump_path: '/var/tmp/borg-ui/database-dumps/sqlite',
            backup_paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
            script_execution_target: 'source',
            pre_backup_script_id: 11,
            post_backup_script_id: 12,
            pre_backup_script_parameters: {
              SQLITE_DATABASE_PATH: '  /home/app/state.sqlite  ',
              EMPTY_VALUE: '   ',
            },
            post_backup_script_parameters: {
              CLEAN_TARGET: ' /var/tmp/borg-ui/database-dumps/sqlite ',
            },
            script_execution_order: 3,
          },
        },
      ],
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
      preBackupScriptId: 99,
      postBackupScriptId: null,
      preBackupScriptParameters: { PLAN_ONLY: 'yes' },
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

    expect(payload.pre_backup_script_id).toBe(99)
    expect(payload.pre_backup_script_parameters).toEqual({ PLAN_ONLY: 'yes' })
    expect(payload.source_locations?.[0].database).toEqual(
      expect.objectContaining({
        pre_backup_script_id: 11,
        post_backup_script_id: 12,
        pre_backup_script_parameters: {
          SQLITE_DATABASE_PATH: '/home/app/state.sqlite',
          EMPTY_VALUE: '',
        },
        post_backup_script_parameters: {
          CLEAN_TARGET: '/var/tmp/borg-ui/database-dumps/sqlite',
        },
        script_execution_order: 3,
      })
    )
  })

  it('preserves Docker container source metadata', () => {
    const invalidScriptTarget = 'sidecar' as unknown as 'source'
    const payload = buildBackupPlanPayload({
      name: 'Docker Sources',
      description: '',
      enabled: true,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: ['/var/tmp/borg-ui/container-exports/postgres'],
      sourceLocations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/var/tmp/borg-ui/container-exports/postgres'],
          container: {
            container_name: ' postgres ',
            display_name: ' Postgres service ',
            image: ' postgres:16 ',
            backup_mode: 'export',
            export_path: ' /var/tmp/borg-ui/container-exports/postgres ',
            script_execution_target: invalidScriptTarget,
            pre_backup_script_id: 11,
            post_backup_script_id: 12,
            pre_backup_script_parameters: {
              CONTAINER_EXPORT_FORMAT: ' tar ',
              EMPTY_VALUE: '   ',
            },
            post_backup_script_parameters: {
              CLEAN_EXPORT: ' yes ',
            },
            script_execution_order: 2,
          },
        },
      ],
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
      preBackupScriptId: 99,
      postBackupScriptId: null,
      preBackupScriptParameters: { PLAN_ONLY: 'yes' },
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

    expect(payload.pre_backup_script_id).toBe(99)
    expect(payload.pre_backup_script_parameters).toEqual({ PLAN_ONLY: 'yes' })
    expect(payload.source_locations?.[0].container).toEqual({
      container_name: 'postgres',
      display_name: 'Postgres service',
      image: 'postgres:16',
      backup_mode: 'export',
      export_path: '/var/tmp/borg-ui/container-exports/postgres',
      script_execution_target: 'source',
      pre_backup_script_id: 11,
      post_backup_script_id: 12,
      pre_backup_script_parameters: {
        CONTAINER_EXPORT_FORMAT: 'tar',
        EMPTY_VALUE: '',
      },
      post_backup_script_parameters: {
        CLEAN_EXPORT: 'yes',
      },
      script_execution_order: 2,
    })
  })

  it('hydrates Docker container source metadata with safe script defaults', () => {
    const invalidScriptTarget = 'sidecar' as unknown as 'source'

    const state = planToState({
      id: 3,
      name: 'Docker Plan',
      enabled: true,
      source_type: 'local',
      source_directories: ['/var/tmp/borg-ui/container-exports/postgres'],
      source_locations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/var/tmp/borg-ui/container-exports/postgres'],
          container: {
            container_name: ' postgres ',
            display_name: ' Postgres service ',
            image: ' postgres:16 ',
            backup_mode: 'export',
            export_path: ' /var/tmp/borg-ui/container-exports/postgres ',
            script_execution_target: invalidScriptTarget,
            pre_backup_script_id: 11,
            post_backup_script_id: 12,
            pre_backup_script_parameters: {
              CONTAINER_EXPORT_FORMAT: ' tar ',
              EMPTY_VALUE: '   ',
            },
            post_backup_script_parameters: {
              CLEAN_EXPORT: ' yes ',
            },
            script_execution_order: 2,
          },
        },
      ],
      exclude_patterns: [],
      archive_name_template: '{plan_name}-{repo_name}-{now}',
      compression: 'lz4',
      repository_run_mode: 'series',
      max_parallel_repositories: 1,
      failure_behavior: 'continue',
      schedule_enabled: false,
      timezone: 'UTC',
      repository_count: 1,
      repositories: [],
    })

    expect(state.sourceLocations?.[0].container).toEqual({
      container_name: 'postgres',
      display_name: 'Postgres service',
      image: 'postgres:16',
      backup_mode: 'export',
      export_path: '/var/tmp/borg-ui/container-exports/postgres',
      script_execution_target: 'source',
      pre_backup_script_id: 11,
      post_backup_script_id: 12,
      pre_backup_script_parameters: {
        CONTAINER_EXPORT_FORMAT: 'tar',
        EMPTY_VALUE: '',
      },
      post_backup_script_parameters: {
        CLEAN_EXPORT: 'yes',
      },
      script_execution_order: 2,
    })
  })
})

describe('BackupPlans route preview', () => {
  it('supports an agent source to the same agent-owned repository', () => {
    const routes = buildRoutePreviews(
      [
        {
          id: 10,
          name: 'Agent Repo',
          path: '/backups/agent',
          executor_type: 'agent',
          agent_machine_id: 7,
        },
      ],
      {
        name: 'Agent Plan',
        description: '',
        enabled: true,
        sourceType: 'agent',
        sourceSshConnectionId: '',
        sourceDirectories: ['/srv/project'],
        sourceLocations: [
          {
            source_type: 'agent',
            source_ssh_connection_id: null,
            agent_machine_id: 7,
            paths: ['/srv/project'],
          },
        ],
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
      },
      [
        {
          id: 7,
          name: 'Agent A',
          agent_id: 'agt_a',
          status: 'online',
          created_at: '',
          updated_at: '',
        },
      ]
    )

    expect(routes[0]).toMatchObject({
      supported: true,
      strategy: 'agent_direct',
      executor: 'agent',
      agentMachineId: 7,
    })
  })

  it('blocks Borg UI server sources to agent-owned repositories', () => {
    const routes = buildRoutePreviews(
      [
        {
          id: 10,
          name: 'Agent Repo',
          path: '/backups/agent',
          executor_type: 'agent',
          agent_machine_id: 7,
        },
      ],
      {
        name: 'Server Plan',
        description: '',
        enabled: true,
        sourceType: 'local',
        sourceSshConnectionId: '',
        sourceDirectories: ['/srv/project'],
        sourceLocations: [
          {
            source_type: 'local',
            source_ssh_connection_id: null,
            paths: ['/srv/project'],
          },
        ],
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
      },
      []
    )

    expect(routes[0]).toMatchObject({
      supported: false,
      messageKey: 'backupPlans.routePreview.serverToAgentRepo',
    })
  })
})
