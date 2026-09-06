import { describe, it, expect } from 'vitest'
import {
  ATTENTION_FILTERS,
  attentionCounts,
  applyToolbar,
  mergeRows,
  type HubRow,
} from '../hubRows'
import type { RepositoryTrack } from '../repositoryTrack'
import type { HubRepository } from '../../../types/operations'

const repo = (overrides: Partial<HubRepository> = {}): HubRepository => ({
  repository_id: 1,
  repository_name: 'nas',
  repository_type: 'local',
  sync_state: 'fresh',
  last_synced_at: '2026-09-06T10:00:00',
  last_stats_at: '2026-09-06T10:00:00',
  last_history_at: null,
  archives: 10,
  history: { indexed: 10, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 100 },
  ...overrides,
})

const runningTrack = (repositoryId: number, name: string): RepositoryTrack => ({
  repositoryId,
  repositoryName: name,
  foreground: null,
  stages: [{ key: 'stats', status: 'running', operation: null, reason: null }],
})

const row = (repository: HubRepository, track: RepositoryTrack | null = null): HubRow => ({
  key: `repo-${repository.repository_id}`,
  repository,
  track,
})

const fixtures = {
  fresh: repo({ repository_id: 1, repository_name: 'alpha' }),
  stale: repo({
    repository_id: 2,
    repository_name: 'bravo',
    sync_state: 'stale',
    last_synced_at: '2026-09-01T10:00:00',
    history: { indexed: 5, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 900 },
  }),
  never: repo({
    repository_id: 3,
    repository_name: 'charlie',
    sync_state: 'never',
    last_synced_at: null,
    archives: 0,
    history: { indexed: 0, pending: 0, failed: 0, skipped: 0, truncated: 0, rows: 0 },
  }),
  failed: repo({
    repository_id: 4,
    repository_name: 'delta',
    last_synced_at: '2026-09-05T10:00:00',
    history: { indexed: 8, pending: 0, failed: 2, skipped: 0, truncated: 1, rows: 500 },
  }),
  running: repo({ repository_id: 5, repository_name: 'echo' }),
}

const rows: HubRow[] = [
  row(fixtures.fresh),
  row(fixtures.stale),
  row(fixtures.never),
  row(fixtures.failed),
  row(fixtures.running, runningTrack(5, 'echo')),
]

const names = (result: HubRow[]) => result.map((r) => r.repository?.repository_name ?? r.key)

describe('attentionCounts', () => {
  it('counts each attention reason and the rows that have at least one', () => {
    expect(attentionCounts(rows)).toEqual({
      stale: 1,
      never: 1,
      history: 1,
      running: 1,
      total: 4,
    })
  })

  it('counts a row once in total even when it has several reasons', () => {
    const both = row(
      repo({
        repository_id: 9,
        sync_state: 'stale',
        history: { indexed: 1, pending: 0, failed: 1, skipped: 0, truncated: 0, rows: 1 },
      })
    )
    expect(attentionCounts([both])).toMatchObject({ stale: 1, history: 1, total: 1 })
  })

  it('ignores the system lane, which has no derived data', () => {
    const system: HubRow = { key: 'system-x', repository: null, track: runningTrack(0, 'System') }
    expect(attentionCounts([system]).total).toBe(0)
  })
})

describe('applyToolbar', () => {
  it('keeps every row with the default toolbar', () => {
    expect(applyToolbar(rows, { query: '', attention: 'all', sort: 'name' })).toHaveLength(5)
  })

  it('matches the name filter case-insensitively on a substring', () => {
    const result = applyToolbar(rows, { query: 'LT', attention: 'all', sort: 'name' })
    expect(names(result)).toEqual(['delta'])
  })

  it.each([
    ['stale', ['bravo']],
    ['never', ['charlie']],
    ['history', ['delta']],
    ['running', ['echo']],
  ] as const)('filters to %s rows', (attention, expected) => {
    expect(names(applyToolbar(rows, { query: '', attention, sort: 'name' }))).toEqual(expected)
  })

  it('shows the union of every reason for the attention view', () => {
    const result = applyToolbar(rows, { query: '', attention: 'attention', sort: 'name' })
    expect(names(result)).toEqual(['bravo', 'charlie', 'delta', 'echo'])
  })

  it('sorts by name and leaves a row with work in progress in its place', () => {
    const shuffled = [rows[3], rows[1], rows[4], rows[0], rows[2]]
    const result = applyToolbar(shuffled, { query: '', attention: 'all', sort: 'name' })
    expect(names(result)).toEqual(['alpha', 'bravo', 'charlie', 'delta', 'echo'])
  })

  it('sorts by history rows, largest first', () => {
    const result = applyToolbar(rows, { query: '', attention: 'all', sort: 'rows' })
    expect(names(result)).toEqual(['bravo', 'delta', 'alpha', 'echo', 'charlie'])
  })

  it('sorts by last synced, most recent first, never synced last', () => {
    const result = applyToolbar(rows, { query: '', attention: 'all', sort: 'synced' })
    expect(names(result)).toEqual(['alpha', 'echo', 'delta', 'bravo', 'charlie'])
  })

  it('keeps the system lane after every repository', () => {
    const system: HubRow = { key: 'system-x', repository: null, track: runningTrack(0, 'System') }
    const result = applyToolbar([system, ...rows], { query: '', attention: 'all', sort: 'name' })
    expect(names(result)[names(result).length - 1]).toBe('system-x')
  })

  it('drops the system lane when a name filter is set', () => {
    const system: HubRow = { key: 'system-x', repository: null, track: runningTrack(0, 'System') }
    const result = applyToolbar([system, ...rows], { query: 'a', attention: 'all', sort: 'name' })
    expect(names(result)).not.toContain('system-x')
  })
})

describe('mergeRows', () => {
  it('pairs each repository with its queue track and appends system work', () => {
    const merged = mergeRows(
      [fixtures.fresh, fixtures.running],
      [runningTrack(5, 'echo'), { ...runningTrack(0, 'System'), repositoryId: null }]
    )
    expect(merged.map((r) => r.key)).toEqual(['repo-1', 'repo-5', 'system-System'])
    expect(merged[1].track?.repositoryName).toBe('echo')
  })
})

describe('ATTENTION_FILTERS', () => {
  it('lists the filters in toolbar order', () => {
    expect(ATTENTION_FILTERS).toEqual(['all', 'attention', 'stale', 'never', 'history', 'running'])
  })
})
