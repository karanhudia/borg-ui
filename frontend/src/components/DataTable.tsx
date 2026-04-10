import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  Skeleton,
  SxProps,
  Theme,
  Stack,
  Divider,
  useMediaQuery,
  useTheme,
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
  /** Span both columns in the mobile 2-col grid */
  mobileFullWidth?: boolean
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

  // Mobile rendering
  mobileBreakpoint?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
}

const ACTION_HOVER_BG_BY_COLOR: Record<string, string> = {
  primary: 'rgba(59,130,246,0.12)',
  error: 'rgba(239,68,68,0.12)',
  warning: 'rgba(245,158,11,0.12)',
  success: 'rgba(34,197,94,0.12)',
  info: 'rgba(14,165,233,0.12)',
  default: 'rgba(255,255,255,0.06)',
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
  mobileBreakpoint = 'sm',
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
  const { t } = useTranslation()
  const [rowsPerPage, setRowsPerPage] = useState(getInitialRowsPerPage)
  const theme = useTheme()
  const isMobile = useMediaQuery(theme.breakpoints.down(mobileBreakpoint))

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
  // Loading state — skeleton rows matching the table structure
  if (loading) {
    const skeletonRows = 5
    const rowWidths = [
      [55, 70, 45, 60, 50],
      [70, 50, 65, 40, 55],
      [45, 65, 55, 70, 60],
      [60, 40, 70, 55, 45],
      [50, 60, 45, 65, 70],
    ]
    if (isMobile) {
      return (
        <Paper variant={variant} sx={{ borderRadius, overflow: 'hidden', ...sx }}>
          <Stack divider={<Divider sx={{ borderColor: 'divider' }} />}>
            {Array.from({ length: skeletonRows }).map((_, i) => (
              <Box
                key={i}
                sx={{
                  p: 1.5,
                  opacity: Math.max(0.25, 1 - i * 0.15),
                  animation: `skeletonFadeIn 0.3s ease forwards`,
                  animationDelay: `${i * 50}ms`,
                  '@keyframes skeletonFadeIn': {
                    from: { opacity: 0 },
                    to: { opacity: Math.max(0.25, 1 - i * 0.15) },
                  },
                }}
              >
                <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.25 }}>
                  {columns.map((col, ci) => (
                    <Box
                      key={col.id}
                      sx={{ minWidth: 0, ...(col.mobileFullWidth ? { gridColumn: 'span 2' } : {}) }}
                    >
                      <Skeleton
                        variant="text"
                        width={48}
                        height={9}
                        sx={{ transform: 'none', mb: 0.5, borderRadius: 0.5 }}
                      />
                      <Skeleton
                        variant="text"
                        width={`${rowWidths[i][ci % 5]}%`}
                        height={16}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Box>
                  ))}
                </Box>
              </Box>
            ))}
          </Stack>
        </Paper>
      )
    }
    return (
      <TableContainer component={Paper} variant={variant} sx={{ borderRadius, maxHeight, ...sx }}>
        <Table stickyHeader={stickyHeader} sx={{ tableLayout: 'fixed' }}>
          <TableHead>
            <TableRow>
              {columns.map((column) => (
                <TableCell
                  key={column.id}
                  align={column.align || 'left'}
                  sx={{
                    bgcolor: headerBgColor,
                    fontWeight: 700,
                    color: 'text.disabled',
                    fontSize: '0.7rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    whiteSpace: 'nowrap',
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
                    fontWeight: 700,
                    color: 'text.disabled',
                    fontSize: '0.7rem',
                    textTransform: 'uppercase',
                    letterSpacing: '0.05em',
                    width: '152px',
                    minWidth: '152px',
                    maxWidth: '152px',
                  }}
                >
                  {t('dataTable.actions')}
                </TableCell>
              )}
            </TableRow>
          </TableHead>
          <TableBody>
            {Array.from({ length: skeletonRows }).map((_, i) => (
              <TableRow
                key={i}
                sx={{
                  opacity: Math.max(0.2, 1 - i * 0.15),
                  '&:last-child td': { borderBottom: 0 },
                }}
              >
                {columns.map((column, ci) => (
                  <TableCell
                    key={column.id}
                    sx={{ width: column.width, minWidth: column.minWidth, maxWidth: column.width }}
                  >
                    <Skeleton
                      variant="text"
                      width={`${rowWidths[i][ci % 5]}%`}
                      height={18}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </TableCell>
                ))}
                {actions && actions.length > 0 && (
                  <TableCell align="right" sx={{ width: '130px' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 0.5 }}>
                      {actions.slice(0, 3).map((_, ai) => (
                        <Skeleton
                          key={ai}
                          variant="rounded"
                          width={28}
                          height={28}
                          sx={{ borderRadius: 1 }}
                        />
                      ))}
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

  const renderActions = (
    row: T,
    iconOpacity = 0.45,
    justify: 'flex-start' | 'flex-end' = 'flex-end'
  ) => (
    <Box sx={{ display: 'flex', gap: 0.5, justifyContent: justify, flexWrap: 'nowrap' }}>
      {actions?.map((action, idx) => {
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

  if (isMobile) {
    return (
      <Paper variant={variant} sx={{ borderRadius, overflow: 'hidden', ...sx }}>
        <Stack divider={<Divider sx={{ borderColor: 'divider' }} />}>
          {paginatedData.map((row) => (
            <Box
              key={getRowKey(row)}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
              sx={{
                p: 1.5,
                ...(enableHover && {
                  '&:hover': {
                    bgcolor: 'rgba(255,255,255,0.02)',
                  },
                }),
                ...(enablePointer &&
                  onRowClick && {
                    cursor: 'pointer',
                  }),
                transition: 'background-color 180ms ease',
              }}
            >
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: '1fr 1fr',
                  gap: 1.25,
                }}
              >
                {columns.map((column) => (
                  <Box
                    key={column.id}
                    sx={{
                      minWidth: 0,
                      overflow: 'hidden',
                      ...(column.mobileFullWidth && { gridColumn: 'span 2' }),
                    }}
                  >
                    <Typography
                      variant="caption"
                      sx={{
                        display: 'block',
                        mb: 0.25,
                        color: 'text.secondary',
                        fontWeight: 700,
                        letterSpacing: '0.03em',
                        textTransform: 'uppercase',
                        fontSize: '0.6rem',
                      }}
                    >
                      {column.label}
                    </Typography>
                    <Box sx={{ minWidth: 0, overflow: 'hidden' }}>
                      {column.render
                        ? column.render(row)
                        : ((row as Record<string, unknown>)[column.id] as React.ReactNode)}
                    </Box>
                  </Box>
                ))}
                {actions && actions.length > 0 && (
                  <Box sx={{ minWidth: 0 }}>
                    <Typography
                      variant="caption"
                      sx={{
                        display: 'block',
                        mb: 0.25,
                        color: 'text.secondary',
                        fontWeight: 700,
                        letterSpacing: '0.03em',
                        textTransform: 'uppercase',
                        fontSize: '0.6rem',
                      }}
                    >
                      {t('dataTable.actions')}
                    </Typography>
                    {renderActions(row, 0.7, 'flex-start')}
                  </Box>
                )}
              </Box>
            </Box>
          ))}
        </Stack>
        {data.length > 0 && (
          <TablePagination
            component="div"
            count={data.length}
            page={page}
            onPageChange={handleChangePage}
            rowsPerPage={rowsPerPage}
            onRowsPerPageChange={handleChangeRowsPerPage}
            rowsPerPageOptions={rowsPerPageOptions}
            labelRowsPerPage={t('dataTable.rowsPerPage')}
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
                flexWrap: 'wrap',
                rowGap: 1,
              },
              '.MuiTablePagination-spacer': {
                display: 'none',
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
                marginLeft: 'auto',
              },
            }}
          />
        )}
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
                  fontWeight: 700,
                  color: 'text.disabled',
                  fontSize: '0.7rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  whiteSpace: 'nowrap',
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
                  fontWeight: 700,
                  color: 'text.disabled',
                  fontSize: '0.7rem',
                  textTransform: 'uppercase',
                  letterSpacing: '0.05em',
                  whiteSpace: 'nowrap',
                  width: '152px',
                  minWidth: '152px',
                  maxWidth: '152px',
                }}
              >
                {t('dataTable.actions')}
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
                    bgcolor: 'rgba(255,255,255,0.03)',
                    '& .MuiIconButton-root': {
                      opacity: 0.7,
                    },
                  },
                }),
                ...(enablePointer &&
                  onRowClick && {
                    cursor: 'pointer',
                  }),
                '&:last-child td': {
                  borderBottom: 0,
                },
                transition: 'background-color 180ms ease',
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
                  {renderActions(row)}
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
          labelRowsPerPage={t('dataTable.rowsPerPage')}
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
