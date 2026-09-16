import type { ReactNode } from 'react'
import { Box, Tooltip, Typography, useTheme, alpha } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatBytes, formatDurationSeconds, formatRelativeTime } from '../../utils/dateUtils'
import { changeColor } from './changeStyle'
import type { ArchiveDetailResponse } from '../../types/archives'

export interface ArchiveStatsHeaderProps {
  archive: ArchiveDetailResponse
  // The changes totals the page already fetches; undefined while loading,
  // on Community, or in a non-full index mode.
  totals?: { added: number; removed: number; modified: number }
  // Why the totals are absent, so the tile can say so instead of showing 0.
  totalsState: 'ready' | 'loading' | 'plan_locked' | 'not_indexed' | 'unavailable'
}

const MINUS = '−'

// A signed difference rendered with the same formatter as the value, or
// null when either side is missing (spec 4.2: a delta needs both figures).
function delta(
  current: number | null | undefined,
  previous: number | null | undefined,
  format: (n: number) => string
): string | null {
  if (current == null || previous == null) return null
  const diff = current - previous
  if (diff === 0) return '±0'
  return diff > 0 ? `+${format(diff)}` : `${MINUS}${format(-diff)}`
}

interface Tile {
  key: string
  label: string
  value: ReactNode
  sub?: ReactNode
  headline?: boolean
}

export default function ArchiveStatsHeader({
  archive,
  totals,
  totalsState,
}: ArchiveStatsHeaderProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const prev = archive.predecessor_stats
  const measured = archive.original_size != null
  const stale = measured && archive.stats_measured_at == null

  const measuredLine = !measured
    ? t('archives.detail.stats.notMeasured')
    : stale
      ? t('archives.detail.stats.remeasuring')
      : t('archives.detail.stats.measuredAt', {
          when: formatRelativeTime(archive.stats_measured_at),
        })

  const withPrevious = (d: string | null) =>
    d ? `${d} ${t('archives.detail.stats.vsPrevious')}` : undefined

  const ratio =
    archive.compressed_size != null && archive.compressed_size > 0 && archive.original_size
      ? `${(archive.original_size / archive.compressed_size).toFixed(1)}:1`
      : null

  const muted = (text: string) => (
    <Typography component="span" variant="body2" sx={{ color: 'text.secondary' }}>
      {text}
    </Typography>
  )

  const filesChanged: ReactNode =
    totalsState === 'ready' && totals ? (
      <Box
        component="span"
        sx={{
          display: 'inline-flex',
          gap: 1,
          fontVariantNumeric: 'tabular-nums',
          fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
        }}
      >
        <Box component="span" sx={{ color: changeColor(theme, 'added') }}>
          +{totals.added}
        </Box>
        <Box component="span" sx={{ color: changeColor(theme, 'removed') }}>
          {MINUS}
          {totals.removed}
        </Box>
        <Box component="span" sx={{ color: changeColor(theme, 'modified') }}>
          ~{totals.modified}
        </Box>
      </Box>
    ) : totalsState === 'plan_locked' ? (
      muted(t('archives.detail.stats.filesChangedLocked'))
    ) : totalsState === 'not_indexed' ? (
      muted(t('archives.detail.stats.filesChangedNotIndexed'))
    ) : totalsState === 'unavailable' ? (
      muted(t('archives.detail.stats.filesChangedUnavailable'))
    ) : (
      muted('…')
    )

  const tiles: Tile[] = [
    {
      key: 'added',
      label: t('archives.detail.stats.addedToRepository'),
      value: measured ? formatBytes(archive.deduplicated_size) : MINUS,
      sub: measuredLine,
      headline: true,
    },
    { key: 'changed', label: t('archives.detail.stats.filesChanged'), value: filesChanged },
    {
      key: 'original',
      label: t('archives.detail.stats.dataBackedUp'),
      value: measured ? formatBytes(archive.original_size) : MINUS,
      sub: withPrevious(delta(archive.original_size, prev?.original_size, formatBytes)),
    },
    {
      key: 'files',
      label: t('archives.detail.stats.files'),
      value: archive.nfiles != null ? archive.nfiles.toLocaleString() : MINUS,
      sub: withPrevious(delta(archive.nfiles, prev?.nfiles, (n) => n.toLocaleString())),
    },
    {
      key: 'duration',
      label: t('archives.detail.stats.duration'),
      value:
        archive.duration_seconds != null ? formatDurationSeconds(archive.duration_seconds) : MINUS,
      sub: withPrevious(
        delta(archive.duration_seconds, prev?.duration_seconds, formatDurationSeconds)
      ),
    },
    {
      key: 'compression',
      label: t('archives.detail.stats.compression'),
      value: ratio ?? muted(t('archives.detail.stats.compressionNotReported')),
    },
  ]

  return (
    <Box
      component="dl"
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr 1fr', md: '1.6fr repeat(5, 1fr)' },
        gap: 1.5,
        m: 0,
      }}
    >
      {tiles.map((tile) => (
        <Tooltip
          key={tile.key}
          title={tile.headline ? t('archives.detail.stats.addedHint') : ''}
          disableHoverListener={!tile.headline}
        >
          <Box
            sx={{
              p: 1.5,
              borderRadius: 2,
              bgcolor: tile.headline
                ? alpha(theme.palette.info.main, theme.palette.mode === 'dark' ? 0.16 : 0.09)
                : alpha(theme.palette.text.primary, theme.palette.mode === 'dark' ? 0.04 : 0.03),
              gridColumn: tile.headline ? { xs: '1 / -1', md: 'auto' } : 'auto',
            }}
          >
            <Typography
              component="dt"
              variant="caption"
              sx={{ color: 'text.secondary', display: 'block' }}
            >
              {tile.label}
            </Typography>
            <Typography
              component="dd"
              variant={tile.headline ? 'h5' : 'subtitle1'}
              sx={{ m: 0, fontWeight: 700, fontVariantNumeric: 'tabular-nums', lineHeight: 1.3 }}
            >
              {tile.value}
            </Typography>
            {tile.sub && (
              <Typography
                variant="caption"
                sx={{ color: stale && tile.headline ? 'warning.main' : 'text.secondary' }}
              >
                {tile.sub}
              </Typography>
            )}
          </Box>
        </Tooltip>
      ))}
    </Box>
  )
}
