import { useMemo } from 'react'

export interface NormalizedStats {
  total_size: number
  unique_size: number
  unique_csize: number
}

interface BorgV1Info {
  cache?: { stats?: NormalizedStats }
}

interface BorgV2ArchiveStats {
  original_size?: number
}

interface BorgV2Info {
  archives?: Array<{ stats?: BorgV2ArchiveStats }>
  rinfo_stats?: { unique_csize?: number; unique_size?: number }
}

export type BorgRepoInfo = BorgV1Info | BorgV2Info

export function useRepositoryStats(
  info: BorgRepoInfo | null | undefined,
  borgVersion: number | undefined
): NormalizedStats | null {
  return useMemo(() => {
    if (!info) return null

    if (borgVersion === 2) {
      const v2 = info as BorgV2Info
      const archives = v2.archives || []
      const rinfo = v2.rinfo_stats || {}
      const totalOriginal = archives.reduce((s, a) => s + (a.stats?.original_size || 0), 0)
      const uniqueCsize = rinfo.unique_csize || 0
      const uniqueSize = rinfo.unique_size || uniqueCsize
      if (totalOriginal === 0 && uniqueCsize === 0) return null
      return { total_size: totalOriginal, unique_size: uniqueSize, unique_csize: uniqueCsize }
    }

    return (info as BorgV1Info).cache?.stats || null
  }, [info, borgVersion])
}
