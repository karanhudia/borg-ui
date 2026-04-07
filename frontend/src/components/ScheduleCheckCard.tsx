import { Chip } from '@mui/material'
import { CalendarClock, History, CalendarCheck, Timer, Play, Pencil, Trash2 } from 'lucide-react'
import EntityCard, { StatItem, ActionItem } from './EntityCard'
import { formatDateShort, formatDateTimeFull, formatCronHuman, convertCronToLocal } from '../utils/dateUtils'

interface ScheduledCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  check_cron_expression: string | null
  last_scheduled_check: string | null
  next_scheduled_check: string | null
  check_max_duration: number
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  enabled: boolean
}

interface ScheduleCheckCardProps {
  check: ScheduledCheck
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  onRunNow: () => void
}

export default function ScheduleCheckCard({
  check,
  canManage,
  onEdit,
  onDelete,
  onRunNow,
}: ScheduleCheckCardProps) {
  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: 'Schedule',
      value: check.check_cron_expression
        ? formatCronHuman(convertCronToLocal(check.check_cron_expression))
        : 'Not set',
      tooltip: check.check_cron_expression ?? '',
    },
    {
      icon: <History size={11} />,
      label: 'Last Check',
      value: check.last_scheduled_check ? formatDateShort(check.last_scheduled_check) : 'Never',
      tooltip: check.last_scheduled_check ? formatDateTimeFull(check.last_scheduled_check) : '',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: 'Next Check',
      value: check.next_scheduled_check ? formatDateShort(check.next_scheduled_check) : 'Never',
      tooltip: check.next_scheduled_check ? formatDateTimeFull(check.next_scheduled_check) : '',
    },
    {
      icon: <Timer size={11} />,
      label: 'Max Duration',
      value: check.check_max_duration ? `${Math.round(check.check_max_duration / 60)}m` : 'Unlimited',
    },
  ]

  const actions: ActionItem[] = [
    {
      icon: <Pencil size={16} />,
      tooltip: 'Edit schedule',
      onClick: onEdit,
      color: 'primary',
      hidden: !canManage,
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: 'Remove schedule',
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const badge = (
    <Chip
      label="Health Check"
      size="small"
      variant="outlined"
      color="info"
      sx={{ fontSize: '0.65rem' }}
    />
  )

  return (
    <EntityCard
      initials={check.repository_name.slice(0, 2).toUpperCase()}
      title={check.repository_name}
      subtitle={check.repository_path}
      badge={badge}
      stats={stats}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: 'Run Check',
              icon: <Play size={13} />,
              onClick: onRunNow,
            }
          : undefined
      }
    />
  )
}
