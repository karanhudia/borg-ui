import { Box, Stack, Tooltip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { differenceInDays } from 'date-fns'
import {
  AlertTriangle,
  CheckCircle2,
  MinusCircle,
  Pause,
  Play,
  RotateCw,
  XCircle,
} from 'lucide-react'
import { formatDateTimeFull } from '../../utils/dateUtils'
import { useT } from './tokens'

export function PulseDot({ color, glow }: { color: string; glow: string }) {
  return (
    <Box sx={{ position: 'relative', width: 8, height: 8, flexShrink: 0 }}>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          bgcolor: color,
          opacity: 0.6,
          animation: 'pulse-ring 2.4s ease-in-out infinite',
          '@keyframes pulse-ring': {
            '0%': { transform: 'scale(1)', opacity: 0.6 },
            '60%': { transform: 'scale(2.2)', opacity: 0 },
            '100%': { transform: 'scale(1)', opacity: 0 },
          },
          boxShadow: `0 0 8px ${glow}`,
        }}
      />
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          borderRadius: '50%',
          bgcolor: color,
          boxShadow: `0 0 6px ${color}`,
        }}
      />
    </Box>
  )
}

type DimHealth = { backup: string; check: string; compact: string; restore?: string }
type DimStatusItem = {
  label: string
  status: string
  value: string
  tooltip?: string
}

const DIM_STATUS: Record<string, { color: string }> = {
  healthy: { color: '#22c55e' },
  warning: { color: '#f59e0b' },
  critical: { color: '#ef4444' },
  unknown: { color: '#475569' },
}

function dimSince(dt: string | null, t: (key: string) => string): string {
  if (!dt) return t('common.never')
  const d = differenceInDays(new Date(), new Date(dt))
  if (d < 1) return t('dashboard.activityTimeline.today')
  if (d < 7) return `${d}d ago`
  if (d < 30) return `${Math.round(d / 7)}w ago`
  return `${Math.round(d / 30)}mo ago`
}

function dimValue(value: string | null | undefined, t: (key: string) => string): string {
  return value ?? t('common.unknown')
}

function dimTimestampTooltip(dt: string | null): string | undefined {
  return dt ? formatDateTimeFull(dt) : undefined
}

function restoreDimValue(
  latestStatus: string | null | undefined,
  lastRestoreCheck: string | null,
  configured: boolean | undefined,
  t: (key: string) => string
): string {
  if (latestStatus === 'failed') return t('status.failed')
  if (latestStatus === 'completed_with_warnings') return t('status.completedWithWarnings')
  if (latestStatus === 'needs_backup') return t('status.needsBackup')
  if (latestStatus === 'running') return t('status.running')
  if (latestStatus === 'pending') return t('status.pending')
  if (latestStatus === 'cancelled') return t('status.cancelled')
  if (!configured && !lastRestoreCheck) return t('scheduledChecks.notConfigured')
  return dimSince(lastRestoreCheck, t)
}

function DimIcon({ status, size = 11 }: { status: string; size?: number }) {
  const { color } = DIM_STATUS[status] ?? DIM_STATUS.unknown
  if (status === 'healthy') return <CheckCircle2 size={size} color={color} />
  if (status === 'warning') return <AlertTriangle size={size} color={color} />
  if (status === 'critical') return <XCircle size={size} color={color} />
  return <MinusCircle size={size} color={color} />
}

/**
 * DimStatusGrid — compact health footer for repository operation dimensions.
 * Shows icon + label + time-since for each operation dimension.
 */
