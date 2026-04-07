import { Box, Switch, Tooltip, Typography } from '@mui/material'
import { CalendarClock, Database, History, CalendarCheck, Play, Copy, Pencil, Trash2 } from 'lucide-react'
import EntityCard, { StatItem, MetaItem, ActionItem } from './EntityCard'
import { formatDateShort, formatDateTimeFull, formatCronHuman, convertCronToLocal } from '../utils/dateUtils'

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

function getJobInitials(name: string): string {
  const words = name.trim().split(/\s+/)
  if (words.length === 1) return words[0].slice(0, 2).toUpperCase()
  return (words[0][0] + words[1][0]).toUpperCase()
}

function getRepoLabel(job: ScheduledJob, repositories: Repository[]): string {
  if (job.repository_ids?.length) {
    if (job.repository_ids.length === 1) {
      const repo = repositories.find(r => r.id === job.repository_ids![0])
      return repo?.name ?? '1 repo'
    }
    return `${job.repository_ids.length} repos`
  }
  if (job.repository_id) {
    const repo = repositories.find(r => r.id === job.repository_id)
    return repo?.name ?? '1 repo'
  }
  if (job.repository) {
    const repo = repositories.find(r => r.path === job.repository)
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
  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: 'Schedule',
      value: formatCronHuman(convertCronToLocal(job.cron_expression)),
      tooltip: job.cron_expression,
    },
    {
      icon: <Database size={11} />,
      label: 'Repository',
      value: getRepoLabel(job, repositories),
    },
    {
      icon: <History size={11} />,
      label: 'Last Run',
      value: job.last_run ? formatDateShort(job.last_run) : 'Never',
      tooltip: job.last_run ? formatDateTimeFull(job.last_run) : '',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: 'Next Run',
      value: job.next_run ? formatDateShort(job.next_run) : 'Never',
      tooltip: job.next_run ? formatDateTimeFull(job.next_run) : '',
    },
  ]

  const meta: MetaItem[] = []
  if (job.description) meta.push({ label: 'Note', value: job.description })
  if (job.run_prune_after)
    meta.push({
      label: 'Prune',
      value: `${job.prune_keep_daily}d/${job.prune_keep_weekly}w/${job.prune_keep_monthly}m/${job.prune_keep_yearly}y`,
      tooltip: `Keep: daily=${job.prune_keep_daily} weekly=${job.prune_keep_weekly} monthly=${job.prune_keep_monthly} yearly=${job.prune_keep_yearly}`,
    })
  if (job.last_prune)
    meta.push({
      label: 'Last Pruned',
      value: formatDateShort(job.last_prune),
      tooltip: formatDateTimeFull(job.last_prune),
    })
  if (job.run_compact_after) meta.push({ label: 'Compact', value: 'After backup' })
  if (job.last_compact)
    meta.push({
      label: 'Last Compact',
      value: formatDateShort(job.last_compact),
      tooltip: formatDateTimeFull(job.last_compact),
    })

  const actions: ActionItem[] = [
    {
      icon: <Copy size={16} />,
      tooltip: 'Duplicate',
      onClick: onDuplicate,
      disabled: isDuplicatePending || !canManage,
      hidden: !canManage,
    },
    {
      icon: <Pencil size={16} />,
      tooltip: 'Edit',
      onClick: onEdit,
      color: 'primary',
      hidden: !canManage,
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: 'Delete',
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const badge = (
    <Tooltip title={canManage ? (job.enabled ? 'Click to disable' : 'Click to enable') : ''} arrow>
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
          onChange={() => {}}  // controlled by parent Box onClick
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
          {job.enabled ? 'Enabled' : 'Disabled'}
        </Typography>
      </Box>
    </Tooltip>
  )

  return (
    <EntityCard
      initials={getJobInitials(job.name)}
      title={job.name}
      subtitle={job.description ?? undefined}
      badge={badge}
      stats={stats}
      meta={meta.length > 0 ? meta : undefined}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: 'Run Now',
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
