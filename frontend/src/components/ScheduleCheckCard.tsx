import { Chip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { CalendarClock, History, CalendarCheck, Timer, Play, Pencil, Trash2 } from 'lucide-react'
import EntityCard, { StatItem, ActionItem } from './EntityCard'
import {
  formatDateShort,
  formatDateTimeFull,
  formatCronHuman,
  convertCronToLocal,
} from '../utils/dateUtils'

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
  const { t } = useTranslation()

  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: t('common.schedule'),
      value: check.check_cron_expression
        ? formatCronHuman(convertCronToLocal(check.check_cron_expression))
        : t('schedule.checkCard.stats.notSet'),
      tooltip: check.check_cron_expression ?? '',
      color: 'info',
    },
    {
      icon: <History size={11} />,
      label: t('schedule.checkCard.stats.lastCheck'),
      value: check.last_scheduled_check
        ? formatDateShort(check.last_scheduled_check)
        : t('common.never'),
      tooltip: check.last_scheduled_check ? formatDateTimeFull(check.last_scheduled_check) : '',
      color: 'warning',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: t('schedule.checkCard.stats.nextCheck'),
      value: check.next_scheduled_check
        ? formatDateShort(check.next_scheduled_check)
        : t('common.never'),
      tooltip: check.next_scheduled_check ? formatDateTimeFull(check.next_scheduled_check) : '',
      color: 'success',
    },
    {
      icon: <Timer size={11} />,
      label: t('schedule.checkCard.stats.maxDuration'),
      value: check.check_max_duration
        ? `${Math.round(check.check_max_duration / 60)}m`
        : t('schedule.checkCard.stats.unlimited'),
      color: 'secondary',
    },
  ]

  const actions: ActionItem[] = [
    {
      icon: <Pencil size={16} />,
      tooltip: t('schedule.checkCard.actions.editSchedule'),
      onClick: onEdit,
      color: 'primary',
      hidden: !canManage,
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: t('schedule.checkCard.actions.removeSchedule'),
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const badge = (
    <Chip
      label={t('schedule.checkCard.badge.healthCheck')}
      size="small"
      variant="outlined"
      color="info"
      sx={{ fontSize: '0.65rem' }}
    />
  )

  return (
    <EntityCard
      title={check.repository_name}
      subtitle={check.repository_path}
      badge={badge}
      stats={stats}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: t('schedule.checkCard.actions.runCheck'),
              icon: <Play size={13} />,
              onClick: onRunNow,
            }
          : undefined
      }
    />
  )
}
