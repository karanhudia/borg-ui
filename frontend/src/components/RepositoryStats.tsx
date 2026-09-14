import type { ReactElement, ReactNode } from 'react'
import {
  Box,
  Card,
  CardContent,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
  useTheme,
  alpha,
} from '@mui/material'
import Compress from '@mui/icons-material/Compress'
import DataUsage from '@mui/icons-material/DataUsage'
import Storage from '@mui/icons-material/Storage'
import { Archive as ArchiveIcon, Database, Layers, PiggyBank } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import {
  repositoryStatItems,
  stateText,
  type RepositoryStatItem,
  type RepositoryStatTone,
  type RepositoryStatsInput,
} from '../utils/repositoryStats'

export interface RepositoryStatsProps extends RepositoryStatsInput {
  archivesLoading?: boolean
}

type PaletteKey = 'info' | 'warning' | 'success' | 'primary'

// The hue each figure carries: blue for what you have, orange for what it
// costs, green for what you gained; the archive count keeps the primary.
const TONE_PALETTE: Record<RepositoryStatTone, PaletteKey> = {
  info: 'info',
  warning: 'warning',
  success: 'success',
  neutral: 'primary',
}

const TILE_ICONS: Record<string, ReactNode> = {
  archives: <ArchiveIcon size={32} />,
  originalSize: <Layers size={32} />,
  usedOnDisk: <Database size={32} />,
  spaceSaved: <PiggyBank size={32} />,
}

const CARD_ICONS: Record<string, (color: string) => ReactNode> = {
  originalSize: (color) => <DataUsage sx={{ color, fontSize: 24 }} />,
  usedOnDisk: (color) => <Storage sx={{ color, fontSize: 24 }} />,
  spaceSaved: (color) => <Compress sx={{ color, fontSize: 24 }} />,
}

function withHint(item: RepositoryStatItem, node: ReactElement) {
  if (!item.hint) return node
  return (
    // the tile carries its own label; the hint describes it
    <Tooltip title={item.hint} arrow describeChild>
      {node}
    </Tooltip>
  )
}

interface StatProps {
  item: RepositoryStatItem
  text: ReactNode
}

/** The archive header's tile, as `RepositoryStatsGrid` drew it. */
function StatTile({ item, text }: StatProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = theme.palette[TONE_PALETTE[item.tone]].main
  const muted = item.state !== 'value'

  return withHint(
    item,
    <Box
      data-testid={`repository-stat-${item.key}`}
      data-state={item.state}
      // the hint opens on focus as well, so a keyboard reader reaches it
      tabIndex={item.hint ? 0 : undefined}
      sx={{
        borderRadius: 2,
        bgcolor: alpha(color, isDark ? 0.1 : 0.07),
        px: 2,
        py: 1.75,
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
            variant="h5"
            sx={{
              fontWeight: muted ? 500 : 700,
              lineHeight: 1.2,
              fontSize: muted ? { xs: '0.95rem', lg: '1rem' } : { xs: '1.4rem', lg: '1.5rem' },
              color: muted ? 'text.secondary' : color,
              fontStyle: muted ? 'italic' : 'normal',
              wordBreak: 'break-word',
            }}
          >
            {text}
          </Typography>
          {item.subtitle ? (
            <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
              {item.subtitle}
            </Typography>
          ) : null}
        </Box>
        <Box sx={{ color, opacity: 0.4, mt: 0.25, flexShrink: 0 }}>{TILE_ICONS[item.key]}</Box>
      </Stack>
    </Box>
  )
}

/** The info dialog's coloured card, on the theme palette so both modes work. */
function StatCard({ item, text }: StatProps) {
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const color = theme.palette[TONE_PALETTE[item.tone]].main
  const muted = item.state !== 'value'

  return withHint(
    item,
    <Card
      data-testid={`repository-stat-${item.key}`}
      data-state={item.state}
      tabIndex={item.hint ? 0 : undefined}
      elevation={0}
      sx={{
        bgcolor: alpha(color, isDark ? 0.16 : 0.09),
        cursor: item.hint ? 'help' : 'default',
      }}
    >
      <CardContent sx={{ py: 2 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          {CARD_ICONS[item.key]?.(color)}
          <Typography variant="caption" sx={{ color: 'text.secondary', fontWeight: 500 }}>
            {item.label}
          </Typography>
        </Box>
        <Typography
          variant="h6"
          sx={{
            fontWeight: muted ? 500 : 700,
            color: muted ? 'text.secondary' : color,
            fontStyle: muted ? 'italic' : 'normal',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {text}
        </Typography>
        {item.subtitle ? (
          <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
            {item.subtitle}
          </Typography>
        ) : null}
      </CardContent>
    </Card>
  )
}

/** The info dialog's outlined card for the counts and the span. */
function OutlinedStat({ item, text }: StatProps) {
  const muted = item.state !== 'value'
  return withHint(
    item,
    <Card
      variant="outlined"
      data-testid={`repository-stat-${item.key}`}
      data-state={item.state}
      tabIndex={item.hint ? 0 : undefined}
      sx={{ cursor: item.hint ? 'help' : 'default' }}
    >
      <CardContent sx={{ py: 1.5 }}>
        <Typography variant="caption" sx={{ color: 'text.secondary', display: 'block' }}>
          {item.label}
        </Typography>
        <Typography
          variant="h6"
          sx={{
            fontWeight: muted ? 500 : 600,
            color: muted ? 'text.secondary' : 'text.primary',
            fontStyle: muted ? 'italic' : 'normal',
            fontVariantNumeric: 'tabular-nums',
          }}
        >
          {text}
        </Typography>
      </CardContent>
    </Card>
  )
}

/**
 * The repository's size figures from the stored `storage` payload (#981),
 * in the archive header (`grid`) or the info dialog (`detail`). Reads
 * nothing live: the same figures the card shows, on Borg 1 and Borg 2
 * alike, with their provenance in the tooltip and an explicit state for
 * what is not there.
 */
export default function RepositoryStats({
  storage,
  archiveCount,
  archivesLoading = false,
  indexPendingKinds,
  variant = 'grid',
}: RepositoryStatsProps) {
  const { t } = useTranslation()
  const items = repositoryStatItems(t, { storage, archiveCount, indexPendingKinds, variant })
  const textOf = (item: RepositoryStatItem) =>
    item.key === 'archives' && archivesLoading ? (
      <Skeleton variant="text" width={40} sx={{ fontSize: '1.5rem' }} />
    ) : (
      stateText(t, item)
    )

  if (variant === 'grid') {
    return (
      <Box
        data-testid="repository-stats"
        data-variant="grid"
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 2,
        }}
      >
        {items.map((item) => (
          <StatTile key={item.key} item={item} text={textOf(item)} />
        ))}
      </Box>
    )
  }

  const coloured = items.slice(0, 3)
  const outlined = items.slice(3)
  return (
    <Box data-testid="repository-stats" data-variant="detail">
      <Typography variant="h6" sx={{ fontWeight: 600, mt: 1, mb: 1.5 }}>
        {t('repositoryStats.heading')}
      </Typography>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          gap: 2,
          mb: 2,
        }}
      >
        {coloured.map((item) => (
          <StatCard key={item.key} item={item} text={textOf(item)} />
        ))}
      </Box>
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
          gap: 2,
        }}
      >
        {outlined.map((item) => (
          <OutlinedStat key={item.key} item={item} text={textOf(item)} />
        ))}
      </Box>
    </Box>
  )
}
