import React from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  IconButton,
  Tooltip,
  Box,
  Typography,
  CircularProgress,
  SxProps,
  Theme,
} from '@mui/material'

export interface Column<T> {
  id: string
  label: string
  align?: 'left' | 'right' | 'center'
  width?: string
  minWidth?: string
  fontWeight?: number
  render?: (row: T) => React.ReactNode
  sortable?: boolean
}

export interface ActionButton<T> {
  icon: React.ReactNode
  label: string
  onClick: (row: T) => void
  color?: 'primary' | 'error' | 'warning' | 'success' | 'info' | 'default'
  disabled?: (row: T) => boolean
  show?: (row: T) => boolean
  tooltip?: string | ((row: T) => string)
}

export interface DataTableProps<T> {
  // Data
  data: T[]
  columns: Column<T>[]

  // Actions
  actions?: ActionButton<T>[]

  // Row behavior
  onRowClick?: (row: T) => void
  getRowKey: (row: T) => string | number

  // Styling
  headerBgColor?: string
  enableHover?: boolean
  enablePointer?: boolean
  stickyHeader?: boolean

  // States
  loading?: boolean
  emptyState?: {
    icon: React.ReactNode
    title: string
    description?: string
  }

  // Table wrapper
  variant?: 'outlined' | 'elevation'
  borderRadius?: number
  maxHeight?: string | number

  // Additional features
  sx?: SxProps<Theme>
}

export default function DataTable<T>({
  data,
  columns,
  actions,
  onRowClick,
  getRowKey,
  headerBgColor = 'background.default',
  enableHover = true,
  enablePointer = false,
  stickyHeader = false,
  loading = false,
  emptyState,
  variant = 'outlined',
  borderRadius = 2,
  maxHeight,
  sx,
}: DataTableProps<T>) {
  // Loading state
  if (loading) {
    return (
      <Paper variant={variant} sx={{ borderRadius, ...sx }}>
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', py: 8 }}>
          <CircularProgress />
        </Box>
      </Paper>
    )
  }

  // Empty state
  if (data.length === 0 && emptyState) {
    return (
      <Paper variant={variant} sx={{ borderRadius, ...sx }}>
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 8,
            px: 3,
            textAlign: 'center',
          }}
        >
          <Box sx={{ mb: 2, color: 'text.secondary', opacity: 0.6 }}>{emptyState.icon}</Box>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            {emptyState.title}
          </Typography>
          {emptyState.description && (
            <Typography variant="body2" color="text.secondary">
              {emptyState.description}
            </Typography>
          )}
        </Box>
      </Paper>
    )
  }

  return (
    <TableContainer
      component={Paper}
      variant={variant}
      sx={{
        borderRadius,
        maxHeight,
        ...sx,
      }}
    >
      <Table stickyHeader={stickyHeader}>
        <TableHead>
          <TableRow>
            {columns.map((column) => (
              <TableCell
                key={column.id}
                align={column.align || 'left'}
                sx={{
                  bgcolor: headerBgColor,
                  fontWeight: column.fontWeight || 600,
                  color: 'text.secondary',
                  width: column.width,
                  minWidth: column.minWidth,
                }}
              >
                {column.label}
              </TableCell>
            ))}
            {actions && actions.length > 0 && (
              <TableCell
                align="right"
                sx={{
                  bgcolor: headerBgColor,
                  fontWeight: 600,
                  color: 'text.secondary',
                  width: '140px',
                  minWidth: '140px',
                }}
              >
                Actions
              </TableCell>
            )}
          </TableRow>
        </TableHead>
        <TableBody>
          {data.map((row) => (
            <TableRow
              key={getRowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              sx={{
                ...(enableHover && {
                  '&:hover': {
                    bgcolor: 'action.hover',
                  },
                }),
                ...(enablePointer &&
                  onRowClick && {
                  cursor: 'pointer',
                }),
                '&:last-child td': {
                  borderBottom: 0,
                },
                transition: 'background-color 0.2s',
              }}
            >
              {columns.map((column) => (
                <TableCell
                  key={column.id}
                  align={column.align || 'left'}
                  sx={{
                    width: column.width,
                    minWidth: column.minWidth,
                  }}
                >

                  {column.render
                    ? column.render(row)
                    : ((row as Record<string, unknown>)[column.id] as React.ReactNode)}
                </TableCell>
              ))}
              {actions && actions.length > 0 && (
                <TableCell align="right" sx={{ width: '140px', minWidth: '140px' }}>
                  <Box sx={{ display: 'flex', gap: 0.5, justifyContent: 'flex-end' }}>
                    {actions.map((action, idx) => {
                      const shouldShow = action.show ? action.show(row) : true
                      if (!shouldShow) return null

                      const isDisabled = action.disabled ? action.disabled(row) : false
                      const tooltipText =
                        typeof action.tooltip === 'function'
                          ? action.tooltip(row)
                          : action.tooltip || action.label

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
                            >
                              {action.icon}
                            </IconButton>
                          </span>
                        </Tooltip>
                      )
                    })}
                  </Box>
                </TableCell>
              )}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </TableContainer>
  )
}
