import { describe, expect, it } from 'vitest'

import { getBorgVersion, getRepoCapabilities, isV2Repo } from './repoCapabilities'

describe('repoCapabilities', () => {
  it('detects Borg 2 repositories', () => {
    expect(isV2Repo({ borg_version: 2 })).toBe(true)
    expect(isV2Repo({ borg_version: 1 })).toBe(false)
    expect(isV2Repo(null)).toBe(false)
  })

  it('returns the effective Borg version', () => {
    expect(getBorgVersion({ borg_version: 2 })).toBe(2)
    expect(getBorgVersion({ borg_version: 1 })).toBe(1)
    expect(getBorgVersion(undefined)).toBe(1)
  })

  it('disables destructive actions for observe-mode repositories', () => {
    expect(getRepoCapabilities({ mode: 'observe' })).toEqual({
      canBackup: false,
      canPrune: false,
      canCompact: false,
      canDelete: false,
      canMount: true,
      canRestore: true,
    })
  })

  it('enables full capabilities for regular repositories', () => {
    expect(getRepoCapabilities({ mode: 'full' })).toEqual({
      canBackup: true,
      canPrune: true,
      canCompact: true,
      canDelete: true,
      canMount: true,
      canRestore: true,
    })
  })
})
