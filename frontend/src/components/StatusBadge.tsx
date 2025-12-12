import React from 'react'
import { Box, Chip } from '@mui/material'
import {
  CheckCircle,
  AlertTriangle,
  XCircle,
  Play,
  Clock,
  RefreshCw,
} from 'lucide-react'

interface StatusBadgeProps {
  status: string
  size?: 'small' | 'medium'
  variant?: 'filled' | 'outlined'
}

/**
 * Standardized status badge component used across Activity, Schedule, and Dashboard views
 * Ensures consistent icon, color, and label representation for all job statuses
 */
export const StatusBadge: React.FC<StatusBadgeProps> = ({
  status,
  size = 'small',
  variant = 'filled',
}) => {
  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'success':
        return <CheckCircle size={16} />
      case 'completed_with_warnings':
        return <AlertTriangle size={16} />
      case 'failed':
      case 'error':
        return <XCircle size={16} />
      case 'running':
      case 'in_progress':
        return <RefreshCw size={16} className="animate-spin" />
      case 'pending':
        return <Clock size={16} />
      default:
        return <Clock size={16} />
    }
  }

  const getStatusColor = (
    status: string
  ): 'success' | 'error' | 'warning' | 'info' | 'default' => {
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
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      {getStatusIcon(status)}
      <Chip
        label={getStatusLabel(status)}
        color={getStatusColor(status)}
        size={size}
        variant={variant}
        sx={{ fontWeight: 500 }}
      />
    </Box>
  )
}

export default StatusBadge
