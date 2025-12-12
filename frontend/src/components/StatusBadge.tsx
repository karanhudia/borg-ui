import React from 'react'
import { Chip } from '@mui/material'

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
        return 'Completed'
      case 'completed_with_warnings':
        return 'Completed with Warnings'
      case 'failed':
        return 'Failed'
      case 'running':
      case 'in_progress':
        return 'Running'
      case 'pending':
        return 'Pending'
      case 'cancelled':
        return 'Cancelled'
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
