import RepositoryStats from './RepositoryStats'
import type { RepositoryStorageSummary } from '../types'

interface RepositoryStatsGridProps {
  storage?: RepositoryStorageSummary | null
  archivesCount: number
  borgVersion?: number
  archivesLoading?: boolean
}

export default function RepositoryStatsGrid({
  storage,
  archivesCount,
  borgVersion,
  archivesLoading,
}: RepositoryStatsGridProps) {
  return (
    <RepositoryStats
      storage={storage}
      archiveCount={archivesCount}
      archivesLoading={archivesLoading}
      borgVersion={borgVersion}
      surface="header"
    />
  )
}
