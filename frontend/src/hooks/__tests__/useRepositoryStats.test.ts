import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useRepositoryStats } from '../useRepositoryStats'

const v1Info = {
  cache: {
    stats: {
      total_size: 10_000_000,
      unique_size: 6_000_000,
      unique_csize: 4_000_000,
    },
  },
}

const v2Info = {
  archives: [{ stats: { original_size: 3_000_000 } }, { stats: { original_size: 5_000_000 } }],
  rinfo_stats: {
    unique_csize: 2_000_000,
    unique_size: 3_500_000,
  },
}

describe('useRepositoryStats', () => {
  it('returns null when info is null', () => {
    const { result } = renderHook(() => useRepositoryStats(null, undefined))
    expect(result.current).toBeNull()
  })

  it('returns null when info is undefined', () => {
    const { result } = renderHook(() => useRepositoryStats(undefined, 1))
    expect(result.current).toBeNull()
  })

  it('returns cache.stats directly for Borg 1', () => {
    const { result } = renderHook(() => useRepositoryStats(v1Info, 1))
    expect(result.current).toEqual(v1Info.cache.stats)
  })

  it('returns cache.stats when borgVersion is undefined (defaults to v1 path)', () => {
    const { result } = renderHook(() => useRepositoryStats(v1Info, undefined))
    expect(result.current).toEqual(v1Info.cache.stats)
  })

  it('returns summed original_size across archives for Borg 2', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.total_size).toBe(8_000_000) // 3M + 5M
  })

  it('uses rinfo_stats unique_csize for Borg 2 on-disk size', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.unique_csize).toBe(2_000_000)
  })

  it('uses rinfo_stats unique_size for Borg 2 unique data', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.unique_size).toBe(3_500_000)
  })

  it('returns null for Borg 2 when all stats are zero (no backups yet)', () => {
    const emptyV2 = { archives: [], rinfo_stats: { unique_csize: 0, unique_size: 0 } }
    const { result } = renderHook(() => useRepositoryStats(emptyV2, 2))
    expect(result.current).toBeNull()
  })

  it('falls back unique_size to unique_csize when rinfo_stats.unique_size is missing', () => {
    const v2NoUniqueSize = {
      archives: [{ stats: { original_size: 1_000_000 } }],
      rinfo_stats: { unique_csize: 500_000 },
    }
    const { result } = renderHook(() => useRepositoryStats(v2NoUniqueSize, 2))
    expect(result.current?.unique_size).toBe(500_000)
    expect(result.current?.unique_csize).toBe(500_000)
  })
})
