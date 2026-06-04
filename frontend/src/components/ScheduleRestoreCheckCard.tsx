import { Box, IconButton, Switch, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import {
  CalendarCheck,
  CalendarClock,
  History,
  Play,
  Search,
  SquarePen,
  Trash2,
} from 'lucide-react'
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
  restore_check_schedule_enabled?: boolean
}

interface ScheduleRestoreCheckCardProps {
  check: ScheduledRestoreCheck
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  onRunNow: () => void
  onToggle: () => void
}

export default function ScheduleRestoreCheckCard({
  check,
  canManage,
  onEdit,
  onDelete,
  onRunNow,
  onToggle,
}: ScheduleRestoreCheckCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const scheduleEnabled = check.restore_check_schedule_enabled ?? check.enabled
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
      icon: <Trash2 size={16} />,
      tooltip: t('scheduledRestoreChecks.actions.removeSchedule'),
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const editIcon = canManage ? (
    <Tooltip title={t('scheduledRestoreChecks.actions.editSchedule')} arrow placement="left">
      <IconButton
        size="small"
        onClick={onEdit}
        aria-label={t('scheduledRestoreChecks.actions.editSchedule')}
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
          ? scheduleEnabled
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
          checked={scheduleEnabled}
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
            color: scheduleEnabled ? 'success.main' : 'text.disabled',
            lineHeight: 1,
          }}
        >
          {scheduleEnabled ? t('schedule.card.badge.enabled') : t('schedule.card.badge.disabled')}
        </Typography>
      </Box>
    </Tooltip>
  )

  return (
    <EntityCard
      title={check.repository_name}
      subtitle={check.repository_path}
      badge={editIcon}
      stats={stats}
      meta={meta}
      toggle={toggle}
      actions={actions}
      primaryAction={
        canManage
          ? {
              label: t('scheduledRestoreChecks.actions.runRestoreCheck'),
              icon: <Play size={13} />,
              onClick: onRunNow,
              disabled: !scheduleEnabled,
            }
          : undefined
      }
    />
  )
}
