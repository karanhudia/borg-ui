import React from 'react'
import { Box, IconButton, Tooltip } from '@mui/material'

export interface ActionButton<T> {
  icon: React.ReactNode
  label: string
  onClick: (row: T) => void
  color?: 'primary' | 'error' | 'warning' | 'success' | 'info' | 'default'
  disabled?: (row: T) => boolean
  show?: (row: T) => boolean
  tooltip?: string | ((row: T) => string)
}

const ACTION_HOVER_BG_BY_COLOR: Record<string, string> = {
  primary: 'rgba(59,130,246,0.12)',
  error: 'rgba(239,68,68,0.12)',
  warning: 'rgba(245,158,11,0.12)',
  success: 'rgba(34,197,94,0.12)',
  info: 'rgba(14,165,233,0.12)',
  default: 'rgba(255,255,255,0.06)',
}

interface RowActionsProps<T> {
  row: T
  actions?: ActionButton<T>[]
  iconOpacity?: number
  justify?: 'flex-start' | 'flex-end'
}

// The icon buttons at the end of a table row or a timeline entry. One
// renderer, so a job's actions look the same wherever the job is listed.
export default function RowActions<T>({
  row,
  actions = [],
  iconOpacity = 0.45,
  justify = 'flex-end',
}: RowActionsProps<T>) {
  return (
    <Box sx={{ display: 'flex', gap: 0.5, justifyContent: justify, flexWrap: 'nowrap' }}>
      {actions.map((action, idx) => {
        const shouldShow = action.show ? action.show(row) : true
        if (!shouldShow) return null

        const isDisabled = action.disabled ? action.disabled(row) : false
        const tooltipText =
          typeof action.tooltip === 'function'
            ? action.tooltip(row)
            : action.tooltip || action.label

        const hoverBg = ACTION_HOVER_BG_BY_COLOR[action.color || 'default']

        return (
          <Tooltip key={idx} title={tooltipText} arrow>
            <span>
              <IconButton
                size="small"
                color={action.color || 'default'}
                onClick={(e) => {
                  e.stopPropagation()
                  action.onClick(row)
                }}
                disabled={isDisabled}
                aria-label={tooltipText}
                sx={{
                  borderRadius: 1,
                  opacity: iconOpacity,
                  transition: 'opacity 140ms ease, background-color 140ms ease',
                  '&:hover': {
                    opacity: 1,
                    bgcolor: hoverBg,
                  },
                  '&.Mui-disabled': { opacity: 0.2 },
                }}
              >
                {action.icon}
              </IconButton>
            </span>
          </Tooltip>
        )
      })}
    </Box>
  )
}
