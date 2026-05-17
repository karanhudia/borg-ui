import { Box, IconButton, Switch, Tooltip, Typography, alpha, useTheme } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { CalendarClock, History, CalendarCheck, Timer, Play, SquarePen, Trash2 } from 'lucide-react'
import EntityCard, { StatItem, ActionItem, MetaItem } from './EntityCard'
import ScheduledInstantTooltip from './ScheduledInstantTooltip'
import {
  formatDateCompact,
  formatDateTimeFull,
  formatCronHuman,
  formatScheduledInstantDisplay,
} from '../utils/dateUtils'

interface ScheduledCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  check_cron_expression: string | null
  check_timezone?: string | null
  timezone?: string | null
  last_scheduled_check: string | null
  next_scheduled_check: string | null
  check_max_duration: number
  check_extra_flags?: string | null
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  // "enabled" = cron is set AND user toggle is on (will actually run)
  enabled: boolean
  // The user-facing on/off toggle, independent of cron presence.
  check_schedule_enabled?: boolean
}

interface ScheduleCheckCardProps {
  check: ScheduledCheck
  canManage: boolean
  onEdit: () => void
  onDelete: () => void
  onRunNow: () => void
  onToggle: () => void
}

export default function ScheduleCheckCard({
  check,
  canManage,
  onEdit,
  onDelete,
  onRunNow,
  onToggle,
}: ScheduleCheckCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const scheduleEnabled = check.check_schedule_enabled ?? check.enabled
  const scheduleTimezone = check.check_timezone || check.timezone || 'UTC'
  const scheduleDisplay = check.check_cron_expression
    ? formatCronHuman(check.check_cron_expression)
    : t('schedule.checkCard.stats.notSet')
  const nextCheckDisplay = check.next_scheduled_check
    ? formatScheduledInstantDisplay(check.next_scheduled_check, scheduleTimezone)
    : null

  const stats: StatItem[] = [
    {
      icon: <CalendarClock size={11} />,
      label: t('common.schedule'),
      value: scheduleDisplay,
      tooltip: check.check_cron_expression
        ? `${check.check_cron_expression} (${scheduleTimezone})`
        : undefined,
      color: 'info',
    },
    {
      icon: <History size={11} />,
      label: t('schedule.checkCard.stats.lastCheck'),
      value: check.last_scheduled_check
        ? formatDateCompact(check.last_scheduled_check)
        : t('common.never'),
      tooltip: check.last_scheduled_check ? formatDateTimeFull(check.last_scheduled_check) : '',
      color: 'warning',
    },
    {
      icon: <CalendarCheck size={11} />,
      label: t('schedule.checkCard.stats.nextCheck'),
      value: nextCheckDisplay?.value ?? t('common.never'),
      tooltip: nextCheckDisplay ? <ScheduledInstantTooltip display={nextCheckDisplay} /> : '',
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

  const meta: MetaItem[] = [
    {
      label: t('common.timezone', { defaultValue: 'Timezone' }),
      value: scheduleTimezone,
    },
  ]
  if (check.check_extra_flags) {
    meta.push({
      label: t('schedule.checkCard.meta.extraFlags'),
      value: check.check_extra_flags,
    })
  }

  const actions: ActionItem[] = [
    {
      icon: <Trash2 size={16} />,
      tooltip: t('schedule.checkCard.actions.removeSchedule'),
      onClick: onDelete,
      color: 'error',
      hidden: !canManage,
    },
  ]

  const editIcon = canManage ? (
    <Tooltip title={t('schedule.checkCard.actions.editSchedule')} arrow placement="left">
      <IconButton
        size="small"
        onClick={onEdit}
        aria-label={t('schedule.checkCard.actions.editSchedule')}
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
              label: t('schedule.checkCard.actions.runCheck'),
              icon: <Play size={13} />,
              onClick: onRunNow,
              disabled: !scheduleEnabled,
            }
          : undefined
      }
    />
  )
}
