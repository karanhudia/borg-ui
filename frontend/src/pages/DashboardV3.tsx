/**
 * DashboardV3 — "Void" ops command center
 *
 * Design system: Real-Time Monitoring × Modern Cinema (ui-ux-pro-max)
 * Palette:       Glass surface · Hairline border
 * Accent:        Indigo #6366f1 · Green #22c55e · Amber #f59e0b · Red #ef4444
 * Typography:    JetBrains Mono for all numeric / data values
 * Layout:        Bento grid (asymmetric) + full-width activity timeline SVG
 *
 * Padding note:  The Layout already provides Container maxWidth="xl" + p:3.
 *                This component adds NO extra outer padding or background.
 */

import React from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { Box, Skeleton, Alert, Button, Stack, Typography, Chip, Tooltip } from '@mui/material'
import {
  XCircle,
  HardDrive,
  Activity,
  Cpu,
  ArrowRight,
  Server,
  CheckCircle2,
  AlertTriangle,
  MinusCircle,
  Play,
  Pause,
  RotateCw,
} from 'lucide-react'
import { formatDistanceToNow, differenceInDays, startOfDay, addDays, format } from 'date-fns'
import { useTheme } from '../context/ThemeContext'
import { useAnalytics } from '../hooks/useAnalytics'
import { dashboardAPI } from '../services/api'
import { formatDateTimeFull } from '../utils/dateUtils'

// ─── Types ────────────────────────────────────────────────────────────────────

interface DashboardOverview {
  summary: {
    total_repositories: number
    local_repositories: number
    ssh_repositories: number
    active_schedules: number
    total_schedules: number
    success_rate_30d: number
    successful_jobs_30d: number
    failed_jobs_30d: number
    total_jobs_30d: number
  }
  storage: {
    total_size: string
    total_size_bytes: number
    total_archives: number
    average_dedup_ratio: number | null
    breakdown: Array<{ name: string; size: string; size_bytes: number; percentage: number }>
  }
  repository_health: Array<{
    id: number
    name: string
    type: string
    mode: 'full' | 'observe'
    last_backup: string | null
    last_check: string | null
    last_compact: string | null
    last_restore_check: string | null
    archive_count: number
    total_size: string
    health_status: 'healthy' | 'warning' | 'critical'
    warnings: string[]
    next_run: string | null
    has_schedule: boolean
    schedule_enabled: boolean
    schedule_name: string | null
    schedule_timezone?: string | null
    restore_check_configured?: boolean
    latest_restore_check_status?: string | null
    latest_restore_check_error?: string | null
    dimension_health: {
      backup: 'healthy' | 'warning' | 'critical' | 'unknown'
      check: 'healthy' | 'warning' | 'critical' | 'unknown'
      compact: 'healthy' | 'warning' | 'critical' | 'unknown'
      restore?: 'healthy' | 'warning' | 'critical' | 'unknown'
    }
  }>
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  upcoming_tasks: Array<any>
  activity_feed: Array<{
    id: number
    type: string
    status: string
    repository: string
    timestamp: string
    message: string
    error: string | null
  }>
  system_metrics: {
    cpu_usage: number
    cpu_count: number
    memory_usage: number
    memory_total: number
    memory_available: number
    disk_usage: number
    disk_total: number
    disk_free: number
  }
}

// ─── Design tokens ────────────────────────────────────────────────────────────

const makeT = (isDark: boolean) => ({
  bgCard: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.03)',
  bgCardHover: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.05)',
  border: isDark ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.1)',
  borderHover: isDark ? 'rgba(255,255,255,0.18)' : 'rgba(0,0,0,0.22)',
  textPrimary: isDark ? '#e2e8f0' : '#1e293b',
  textMuted: isDark ? '#94a3b8' : '#64748b',
  textDim: isDark ? '#64748b' : '#94a3b8',
  green: '#22c55e',
  greenDim: isDark ? 'rgba(34,197,94,0.1)' : 'rgba(34,197,94,0.12)',
  greenGlow: 'rgba(34,197,94,0.25)',
  amber: '#f59e0b',
  amberDim: isDark ? 'rgba(245,158,11,0.1)' : 'rgba(245,158,11,0.12)',
  red: '#ef4444',
  redDim: isDark ? 'rgba(239,68,68,0.1)' : 'rgba(239,68,68,0.12)',
  blue: '#3b82f6',
  blueDim: isDark ? 'rgba(59,130,246,0.1)' : 'rgba(59,130,246,0.12)',
  indigo: '#6366f1',
  indigoDim: isDark ? 'rgba(99,102,241,0.12)' : 'rgba(99,102,241,0.1)',
  mono: '"JetBrains Mono","Fira Code","Cascadia Code",ui-monospace,monospace',
  radius: '14px',
  // SVG / internal
  svgTrack: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.1)',
  colShade: isDark ? 'rgba(255,255,255,0.015)' : 'rgba(0,0,0,0.02)',
  barBg: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.07)',
  repoBadgeBg: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.05)',
  hoverBg: isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.04)',
  todayCol: isDark ? 'rgba(99,102,241,0.06)' : 'rgba(99,102,241,0.08)',
  axisLabel: isDark ? '#475569' : '#94a3b8',
  insetLine: isDark ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.06)',
})

type Tokens = ReturnType<typeof makeT>

const TokenContext = React.createContext<Tokens>(makeT(true))
const useT = () => React.useContext(TokenContext)

const STATUS = {
  healthy: { color: '#22c55e', dim: 'rgba(34,197,94,0.10)', glow: 'rgba(34,197,94,0.3)' },
  warning: { color: '#f59e0b', dim: 'rgba(245,158,11,0.13)', glow: 'rgba(245,158,11,0.3)' },
  critical: { color: '#ef4444', dim: 'rgba(239,68,68,0.15)', glow: 'rgba(239,68,68,0.3)' },
  unknown: { color: '#64748b', dim: 'rgba(100,116,139,0.05)', glow: 'transparent' },
}