export function DimStatusGrid({
  mode,
  dim,
  lastBackup,
  lastCheck,
  lastCompact,
  lastRestoreCheck,
  latestRestoreCheckStatus,
  latestRestoreCheckError,
  restoreCheckConfigured,
}: {
  mode: 'full' | 'observe'
  dim: DimHealth | undefined
  lastBackup: string | null
  lastCheck: string | null
  lastCompact: string | null
  lastRestoreCheck: string | null
  latestRestoreCheckStatus?: string | null
  latestRestoreCheckError?: string | null
  restoreCheckConfigured?: boolean
}) {
  const T = useT()
  const { t } = useTranslation()

  const restoreItem: DimStatusItem = {
    label: t('dashboard.repositoryHealth.dimensionLabels.restore'),
    status: dim?.restore ?? 'unknown',
    value: restoreDimValue(latestRestoreCheckStatus, lastRestoreCheck, restoreCheckConfigured, t),
    tooltip: latestRestoreCheckError ?? dimTimestampTooltip(lastRestoreCheck),
  }

  const items: DimStatusItem[] =
    mode === 'observe'
      ? [
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.freshness'),
            status: dim?.backup ?? 'unknown',
            value: dimSince(lastBackup, t),
            tooltip: dimTimestampTooltip(lastBackup),
          },
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.archives'),
            status: dim?.compact ?? 'unknown',
            value: t('dashboard.repositoryHealth.archiveCountShort', {
              count: Number(lastCompact ?? 0),
            }),
          },
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.check'),
            status: dim?.check ?? 'unknown',
            value:
              dim?.check === 'unknown'
                ? t('scheduledChecks.notConfigured')
                : dimSince(lastCheck, t),
            tooltip: dim?.check === 'unknown' ? undefined : dimTimestampTooltip(lastCheck),
          },
          restoreItem,
        ]
      : [
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.backup'),
            status: dim?.backup ?? 'unknown',
            value: dimSince(lastBackup, t),
            tooltip: dimTimestampTooltip(lastBackup),
          },
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.check'),
            status: dim?.check ?? 'unknown',
            value: dimSince(lastCheck, t),
            tooltip: dimTimestampTooltip(lastCheck),
          },
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.compact'),
            status: dim?.compact ?? 'unknown',
            value: dimSince(lastCompact, t),
            tooltip: dimTimestampTooltip(lastCompact),
          },
          restoreItem,
        ]

  return (
    <Box
      sx={{
        display: 'grid',
        gridTemplateColumns: `repeat(${items.length}, minmax(0, 1fr))`,
        width: '100%',
        gap: 0,
      }}
    >
      {items.map((item, i) => {
        const { color } = DIM_STATUS[item.status] ?? DIM_STATUS.unknown
        return (
          <Box
            key={item.label}
            sx={{
              minWidth: 0,
              pl: i > 0 ? 0.8 : 0,
              pr: i < items.length - 1 ? 0.8 : 0,
              borderLeft: i > 0 ? `1px solid ${T.border}` : 'none',
            }}
          >
            {/* Label row */}
            <Stack direction="row" spacing={0.4} alignItems="center" sx={{ mb: 0.2, minWidth: 0 }}>
              <DimIcon status={item.status} size={9} />
              <Typography
                sx={{
                  fontSize: '0.49rem',
                  fontWeight: 600,
                  color: T.textDim,
                  letterSpacing: 0.8,
                  textTransform: 'uppercase',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {item.label}
              </Typography>
            </Stack>
            {/* Time value */}
            <Tooltip title={item.tooltip ?? ''} arrow placement="top">
              <Typography
                sx={{
                  cursor: item.tooltip ? 'help' : 'default',
                  display: 'inline-block',
                  fontFamily: T.mono,
                  fontSize: '0.58rem',
                  fontWeight: 600,
                  color,
                  lineHeight: 1,
                  maxWidth: '100%',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {dimValue(item.value, t)}
              </Typography>
            </Tooltip>
          </Box>
        )
      })}
    </Box>
  )
}

/**
 * ScheduleBadge — always-visible schedule state indicator.
 *
 * States:
 *   no schedule   → "manual"  muted text (no pill)
 *   paused         → amber pill  "paused"
 *   active, no ETA → blue pill   "scheduled"
 *   active, future → indigo pill "▶ 2h / 4d"  (pulses when < 1h)
 */
export function ScheduleBadge({
  nextRun,
  hasSchedule,
  scheduleEnabled,
  scheduleName,
  scheduleTimezone,
  nowMs,
}: {
  nextRun: string | null
  hasSchedule: boolean
  scheduleEnabled: boolean
  scheduleName: string | null
  scheduleTimezone?: string | null
  nowMs: number
}) {
  const T = useT()
  const { t } = useTranslation()
  const timezoneLabel = scheduleTimezone || 'UTC'

  // ── No schedule at all ─────────────────────────────────────────────
  if (!hasSchedule) {
    return (
      <Typography
        title={t('dashboard.scheduleBadge.noSchedule')}
        sx={{
          fontFamily: T.mono,
          fontSize: '0.58rem',
          fontWeight: 500,
          color: T.textDim,
          letterSpacing: 0.5,
          userSelect: 'none',
        }}
      >
        {t('dashboard.scheduleBadge.manual')}
      </Typography>
    )
  }

  // ── Schedule exists but disabled ────────────────────────────────────
  if (!scheduleEnabled) {
    return (
      <Stack
        direction="row"
        spacing={0.4}
        alignItems="center"
        title={
          scheduleName
            ? `${t('dashboard.scheduleBadge.pausedTitle', { name: scheduleName })} (${timezoneLabel})`
            : `${t('dashboard.scheduleBadge.pausedTitleGeneric')} (${timezoneLabel})`
        }
        sx={{
          px: 0.8,
          py: 0.2,
          bgcolor: T.amberDim,
          border: `1px solid ${T.amber}35`,
          borderRadius: '99px',
          flexShrink: 0,
        }}
      >
        <Pause size={9} color={T.amber} />
        <Typography
          sx={{
            fontFamily: T.mono,
            fontSize: '0.6rem',
            fontWeight: 600,
            color: T.amber,
            lineHeight: 1,
          }}
        >
          {t('dashboard.scheduleBadge.paused')}
        </Typography>
      </Stack>
    )
  }

  // ── Active schedule, no next_run yet calculated ─────────────────────
  if (!nextRun) {
    return (
      <Stack
        direction="row"
        spacing={0.4}
        alignItems="center"
        title={`${scheduleName ?? t('dashboard.scheduleBadge.scheduled')} (${timezoneLabel})`}
        sx={{
          px: 0.8,
          py: 0.2,
          bgcolor: T.blueDim,
          border: `1px solid ${T.blue}35`,
          borderRadius: '99px',
          flexShrink: 0,
        }}
      >
        <RotateCw size={9} color={T.blue} />
        <Typography
          sx={{
            fontFamily: T.mono,
            fontSize: '0.6rem',
            fontWeight: 600,
            color: T.blue,
            lineHeight: 1,
          }}
        >
          {t('dashboard.scheduleBadge.scheduled')}
        </Typography>
      </Stack>
    )
  }

  // ── Active schedule with a known next run ───────────────────────────
  const msAway = new Date(nextRun).getTime() - nowMs
  const hoursAway = msAway / 1000 / 60 / 60
  const isImminent = hoursAway > 0 && hoursAway < 1

  const label =
    msAway <= 0
      ? t('dashboard.scheduleBadge.now')
      : hoursAway < 1
        ? `${Math.round(hoursAway * 60)}m`
        : hoursAway < 24
          ? `${Math.floor(hoursAway)}h`
          : `${Math.floor(hoursAway / 24)}d`

  return (
    <Stack
      direction="row"
      spacing={0.4}
      alignItems="center"
      title={
        scheduleName
          ? `${t('dashboard.scheduleBadge.nextRunTitle', { name: scheduleName, label })} (${timezoneLabel})`
          : `${t('dashboard.scheduleBadge.nextRunTitleGeneric', { label })} (${timezoneLabel})`
      }
      sx={{
        px: 0.8,
        py: 0.2,
        bgcolor: T.indigoDim,
        border: `1px solid ${T.indigo}35`,
        borderRadius: '99px',
        flexShrink: 0,
        ...(isImminent && {
          animation: 'badge-pulse 2s ease-in-out infinite',
          '@keyframes badge-pulse': {
            '0%, 100%': { boxShadow: `0 0 0 0 ${T.indigo}50` },
            '50%': { boxShadow: `0 0 0 5px ${T.indigo}00` },
          },
        }),
      }}
    >
      <Play size={9} color={T.indigo} />
      <Typography
        sx={{
          fontFamily: T.mono,
          fontSize: '0.6rem',
          fontWeight: 700,
          color: T.indigo,
          lineHeight: 1,
        }}
      >
        {label}
      </Typography>
    </Stack>
  )
}
