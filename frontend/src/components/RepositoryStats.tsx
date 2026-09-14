import { Box, Card, CardContent, Tooltip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDateTimeFull } from '../utils/dateUtils'
import type { RepositoryStorageSummary } from '../types'

export interface RepositoryStatsProps {
  storage?: RepositoryStorageSummary | null
  borgVersion?: number
  archiveCount?: number
  compact?: boolean
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
  compact = false,
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
  const stats: Array<{ label: string; value: React.ReactNode; tooltip?: string }> = [
    ...(archiveCount === undefined
      ? []
      : [{ label: t('repositoryStats.archives'), value: archiveCount.toLocaleString() }]),
    {
      label: repositoryLabel,
      value: <StorageValue value={storage?.size_bytes} />,
      tooltip: measuredTooltip,
    },
    {
      label: t('repositoryStats.originalSize'),
      value: <StorageValue value={storage?.original_size} />,
    },
    {
      label: t('repositoryStats.compressedSize'),
      value: <StorageValue value={storage?.compressed_size} unsupported={borgVersion === 2} />,
    },
    {
      label: t('repositoryStats.deduplicatedSize'),
      value: <StorageValue value={storage?.deduplicated_size} />,
    },
    {
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
        label: t('repositoryStats.compactSourceData'),
        value: <StorageValue value={compactStats?.original_size} />,
        tooltip: storage?.compact_at
          ? t('repositoryStats.compactedAt', { date: formatDateTimeFull(storage.compact_at) })
          : undefined,
      },
      {
        label: t('repositoryStats.compactDeduplicated'),
        value: <StorageValue value={compactStats?.deduplicated_size} />,
      },
      {
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
      {stats.map((stat) => (
        <Stat key={stat.label} {...stat} />
      ))}
    </Box>
  )
}
