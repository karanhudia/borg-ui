import React from 'react'
import { Chip } from '@mui/material'
import { useTranslation } from 'react-i18next'

interface StatusBadgeProps {
  status: string
  size?: 'small' | 'medium'
  variant?: 'filled' | 'outlined'
}

/**
 * Standardized status badge component used across Activity, Schedule, and Dashboard views
 * Shows consistent color and label representation for all job statuses (no icon)
 */
export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'small',
  variant = 'filled',
}) => {
  const { t } = useTranslation()

  const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'info' | 'default' => {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'success':
        return 'success'
      case 'completed_with_warnings':
        return 'warning'
      case 'failed':
      case 'error':
        return 'error'
      case 'running':
      case 'in_progress':
        return 'info'
      case 'pending':
        return 'default'
      default:
        return 'default'
    }
  }

  const getStatusLabel = (status: string): string => {
    switch (status.toLowerCase()) {
      case 'completed':
        return t('status.completed')
      case 'completed_with_warnings':
        return t('status.completedWithWarnings')
      case 'failed':
        return t('status.failed')
      case 'running':
      case 'in_progress':
        return t('status.running')
      case 'pending':
        return t('status.pending')
      case 'cancelled':
        return t('status.cancelled')
      default:
        return status.charAt(0).toUpperCase() + status.slice(1)
    }
  }

  return (
    <Chip
      label={getStatusLabel(status)}
      color={getStatusColor(status)}
      size={size}
      variant={variant}
      sx={{ fontWeight: 500 }}
    />
  )
}

export default StatusBadge
