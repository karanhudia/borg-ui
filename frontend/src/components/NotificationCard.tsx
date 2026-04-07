import {
  Bell,
  BellOff,
  Clock,
  Copy,
  Database,
  Pencil,
  TestTube,
  Trash2,
  Zap,
  Archive,
  RotateCcw,
  ShieldCheck,
  AlertCircle,
} from 'lucide-react'
import { useTranslation } from 'react-i18next'
import EntityCard, { ActionItem, StatItem } from './EntityCard'
import { Box, CircularProgress, Tooltip, useTheme, alpha } from '@mui/material'
import { formatDateShort } from '../utils/dateUtils'

interface NotificationSetting {
  id: number
  name: string
  service_url: string
  enabled: boolean
  title_prefix: string | null
  include_job_name_in_title: boolean
  notify_on_backup_start: boolean
  notify_on_backup_success: boolean
  notify_on_backup_failure: boolean
  notify_on_restore_success: boolean
  notify_on_restore_failure: boolean
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  notify_on_schedule_failure: boolean
  monitor_all_repositories: boolean
  repositories: { id: number; name: string }[]
  created_at: string
  updated_at: string
  last_used_at: string | null
}

interface NotificationCardProps {
  notification: NotificationSetting
  onTest: () => void
  onEdit: () => void
  onDuplicate: () => void
  onDelete: () => void
  isTesting?: boolean
}

