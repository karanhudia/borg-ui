import { useMemo } from 'react'
import { Box, Button, Skeleton, Typography, alpha, useTheme } from '@mui/material'
import {
  CalendarRange,
  Clock,
  CornerDownRight,
  Download,
  Info,
  RefreshCw,
  RotateCcw,
  User,
  Zap,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { ActivityItem } from '../Activity'
import type { ActionButton } from '../../components/RowActions'
import EmptyStateCard from '../../components/EmptyStateCard'
import StatusBadge from '../../components/StatusBadge'
import RunEntry from './RunEntry'
import { ENTRY_COLUMNS, metaGridSx, umbrellaColor } from './entryGrid'
import { formatDurationSeconds, parseBackendDate } from '../../utils/dateUtils'
import {
  ACTIVE_STATUSES,
  clusterRuns,
  dayLabel,
  flattenRuns,
  groupByDay,
  repositoryCount,
  runTime,
  type Cluster,
  type UmbrellaKind,
} from './runs'

interface ActivityTimelineProps {
  items: ActivityItem[]
  loading: boolean
  actions: ActionButton<ActivityItem>[]
  showRepository: boolean
  getKey: (item: ActivityItem) => string
  hasMore?: boolean
  loadingMore?: boolean
  onLoadMore?: () => void
}

const UMBRELLA_ICONS: Record<UmbrellaKind, typeof User> = {
  plan: CalendarRange,
  schedule: Clock,
  manual: User,
  import: Download,
  followup: CornerDownRight,
  reconcile: RefreshCw,
  retry: RotateCcw,
  other: Zap,
}

function clusterStatus(items: ActivityItem[]): string {
  if (items.some((item) => ACTIVE_STATUSES.has(item.status))) return 'running'
  if (items.some((item) => item.status === 'failed')) return 'failed'
  if (items.some((item) => item.status === 'completed_with_warnings'))
    return 'completed_with_warnings'
  if (items.every((item) => item.status === 'cancelled')) return 'cancelled'
  if (items.every((item) => item.status === 'skipped')) return 'skipped'
  return 'completed'
}

function clusterSpan(items: ActivityItem[]): string | null {
  let start = Infinity
  let end = -Infinity
  for (const item of items) {
    if (!item.started_at) continue
    if (!item.completed_at) return null
    start = Math.min(start, parseBackendDate(item.started_at).getTime())
    end = Math.max(end, parseBackendDate(item.completed_at).getTime())
  }
  return Number.isFinite(start) && Number.isFinite(end)
    ? formatDurationSeconds(Math.max(Math.round((end - start) / 1000), 0))
    : null
}

// Every run sits under the umbrella that started it: a plan run, a
// schedule firing, a manual click. The band carries the umbrella's name,
// counts, a rolled-up status and the span; members read top to bottom in
// the order they happened and repeat nothing the band says.
function UmbrellaBand({
  cluster,
  actions,
  showRepository,
  getKey,
}: {
  cluster: Cluster
  actions: ActionButton<ActivityItem>[]
  showRepository: boolean
  getKey: (item: ActivityItem) => string
  hasMore?: boolean
  loadingMore?: boolean
  onLoadMore?: () => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const time = runTime(cluster.items[0])
  const accent = umbrellaColor(theme, cluster.umbrella.kind)
  const Icon = UMBRELLA_ICONS[cluster.umbrella.kind]
  const steps = flattenRuns(cluster.items)
  const status = clusterStatus(steps)
  const span = clusterSpan(steps)
  const repositories = repositoryCount(
    cluster.items.filter((item) => item.type !== 'script_execution')
  )
  const many = cluster.items.length > 1
  return (
    <Box
      data-testid="umbrella-band"
      data-umbrella={cluster.umbrella.kind}
      sx={{
        position: 'relative',
        my: 0.75,
        borderRadius: 2,
        // A ring, not a border: a border would push the members' content
        // edge one pixel off the entries outside the band.
        boxShadow: `inset 0 0 0 1px ${alpha(accent, 0.22)}`,
        bgcolor: alpha(accent, cluster.umbrella.kind === 'manual' ? 0.025 : 0.035),
        pb: 0.5,
      }}
    >
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: ENTRY_COLUMNS,
          columnGap: 1,
          // Top-aligned, so a title that wraps on a phone keeps the time
          // and the icon on its first line.
          alignItems: 'start',
          pt: 1.25,
          pb: 0.25,
          pr: 1,
        }}
      >
        <Typography
          variant="body2"
          sx={{
            color: 'text.secondary',
            fontVariantNumeric: 'tabular-nums',
            textAlign: 'right',
            pr: 0.5,
            lineHeight: '20px',
          }}
        >
          {time ? time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : ''}
        </Typography>
        <Box sx={{ display: 'flex', justifyContent: 'center' }}>
          <Box
            sx={{
              position: 'relative',
              zIndex: 1,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              width: 20,
              height: 20,
              borderRadius: '50%',
              color: accent,
              bgcolor: 'background.paper',
              boxShadow: `0 0 0 2px ${alpha(accent, 0.25)}`,
            }}
          >
            <Icon size={12} />
          </Box>
        </Box>
        <Box
          sx={{
            display: 'flex',
            flexWrap: 'wrap',
            alignItems: 'center',
            columnGap: 1,
            rowGap: 0.5,
            minWidth: 0,
          }}
        >
          <Typography
            variant="body2"
            sx={{ fontWeight: 700, color: accent, lineHeight: '20px' }}
            noWrap
          >
            {cluster.umbrella.label}
          </Typography>
          {many && (
            <Typography variant="body2" sx={{ color: 'text.secondary' }} noWrap>
              {[
                repositories > 0 && t('activity.planRun.repositories', { count: repositories }),
                t('activity.planRun.members', { count: cluster.items.length }),
              ]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
          )}
          {many && (
            <Box sx={metaGridSx(actions.length)}>
              <Box sx={{ minWidth: 0 }}>
                <StatusBadge status={status} />
              </Box>
              <Box />
              <Typography
                variant="body2"
                sx={{
                  color: 'text.secondary',
                  fontVariantNumeric: 'tabular-nums',
                  textAlign: 'right',
                }}
              >
                {span ?? ''}
              </Typography>
              <Box />
            </Box>
          )}
        </Box>
      </Box>
      {cluster.items.map((item) => (
        <RunEntry
          key={getKey(item)}
          item={item}
          actions={actions}
          showRepository={showRepository}
        />
      ))}
    </Box>
  )
}

// The same shape the list settles into: a day label, then bands of a
// header row and members on the rail, each with the shared meta columns
// on the right. Nothing jumps when the rows arrive.
function SkeletonRow({ header }: { header?: boolean }) {
  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: ENTRY_COLUMNS,
        columnGap: 1,
        alignItems: 'center',
        pr: 1,
        py: header ? 0.75 : 1.25,
      }}
    >
      <Skeleton width={40} height={20} sx={{ justifySelf: 'end', mr: 0.5 }} />
      <Skeleton
        variant="circular"
        width={header ? 20 : 10}
        height={header ? 20 : 10}
        sx={{ mx: 'auto', position: 'relative', zIndex: 1 }}
      />
      <Box sx={{ display: 'flex', alignItems: 'center', columnGap: 1, minWidth: 0 }}>
        {header ? (
          <Skeleton width={220} height={20} />
        ) : (
          <>
            <Box sx={{ display: 'grid', rowGap: 0.5 }}>
              <Skeleton width={180} height={20} />
              <Skeleton width={300} height={14} />
            </Box>
            <Skeleton width={96} height={24} sx={{ borderRadius: 999, ml: 1 }} />
            <Box sx={{ ...metaGridSx(3), display: { xs: 'none', md: 'grid' } }}>
              <Skeleton width={90} height={24} sx={{ borderRadius: 1 }} />
              <Skeleton width={56} height={24} sx={{ borderRadius: 1 }} />
              <Skeleton width={64} height={20} sx={{ justifySelf: 'end' }} />
              <Box sx={{ display: 'flex', gap: 1, justifyContent: 'flex-end' }}>
                {[0, 1, 2].map((index) => (
                  <Skeleton key={index} variant="circular" width={18} height={18} />
                ))}
              </Box>
            </Box>
          </>
        )}
      </Box>
    </Box>
  )
}

