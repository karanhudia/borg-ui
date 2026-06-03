import { describe, expect, it } from 'vitest'
import type { Repository } from '../../types'
import {
  getExecutableLegacyRepositories,
  isExecutableLegacyRepository,
} from '../executableRepositories'

const repo = (overrides: Partial<Repository>): Repository =>
  ({
    id: 1,
    name: 'Repo',
    path: '/repo',
    mode: 'full',
    ...overrides,
  }) as Repository

describe('executable legacy repository filtering', () => {
  it('includes full-mode repositories with legacy source directories', () => {
    expect(isExecutableLegacyRepository(repo({ source_directories: ['/srv/app'] }))).toBe(true)
  })

  it('includes full-mode repositories with source locations', () => {
    expect(
      isExecutableLegacyRepository(
        repo({
          source_locations: [{ source_type: 'local', paths: ['/srv/app'] }],
        })
      )
    ).toBe(true)
  })

  it('includes full-mode repositories with database backup paths', () => {
    expect(
      isExecutableLegacyRepository(
        repo({
          source_locations: [
            {
              source_type: 'local',
              paths: [],
              database: {
                template_id: 'postgres',
                engine: 'postgres',
                display_name: 'Postgres',
                backup_strategy: 'dump',
                capture_mode: 'dump',
                backup_paths: ['/tmp/pg.sql'],
                script_execution_target: 'server',
              },
            },
          ],
        })
      )
    ).toBe(true)
  })

  it('excludes observe-mode repositories and repositories without sources', () => {
    const executable = repo({ id: 1, source_directories: ['/srv/app'] })
    const observe = repo({ id: 2, mode: 'observe', source_directories: ['/srv/app'] })
    const planOwned = repo({ id: 3, source_directories: [], source_locations: [] })

    expect(getExecutableLegacyRepositories([observe, planOwned, executable]).map((r) => r.id)).toEqual(
      [1]
    )
  })
})
