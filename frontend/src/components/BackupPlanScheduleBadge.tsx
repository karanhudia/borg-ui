import { Chip, Tooltip } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { useTranslation } from 'react-i18next'
import { formatCronHuman, formatDate } from '../utils/dateUtils'

interface BackupPlanScheduleBadgeProps {
  scheduleEnabled: boolean
  nextRun?: string | null
  cronExpression?: string | null
  timezone?: string | null
}

function formatNextRunLabel(nextRun: string): string {
  return new Date(nextRun).toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export default function BackupPlanScheduleBadge({
  scheduleEnabled,
  nextRun,
  cronExpression,
  timezone,
}: BackupPlanScheduleBadgeProps) {
  const { t } = useTranslation()
  const theme = useTheme()

  if (!scheduleEnabled) return null

  const label = nextRun
    ? t('backupPlans.status.nextRunBadge', { when: formatNextRunLabel(nextRun) })
    : t('backupPlans.status.scheduledBadge')
  const title = nextRun
    ? t('backupPlans.status.nextRunTitle', {
        date: formatDate(nextRun),
        timezone: timezone || 'UTC',
      })
    : t('backupPlans.status.scheduleTitle', {
        schedule: cronExpression
          ? formatCronHuman(cronExpression)
          : t('backupPlans.status.scheduledBadge'),
        timezone: timezone || 'UTC',
      })
  const color = theme.palette.success.main

  return (
    <Tooltip title={title} arrow placement="left">
      <Chip
        label={label}
        size="small"
        sx={{
          height: 20,
          maxWidth: { xs: 160, sm: 190 },
          minWidth: 0,
          bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.12 : 0.09),
          color,
          border: '1px solid',
          borderColor: alpha(color, theme.palette.mode === 'dark' ? 0.32 : 0.24),
          fontSize: '0.64rem',
          fontWeight: 700,
          '& .MuiChip-label': {
            px: 0.9,
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          },
        }}
      />
    </Tooltip>
  )
}
