import { describe, expect, it } from 'vitest'
import type { BackupPlan } from '../../../types'

import {
  backupPlanRunAnalytics,
  backupPlanUsesRepository,
  parseRepositoryFilterId,
  processBackupPlans,
} from '../helpers'

const basePlan: BackupPlan = {
  id: 1,
  name: 'Primary Plan',
  enabled: true,
  source_type: 'local',
  source_directories: ['/srv/primary'],
  exclude_patterns: [],
  archive_name_template: '{plan_name}-{repo_name}-{now}',
  compression: 'lz4',
  repository_run_mode: 'series',
  max_parallel_repositories: 1,
  failure_behavior: 'continue',
  schedule_enabled: false,
  timezone: 'UTC',
  repository_count: 1,
  repositories: [
    {
      repository_id: 10,
      enabled: true,
      execution_order: 1,
    },
  ],
}

describe('parseRepositoryFilterId', () => {
  it('accepts positive integer repository ids', () => {
    expect(parseRepositoryFilterId('42')).toBe(42)
  })

  it('rejects missing, non-numeric, and non-positive repository ids', () => {
    expect(parseRepositoryFilterId(null)).toBeNull()
    expect(parseRepositoryFilterId('abc')).toBeNull()
    expect(parseRepositoryFilterId('0')).toBeNull()
    expect(parseRepositoryFilterId('-1')).toBeNull()
  })
})

describe('backupPlanUsesRepository', () => {
  it('matches only enabled repository links', () => {
    expect(backupPlanUsesRepository(basePlan, 10)).toBe(true)
    expect(
      backupPlanUsesRepository(
        {
          ...basePlan,
          repositories: [{ repository_id: 10, enabled: false, execution_order: 1 }],
        },
        10
      )
    ).toBe(false)
  })
})

describe('processBackupPlans', () => {
  it('filters backup plans to a linked repository id before search, sort, and grouping', () => {
    const secondaryPlan: BackupPlan = {
      ...basePlan,
      id: 2,
      name: 'Secondary Plan',
      repositories: [{ repository_id: 20, enabled: true, execution_order: 1 }],
    }

    const result = processBackupPlans({
      backupPlans: [basePlan, secondaryPlan],
      repositoryFilterId: 20,
      searchQuery: '',
      sortBy: 'name-asc',
      groupBy: 'none',
      t: ((key: string) => key) as never,
    })

    expect(result.groups).toEqual([{ name: null, plans: [secondaryPlan] }])
  })

  it('groups mixed-source backup plans with source grouping', () => {
    const mixedPlan: BackupPlan = {
      ...basePlan,
      id: 2,
      name: 'Mixed Source Plan',
      source_type: 'mixed',
    }

    const result = processBackupPlans({
      backupPlans: [basePlan, mixedPlan],
      repositoryFilterId: null,
      searchQuery: '',
      sortBy: 'name-asc',
      groupBy: 'source',
      t: ((key: string) => key) as never,
    })

    expect(result.groups).toEqual([
      { name: 'backupPlans.groups.localSource', plans: [basePlan] },
      { name: 'backupPlans.sourceChooser.mixedSources', plans: [mixedPlan] },
    ])
  })
})

describe('backupPlanRunAnalytics', () => {
  const run = {
    id: 5,
    backup_plan_id: 1,
    trigger: 'manual',
    status: 'failed',
    started_at: '2026-10-22T10:00:00Z',
    completed_at: '2026-10-22T10:01:30Z',
    error_message: 'borg: /srv/secret: permission denied',
    repositories: [
      { id: 1, status: 'completed' },
      { id: 2, status: 'failed', error_message: 'lock on /srv/x' },
    ],
  }

  it('maps a finished run to Complete or Fail with counts, never messages', () => {
    const [action, props] = backupPlanRunAnalytics(run)
    expect(action).toBe('Fail')
    expect(props).toEqual({
      entity: 'backup_plan',
      trigger: 'manual',
      status: 'failed',
      duration_seconds: 90,
      repository_count: 2,
      failed_repository_count: 1,
    })
    expect(JSON.stringify(props)).not.toContain('secret')
    expect(backupPlanRunAnalytics({ ...run, status: 'completed_with_warnings' })[0]).toBe(
      'Complete'
    )
    expect(
      backupPlanRunAnalytics({ ...run, status: 'skipped', skip_reason: 'source_unavailable' })[1]
    ).toMatchObject({ status: 'skipped', skip_reason: 'source_unavailable' })
  })
})
