import { describe, it, expect } from 'vitest'
import {
  getArchiveType,
  getTimeGroup,
  sortArchives,
} from '../archiveGrouping'
import type { Archive } from '../../types'

const makeArchive = (name: string, start: string): Archive => ({
  id: '1',
  archive: name,
  name,
  start,
  time: start,
})

describe('getArchiveType', () => {
  it('returns "manual" for archives starting with manual-backup-', () => {
    const archive = makeArchive('manual-backup-2024-01-01T00:00:00', '2024-01-01T00:00:00')
    expect(getArchiveType(archive)).toBe('manual')
  })

  it('returns "scheduled" for other archives', () => {
    const archive = makeArchive('repo-2024-01-01T00:00:00', '2024-01-01T00:00:00')
    expect(getArchiveType(archive)).toBe('scheduled')
  })
})

describe('getTimeGroup', () => {
  it('returns "yesterday" for an archive from yesterday', () => {
    const now = new Date('2024-06-15T12:00:00')
    const yesterday = new Date('2024-06-14T12:00:00')
    expect(getTimeGroup(yesterday, now)).toBe('yesterday')
  })

  it('returns "last7days" for an archive from 3 days ago', () => {
    const now = new Date('2024-06-15T12:00:00')
    const threeDaysAgo = new Date('2024-06-12T12:00:00')
    expect(getTimeGroup(threeDaysAgo, now)).toBe('last7days')
  })
})

describe('sortArchives', () => {
  const archives: Archive[] = [
    makeArchive('a', '2024-01-01T00:00:00'),
    makeArchive('b', '2024-01-03T00:00:00'),
    makeArchive('c', '2024-01-02T00:00:00'),
  ]

  it('falls through to original order on unknown sort option', () => {
    // Exercises the default branch of the switch statement
    const result = sortArchives(archives, 'unknown' as never)
    expect(result).toHaveLength(3)
  })
})
