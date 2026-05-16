import { describe, expect, it } from 'vitest'
import { buildScheduleDeepLink, parseScheduleDeepLink } from '../scheduleDeepLink'

describe('scheduleDeepLink', () => {
  describe('buildScheduleDeepLink', () => {
    it('builds a check-target hash', () => {
      expect(buildScheduleDeepLink('repo-checks', 42)).toBe('#repo-checks/42')
    })

    it('builds a restore-target hash', () => {
      expect(buildScheduleDeepLink('restore-checks', 7)).toBe('#restore-checks/7')
    })
  })

  describe('parseScheduleDeepLink', () => {
    it('parses a check-target hash', () => {
      expect(parseScheduleDeepLink('#repo-checks/42')).toEqual({
        target: 'repo-checks',
        repositoryId: 42,
      })
    })

    it('parses a restore-target hash', () => {
      expect(parseScheduleDeepLink('#restore-checks/7')).toEqual({
        target: 'restore-checks',
        repositoryId: 7,
      })
    })

    it('parses a hash without leading #', () => {
      expect(parseScheduleDeepLink('repo-checks/3')).toEqual({
        target: 'repo-checks',
        repositoryId: 3,
      })
    })

    it('returns null for unrelated hashes', () => {
      expect(parseScheduleDeepLink('#')).toBeNull()
      expect(parseScheduleDeepLink('')).toBeNull()
      expect(parseScheduleDeepLink('#repos/42')).toBeNull()
      expect(parseScheduleDeepLink('#repo-checks/')).toBeNull()
      expect(parseScheduleDeepLink('#repo-checks/abc')).toBeNull()
      expect(parseScheduleDeepLink('#repo-checks/42/extra')).toBeNull()
    })
  })
})
