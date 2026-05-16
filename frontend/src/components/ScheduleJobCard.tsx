import { Box, IconButton, Switch, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  CalendarClock,
  Database,
  History,
  CalendarCheck,
  Play,
  Copy,
  SquarePen,
  Trash2,
} from 'lucide-react'
import EntityCard, { StatItem, MetaItem, ActionItem } from './EntityCard'
import ScheduledInstantTooltip from './ScheduledInstantTooltip'
import {
  formatDateCompact,
  formatDateTimeFull,
  formatCronHuman,
  formatScheduledInstantDisplay,
} from '../utils/dateUtils'

interface Repository {
  id: number
  name: string
  path: string
}

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  timezone?: string | null
  repository: string | null
  repository_id: number | null
  repository_ids: number[] | null
  enabled: boolean
  last_run: string | null
  next_run: string | null
  description: string | null
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  last_prune: string | null
  last_compact: string | null
}

interface ScheduleJobCardProps {
  job: ScheduledJob
  repositories: Repository[]
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  onDuplicate: () => void
  onRunNow: () => void
  onToggle: () => void
  isRunNowPending?: boolean
  isDuplicatePending?: boolean
}

function getRepoLabel(job: ScheduledJob, repositories: Repository[]): string {
  if (job.repository_ids?.length) {
    if (job.repository_ids.length === 1) {
      const repo = repositories.find((r) => r.id === job.repository_ids![0])
      return repo?.name ?? '1 repo'
    }
    return `${job.repository_ids.length} repos`
  }
  if (job.repository_id) {
    const repo = repositories.find((r) => r.id === job.repository_id)
    return repo?.name ?? '1 repo'
  }
  if (job.repository) {
    const repo = repositories.find((r) => r.path === job.repository)
    return repo?.name ?? job.repository
  }
  return 'Unknown'
}

export default function ScheduleJobCard({
  job,
  repositories,
  canManage,
  onEdit,
  onDelete,
  onDuplicate,
  onRunNow,
  onToggle,
  isRunNowPending,
  isDuplicatePending,
}: ScheduleJobCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const scheduleTimezone = job.timezone || 'UTC'
  const scheduleDisplay = formatCronHuman(job.cron_expression)
  const nextRunDisplay = job.next_run
    ? formatScheduledInstantDisplay(job.next_run, scheduleTimezone)
    : null

  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: t('schedule.card.stats.schedule'),
      value: scheduleDisplay,
      tooltip: `${job.cron_expression} (${scheduleTimezone})`,
      color: 'info',
    },
    {
      icon: <Database size={11} />,
      label: t('schedule.card.stats.repository'),
      value: getRepoLabel(job, repositories),
      color: 'secondary',
    },
    {
      icon: <History size={11} />,
      label: t('schedule.card.stats.lastRun'),
      value: job.last_run ? formatDateCompact(job.last_run) : t('common.never'),
      tooltip: job.last_run ? formatDateTimeFull(job.last_run) : '',
      color: 'warning',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: t('schedule.card.stats.nextRun'),
      value: nextRunDisplay?.value ?? t('common.never'),
      tooltip: nextRunDisplay ? <ScheduledInstantTooltip display={nextRunDisplay} /> : '',
      color: 'success',
    },
  ]

  const meta: MetaItem[] = []
  meta.push({
    label: t('common.timezone', { defaultValue: 'Timezone' }),
    value: scheduleTimezone,
  })
  if (job.description) meta.push({ label: t('schedule.card.meta.note'), value: job.description })
  if (job.run_prune_after)
    meta.push({
      label: t('schedule.card.meta.prune'),
      value: `${job.prune_keep_daily}d/${job.prune_keep_weekly}w/${job.prune_keep_monthly}m/${job.prune_keep_yearly}y`,
      tooltip: `Keep: daily=${job.prune_keep_daily} weekly=${job.prune_keep_weekly} monthly=${job.prune_keep_monthly} yearly=${job.prune_keep_yearly}`,
    })
  if (job.last_prune)
    meta.push({
      label: t('schedule.card.meta.lastPruned'),
      value: formatDateCompact(job.last_prune),
      tooltip: formatDateTimeFull(job.last_prune),
    })
  if (job.run_compact_after)
    meta.push({
      label: t('schedule.card.meta.compact'),
      value: t('schedule.card.meta.afterBackup'),
    })
  if (job.last_compact)
    meta.push({
      label: t('schedule.card.meta.lastCompact'),
      value: formatDateCompact(job.last_compact),
      tooltip: formatDateTimeFull(job.last_compact),
    })

  const actions: ActionItem[] = [
    {
      icon: <Copy size={16} />,
      tooltip: t('schedule.card.actions.duplicate'),
      onClick: onDuplicate,
      disabled: isDuplicatePending || !canManage,
      hidden: !canManage,
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: t('common.buttons.delete'),
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const editIcon = canManage ? (
    <Tooltip title={t('common.buttons.edit')} arrow placement="left">
      <IconButton
        size="small"
        onClick={onEdit}
        aria-label={t('common.buttons.edit')}
        sx={{
          width: 28,
          height: 28,
          borderRadius: 1,
          flexShrink: 0,
          color: 'text.disabled',
          '&:hover': {
            color: 'text.primary',
            bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
          },
        }}
      >
        <SquarePen size={14} />
      </IconButton>
    </Tooltip>
  ) : undefined

  const toggle = (
    <Tooltip
      title={
        canManage
          ? job.enabled
            ? t('schedule.card.badge.clickToDisable')
            : t('schedule.card.badge.clickToEnable')
          : ''
      }
      arrow
    >
      <Box
        component="label"
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          cursor: canManage ? 'pointer' : 'default',
          userSelect: 'none',
        }}
      >
        <Switch
          checked={job.enabled}
          size="small"
          color="success"
          disabled={!canManage}
          onChange={canManage ? onToggle : undefined}
        />
        <Typography
          variant="caption"
          sx={{
            fontWeight: 600,
            fontSize: '0.7rem',
            color: job.enabled ? 'success.main' : 'text.disabled',
            lineHeight: 1,
          }}
        >
          {job.enabled ? t('schedule.card.badge.enabled') : t('schedule.card.badge.disabled')}
        </Typography>
      </Box>
    </Tooltip>
  )

  return (
    <EntityCard
      title={job.name}
      subtitle={job.description ?? undefined}
      badge={editIcon}
      stats={stats}
      meta={meta.length > 0 ? meta : undefined}
      toggle={toggle}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: t('schedule.card.actions.runNow'),
              icon: <Play size={13} />,
              onClick: onRunNow,
              disabled: !job.enabled || isRunNowPending,
            }
          : undefined
      }
      accentColor="#059669"
    />
  )
}
