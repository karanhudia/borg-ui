import { describe, it, expect } from 'vitest'
import { renderHook } from '@testing-library/react'
import { useRepositoryStats } from '../useRepositoryStats'

const v1Info = {
  cache: {
    stats: {
      total_size: 10_000_000,
      total_csize: 8_000_000,
      unique_csize: 4_000_000,
    },
  },
}

const v2Info = {
  archives: [
    { time: '2026-04-10T13:41:53+05:30', stats: { original_size: 3_000_000, nfiles: 4 } },
    { time: '2026-04-11T13:41:53+05:30', stats: { original_size: 5_000_000, nfiles: 6 } },
  ],
  rinfo_stats: {
    unique_csize: 2_000_000,
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

  it('maps Borg 1 cache stats to original/compressed/deduplicated sizes', () => {
    const { result } = renderHook(() => useRepositoryStats(v1Info, 1))
    expect(result.current).toEqual({
      original_size: 10_000_000,
      compressed_size: 8_000_000,
      deduplicated_size: 4_000_000,
    })
  })

  it('maps Borg 1 cache stats when borgVersion is undefined', () => {
    const { result } = renderHook(() => useRepositoryStats(v1Info, undefined))
    expect(result.current).toEqual({
      original_size: 10_000_000,
      compressed_size: 8_000_000,
      deduplicated_size: 4_000_000,
    })
  })

  it('returns summed original_size across archives for Borg 2', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.original_size).toBe(8_000_000)
  })

  it('uses rinfo_stats unique_csize as the displayed compressed size for Borg 2 fallback', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.compressed_size).toBe(2_000_000)
  })

  it('uses rinfo_stats unique_csize as the displayed deduplicated size for Borg 2 fallback', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.deduplicated_size).toBe(2_000_000)
  })

  it('uses nfiles from the latest Borg 2 archive', () => {
    const { result } = renderHook(() => useRepositoryStats(v2Info, 2))
    expect(result.current?.total_files).toBe(6)
  })

  it('returns null for Borg 2 when all stats are zero (no backups yet)', () => {
    const emptyV2 = { archives: [], rinfo_stats: { unique_csize: 0, unique_size: 0 } }
    const { result } = renderHook(() => useRepositoryStats(emptyV2, 2))
    expect(result.current).toBeNull()
  })

  it('returns summary_stats directly when backend provides them', () => {
    const withSummaryStats = {
      archives: [{ stats: { original_size: 1_000_000 } }],
      rinfo_stats: { unique_csize: 500_000 },
      summary_stats: {
        original_size: 9_000_000,
        compressed_size: 7_000_000,
        deduplicated_size: 2_000_000,
      },
    }
    const { result } = renderHook(() => useRepositoryStats(withSummaryStats, 2))
    expect(result.current).toEqual(withSummaryStats.summary_stats)
  })
})
