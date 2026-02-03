import React, { useState } from 'react'
import {
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  TablePagination,
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

  // Pagination
  defaultRowsPerPage?: number
  rowsPerPageOptions?: number[]
  tableId?: string // Unique identifier for localStorage persistence

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
  defaultRowsPerPage = 10,
  rowsPerPageOptions = [5, 10, 25, 50, 100],
  tableId,
  sx,
}: DataTableProps<T>) {
  // Load saved rows per page from localStorage if available
  const getInitialRowsPerPage = () => {
    if (!tableId) return defaultRowsPerPage
    const saved = localStorage.getItem(`table-rows-per-page-${tableId}`)
    if (saved) {
      const parsed = parseInt(saved, 10)
      // Validate that the saved value is in the options
      if (rowsPerPageOptions.includes(parsed)) {
        return parsed
      }
    }
    return defaultRowsPerPage
  }

  // Pagination state
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(getInitialRowsPerPage)

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newRowsPerPage = parseInt(event.target.value, 10)
    setRowsPerPage(newRowsPerPage)
    setPage(0) // Reset to first page when changing rows per page

    // Save to localStorage if tableId is provided
    if (tableId) {
      localStorage.setItem(`table-rows-per-page-${tableId}`, String(newRowsPerPage))
    }
  }

  // Calculate paginated data
  const paginatedData = data.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
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
      <Table stickyHeader={stickyHeader} sx={{ tableLayout: 'fixed' }}>
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
                  maxWidth: column.width,
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
                  width: '130px',
                  minWidth: '130px',
                  maxWidth: '130px',
                }}
              >
                Actions
              </TableCell>
            )}
          </TableRow>
        </TableHead>
        <TableBody>
          {paginatedData.map((row) => (
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
                    maxWidth: column.width,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {column.render
                    ? column.render(row)
                    : ((row as Record<string, unknown>)[column.id] as React.ReactNode)}
                </TableCell>
              ))}
              {actions && actions.length > 0 && (
                <TableCell
                  align="right"
                  sx={{ width: '130px', minWidth: '130px', maxWidth: '130px' }}
                >
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
      {data.length > 0 && (
        <TablePagination
          component="div"
          count={data.length}
          page={page}
          onPageChange={handleChangePage}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={handleChangeRowsPerPage}
          rowsPerPageOptions={rowsPerPageOptions}
          labelRowsPerPage="Rows per page:"
          labelDisplayedRows={({ from, to, count }) =>
            `${from}–${to} of ${count !== -1 ? count : `more than ${to}`}`
          }
          sx={{
            borderTop: 1,
            borderColor: 'divider',
            '.MuiTablePagination-toolbar': {
              minHeight: '64px',
              paddingLeft: 2,
              paddingRight: 1,
            },
            '.MuiTablePagination-selectLabel, .MuiTablePagination-displayedRows': {
              marginTop: 0,
              marginBottom: 0,
              display: 'flex',
              alignItems: 'center',
            },
            '.MuiTablePagination-select': {
              paddingTop: 1,
              paddingBottom: 1,
              paddingLeft: 1,
              paddingRight: 4,
              display: 'flex',
              alignItems: 'center',
            },
            '.MuiTablePagination-actions': {
              marginLeft: 2,
            },
          }}
        />
      )}
    </TableContainer>
  )
}
