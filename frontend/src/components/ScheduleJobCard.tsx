import { Box, Switch, Tooltip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  CalendarClock,
  Database,
  History,
  CalendarCheck,
  Play,
  Copy,
  Pencil,
  Trash2,
} from 'lucide-react'
import EntityCard, { StatItem, MetaItem, ActionItem } from './EntityCard'
import {
  formatDateShort,
  formatDateTimeFull,
  formatCronHuman,
  convertCronToLocal,
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

  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: t('schedule.card.stats.schedule'),
      value: formatCronHuman(convertCronToLocal(job.cron_expression)),
      tooltip: job.cron_expression,
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
      value: job.last_run ? formatDateShort(job.last_run) : t('common.never'),
      tooltip: job.last_run ? formatDateTimeFull(job.last_run) : '',
      color: 'warning',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: t('schedule.card.stats.nextRun'),
      value: job.next_run ? formatDateShort(job.next_run) : t('common.never'),
      tooltip: job.next_run ? formatDateTimeFull(job.next_run) : '',
      color: 'success',
    },
  ]

  const meta: MetaItem[] = []
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
      value: formatDateShort(job.last_prune),
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
      value: formatDateShort(job.last_compact),
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
      icon: <Pencil size={16} />,
      tooltip: t('common.buttons.edit'),
      onClick: onEdit,
      color: 'primary',
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

  const badge = (
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
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 0.25,
          cursor: canManage ? 'pointer' : 'default',
          userSelect: 'none',
        }}
        onClick={canManage ? onToggle : undefined}
      >
        <Switch
          checked={job.enabled}
          size="small"
          color="success"
          disabled={!canManage}
          onChange={() => {}} // controlled by parent Box onClick
          sx={{ pointerEvents: 'none' }}
        />
        <Typography
          variant="caption"
          sx={{
            fontWeight: 600,
            fontSize: '0.7rem',
            color: job.enabled ? 'success.main' : 'text.disabled',
            lineHeight: 1,
            mr: 0.5,
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
      badge={badge}
      stats={stats}
      meta={meta.length > 0 ? meta : undefined}
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