function TimelineSkeleton() {
  return (
    <Box
      data-testid="activity-skeleton"
      aria-busy
      sx={{
        position: 'relative',
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 12,
          bottom: 12,
          left: { xs: 65, md: 77 },
          width: 2,
          bgcolor: 'divider',
          opacity: 0.7,
        },
      }}
    >
      <Skeleton width={140} height={14} sx={{ ml: { xs: '84px', md: '96px' }, mb: 1 }} />
      {[2, 1, 1].map((members, index) => (
        <Box
          key={index}
          sx={{
            my: 0.75,
            borderRadius: 2,
            // As faint as the real bands' ring; the divider itself reads as a
            // hard border around a block this size.
            boxShadow: (theme) => `inset 0 0 0 1px ${alpha(theme.palette.text.primary, 0.08)}`,
            pb: 0.5,
          }}
        >
          <SkeletonRow header />
          {Array.from({ length: members }, (_, member) => (
            <SkeletonRow key={member} />
          ))}
        </Box>
      ))}
    </Box>
  )
}

export default function ActivityTimeline({
  items,
  loading,
  actions,
  showRepository,
  getKey,
  hasMore = false,
  loadingMore = false,
  onLoadMore,
}: ActivityTimelineProps) {
  const { t } = useTranslation()
  const days = useMemo(
    () => groupByDay(items).map((group) => ({ ...group, clusters: clusterRuns(group.items, t) })),
    [items, t]
  )

  if (loading && items.length === 0) return <TimelineSkeleton />

  if (items.length === 0) {
    return (
      <EmptyStateCard
        icon={<Info size={48} />}
        title={t('activity.empty.title')}
        description={t('activity.empty.message')}
      />
    )
  }

  return (
    <Box
      role="list"
      aria-label={t('activity.title')}
      sx={{
        position: 'relative',
        // One rail down the whole ledger, through day groups and umbrella
        // bands alike; every status dot sits on it. Time column, gap, half
        // the node column.
        '&::before': {
          content: '""',
          position: 'absolute',
          top: 12,
          bottom: 12,
          left: { xs: 65, md: 77 },
          width: 2,
          bgcolor: 'divider',
          opacity: 0.7,
        },
      }}
    >
      {days.map((group) => (
        <Box key={group.key} data-testid="activity-day" sx={{ mb: 2 }}>
          <Typography
            variant="overline"
            component="h2"
            sx={{
              display: 'block',
              color: 'text.secondary',
              letterSpacing: '0.08em',
              fontSize: '0.6875rem',
              lineHeight: 1,
              // Time column, gap, rail, gap: the label sits on the content edge.
              pl: { xs: '84px', md: '96px' },
              mb: 0.5,
            }}
          >
            {dayLabel(group.date, t)}
          </Typography>
          <Box>
            {group.clusters.map((cluster) => (
              <UmbrellaBand
                key={cluster.key}
                cluster={cluster}
                actions={actions}
                showRepository={showRepository}
                getKey={getKey}
              />
            ))}
          </Box>
        </Box>
      ))}
      {hasMore && (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 1 }}>
          <Button variant="outlined" size="small" onClick={onLoadMore} disabled={loadingMore}>
            {t(loadingMore ? 'activity.actions.loadingMore' : 'activity.actions.loadMore')}
          </Button>
        </Box>
      )}
    </Box>
  )
}
