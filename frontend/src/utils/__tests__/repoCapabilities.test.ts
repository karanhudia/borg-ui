import { describe, it, expect } from 'vitest'
import { getRepoCapabilities } from '../repoCapabilities'

describe('getRepoCapabilities', () => {
  describe('full mode', () => {
    it('allows all write operations', () => {
      const caps = getRepoCapabilities({ mode: 'full' })
      expect(caps.canBackup).toBe(true)
      expect(caps.canPrune).toBe(true)
      expect(caps.canCompact).toBe(true)
      expect(caps.canDeleteArchive).toBe(true)
      expect(caps.canDeleteRepository).toBe(true)
    })

    it('allows read operations', () => {
      const caps = getRepoCapabilities({ mode: 'full' })
      expect(caps.canMount).toBe(true)
      expect(caps.canRestore).toBe(true)
    })
  })

  describe('observe mode', () => {
    it('blocks archive write operations but still allows repository removal', () => {
      const caps = getRepoCapabilities({ mode: 'observe' })
      expect(caps.canBackup).toBe(false)
      expect(caps.canPrune).toBe(false)
      expect(caps.canCompact).toBe(false)
      expect(caps.canDeleteArchive).toBe(false)
      expect(caps.canDeleteRepository).toBe(true)
    })

    it('allows read operations', () => {
      const caps = getRepoCapabilities({ mode: 'observe' })
      expect(caps.canMount).toBe(true)
      expect(caps.canRestore).toBe(true)
    })
  })

  describe('missing mode', () => {
    it('treats undefined mode as full', () => {
      const caps = getRepoCapabilities({})
      expect(caps.canBackup).toBe(true)
      expect(caps.canDeleteArchive).toBe(true)
      expect(caps.canDeleteRepository).toBe(true)
    })
  })
})
