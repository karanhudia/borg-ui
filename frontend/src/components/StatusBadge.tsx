import React from 'react'
import { Chip, Tooltip } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { CircleMinus } from 'lucide-react'
import { statusLabel } from './jobs/jobLabels'

interface StatusBadgeProps {
  status: string
  size?: 'small' | 'medium'
  variant?: 'filled' | 'outlined'
  tooltip?: React.ReactNode
}

/**
 * Standardized status badge component used across Activity, Schedule, and Dashboard views
 * Shows consistent color and label representation for all job statuses.
 */
export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'small',
  variant = 'outlined',
  tooltip,
}) => {
  const { t } = useTranslation()

  const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'info' | 'default' => {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'success':
        return 'success'
      case 'completed_with_warnings':
      case 'needs_backup':
        return 'warning'
      case 'failed':
      case 'error':
        return 'error'
      case 'running':
      case 'in_progress':
        return 'info'
      case 'pending':
      case 'skipped':
        return 'default'
      default:
        return 'default'
    }
  }

  const label = statusLabel(status, t)

  return (
    <Tooltip title={tooltip || label} arrow>
      <Chip
        icon={status.toLowerCase() === 'skipped' ? <CircleMinus size={15} /> : undefined}
        label={label}
        color={getStatusColor(status)}
        size={size}
        variant={variant}
        sx={{
          fontWeight: 500,
          maxWidth: '100%',
          minWidth: 0,
          '& .MuiChip-label': {
            overflow: 'hidden',
            textOverflow: 'ellipsis',
          },
        }}
      />
    </Tooltip>
  )
}

export default StatusBadge
