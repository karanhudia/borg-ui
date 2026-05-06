import { Chip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { CalendarCheck, CalendarClock, History, Play, Pencil, Search, Trash2 } from 'lucide-react'
import EntityCard, { ActionItem, StatItem } from './EntityCard'
import ScheduledInstantTooltip from './ScheduledInstantTooltip'
import {
  formatCronHuman,
  formatDateCompact,
  formatDateTimeFull,
  formatScheduledInstantDisplay,
} from '../utils/dateUtils'

interface ScheduledRestoreCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  restore_check_cron_expression: string | null
  restore_check_timezone?: string | null
  timezone?: string | null
  restore_check_paths: string[]
  restore_check_full_archive: boolean
  restore_check_mode?: 'canary' | 'probe_paths' | 'full_archive'
  last_restore_check: string | null
  last_scheduled_restore_check: string | null
  next_scheduled_restore_check: string | null
  notify_on_restore_check_success: boolean
  notify_on_restore_check_failure: boolean
  enabled: boolean
}

interface ScheduleRestoreCheckCardProps {
  check: ScheduledRestoreCheck
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  onRunNow: () => void
}

export default function ScheduleRestoreCheckCard({
  check,
  canManage,
  onEdit,
  onDelete,
  onRunNow,
}: ScheduleRestoreCheckCardProps) {
  const { t } = useTranslation()
  const scheduleTimezone = check.restore_check_timezone || check.timezone || 'UTC'
  const scheduleDisplay = check.restore_check_cron_expression
    ? formatCronHuman(check.restore_check_cron_expression)
    : t('scheduledRestoreChecks.stats.notSet')
  const nextCheckDisplay = check.next_scheduled_restore_check
    ? formatScheduledInstantDisplay(check.next_scheduled_restore_check, scheduleTimezone)
    : null

  const probePathCount = check.restore_check_paths.length
  const probePathValue = check.restore_check_full_archive
    ? t('scheduledRestoreChecks.stats.fullArchive')
    : probePathCount > 0
      ? t('scheduledRestoreChecks.stats.pathCountValue', { count: probePathCount })
      : t('scheduledRestoreChecks.stats.canary')

  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: t('common.schedule'),
      value: scheduleDisplay,
      tooltip: check.restore_check_cron_expression
        ? `${check.restore_check_cron_expression} (${scheduleTimezone})`
        : undefined,
      color: 'info',
    },
    {
      icon: <History size={11} />,
      label: t('scheduledRestoreChecks.stats.lastVerifiedRestore'),
      value: check.last_restore_check
        ? formatDateCompact(check.last_restore_check)
        : t('common.never'),
      tooltip: check.last_restore_check ? formatDateTimeFull(check.last_restore_check) : '',
      color: 'warning',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: t('scheduledRestoreChecks.stats.nextCheck'),
      value: nextCheckDisplay?.value ?? t('common.never'),
      tooltip: nextCheckDisplay ? <ScheduledInstantTooltip display={nextCheckDisplay} /> : '',
      color: 'success',
    },
    {
      icon: <Search size={11} />,
      label: t('scheduledRestoreChecks.stats.probePaths'),
      value: probePathValue,
      tooltip:
        !check.restore_check_full_archive && probePathCount > 0
          ? check.restore_check_paths.join('\n')
          : undefined,
      color: 'secondary',
    },
  ]

  const meta = [
    {
      label: t('common.timezone', { defaultValue: 'Timezone' }),
      value: scheduleTimezone,
    },
  ]

  const actions: ActionItem[] = [
    {
      icon: <Pencil size={16} />,
      tooltip: t('scheduledRestoreChecks.actions.editSchedule'),
      onClick: onEdit,
      color: 'primary',
      hidden: !canManage,
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: t('scheduledRestoreChecks.actions.removeSchedule'),
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  return (
    <EntityCard
      title={check.repository_name}
      subtitle={check.repository_path}
      badge={
        <Chip
          label={t('scheduledRestoreChecks.badge.restoreCheck')}
          size="small"
          variant="outlined"
          color="success"
          sx={{ fontSize: '0.65rem' }}
        />
      }
      stats={stats}
      meta={meta}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: t('scheduledRestoreChecks.actions.runRestoreCheck'),
              icon: <Play size={13} />,
              onClick: onRunNow,
            }
          : undefined
      }
    />
  )
}
