import { Box, Card, CardContent, Skeleton, Tooltip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDateTimeFull } from '../utils/dateUtils'
import type { RepositoryStorageSummary } from '../types'

export interface RepositoryStatsProps {
  storage?: RepositoryStorageSummary | null
  borgVersion?: number
  archiveCount?: number
  archivesLoading?: boolean
  compact?: boolean
  surface?: 'header' | 'dialog'
}

function StorageValue({
  value,
  unsupported = false,
}: {
  value: number | null | undefined
  unsupported?: boolean
}) {
  const { t } = useTranslation()
  if (unsupported) return <>{t('repositoryStats.notReported')}</>
  return (
    <>{value === null || value === undefined ? t('repositoryStats.unknown') : formatBytes(value)}</>
  )
}

function Stat({
  label,
  value,
  tooltip,
}: {
  label: string
  value: React.ReactNode
  tooltip?: string
}) {
  const card = (
    <Card variant="outlined" sx={{ bgcolor: 'background.paper' }}>
      <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
          {label}
        </Typography>
        <Typography variant="h6" sx={{ fontWeight: 700 }}>
          {value}
        </Typography>
      </CardContent>
    </Card>
  )
  return tooltip ? (
    <Tooltip title={tooltip} arrow>
      {card}
    </Tooltip>
  ) : (
    card
  )
}

export default function RepositoryStats({
  storage,
  borgVersion,
  archiveCount,
  archivesLoading = false,
  compact = false,
  surface = 'dialog',
}: RepositoryStatsProps) {
  const { t } = useTranslation()
  const source = storage?.size_source
  const repositoryLabel =
    source === 'borg1_cache_stats'
      ? t('repositoryStats.deduplicatedSize')
      : source === 'storage_used'
        ? t('repositoryStats.storageUsed')
        : t('repositoryStats.repositorySize')
  const measuredTooltip = storage?.measured_at
    ? t('repositoryStats.measuredAt', { date: formatDateTimeFull(storage.measured_at) })
    : undefined
  const compactStats = storage?.compact
  const archiveStat =
    archiveCount === undefined
      ? []
      : [
          {
            id: 'archives',
            label:
              surface === 'header'
                ? t('repositoryStatsGrid.totalArchives')
                : t('repositoryStats.archives'),
            value: archivesLoading ? (
              <Skeleton variant="text" width={40} />
            ) : (
              archiveCount.toLocaleString()
            ),
          },
        ]
  const repositoryStat = {
    id: 'repository-size',
    label: repositoryLabel,
    value: <StorageValue value={storage?.size_bytes} />,
    tooltip: measuredTooltip,
  }
  const originalStat = {
    id: 'original-size',
    label:
      surface === 'header'
        ? t('repositoryStatsGrid.originalSize')
        : t('repositoryStats.originalSize'),
    value: <StorageValue value={storage?.original_size} />,
  }

  if (surface === 'header') {
    const finalStat =
      borgVersion === 2
        ? {
            id: 'files',
            label: t('repositoryStatsGrid.numberOfFiles'),
            value:
              storage?.latest_archive_files == null
                ? t('repositoryStats.unknown')
                : storage.latest_archive_files.toLocaleString(),
          }
        : {
            id: 'compressed-size',
            label: t('repositoryStatsGrid.compressedSize'),
            value: <StorageValue value={storage?.compressed_size} />,
          }
    const headerStats = [...archiveStat, repositoryStat, originalStat, finalStat]
    return (
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 2,
        }}
      >
        {headerStats.map(({ id, ...stat }) => (
          <Stat key={id} {...stat} />
        ))}
      </Box>
    )
  }

  const stats: Array<{ id: string; label: string; value: React.ReactNode; tooltip?: string }> = [
    ...archiveStat,
    repositoryStat,
    originalStat,
    {
      id: 'compressed-size',
      label: t('repositoryStats.compressedSize'),
      value: <StorageValue value={storage?.compressed_size} unsupported={borgVersion === 2} />,
    },
    ...(source === 'borg1_cache_stats'
      ? []
      : [
          {
            id: 'deduplicated-size',
            label: t('repositoryStats.deduplicatedSize'),
            value: <StorageValue value={storage?.deduplicated_size} />,
          },
        ]),
    {
      id: 'files',
      label: t('repositoryStats.files'),
      value:
        storage?.latest_archive_files == null
          ? t('repositoryStats.unknown')
          : storage.latest_archive_files.toLocaleString(),
    },
  ]
  if (compact && borgVersion === 2)
    stats.push(
      {
        id: 'compact-source-data',
        label: t('repositoryStats.compactSourceData'),
        value: <StorageValue value={compactStats?.original_size} />,
        tooltip: storage?.compact_at
          ? t('repositoryStats.compactedAt', { date: formatDateTimeFull(storage.compact_at) })
          : undefined,
      },
      {
        id: 'compact-deduplicated',
        label: t('repositoryStats.compactDeduplicated'),
        value: <StorageValue value={compactStats?.deduplicated_size} />,
      },
      {
        id: 'compression-factor',
        label: t('repositoryStats.compressionFactor'),
        value:
          compactStats?.compression_factor == null
            ? t('repositoryStats.unknown')
            : `${compactStats.compression_factor}×`,
      }
    )
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
        gap: 2,
      }}
    >
      {stats.map(({ id, ...stat }) => (
        <Stat key={id} {...stat} />
      ))}
    </Box>
  )
}
