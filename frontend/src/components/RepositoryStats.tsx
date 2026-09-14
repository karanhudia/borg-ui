import type { ReactNode } from 'react'
import { Box, Skeleton, Stack, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import { Archive as ArchiveIcon, Database, FileText, Layers } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { RepositoryStorage } from '../types'
import { formatBytes, formatDateShort } from '../utils/dateUtils'
import {
  repositoryStatItems,
  stateText,
  type RepositoryStatItem,
  type RepositoryStatsInput,
} from '../utils/repositoryStats'

export interface RepositoryStatsProps extends RepositoryStatsInput {
  archivesLoading?: boolean
}

type ColorKey = 'primary' | 'success' | 'info' | 'secondary' | 'warning'

const ICONS: Record<string, ReactNode> = {
  archives: <ArchiveIcon size={32} />,
  size: <Database size={32} />,
  originalSize: <Layers size={32} />,
  compressedSize: <Database size={32} />,
  deduplicatedSize: <Database size={32} />,
  latestArchiveFiles: <FileText size={32} />,
}
const COLORS: ColorKey[] = ['primary', 'success', 'info', 'secondary', 'warning']

interface StatTileProps {
  item: RepositoryStatItem
  text: ReactNode
  colorKey: ColorKey
  dense: boolean
}

function StatTile({ item, text, colorKey, dense }: StatTileProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = (theme.palette[colorKey] as { main: string }).main
  const muted = item.state !== 'value'

  const tile = (
    <Box
      data-testid={`repository-stat-${item.key}`}
      data-state={item.state}
      // the hint opens on focus as well, so a keyboard reader reaches it
      tabIndex={item.hint ? 0 : undefined}
      sx={{
        borderRadius: 2,
        bgcolor: alpha(color, isDark ? 0.1 : 0.07),
        px: 2,
        py: dense ? 1.25 : 1.75,
        boxShadow: isDark
          ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 2px 8px ${alpha('#000', 0.2)}`
          : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 6px ${alpha('#000', 0.06)}`,
        cursor: item.hint ? 'help' : 'default',
      }}
    >
      <Stack direction="row" sx={{ justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box sx={{ minWidth: 0 }}>
          <Typography
            variant="caption"
            sx={{
              textTransform: 'uppercase',
              letterSpacing: '0.06em',
              fontSize: '0.6rem',
              fontWeight: 700,
              color,
              display: 'block',
              mb: 0.75,
            }}
          >
            {item.label}
          </Typography>
          <Typography
            variant={dense ? 'h6' : 'h5'}
            sx={{
              fontWeight: muted ? 500 : 700,
              lineHeight: 1.2,
              fontSize: muted
                ? { xs: '0.95rem', lg: '1rem' }
                : dense
                  ? '1.15rem'
                  : { xs: '1.4rem', lg: '1.5rem' },
              color: muted ? 'text.secondary' : color,
              fontStyle: muted ? 'italic' : 'normal',
              wordBreak: 'break-word',
            }}
          >
            {text}
          </Typography>
        </Box>
        <Box sx={{ color, opacity: 0.4, mt: 0.25, flexShrink: 0 }}>{ICONS[item.key]}</Box>
      </Stack>
    </Box>
  )

  if (!item.hint) return tile
  return (
    // the tile carries its own label; the hint describes it
    <Tooltip title={item.hint} arrow describeChild>
      {tile}
    </Tooltip>
  )
}

function bytesOrNull(value: number | null | undefined): string | null {
  return value === null || value === undefined ? null : formatBytes(value)
}

function factorOrNull(value: number | null | undefined): string | null {
  return value === null || value === undefined ? null : `${value.toFixed(2)}×`
}

/** The newest compact's statistics (Borg 2 with `--stats`), with its time. */
function CompactBlock({ storage }: { storage: RepositoryStorage }) {
  const { t } = useTranslation()
  const compact = storage.compact
  if (!compact) return null
  const rows = [
    {
      key: 'sourceSize',
      label: t('repositoryStats.compact.sourceSize'),
      value: bytesOrNull(compact.source_size),
    },
    {
      key: 'deduplicatedSize',
      label: t('repositoryStats.compact.deduplicatedSize'),
      value: bytesOrNull(compact.deduplicated_size),
    },
    {
      key: 'compressionFactor',
      label: t('repositoryStats.compact.compressionFactor'),
      value: factorOrNull(compact.compression_factor),
    },
    {
      key: 'deduplicationFactor',
      label: t('repositoryStats.compact.deduplicationFactor'),
      value: factorOrNull(compact.deduplication_factor),
    },
    {
      key: 'saved',
      label: t('repositoryStats.compact.saved'),
      value: bytesOrNull(compact.compaction_saved),
    },
  ].filter((row) => row.value !== null)
  if (rows.length === 0) return null
  const caption = [
    storage.compact_at
      ? t('repositoryStats.compact.at', { time: formatDateShort(storage.compact_at) })
      : null,
    compact.size_precision === 'rounded' ? t('repositoryStats.compact.rounded') : null,
  ]
    .filter(Boolean)
    .join(' ')
  return (
    <Box data-testid="repository-stats-compact">
      <Typography variant="subtitle2" sx={{ fontWeight: 600, mt: 1, mb: caption ? 0 : 1 }}>
        {t('repositoryStats.compact.heading')}
      </Typography>
      {caption ? (
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block', mb: 1 }}>
          {caption}
        </Typography>
      ) : null}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
          gap: 1.5,
        }}
      >
        {rows.map((row) => (
          <Box
            key={row.key}
            data-testid={`repository-stat-compact-${row.key}`}
            sx={{ px: 1.5, py: 1, borderRadius: 1.5, border: '1px solid', borderColor: 'divider' }}
          >
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              {row.label}
            </Typography>
            <Typography variant="body1" sx={{ fontWeight: 600 }}>
              {row.value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  )
}

/**
 * The repository's size figures from the stored `storage` payload (#981),
 * in the archive header (`grid`) or the info dialog (`detail`). Reads
 * nothing live: the same numbers the card shows, with their provenance in
 * the tooltip and an explicit state for what is not there.
 */
export default function RepositoryStats({
  storage,
  borgVersion,
  archiveCount,
  archivesLoading = false,
  indexPendingKinds,
  variant = 'grid',
}: RepositoryStatsProps) {
  const { t } = useTranslation()
  const version = borgVersion === 2 ? 2 : 1
  const items = repositoryStatItems(t, {
    storage,
    borgVersion: version,
    archiveCount,
    indexPendingKinds,
    variant,
  })
  const dense = variant === 'detail'

  return (
    <Box data-testid="repository-stats" data-variant={variant}>
      {dense ? (
        <Typography variant="h6" sx={{ fontWeight: 600, mt: 1, mb: 1.5 }}>
          {t('repositoryStats.heading')}
        </Typography>
      ) : null}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: dense
            ? { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' }
            : { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 2,
          mb: dense ? 2 : 0,
        }}
      >
        {items.map((item, index) => (
          <StatTile
            key={item.key}
            item={item}
            colorKey={COLORS[index % COLORS.length]}
            dense={dense}
            text={
              item.key === 'archives' && archivesLoading ? (
                <Skeleton variant="text" width={40} sx={{ fontSize: '1.5rem' }} />
              ) : (
                stateText(t, item, version)
              )
            }
          />
        ))}
      </Box>
      {dense && storage ? <CompactBlock storage={storage} /> : null}
    </Box>
  )
}
