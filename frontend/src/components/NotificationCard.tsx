import { Bell, BellOff, Clock, Copy, Database, Pencil, TestTube, Trash2, Zap } from 'lucide-react'
import EntityCard, { ActionItem, StatItem } from './EntityCard'
import { Chip, CircularProgress } from '@mui/material'
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
      label: 'Service',
      value: getServiceType(notification.service_url),
    },
    {
      icon: <Zap size={11} />,
      label: 'Events',
      value: `${eventCount} active`,
      tooltip: (() => {
        const eventLabels: string[] = []
        if (notification.notify_on_backup_start) eventLabels.push('Backup start')
        if (notification.notify_on_backup_success) eventLabels.push('Backup success')
        if (notification.notify_on_backup_failure) eventLabels.push('Backup failure')
        if (notification.notify_on_restore_success) eventLabels.push('Restore success')
        if (notification.notify_on_restore_failure) eventLabels.push('Restore failure')
        if (notification.notify_on_check_success) eventLabels.push('Check success')
        if (notification.notify_on_check_failure) eventLabels.push('Check failure')
        if (notification.notify_on_schedule_failure) eventLabels.push('Schedule errors')
        return eventLabels.length > 0 ? eventLabels.join(' · ') : 'No events configured'
      })(),
    },
    {
      icon: <Database size={11} />,
      label: 'Scope',
      value: notification.monitor_all_repositories
        ? 'All repos'
        : `${notification.repositories.length} repo${notification.repositories.length !== 1 ? 's' : ''}`,
    },
    {
      icon: <Clock size={11} />,
      label: 'Last Used',
      value: notification.last_used_at ? formatDateShort(notification.last_used_at) : 'Never',
      tooltip: notification.last_used_at ? notification.last_used_at : '',
    },
  ]

  const badge = (
    <Chip
      icon={notification.enabled ? <Bell size={14} /> : <BellOff size={14} />}
      label={notification.enabled ? 'Active' : 'Muted'}
      color={notification.enabled ? 'success' : 'default'}
      size="small"
      variant="outlined"
    />
  )

  const actions: ActionItem[] = [
    {
      icon: isTesting ? <CircularProgress size={16} /> : <TestTube size={16} />,
      tooltip: 'Send test notification',
      onClick: onTest,
      disabled: isTesting,
    },
    {
      icon: <Copy size={16} />,
      tooltip: 'Duplicate',
      onClick: onDuplicate,
    },
    {
      icon: <Pencil size={16} />,
      tooltip: 'Edit',
      onClick: onEdit,
      color: 'primary',
    },
    {
      icon: <Trash2 size={16} />,
      tooltip: 'Delete',
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
      actions={actions}
    />
  )
}
