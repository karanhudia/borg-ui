import { describe, expect, it } from 'vitest'
import type { BackupPlan } from '../../../types'

import {
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
})
