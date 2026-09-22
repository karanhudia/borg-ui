import type { ReactNode } from 'react'
import { Box, Tooltip, Typography, useTheme } from '@mui/material'
import { FileDiff, FileText, HardDrive, Layers, Package, Timer } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import TintedTile from '../shared/TintedTile'
import type { Tone } from '../shared/tones'
import { formatBytes, formatDurationSeconds } from '../../utils/dateUtils'
import { changeColor } from './changeStyle'
import type { ArchiveDetailResponse } from '../../types/archives'

export interface ArchiveStatsHeaderProps {
  archive: ArchiveDetailResponse
  // The changes totals the page already fetches; undefined while loading,
  // on Community, or in a non-full index mode.
  totals?: { added: number; removed: number; modified: number }
  // Why the totals are absent, so the tile can say so instead of showing 0.
  totalsState: 'ready' | 'loading' | 'not_indexed' | 'unavailable'
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
  // The same tint per figure as the info tab and the repository header.
  tone: Tone
  icon: LucideIcon
  muted?: boolean
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

  // Only the exceptions are news: a figure measured at creation says nothing
  // the archive's own date does not.
  const measuredLine = !measured
    ? t('archives.detail.stats.notMeasured')
    : stale
      ? t('archives.detail.stats.remeasuring')
      : undefined

  const withPrevious = (d: string | null) =>
    d ? `${d} ${t('archives.detail.stats.vsPrevious')}` : undefined

  const ratio =
    archive.compressed_size != null && archive.compressed_size > 0 && archive.original_size != null
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
          flexWrap: 'wrap',
          columnGap: 0.75,
          fontSize: '0.85em',
          '& > span': { whiteSpace: 'nowrap' },
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
      value:
        measured && archive.deduplicated_size != null
          ? formatBytes(archive.deduplicated_size)
          : MINUS,
      sub: measuredLine,
      headline: true,
      tone: 'info',
      icon: Layers,
      muted: !measured,
    },
    {
      key: 'changed',
      label: t('archives.detail.stats.filesChanged'),
      value: filesChanged,
      tone: 'primary',
      icon: FileDiff,
      muted: totalsState !== 'ready',
    },
    {
      key: 'original',
      label: t('archives.detail.stats.dataBackedUp'),
      value: measured ? formatBytes(archive.original_size) : MINUS,
      sub: withPrevious(delta(archive.original_size, prev?.original_size, formatBytes)),
      tone: 'success',
      icon: HardDrive,
      muted: !measured,
    },
    {
      key: 'files',
      label: t('archives.detail.stats.files'),
      value: archive.nfiles != null ? archive.nfiles.toLocaleString() : MINUS,
      sub: withPrevious(delta(archive.nfiles, prev?.nfiles, (n) => n.toLocaleString())),
      tone: 'primary',
      icon: FileText,
      muted: archive.nfiles == null,
    },
    {
      key: 'duration',
      label: t('archives.detail.stats.duration'),
      value:
        archive.duration_seconds != null ? formatDurationSeconds(archive.duration_seconds) : MINUS,
      sub: withPrevious(
        delta(archive.duration_seconds, prev?.duration_seconds, formatDurationSeconds)
      ),
      tone: 'warning',
      icon: Timer,
      muted: archive.duration_seconds == null,
    },
    {
      key: 'compression',
      label: t('archives.detail.stats.compression'),
      value: ratio ?? t('archives.detail.stats.compressionNotReported'),
      tone: 'secondary',
      icon: Package,
      muted: ratio == null,
    },
  ]

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: { xs: '1fr 1fr', md: 'repeat(6, minmax(0, 1fr))' },
        gap: 1.5,
      }}
    >
      {tiles.map((tile) => {
        const node = (
          <Box
            sx={{
              gridColumn: tile.headline ? { xs: '1 / -1', md: 'auto' } : 'auto',
              height: '100%',
            }}
          >
            <TintedTile
              testId={`archive-stat-${tile.key}`}
              label={tile.label}
              value={tile.value}
              sub={
                tile.sub ? (
                  <Box
                    component="span"
                    sx={{ color: stale && tile.headline ? 'warning.main' : 'inherit' }}
                  >
                    {tile.sub}
                  </Box>
                ) : undefined
              }
              tone={tile.tone}
              icon={tile.icon}
              muted={tile.muted}
            />
          </Box>
        )
        if (!tile.headline)
          return (
            <Box key={tile.key} sx={{ height: '100%' }}>
              {node}
            </Box>
          )
        return (
          <Tooltip key={tile.key} title={t('archives.detail.stats.addedHint')}>
            {node}
          </Tooltip>
        )
      })}
    </Box>
  )
}
