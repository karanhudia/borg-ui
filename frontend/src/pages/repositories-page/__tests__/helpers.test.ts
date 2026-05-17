import { describe, expect, it } from 'vitest'
import type { TFunction } from 'i18next'

import { processRepositories } from '../helpers'
import type { Repository } from '../types'

const t = ((key: string) => key) as TFunction

const baseRepository: Repository = {
  id: 1,
  name: 'Primary',
  path: '/backups/primary',
  encryption: 'repokey',
  compression: 'lz4',
  source_directories: [],
  exclude_patterns: [],
  last_backup: null,
  last_check: null,
  last_compact: null,
  total_size: null,
  archive_count: 0,
  created_at: '2026-05-15T10:00:00Z',
  updated_at: null,
  mode: 'full',
}

describe('processRepositories', () => {
  it('filters repositories to the selected backup plan repository ids', () => {
    const secondaryRepository = {
      ...baseRepository,
      id: 2,
      name: 'Secondary',
      path: '/backups/secondary',
    }

    const result = processRepositories({
      repositories: [baseRepository, secondaryRepository],
      searchQuery: '',
      sortBy: 'name-asc',
      groupBy: 'none',
      backupPlanRepositoryIds: new Set([secondaryRepository.id]),
      t,
    })

    expect(result.groups).toEqual([{ name: null, repositories: [secondaryRepository] }])
  })
})