const SEG_COLORS = ['#6366f1', '#3b82f6', '#22c55e', '#f59e0b', '#ec4899']

// Job type → chart color
const JOB_COLOR: Record<string, string> = {
  backup: '#22c55e',
  check: '#3b82f6',
  compact: '#6366f1',
  restore: '#f59e0b',
  prune: '#ec4899',
}

// ─── Sub-components ───────────────────────────────────────────────────────────

function SuccessDonut({ rate, good, total }: { rate: number; good: number; total: number }) {
  const T = useT()
  const size = 148,
    sw = 13,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const filled = (rate / 100) * circ
  const color = rate >= 90 ? T.green : rate >= 70 ? T.amber : T.red
  return (
    <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
      <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={T.svgTrack}
          strokeWidth={sw}
        />
        <circle
          cx={size / 2}
          cy={size / 2}
          r={r}
          fill="none"
          stroke={color}
          strokeWidth={sw}
          strokeDasharray={`${filled} ${circ}`}
          strokeLinecap="round"
          style={{
            filter: `drop-shadow(0 0 8px ${color}80)`,
            transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)',
          }}
        />
      </svg>
      <Box
        sx={{
          position: 'absolute',
          inset: 0,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <Typography
          sx={{ fontFamily: T.mono, fontSize: '1.75rem', fontWeight: 700, color, lineHeight: 1 }}
        >
          {rate.toFixed(0)}%
        </Typography>
        <Typography sx={{ fontSize: '0.6rem', color: T.textMuted, mt: 0.5, letterSpacing: 1 }}>
          {good}/{total} OK
        </Typography>
      </Box>
    </Box>
  )
}

function StorageDonut({
  breakdown,
  totalSize,
  totalArchives,
}: {
  breakdown: Array<{ name: string; size: string; size_bytes: number; percentage: number }>
  totalSize: string
  totalArchives: number
}) {
  const T = useT()
  const { t } = useTranslation()
  const size = 148,
    sw = 16,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const slices = breakdown.slice(0, 5)
  const segments = slices.reduce<
    Array<{
      s: (typeof slices)[number]
      arc: number
      offset: number
      color: string
    }>
  >((acc, s, i) => {
    const previous = acc[acc.length - 1]
    const arc = (s.percentage / 100) * circ
    acc.push({
      s,
      arc,
      offset: previous ? previous.offset + previous.arc : 0,
      color: SEG_COLORS[i],
    })
    return acc
  }, [])

  return (
    <Box>
      <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={T.svgTrack}
            strokeWidth={sw}
          />
          {segments.map((seg, i) => (
            <circle
              key={i}
              cx={size / 2}
              cy={size / 2}
              r={r}
              fill="none"
              stroke={seg.color}
              strokeWidth={sw}
              strokeDasharray={`${Math.max(seg.arc - 2, 0)} ${circ}`}
              strokeDashoffset={-seg.offset}
              strokeLinecap="butt"
              style={{
                filter: `drop-shadow(0 0 6px ${seg.color}70)`,
                transition: 'stroke-dasharray 0.8s cubic-bezier(0.4,0,0.2,1)',
              }}
            />
          ))}
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography
            sx={{
              fontFamily: T.mono,
              fontSize: '1.05rem',
              fontWeight: 800,
              color: T.textPrimary,
              lineHeight: 1,
            }}
          >
            {totalSize}
          </Typography>
          <Typography
            sx={{
              fontSize: '0.55rem',
              color: T.textMuted,
              mt: 0.5,
              letterSpacing: 1.5,
              textTransform: 'uppercase',
            }}
          >
            {t('dashboard.storageDonut.archivesCount', { count: totalArchives })}
          </Typography>
        </Box>
      </Box>
      <Box sx={{ mt: 1.5, display: 'flex', flexDirection: 'column', gap: 0.65 }}>
        {slices.map((s, i) => (
          <Stack key={s.name} direction="row" alignItems="center" spacing={0.75}>
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                bgcolor: SEG_COLORS[i],
                boxShadow: `0 0 4px ${SEG_COLORS[i]}80`,
                flexShrink: 0,
              }}
            />
            <Typography
              sx={{
                fontSize: '0.65rem',
                color: T.textMuted,
                flex: 1,
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {s.name}
            </Typography>
            <Typography
              sx={{ fontFamily: T.mono, fontSize: '0.65rem', color: T.textPrimary, flexShrink: 0 }}
            >
              {s.percentage}%
            </Typography>
          </Stack>
        ))}
        {slices.length === 0 && (
          <Typography sx={{ fontSize: '0.7rem', color: T.textMuted, textAlign: 'center', py: 1 }}>
            {t('dashboard.storageDonut.noData')}
          </Typography>
        )}
      </Box>
    </Box>
  )
}

function ArcGauge({
  value,
  color,
  label,
  sub,
}: {
  value: number
  color: string
  label: string
  sub?: string
}) {
  const T = useT()
  const size = 52,
    sw = 5,
    r = (size - sw) / 2
  const circ = 2 * Math.PI * r
  const filled = (Math.min(value, 100) / 100) * circ
  return (
    <Box sx={{ textAlign: 'center' }}>
      <Box sx={{ position: 'relative', width: size, height: size, mx: 'auto' }}>
        <svg width={size} height={size} style={{ transform: 'rotate(-90deg)' }}>
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={T.svgTrack}
            strokeWidth={sw}
          />
          <circle
            cx={size / 2}
            cy={size / 2}
            r={r}
            fill="none"
            stroke={color}
            strokeWidth={sw}
            strokeDasharray={`${filled} ${circ}`}
            strokeLinecap="round"
            style={{
              filter: `drop-shadow(0 0 4px ${color}60)`,
              transition: 'stroke-dasharray 0.7s ease',
            }}
          />
        </svg>
        <Box
          sx={{
            position: 'absolute',
            inset: 0,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Typography
            sx={{ fontFamily: T.mono, fontSize: '0.62rem', fontWeight: 700, color: T.textPrimary }}
          >
            {value.toFixed(0)}%
          </Typography>
        </Box>
      </Box>
      <Typography sx={{ fontSize: '0.62rem', fontWeight: 600, color: T.textMuted, mt: 0.5 }}>
        {label}
      </Typography>
      {sub && (
        <Typography sx={{ fontSize: '0.58rem', color: T.textDim, mt: 0.15 }}>{sub}</Typography>
      )}
    </Box>
  )
}

function PulseDot({ color, glow }: { color: string; glow: string }) {
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
function DimStatusGrid({
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
          {
            label: t('dashboard.repositoryHealth.dimensionLabels.restore'),
            status: dim?.restore ?? 'unknown',
            value: restoreDimValue(
              latestRestoreCheckStatus,
              lastRestoreCheck,
              restoreCheckConfigured,
              t
            ),
            tooltip: latestRestoreCheckError ?? dimTimestampTooltip(lastRestoreCheck),
          },
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
function ScheduleBadge({
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

/**
 * Activity Timeline — SVG scatter plot
 * X axis: last 14 days
 * Y axis: time of day (0 – 24 h)
 * Each dot = one job event, colored by type; red border = failed
 */
function ActivityTimeline({ activities }: { activities: DashboardOverview['activity_feed'] }) {
  const T = useT()
  const { t } = useTranslation()
  const DAYS = 14
  const VB_W = 680,
    VB_H = 110
  const ML = 32,
    MR = 8,
    MT = 10,
    MB = 22
  const cW = VB_W - ML - MR // chart width
  const cH = VB_H - MT - MB // chart height
  const colW = cW / DAYS

  const today = startOfDay(new Date())

  // Map activities to (x, y) positions
  const dots = activities.flatMap((a) => {
    const date = new Date(a.timestamp)
    const dayAgo = differenceInDays(today, startOfDay(date))
    if (dayAgo >= DAYS || dayAgo < 0) return []
    const col = DAYS - 1 - dayAgo
    const x = ML + (col + 0.5) * colW
    const hourFrac = (date.getHours() * 60 + date.getMinutes()) / (24 * 60)
    const y = MT + hourFrac * cH
    const jobColor = a.status === 'failed' ? T.red : (JOB_COLOR[a.type] ?? T.textMuted)
    return [
      {
        x,
        y,
        color: jobColor,
        failed: a.status === 'failed',
        title: `${a.type} • ${a.repository} • ${format(date, 'HH:mm')}`,
      },
    ]
  })

  // Day column labels (show every 2nd to avoid crowding)
  const dayLabels = Array.from({ length: DAYS }, (_, i) => {
    const d = addDays(today, -(DAYS - 1 - i))
    return {
      x: ML + (i + 0.5) * colW,
      label: format(d, 'M/d'),
      show: i % 2 === 0 || i === DAYS - 1,
    }
  })

  // Hour guide lines
  const hours = [0, 6, 12, 18, 24]

  return (
    <Box>
      <svg
        viewBox={`0 0 ${VB_W} ${VB_H}`}
        style={{ width: '100%', height: 'auto', overflow: 'visible' }}
        aria-label={t('dashboard.activityTimeline.ariaLabel')}
      >
        {/* Alternating column shading */}
        {dayLabels.map(({ x }, i) =>
          i % 2 === 0 ? (
            <rect key={i} x={x - colW / 2} y={MT} width={colW} height={cH} fill={T.colShade} />
          ) : null
        )}

        {/* Hour guide lines */}
        {hours.map((h) => {
          const y = MT + (h / 24) * cH
          return (
            <g key={h}>
              <line x1={ML} y1={y} x2={ML + cW} y2={y} stroke={T.svgTrack} strokeWidth={1} />
              {h < 24 && (
                <text
                  x={ML - 4}
                  y={y + 4}
                  fontSize={8}
                  fill={T.axisLabel}
                  textAnchor="end"
                  fontFamily="ui-monospace,monospace"
                >
                  {h}h
                </text>
              )}
            </g>
          )
        })}

        {/* Today highlight column */}
        <rect x={ML + (DAYS - 1) * colW} y={MT} width={colW} height={cH} fill={T.todayCol} rx={2} />

        {/* Activity dots */}
        {dots.map((d, i) => (
          <g key={i}>
            {/* Glow halo for failed */}
            {d.failed && <circle cx={d.x} cy={d.y} r={7} fill={d.color} opacity={0.2} />}
            <circle
              cx={d.x}
              cy={d.y}
              r={4}
              fill={d.color}
              stroke={d.failed ? 'rgba(255,255,255,0.4)' : 'none'}
              strokeWidth={d.failed ? 1 : 0}
              style={{ filter: `drop-shadow(0 0 4px ${d.color}90)` }}
            >
              <title>{d.title}</title>
            </circle>
          </g>
        ))}

        {/* Day labels */}
        {dayLabels.map(({ x, label, show }, i) =>
          show ? (
            <text
              key={i}
              x={x}
              y={VB_H - 4}
              fontSize={8}
              fill={T.axisLabel}
              textAnchor="middle"
              fontFamily="ui-monospace,monospace"
            >
              {label}
            </text>
          ) : null
        )}

        {/* "Today" label */}
        <text
          x={ML + (DAYS - 0.5) * colW}
          y={MT - 4}
          fontSize={8}
          fill={T.indigo}
          textAnchor="middle"
          fontFamily="ui-monospace,monospace"
        >
          {t('dashboard.activityTimeline.today')}
        </text>
      </svg>

      {/* Legend */}
      <Stack direction="row" spacing={2} flexWrap="wrap" useFlexGap sx={{ mt: 0.5 }}>
        {Object.entries(JOB_COLOR).map(([type, color]) => (
          <Stack key={type} direction="row" spacing={0.5} alignItems="center">
            <Box
              sx={{
                width: 7,
                height: 7,
                borderRadius: '50%',
                bgcolor: color,
                boxShadow: `0 0 4px ${color}80`,
              }}
            />
            <Typography sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}>
              {t(`dashboard.activityTimeline.jobType.${type}`, { defaultValue: type })}
            </Typography>
          </Stack>
        ))}
        <Stack direction="row" spacing={0.5} alignItems="center">
          <Box
            sx={{
              width: 7,
              height: 7,
              borderRadius: '50%',
              bgcolor: T.red,
              border: '1px solid rgba(255,255,255,0.4)',
            }}
          />
          <Typography sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}>
            {t('dashboard.activityTimeline.legendFailed')}
          </Typography>
        </Stack>
      </Stack>
    </Box>
  )
}

function gaugeColor(pct: number, T: Tokens) {
  return pct > 80 ? T.red : pct > 60 ? T.amber : T.blue
}

function toGB(b: number) {
  return (b / 1024 / 1024 / 1024).toFixed(1)
}

// ─── Main Component ───────────────────────────────────────────────────────────

export default function DashboardV3() {
  const navigate = useNavigate()
  const { effectiveMode } = useTheme()
  const { t } = useTranslation()
  const { trackNavigation, EventAction } = useAnalytics()
  const T = makeT(effectiveMode === 'dark')
  const [nowMs] = React.useState(() => Date.now())

  const glass = {
    bgcolor: T.bgCard,
    border: `1px solid ${T.border}`,
    borderRadius: T.radius,
    backdropFilter: 'blur(12px)',
    transition: 'border-color 0.2s',
    '&:hover': { borderColor: T.borderHover },
  } as const

  const {
    data: ov,
    isLoading,
    error,
    refetch,
  } = useQuery<DashboardOverview>({
    queryKey: ['dashboard-v3'],
    queryFn: () => dashboardAPI.getOverview().then((response) => response.data),
    refetchInterval: 30_000,
  })

  if (isLoading)
    return (
      <Box sx={{ color: T.textPrimary }}>
        {/* Health banner skeleton */}
        <Box
          sx={{
            bgcolor: T.bgCard,
            border: `1px solid ${T.border}`,
            borderRadius: '14px',
            mb: 2.5,
            px: 2.5,
            py: 1.75,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 2,
          }}
        >
          <Stack direction="row" spacing={2} alignItems="center">
            <Skeleton variant="circular" width={8} height={8} />
            <Box>
              <Skeleton
                variant="text"
                width={80}
                height={15}
                sx={{ mb: 0.2, transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton
                variant="text"
                width={120}
                height={24}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
          </Stack>
          <Stack direction="row" spacing={3}>
            {[56, 70, 62, 68].map((w, i) => (
              <Box key={i}>
                <Skeleton
                  variant="text"
                  width={w}
                  height={14}
                  sx={{ mb: 0.4, transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width={w - 10}
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
            ))}
          </Stack>
        </Box>

        {/* Bento grid — 220px left + 1fr right (matches real layout) */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '220px 1fr' },
            gap: 2.5,
            alignItems: 'start',
          }}
        >
          {/* Left column: donut + resources + storage */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            {/* Success donut card */}
            <Box
              sx={{
                bgcolor: T.bgCard,
                border: `1px solid ${T.border}`,
                borderRadius: '14px',
                p: 2.5,
                textAlign: 'center',
              }}
            >
              <Skeleton
                variant="text"
                width={80}
                height={10}
                sx={{ mx: 'auto', mb: 2, transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton variant="circular" width={148} height={148} sx={{ mx: 'auto', mb: 2 }} />
              <Stack direction="row" justifyContent="center" spacing={2.5}>
                <Box>
                  <Skeleton
                    variant="text"
                    width={32}
                    height={22}
                    sx={{ transform: 'none', borderRadius: 0.5 }}
                  />
                  <Skeleton
                    variant="text"
                    width={40}
                    height={10}
                    sx={{ mt: 0.25, transform: 'none', borderRadius: 0.5 }}
                  />
                </Box>
                <Box sx={{ width: '1px', height: 28, bgcolor: T.border }} />
                <Box>
                  <Skeleton
                    variant="text"
                    width={32}
                    height={22}
                    sx={{ transform: 'none', borderRadius: 0.5 }}
                  />
                  <Skeleton
                    variant="text"
                    width={40}
                    height={10}
                    sx={{ mt: 0.25, transform: 'none', borderRadius: 0.5 }}
                  />
                </Box>
              </Stack>
            </Box>

            {/* Resources card (3 arc gauges) */}
            <Box
              sx={{
                bgcolor: T.bgCard,
                border: `1px solid ${T.border}`,
                borderRadius: '14px',
                p: 2.5,
              }}
            >
              <Skeleton
                variant="text"
                width={80}
                height={10}
                sx={{ mb: 2, transform: 'none', borderRadius: 0.5 }}
              />
              <Stack direction="row" justifyContent="space-around">
                {[0, 1, 2].map((i) => (
                  <Box key={i} sx={{ textAlign: 'center' }}>
                    <Skeleton
                      variant="circular"
                      width={60}
                      height={60}
                      sx={{ mx: 'auto', mb: 0.75 }}
                    />
                    <Skeleton
                      variant="text"
                      width={28}
                      height={10}
                      sx={{ mx: 'auto', transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>
                ))}
              </Stack>
            </Box>

            {/* Storage donut card */}
            <Box
              sx={{
                bgcolor: T.bgCard,
                border: `1px solid ${T.border}`,
                borderRadius: '14px',
                p: 2.5,
              }}
            >
              <Skeleton
                variant="text"
                width={60}
                height={10}
                sx={{ mb: 1.75, transform: 'none', borderRadius: 0.5 }}
              />
              <Skeleton variant="circular" width={96} height={96} sx={{ mx: 'auto', mb: 1 }} />
            </Box>
          </Box>

          {/* Right column: repo health + activity */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            {/* Repo health section */}
            <Box
              sx={{
                bgcolor: T.bgCard,
                border: `1px solid ${T.border}`,
                borderRadius: '14px',
                p: 2.5,
              }}
            >
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 2 }}
              >
                <Skeleton
                  variant="text"
                  width={120}
                  height={12}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Stack direction="row" spacing={0.75}>
                  <Skeleton variant="rounded" width={52} height={19} sx={{ borderRadius: 1 }} />
                  <Skeleton variant="rounded" width={52} height={19} sx={{ borderRadius: 1 }} />
                </Stack>
              </Stack>
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(3, 1fr)' },
                  gap: 1.5,
                }}
              >
                {[0, 1, 2, 3, 4, 5].map((i) => (
                  <Box
                    key={i}
                    sx={{
                      bgcolor: T.bgCard,
                      border: `1px solid ${T.border}`,
                      borderRadius: '10px',
                      p: 1.5,
                      opacity: Math.max(0.3, 1 - i * 0.08),
                      animation: `dashSkeletonFadeIn 0.4s ease forwards`,
                      animationDelay: `${i * 60}ms`,
                      '@keyframes dashSkeletonFadeIn': {
                        from: { opacity: 0, transform: 'translateY(6px)' },
                        to: { opacity: Math.max(0.3, 1 - i * 0.08), transform: 'translateY(0)' },
                      },
                    }}
                  >
                    {/* Top: status dot + type chip | schedule badge */}
                    <Stack
                      direction="row"
                      alignItems="center"
                      justifyContent="space-between"
                      sx={{ mb: 0.75 }}
                    >
                      <Stack direction="row" spacing={0.75} alignItems="center">
                        <Skeleton variant="circular" width={8} height={8} />
                        <Skeleton
                          variant="rounded"
                          width={36}
                          height={15}
                          sx={{ borderRadius: 0.5 }}
                        />
                      </Stack>
                      <Skeleton
                        variant="rounded"
                        width={50}
                        height={15}
                        sx={{ borderRadius: 0.75 }}
                      />
                    </Stack>
                    {/* Repo name */}
                    <Skeleton
                      variant="text"
                      width={[90, 110, 80, 95, 105, 75][i]}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5, mb: 0.3 }}
                    />
                    {/* Stats row */}
                    <Stack direction="row" spacing={1.5} sx={{ mb: 0.9 }}>
                      <Skeleton
                        variant="text"
                        width={28}
                        height={10}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                      <Skeleton
                        variant="text"
                        width={36}
                        height={10}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Stack>
                    {/* Divider */}
                    <Box sx={{ height: '1px', bgcolor: T.border, mb: 0.9 }} />
                    {/* DimStatusGrid: BACKUP · CHECK · COMPACT */}
                    <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 0.5 }}>
                      {[0, 1, 2].map((j) => (
                        <Box key={j}>
                          <Skeleton
                            variant="text"
                            width={32}
                            height={10}
                            sx={{ transform: 'none', borderRadius: 0.5, mb: 0.25 }}
                          />
                          <Skeleton
                            variant="text"
                            width={28}
                            height={12}
                            sx={{ transform: 'none', borderRadius: 0.5 }}
                          />
                        </Box>
                      ))}
                    </Box>
                  </Box>
                ))}
              </Box>
            </Box>

            {/* Activity feed */}
            <Box
              sx={{
                bgcolor: T.bgCard,
                border: `1px solid ${T.border}`,
                borderRadius: '14px',
                p: 2.5,
              }}
            >
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Skeleton
                  variant="text"
                  width={100}
                  height={10}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width={60}
                  height={12}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Stack>
              <Stack spacing={1.25}>
                {[0, 1, 2, 3, 4].map((i) => (
                  <Box
                    key={i}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                      opacity: Math.max(0.2, 1 - i * 0.15),
                    }}
                  >
                    <Skeleton
                      variant="rounded"
                      width={6}
                      height={6}
                      sx={{ borderRadius: '50%', flexShrink: 0 }}
                    />
                    <Skeleton
                      variant="text"
                      width={[100, 140, 88, 120, 96][i]}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                    <Box sx={{ flex: 1 }} />
                    <Skeleton
                      variant="text"
                      width={56}
                      height={10}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>
                ))}
              </Stack>
            </Box>
          </Box>
        </Box>
      </Box>
    )
  if (error || !ov)
    return (
      <Alert
        severity="error"
        action={
          <Button
            size="small"
            onClick={() => {
              trackNavigation(EventAction.VIEW, {
                section: 'dashboard',
                operation: 'retry_refresh',
              })
              refetch()
            }}
          >
            {t('dashboard.error.retry')}
          </Button>
        }
      >
        {t('dashboard.error.unavailable')}
      </Alert>
    )

  const { summary, storage, repository_health: repos, system_metrics: sys } = ov
  const criticalCount = repos.filter((r) => r.health_status === 'critical').length
  const warningCount = repos.filter((r) => r.health_status === 'warning').length
  const healthyCount = repos.filter((r) => r.health_status === 'healthy').length
  const sysStatus = criticalCount > 0 ? 'critical' : warningCount > 0 ? 'warning' : 'healthy'
  const sc = STATUS[sysStatus]

  // Most recent backup across all repos
  const lastBackupDate = repos
    .map((r) => (r.last_backup ? new Date(r.last_backup) : null))
    .filter(Boolean)
    .sort((a, b) => b!.getTime() - a!.getTime())[0]

  return (
    <TokenContext.Provider value={T}>
      {/* No outer bgcolor / padding — Layout's Container already provides this */}
      <Box sx={{ color: T.textPrimary }}>
        {/* ── Health banner ─────────────────────────────────────────────────── */}
        <Box
          sx={{
            ...glass,
            mb: 2.5,
            px: 2.5,
            py: 1.75,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexWrap: 'wrap',
            gap: 2,
            borderColor: sc.color + '35',
            boxShadow: `0 0 28px ${sc.glow}, inset 0 1px 0 ${T.insetLine}`,
          }}
        >
          <Stack direction="row" spacing={2} alignItems="center">
            <PulseDot color={sc.color} glow={sc.glow} />
            <Box>
              <Typography
                sx={{
                  fontSize: '0.62rem',
                  color: T.textMuted,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  mb: 0.2,
                }}
              >
                {t('dashboard.banner.systemStatus')}
              </Typography>
              <Typography
                sx={{ fontFamily: T.mono, fontSize: '1rem', fontWeight: 700, color: sc.color }}
              >
                {sysStatus === 'healthy'
                  ? t('dashboard.banner.allNominal')
                  : sysStatus === 'warning'
                    ? t('dashboard.banner.warnings', {
                        count: warningCount,
                        s: warningCount > 1 ? 's' : '',
                      })
                    : t('dashboard.banner.critical', { count: criticalCount })}
              </Typography>
            </Box>
          </Stack>

          {/* Quick stats */}
          <Stack direction="row" spacing={3} flexWrap="wrap" useFlexGap>
            {[
              {
                label: t('dashboard.stats.repositories'),
                value: summary.total_repositories,
                color: T.blue,
              },
              {
                label: t('dashboard.banner.stats.lastBackup'),
                value: lastBackupDate
                  ? formatDistanceToNow(lastBackupDate, { addSuffix: true })
                  : t('common.never'),
                color:
                  lastBackupDate && differenceInDays(new Date(), lastBackupDate) > 1
                    ? T.amber
                    : T.green,
              },
              {
                label: t('dashboard.banner.stats.schedules'),
                value: `${summary.active_schedules}/${summary.total_schedules}`,
                color: T.textMuted,
              },
              {
                label: t('dashboard.banner.stats.storage'),
                value: storage.total_size,
                color: T.textPrimary,
              },
            ].map(({ label, value, color }) => (
              <Box key={label}>
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 1.5,
                    textTransform: 'uppercase',
                  }}
                >
                  {label}
                </Typography>
                <Typography
                  sx={{
                    fontFamily: T.mono,
                    fontWeight: 700,
                    color,
                    fontSize: '0.95rem',
                    lineHeight: 1.3,
                  }}
                >
                  {value}
                </Typography>
              </Box>
            ))}
          </Stack>

          <Button
            size="small"
            variant="text"
            onClick={() => {
              trackNavigation(EventAction.VIEW, {
                section: 'dashboard',
                operation: 'refresh',
              })
              refetch()
            }}
            sx={{
              color: T.textMuted,
              fontSize: '0.68rem',
              minWidth: 0,
              px: 1.25,
              '&:hover': { color: T.textPrimary, bgcolor: T.hoverBg },
            }}
          >
            {t('common.buttons.refresh')}
          </Button>
        </Box>

        {/* ── Bento grid ────────────────────────────────────────────────────── */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', md: '220px 1fr' },
            gap: 2.5,
            alignItems: 'start',
          }}
        >
          {/* Left: donut + resources */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            <Box sx={{ ...glass, p: 2.5, textAlign: 'center' }}>
              <Typography
                sx={{
                  fontSize: '0.58rem',
                  color: T.textMuted,
                  letterSpacing: 2,
                  textTransform: 'uppercase',
                  mb: 2,
                }}
              >
                {t('dashboard.successDonut.label')}
              </Typography>
              <SuccessDonut
                rate={summary.success_rate_30d}
                good={summary.successful_jobs_30d}
                total={summary.total_jobs_30d}
              />
              <Stack direction="row" justifyContent="center" spacing={2.5} sx={{ mt: 2 }}>
                <Box>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: T.green,
                      fontSize: '1.1rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.successful_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.58rem', color: T.textMuted, mt: 0.25 }}>
                    {t('dashboard.successDonut.passed')}
                  </Typography>
                </Box>
                <Box sx={{ width: '1px', height: 28, bgcolor: T.border, flexShrink: 0 }} />
                <Box>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontWeight: 700,
                      color: summary.failed_jobs_30d > 0 ? T.red : T.textMuted,
                      fontSize: '1.1rem',
                      lineHeight: 1,
                    }}
                  >
                    {summary.failed_jobs_30d}
                  </Typography>
                  <Typography sx={{ fontSize: '0.58rem', color: T.textMuted, mt: 0.25 }}>
                    {t('dashboard.successDonut.failed')}
                  </Typography>
                </Box>
              </Stack>
            </Box>

            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 2 }}>
                <Cpu size={13} color={T.textMuted} />
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {t('dashboard.resources')}
                </Typography>
              </Stack>
              <Stack direction="row" justifyContent="space-around">
                <ArcGauge
                  value={sys.cpu_usage}
                  color={gaugeColor(sys.cpu_usage, T)}
                  label={t('dashboard.cpu')}
                  sub={`${sys.cpu_count}c`}
                />
                <ArcGauge
                  value={sys.memory_usage}
                  color={gaugeColor(sys.memory_usage, T)}
                  label={t('dashboard.memAbbr')}
                  sub={`${toGB(sys.memory_total - sys.memory_available)}/${toGB(sys.memory_total)}G`}
                />
                <ArcGauge
                  value={sys.disk_usage}
                  color={gaugeColor(sys.disk_usage, T)}
                  label={t('dashboard.diskAbbr')}
                  sub={`${toGB(sys.disk_total - sys.disk_free)}/${toGB(sys.disk_total)}G`}
                />
              </Stack>
            </Box>

            {/* Storage donut */}
            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1.75 }}>
                <HardDrive size={13} color={T.textMuted} />
                <Typography
                  sx={{
                    fontSize: '0.58rem',
                    color: T.textMuted,
                    letterSpacing: 2,
                    textTransform: 'uppercase',
                  }}
                >
                  {t('dashboard.banner.stats.storage')}
                </Typography>
              </Stack>
              <StorageDonut
                breakdown={storage.breakdown}
                totalSize={storage.total_size}
                totalArchives={storage.total_archives}
              />
              {storage.average_dedup_ratio != null && (
                <Box
                  sx={{
                    mt: 1.5,
                    px: 1.25,
                    py: 0.6,
                    bgcolor: T.indigoDim,
                    border: `1px solid ${T.indigo}25`,
                    borderRadius: '8px',
                    display: 'flex',
                    justifyContent: 'space-between',
                  }}
                >
                  <Typography sx={{ fontSize: '0.62rem', color: T.textMuted }}>
                    {t('dashboard.storageDonut.dedupRatio')}
                  </Typography>
                  <Typography
                    sx={{
                      fontFamily: T.mono,
                      fontSize: '0.72rem',
                      fontWeight: 700,
                      color: T.indigo,
                    }}
                  >
                    {storage.average_dedup_ratio.toFixed(2)}×
                  </Typography>
                </Box>
              )}
            </Box>
          </Box>

          {/* Right: repo mini-cards + activity */}
          <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 2 }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Server size={13} color={T.textMuted} />
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      color: T.textMuted,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                    }}
                  >
                    {t('dashboard.repositoryHealth.title')}
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={0.75}>
                  {criticalCount > 0 && (
                    <Chip
                      label={t('dashboard.banner.critical', { count: criticalCount })}
                      size="small"
                      sx={{
                        height: 19,
                        fontSize: '0.6rem',
                        bgcolor: T.redDim,
                        color: T.red,
                        border: `1px solid ${T.red}30`,
                        fontFamily: T.mono,
                      }}
                    />
                  )}
                  {warningCount > 0 && (
                    <Chip
                      label={t('dashboard.banner.warnChip', { count: warningCount })}
                      size="small"
                      sx={{
                        height: 19,
                        fontSize: '0.6rem',
                        bgcolor: T.amberDim,
                        color: T.amber,
                        border: `1px solid ${T.amber}30`,
                        fontFamily: T.mono,
                      }}
                    />
                  )}
                  {healthyCount > 0 && (
                    <Chip
                      label={t('dashboard.banner.okChip', { count: healthyCount })}
                      size="small"
                      sx={{
                        height: 19,
                        fontSize: '0.6rem',
                        bgcolor: T.greenDim,
                        color: T.green,
                        border: `1px solid ${T.green}30`,
                        fontFamily: T.mono,
                      }}
                    />
                  )}
                </Stack>
              </Stack>

              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: { xs: '1fr', sm: 'repeat(2,1fr)', lg: 'repeat(3,1fr)' },
                  gap: 1.5,
                }}
              >
                {repos.map((repo) => {
                  // Card color follows the backend's aggregate repository health.
                  // Failed restore verification can make the card critical because recovery is at risk.
                  const cardStatus: keyof typeof STATUS =
                    repo.health_status === 'critical'
                      ? 'critical'
                      : repo.health_status === 'warning'
                        ? 'warning'
                        : 'healthy'
                  const cs = STATUS[cardStatus]

                  return (
                    <Box
                      key={repo.id}
                      onClick={() => {
                        trackNavigation(EventAction.VIEW, {
                          section: 'dashboard',
                          destination: 'repositories',
                          source: 'repository_health',
                        })
                        navigate('/repositories')
                      }}
                      sx={{
                        bgcolor: cs.dim,
                        border: `1px solid ${cs.color}30`,
                        borderRadius: '10px',
                        p: 1.25,
                        cursor: 'pointer',
                        transition: 'all 0.18s',
                        '&:hover': {
                          borderColor: cs.color + '60',
                          transform: 'translateY(-1px)',
                          boxShadow: `0 4px 20px ${cs.glow}`,
                        },
                      }}
                    >
                      {/* ── Top row: status dot + type chip | next-run pill ── */}
                      <Stack
                        direction="row"
                        alignItems="center"
                        justifyContent="space-between"
                        sx={{ mb: 0.55 }}
                      >
                        <Stack direction="row" spacing={0.75} alignItems="center">
                          <PulseDot color={cs.color} glow={cs.glow} />
                          <Chip
                            label={repo.type.toUpperCase()}
                            size="small"
                            sx={{
                              height: 15,
                              fontSize: '0.52rem',
                              bgcolor: T.repoBadgeBg,
                              color: T.textMuted,
                              border: `1px solid ${T.border}`,
                              fontFamily: T.mono,
                              px: 0,
                            }}
                          />
                          {repo.mode === 'observe' && (
                            <Chip
                              label={t('repositories.observeOnly')}
                              size="small"
                              sx={{
                                height: 15,
                                fontSize: '0.52rem',
                                bgcolor: T.indigoDim,
                                color: T.indigo,
                                border: `1px solid ${T.indigo}30`,
                                fontFamily: T.mono,
                                px: 0,
                              }}
                            />
                          )}
                        </Stack>
                        <ScheduleBadge
                          nextRun={repo.next_run}
                          hasSchedule={repo.has_schedule}
                          scheduleEnabled={repo.schedule_enabled}
                          scheduleName={repo.schedule_name}
                          scheduleTimezone={repo.schedule_timezone}
                          nowMs={nowMs}
                        />
                      </Stack>

                      {/* ── Name + stats ── */}
                      <Typography
                        sx={{
                          fontSize: '0.78rem',
                          fontWeight: 600,
                          color: T.textPrimary,
                          mb: 0.2,
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {repo.name}
                      </Typography>
                      <Stack direction="row" spacing={1.35} sx={{ mb: 0.65 }}>
                        <Typography
                          sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}
                        >
                          {t('dashboard.repositoryHealth.archiveCountShort', {
                            count: repo.archive_count,
                          })}
                        </Typography>
                        <Typography
                          sx={{ fontFamily: T.mono, fontSize: '0.6rem', color: T.textMuted }}
                        >
                          {repo.total_size}
                        </Typography>
                      </Stack>

                      {/* ── Divider ── */}
                      <Box sx={{ height: '1px', bgcolor: T.border, mb: 0.65 }} />

                      {/* ── Dimension status row: BACKUP · CHECK · COMPACT · RESTORE ── */}
                      <DimStatusGrid
                        mode={repo.mode}
                        dim={repo.dimension_health}
                        lastBackup={repo.last_backup}
                        lastCheck={repo.last_check}
                        lastCompact={
                          repo.mode === 'observe' ? String(repo.archive_count) : repo.last_compact
                        }
                        lastRestoreCheck={repo.last_restore_check}
                        latestRestoreCheckStatus={repo.latest_restore_check_status}
                        latestRestoreCheckError={repo.latest_restore_check_error}
                        restoreCheckConfigured={repo.restore_check_configured}
                      />
                    </Box>
                  )
                })}
              </Box>
              {repos.length === 0 && (
                <Typography
                  sx={{ color: T.textMuted, textAlign: 'center', py: 4, fontSize: '0.85rem' }}
                >
                  {t('dashboard.noRepositoriesShort')}
                </Typography>
              )}
            </Box>

            {/* Activity timeline */}
            <Box sx={{ ...glass, p: 2.5 }}>
              <Stack
                direction="row"
                alignItems="center"
                justifyContent="space-between"
                sx={{ mb: 1.75 }}
              >
                <Stack direction="row" spacing={1} alignItems="center">
                  <Activity size={13} color={T.textMuted} />
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      color: T.textMuted,
                      letterSpacing: 2,
                      textTransform: 'uppercase',
                    }}
                  >
                    {t('dashboard.recentActivity.last14Days')}
                  </Typography>
                </Stack>
                <Button
                  size="small"
                  variant="text"
                  endIcon={<ArrowRight size={12} />}
                  onClick={() => {
                    trackNavigation(EventAction.VIEW, {
                      section: 'dashboard',
                      destination: 'activity',
                      source: 'recent_activity',
                    })
                    navigate('/activity')
                  }}
                  sx={{
                    fontSize: '0.65rem',
                    color: T.textMuted,
                    '&:hover': { color: T.textPrimary, bgcolor: T.hoverBg },
                  }}
                >
                  {t('dashboard.recentActivity.fullLog')}
                </Button>
              </Stack>

              {ov.activity_feed.length === 0 ? (
                <Typography
                  sx={{ color: T.textMuted, textAlign: 'center', py: 3, fontSize: '0.8rem' }}
                >
                  {t('dashboard.recentActivity.emptyRecorded')}
                </Typography>
              ) : (
                <ActivityTimeline activities={ov.activity_feed} />
              )}

              {ov.activity_feed.some((a) => a.status === 'failed') && (
                <Box sx={{ mt: 2, borderTop: `1px solid ${T.border}`, pt: 1.5 }}>
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      color: T.red,
                      letterSpacing: 1.5,
                      textTransform: 'uppercase',
                      mb: 1,
                    }}
                  >
                    {t('dashboard.recentFailures.title')}
                  </Typography>
                  <Stack spacing={0.6}>
                    {ov.activity_feed
                      .filter((a) => a.status === 'failed')
                      .slice(0, 3)
                      .map((a) => (
                        <Box
                          key={`${a.type}-${a.id}`}
                          sx={{ display: 'flex', gap: 1.5, alignItems: 'flex-start' }}
                        >
                          <XCircle
                            size={13}
                            color={T.red}
                            style={{ marginTop: 2, flexShrink: 0 }}
                          />
                          <Box sx={{ minWidth: 0 }}>
                            <Stack direction="row" spacing={1.5}>
                              <Typography
                                sx={{
                                  fontFamily: T.mono,
                                  fontSize: '0.68rem',
                                  fontWeight: 600,
                                  color: T.textPrimary,
                                }}
                              >
                                {a.repository}
                              </Typography>
                              <Tooltip
                                title={formatDateTimeFull(a.timestamp)}
                                arrow
                                placement="top"
                              >
                                <Typography
                                  sx={{
                                    cursor: 'help',
                                    fontFamily: T.mono,
                                    fontSize: '0.62rem',
                                    color: T.textMuted,
                                  }}
                                >
                                  {formatDistanceToNow(new Date(a.timestamp), { addSuffix: true })}
                                </Typography>
                              </Tooltip>
                            </Stack>
                            {a.error && (
                              <Typography
                                sx={{
                                  fontFamily: T.mono,
                                  fontSize: '0.6rem',
                                  color: T.red + 'cc',
                                  mt: 0.25,
                                  wordBreak: 'break-all',
                                }}
                              >
                                {a.error}
                              </Typography>
                            )}
                          </Box>
                        </Box>
                      ))}
                  </Stack>
                </Box>
              )}
            </Box>
          </Box>
        </Box>
      </Box>
    </TokenContext.Provider>
  )
}
