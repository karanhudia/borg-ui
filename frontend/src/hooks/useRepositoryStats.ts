import { useMemo } from 'react'

export interface NormalizedStats {
  original_size: number
  compressed_size: number
  deduplicated_size: number
  total_files?: number
}

interface BorgV1Info {
  cache?: {
    stats?: {
      total_size?: number
      total_csize?: number
      unique_csize?: number
    }
  }
  summary_stats?: NormalizedStats | null
}

interface BorgV2Info {
  archives?: Array<{
    time?: string
    start?: string
    stats?: { original_size?: number; nfiles?: number }
  }>
  rinfo_stats?: { unique_csize?: number; unique_size?: number }
  summary_stats?: NormalizedStats | null
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
      if (v2.summary_stats) {
        return v2.summary_stats
      }

      const archives = v2.archives || []
      const originalSize = archives.reduce(
        (sum, archive) => sum + (archive.stats?.original_size || 0),
        0
      )
      const deduplicatedSize = v2.rinfo_stats?.unique_csize || 0
      const latestArchive = archives.reduce<{
        time?: string
        start?: string
        stats?: { original_size?: number; nfiles?: number }
      } | null>((latest, archive) => {
        if (!latest) return archive

        const latestTs = Date.parse(latest.time || latest.start || '')
        const archiveTs = Date.parse(archive.time || archive.start || '')

        if (Number.isNaN(latestTs)) return archive
        if (Number.isNaN(archiveTs)) return latest

        return archiveTs > latestTs ? archive : latest
      }, null)
      const totalFiles = latestArchive?.stats?.nfiles || 0

      if (originalSize === 0 && deduplicatedSize === 0) return null

      return {
        original_size: originalSize,
        compressed_size: deduplicatedSize,
        deduplicated_size: deduplicatedSize,
        total_files: totalFiles,
      }
    }

    const v1 = info as BorgV1Info
    if (v1.summary_stats) {
      return v1.summary_stats
    }

    const cacheStats = v1.cache?.stats
    if (!cacheStats) return null

    return {
      original_size: cacheStats.total_size || 0,
      compressed_size: cacheStats.total_csize || 0,
      deduplicated_size: cacheStats.unique_csize || 0,
    }
  }, [info, borgVersion])
}