function getServiceType(url: string): string {
  const match = url.match(/^([a-z]+):\/\//)
  if (!match) return 'Webhook'
  const scheme = match[1].toLowerCase()
  const map: Record<string, string> = {
    slack: 'Slack',
    discord: 'Discord',
    tgram: 'Telegram',
    tgrams: 'Telegram',
    mailto: 'Email',
    msteams: 'Teams',
    pover: 'Pushover',
    ntfy: 'Ntfy',
    json: 'Webhook',
    xml: 'Webhook',
    form: 'Webhook',
    gotify: 'Gotify',
    matrix: 'Matrix',
  }
  return map[scheme] ?? scheme.charAt(0).toUpperCase() + scheme.slice(1)
}

export default function NotificationCard({
  notification,
  onTest,
  onEdit,
  onDuplicate,
  onDelete,
  isTesting = false,
}: NotificationCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const eventCount = [
    notification.notify_on_backup_start,
    notification.notify_on_backup_success,
    notification.notify_on_backup_failure,
    notification.notify_on_restore_success,
    notification.notify_on_restore_failure,
    notification.notify_on_check_success,
    notification.notify_on_check_failure,
    notification.notify_on_schedule_failure,
  ].filter(Boolean).length

  const stats: StatItem[] = [
    {
      icon: <Bell size={11} />,
      label: t('notifications.card.stats.service'),
      value: getServiceType(notification.service_url),
      color: 'primary',
    },
    {
      icon: <Zap size={11} />,
      label: t('notifications.card.stats.events'),
      value: `${eventCount} ${t('notifications.card.stats.active')}`,
      color: 'warning',
    },
    {
      icon: <Database size={11} />,
      label: t('notifications.card.stats.scope'),
      value: notification.monitor_all_repositories
        ? t('notifications.card.stats.allRepos')
        : t('notifications.card.stats.repoCount', { count: notification.repositories.length }),
      color: 'secondary',
    },
    {
      icon: <Clock size={11} />,
      label: t('notifications.card.stats.lastUsed'),
      value: notification.last_used_at
        ? formatDateShort(notification.last_used_at)
        : t('common.never'),
      tooltip: notification.last_used_at ? notification.last_used_at : '',
      color: 'info',
    },
  ]

  // Badge: plain icon only, no text, no border
  const badge = (
    <Box
      sx={{
        display: 'flex',
        color: notification.enabled
          ? theme.palette.success.main
          : isDark
            ? alpha('#fff', 0.2)
            : alpha('#000', 0.2),
      }}
    >
      {notification.enabled ? <Bell size={16} /> : <BellOff size={16} />}
    </Box>
  )

  // Event categories strip — 4 groups, each lit when any event in that category is on
  const categories = [
    {
      icon: <Archive size={10} />,
      label: t('notifications.card.categories.backup'),
      active:
        notification.notify_on_backup_start ||
        notification.notify_on_backup_success ||
        notification.notify_on_backup_failure,
      tooltip:
        [
          notification.notify_on_backup_start && t('notifications.card.events.start'),
          notification.notify_on_backup_success && t('notifications.card.events.success'),
          notification.notify_on_backup_failure && t('notifications.card.events.failure'),
        ]
          .filter(Boolean)
          .join(' · ') || t('notifications.card.events.off'),
    },
    {
      icon: <RotateCcw size={10} />,
      label: t('notifications.card.categories.restore'),
      active: notification.notify_on_restore_success || notification.notify_on_restore_failure,
      tooltip:
        [
          notification.notify_on_restore_success && t('notifications.card.events.success'),
          notification.notify_on_restore_failure && t('notifications.card.events.failure'),
        ]
          .filter(Boolean)
          .join(' · ') || t('notifications.card.events.off'),
    },
    {
      icon: <ShieldCheck size={10} />,
      label: t('notifications.card.categories.check'),
      active: notification.notify_on_check_success || notification.notify_on_check_failure,
      tooltip:
        [
          notification.notify_on_check_success && t('notifications.card.events.success'),
          notification.notify_on_check_failure && t('notifications.card.events.failure'),
        ]
          .filter(Boolean)
          .join(' · ') || t('notifications.card.events.off'),
    },
    {
      icon: <AlertCircle size={10} />,
      label: t('notifications.card.categories.schedule'),
      active: notification.notify_on_schedule_failure,
      tooltip: notification.notify_on_schedule_failure
        ? t('notifications.card.events.errors')
        : t('notifications.card.events.off'),
    },
  ]

  const ACTIVE_COLOR = '#059669'

  const eventTags = (
    <Box sx={{ display: 'flex', gap: 0.75, flexWrap: 'wrap' }}>
      {categories.map((cat) => (
        <Tooltip key={cat.label} title={`${cat.label}: ${cat.tooltip}`} arrow>
          <Box
            sx={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 0.4,
              px: 0.75,
              py: 0.3,
              borderRadius: 1,
              border: '1px solid',
              cursor: 'default',
              transition: 'all 150ms',
              ...(cat.active
                ? {
                    borderColor: alpha(ACTIVE_COLOR, isDark ? 0.4 : 0.35),
                    bgcolor: alpha(ACTIVE_COLOR, isDark ? 0.12 : 0.07),
                    color: ACTIVE_COLOR,
                  }
                : {
                    borderColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
                    bgcolor: 'transparent',
                    color: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.2),
                  }),
            }}
          >
            {cat.icon}
            <Box
              component="span"
              sx={{
                fontSize: '0.62rem',
                fontWeight: 600,
                letterSpacing: '0.04em',
                lineHeight: 1,
                textTransform: 'uppercase',
              }}
            >
              {cat.label}
            </Box>
          </Box>
        </Tooltip>
      ))}
    </Box>
  )

  const actions: ActionItem[] = [
    {
      icon: isTesting ? <CircularProgress size={16} /> : <TestTube size={16} />,
      tooltip: t('notifications.card.actions.sendTest'),
      onClick: onTest,
      disabled: isTesting,
    },
    {
      icon: <Copy size={16} />,
      tooltip: t('notifications.card.actions.duplicate'),
      onClick: onDuplicate,
    },
    {
      icon: <Pencil size={16} />,
      tooltip: t('common.buttons.edit'),
      onClick: onEdit,
      color: 'primary',
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: t('common.buttons.delete'),
      onClick: onDelete,
      color: 'error',
    },
  ]

  return (
    <EntityCard
      title={notification.name}
      subtitle={
        notification.service_url.length > 60
          ? notification.service_url.slice(0, 57) + '...'
          : notification.service_url
      }
      badge={badge}
      stats={stats}
      tags={eventTags}
      actions={actions}
    />
  )
}
