import React, { useState, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import {
  Box,
  Typography,
  TablePagination,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  alpha,
  useTheme,
  Skeleton,
} from '@mui/material'
import {
  FolderOpen,
  ChevronDown,
  Calendar,
  Archive as ArchiveIcon,
  List,
  Layers,
} from 'lucide-react'
import ArchiveCard from './ArchiveCard'
import ArchiveCardSkeleton from './ArchiveCardSkeleton'
import { Archive } from '../types'
import {
  groupArchivesByTime,
  getGroupsArray,
  sortArchives,
  filterArchivesByType,
  type SortOption,
  type TimeGroup,
  type FilterType,
} from '../utils/archiveGrouping'

interface ArchivesListProps {
  archives: Archive[]
  repositoryName: string
  loading: boolean
  onViewArchive: (archive: Archive) => void
  onRestoreArchive: (archive: Archive) => void
  onMountArchive: (archive: Archive) => void
  onDeleteArchive: (archiveName: string) => void
  mountDisabled?: boolean
  canDelete?: boolean
  defaultRowsPerPage?: number
  rowsPerPageOptions?: number[]
}

export default function ArchivesList({
  archives,
  loading,
  onViewArchive,
  onRestoreArchive,
  onMountArchive,
  onDeleteArchive,
  mountDisabled = false,
  canDelete = true,
  defaultRowsPerPage = 10,
  rowsPerPageOptions = [5, 10, 25, 50, 100],
}: ArchivesListProps) {
  // Load saved preferences from localStorage
  const getInitialRowsPerPage = () => {
    const saved = localStorage.getItem('archives-list-rows-per-page')
    if (saved) {
      const parsed = parseInt(saved, 10)
      if (rowsPerPageOptions.includes(parsed)) {
        return parsed
      }
    }
    return defaultRowsPerPage
  }

  const getInitialSortBy = (): SortOption => {
    const saved = localStorage.getItem('archives-list-sort-by')
    if (saved && ['date-desc', 'date-asc'].includes(saved)) {
      return saved as SortOption
    }
    return 'date-desc'
  }

  const getInitialGroupingEnabled = (): boolean => {
    const saved = localStorage.getItem('archives-list-grouping-enabled')
    if (saved === 'true') return true
    if (saved === 'false') return false
    return false // Default to false (flat list)
  }

  const getInitialExpandedGroups = (): Set<TimeGroup> => {
    const saved = localStorage.getItem('archives-list-expanded-groups')
    if (saved) {
      try {
        const parsed = JSON.parse(saved) as TimeGroup[]
        return new Set(parsed)
      } catch {
        // Fall through to defaults
      }
    }
    // Default: today and yesterday expanded
    return new Set(['today', 'yesterday'])
  }

  const getInitialFilter = (): FilterType => {
    const saved = localStorage.getItem('archives-list-filter')
    if (saved && ['all', 'scheduled', 'manual'].includes(saved)) {
      return saved as FilterType
    }
    return 'all'
  }

  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // State
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(getInitialRowsPerPage)
  const [sortBy, setSortBy] = useState<SortOption>(getInitialSortBy)
  const [groupingEnabled, setGroupingEnabled] = useState(getInitialGroupingEnabled)
  const [expandedGroups, setExpandedGroups] = useState<Set<TimeGroup>>(getInitialExpandedGroups)
  const [filter, setFilter] = useState<FilterType>(getInitialFilter)

  // Filter and sort archives
  const sortedArchives = useMemo(() => {
    // Apply filter first
    const filtered = filterArchivesByType(archives, filter)
    // When grouping is enabled, always sort by date-desc for proper grouping
    const effectiveSortBy = groupingEnabled ? 'date-desc' : sortBy
    return sortArchives(filtered, effectiveSortBy)
  }, [archives, filter, sortBy, groupingEnabled])

  // Group archives
  const groupedArchives = useMemo(() => {
    if (!groupingEnabled) return null
    const grouped = groupArchivesByTime(sortedArchives)
    return getGroupsArray(grouped)
  }, [sortedArchives, groupingEnabled])

  // Handlers
  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newRowsPerPage = parseInt(event.target.value, 10)
    setRowsPerPage(newRowsPerPage)
    setPage(0)
    localStorage.setItem('archives-list-rows-per-page', String(newRowsPerPage))
  }

  const handleSortChange = (event: { target: { value: string } }) => {
    const newSort = event.target.value as SortOption
    setSortBy(newSort)
    setPage(0)
    localStorage.setItem('archives-list-sort-by', newSort)
  }

  const handleToggleGroup = (groupKey: TimeGroup) => {
    const newExpanded = new Set(expandedGroups)
    if (newExpanded.has(groupKey)) {
      newExpanded.delete(groupKey)
    } else {
      newExpanded.add(groupKey)
    }
    setExpandedGroups(newExpanded)
    localStorage.setItem('archives-list-expanded-groups', JSON.stringify(Array.from(newExpanded)))
  }

  const handleViewModeChange = (_event: React.MouseEvent<HTMLElement>, newMode: string | null) => {
    if (newMode !== null) {
      const enabled = newMode === 'grouped'
      setGroupingEnabled(enabled)
      setPage(0)
      localStorage.setItem('archives-list-grouping-enabled', String(enabled))
    }
  }

  const handleFilterChange = (event: { target: { value: string } }) => {
    const filterValue = event.target.value as FilterType
    setFilter(filterValue)
    setPage(0)
    localStorage.setItem('archives-list-filter', filterValue)
  }

  const tableHeader = (
    <Box
      sx={{
        display: { xs: 'none', md: 'grid' },
        gridTemplateColumns: '1fr 64px 120px auto',
        alignItems: 'center',
        gap: 1,
        px: 2,
        py: 1,
        bgcolor: isDark ? alpha('#fff', 0.03) : alpha('#000', 0.02),
        borderBottom: '1px solid',
        borderBottomColor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
        fontSize: '0.65rem',
        fontWeight: 600,
        textTransform: 'uppercase',
        letterSpacing: '0.06em',
        color: 'text.disabled',
      }}
    >
      <span>{t('archivesList.columnArchive', 'Archive')}</span>
      <span>{t('archivesList.columnType', 'Type')}</span>
      <span>{t('archivesList.columnDate', 'Date')}</span>
      <Box sx={{ textAlign: 'right' }}>{t('archivesList.columnActions', 'Actions')}</Box>
    </Box>
  )

  // Loading State
  if (loading) {
    return (
      <Box>
        {/* Header bar skeleton — mirrors the real header exactly */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: { xs: 'column', sm: 'row' },
            justifyContent: 'space-between',
            alignItems: { xs: 'flex-start', sm: 'center' },
            gap: { xs: 1.5, sm: 1 },
            px: 2,
            py: 1.25,
            mb: 2.5,
            borderRadius: 2,
            bgcolor: isDark
              ? alpha(theme.palette.primary.main, 0.1)
              : alpha(theme.palette.primary.main, 0.06),
            border: '1px solid',
            borderColor: isDark
              ? alpha(theme.palette.primary.main, 0.2)
              : alpha(theme.palette.primary.main, 0.15),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.25 }}>
            <Skeleton variant="rounded" width={64} height={19} sx={{ borderRadius: 1 }} />
            <Skeleton variant="rounded" width={22} height={20} sx={{ borderRadius: 1 }} />
          </Box>
          <Box sx={{ display: 'flex', gap: 0.5, alignItems: 'center' }}>
            <Skeleton variant="rounded" width={72} height={20} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={60} height={20} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={72} height={20} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={44} height={20} sx={{ borderRadius: 1.5 }} />
            <Skeleton variant="rounded" width={44} height={20} sx={{ borderRadius: 1.5 }} />
          </Box>
        </Box>
        <Box
          sx={{
            borderRadius: 3,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
            overflow: 'hidden',
          }}
        >
          {[0, 1, 2, 3, 4, 5, 6, 7, 8, 9].map((i) => (
            <ArchiveCardSkeleton key={i} index={i} />
          ))}
        </Box>
      </Box>
    )
  }

  // Empty State
  if (archives.length === 0) {
    return (
      <Box
        sx={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          py: 8,
          color: 'text.secondary',
        }}
      >
        <FolderOpen size={48} style={{ marginBottom: 16 }} />
        <Typography variant="body1" color="text.secondary">
          {t('archivesList.empty')}
        </Typography>
      </Box>
    )
  }

  // Archives List
  return (
    <Box>
      {/* Sticky panel header: title + count + controls */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: { xs: 1.5, sm: 1 },
          px: 2,
          py: 1.25,
          mb: 2.5,
          borderRadius: 2,
          bgcolor: isDark
            ? alpha(theme.palette.primary.main, 0.1)
            : alpha(theme.palette.primary.main, 0.06),
          border: '1px solid',
          borderColor: isDark
            ? alpha(theme.palette.primary.main, 0.2)
            : alpha(theme.palette.primary.main, 0.15),
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1.25, flexShrink: 0 }}>
          <Typography variant="h6" fontWeight={700} sx={{ fontSize: '0.95rem' }}>
            Archives
          </Typography>
          <Typography
            variant="body2"
            sx={{
              fontSize: '0.72rem',
              fontWeight: 600,
              px: 0.75,
              py: 0.2,
              borderRadius: 1,
              bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.06),
              color: 'text.secondary',
              lineHeight: 1.6,
            }}
          >
            {filter === 'all' || sortedArchives.length === archives.length
              ? archives.length
              : `${sortedArchives.length}/${archives.length}`}
          </Typography>
        </Box>

        {/* View controls */}
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'row',
            flexWrap: 'wrap',
            gap: 1,
            alignItems: 'center',
            width: { xs: '100%', sm: 'auto' },
          }}
        >
          {/* Sort group — flat view only */}
          {!groupingEnabled && (
            <>
              <Box
                sx={{
                  display: 'flex',
                  gap: 0.5,
                  alignItems: 'center',
                }}
              >
                {(['date-desc', 'date-asc'] as SortOption[]).map((opt) => {
                  const active = sortBy === opt
                  return (
                    <Box
                      key={opt}
                      onClick={() => handleSortChange({ target: { value: opt } })}
                      sx={{
                        display: 'flex',
                        alignItems: 'center',
                        gap: 0.5,
                        px: 1.25,
                        py: 0.5,
                        borderRadius: 1.5,
                        border: '1px solid',
                        cursor: 'pointer',
                        userSelect: 'none',
                        fontSize: '0.72rem',
                        fontWeight: 600,
                        transition: 'all 150ms',
                        borderColor: active
                          ? alpha(theme.palette.primary.main, isDark ? 0.45 : 0.35)
                          : isDark
                            ? alpha('#fff', 0.1)
                            : alpha('#000', 0.1),
                        bgcolor: active
                          ? alpha(theme.palette.primary.main, isDark ? 0.14 : 0.08)
                          : 'transparent',
                        color: active ? 'primary.main' : 'text.secondary',
                        '&:hover': {
                          borderColor: alpha(theme.palette.primary.main, 0.35),
                          color: 'primary.main',
                        },
                      }}
                    >
                      {opt === 'date-desc'
                        ? t('archivesList.newestFirst')
                        : t('archivesList.oldestFirst')}
                    </Box>
                  )
                })}
              </Box>
              {/* Group divider */}
              <Box
                sx={{
                  width: '1px',
                  alignSelf: 'stretch',
                  bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
                  flexShrink: 0,
                  display: { xs: 'none', sm: 'block' },
                }}
              />
            </>
          )}

          {/* Filter group */}
          <Box
            sx={{
              display: 'flex',
              gap: 0.5,
              alignItems: 'center',
            }}
          >
            {(['all', 'scheduled', 'manual'] as FilterType[]).map((opt) => {
              const active = filter === opt
              const label =
                opt === 'all'
                  ? t('archivesList.allArchives')
                  : opt === 'scheduled'
                    ? t('archivesList.scheduled')
                    : t('archivesList.manual')
              const color =
                opt === 'scheduled'
                  ? theme.palette.success.main
                  : opt === 'manual'
                    ? theme.palette.primary.main
                    : undefined
              return (
                <Box
                  key={opt}
                  onClick={() =>
                    handleFilterChange({
                      target: { value: opt },
                    } as React.ChangeEvent<HTMLSelectElement>)
                  }
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    px: 1.25,
                    py: 0.5,
                    borderRadius: 1.5,
                    border: '1px solid',
                    cursor: 'pointer',
                    userSelect: 'none',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    transition: 'all 150ms',
                    borderColor:
                      active && color
                        ? alpha(color, isDark ? 0.45 : 0.35)
                        : active
                          ? isDark
                            ? alpha('#fff', 0.2)
                            : alpha('#000', 0.15)
                          : isDark
                            ? alpha('#fff', 0.1)
                            : alpha('#000', 0.1),
                    bgcolor:
                      active && color
                        ? alpha(color, isDark ? 0.14 : 0.08)
                        : active
                          ? isDark
                            ? alpha('#fff', 0.06)
                            : alpha('#000', 0.05)
                          : 'transparent',
                    color: active && color ? color : active ? 'text.primary' : 'text.secondary',
                    '&:hover': {
                      borderColor: color
                        ? alpha(color, 0.35)
                        : isDark
                          ? alpha('#fff', 0.2)
                          : alpha('#000', 0.15),
                      color: color ?? 'text.primary',
                    },
                  }}
                >
                  {label}
                </Box>
              )
            })}
          </Box>

          {/* Group divider */}
          <Box
            sx={{
              width: '1px',
              alignSelf: 'stretch',
              bgcolor: isDark ? alpha('#fff', 0.08) : alpha('#000', 0.08),
              flexShrink: 0,
              display: { xs: 'none', sm: 'block' },
            }}
          />

          {/* View mode group */}
          <Box
            sx={{
              display: 'flex',
              gap: 0.5,
              alignItems: 'center',
            }}
          >
            {(['grouped', 'flat'] as const).map((mode) => {
              const active = (groupingEnabled ? 'grouped' : 'flat') === mode
              return (
                <Box
                  key={mode}
                  onClick={(e) =>
                    handleViewModeChange(e as unknown as React.MouseEvent<HTMLElement>, mode)
                  }
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    px: 1.25,
                    py: 0.5,
                    borderRadius: 1.5,
                    border: '1px solid',
                    cursor: 'pointer',
                    userSelect: 'none',
                    fontSize: '0.72rem',
                    fontWeight: 600,
                    transition: 'all 150ms',
                    borderColor: active
                      ? isDark
                        ? alpha('#fff', 0.2)
                        : alpha('#000', 0.15)
                      : isDark
                        ? alpha('#fff', 0.1)
                        : alpha('#000', 0.1),
                    bgcolor: active
                      ? isDark
                        ? alpha('#fff', 0.06)
                        : alpha('#000', 0.05)
                      : 'transparent',
                    color: active ? 'text.primary' : 'text.secondary',
                    '&:hover': {
                      borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.15),
                      color: 'text.primary',
                    },
                  }}
                >
                  {mode === 'grouped' ? <Layers size={13} /> : <List size={13} />}
                  {mode === 'grouped' ? t('archivesList.grouped') : t('archivesList.list')}
                </Box>
              )
            })}
          </Box>
        </Box>
      </Box>

      {/* Empty state for filtered results */}
      {sortedArchives.length === 0 && archives.length > 0 ? (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            py: 8,
            color: 'text.secondary',
          }}
        >
          <FolderOpen size={48} style={{ marginBottom: 16 }} />
          <Typography variant="body1" color="text.secondary">
            {filter === 'scheduled'
              ? t('archivesList.noScheduledArchives')
              : t('archivesList.noManualArchives')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {t('archivesList.tryDifferentFilter')}
          </Typography>
        </Box>
      ) : groupingEnabled && groupedArchives ? (
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
          {groupedArchives.map((group) => (
            <Accordion
              key={group.key}
              expanded={expandedGroups.has(group.key)}
              onChange={() => handleToggleGroup(group.key)}
              sx={{
                borderRadius: 2,
                '&:before': { display: 'none' },
                boxShadow: 'none',
                border: '1px solid',
                borderColor: 'divider',
              }}
            >
              <AccordionSummary
                expandIcon={<ChevronDown size={20} />}
                sx={{
                  '&:hover': { bgcolor: 'action.hover' },
                  borderRadius: 2,
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                  {group.iconName === 'Calendar' ? (
                    <Calendar size={20} />
                  ) : (
                    <ArchiveIcon size={20} />
                  )}
                  <Typography variant="h6" fontSize="1rem" fontWeight={600}>
                    {group.label}
                  </Typography>
                  <Chip label={group.archives.length} size="small" sx={{ ml: 'auto', mr: 2 }} />
                </Box>
              </AccordionSummary>
              <AccordionDetails sx={{ pt: 0, pb: 0, px: 0 }}>
                {group.archives.map((archive) => (
                  <ArchiveCard
                    key={archive.id}
                    archive={archive}
                    onView={onViewArchive}
                    onRestore={onRestoreArchive}
                    onMount={onMountArchive}
                    onDelete={onDeleteArchive}
                    mountDisabled={mountDisabled}
                    canDelete={canDelete}
                  />
                ))}
              </AccordionDetails>
            </Accordion>
          ))}
        </Box>
      ) : (
        <>
          <Box
            sx={{
              borderRadius: 3,
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
              overflow: 'hidden',
              mb: 2,
            }}
          >
            {tableHeader}
            {sortedArchives
              .slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
              .map((archive) => (
                <ArchiveCard
                  key={archive.id}
                  archive={archive}
                  onView={onViewArchive}
                  onRestore={onRestoreArchive}
                  onMount={onMountArchive}
                  onDelete={onDeleteArchive}
                  mountDisabled={mountDisabled}
                  canDelete={canDelete}
                />
              ))}
          </Box>

          {/* Pagination */}
          {sortedArchives.length > 0 && (
            <Box>
              <TablePagination
                component="div"
                count={sortedArchives.length}
                page={page}
                onPageChange={handleChangePage}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleChangeRowsPerPage}
                rowsPerPageOptions={rowsPerPageOptions}
                labelRowsPerPage={t('archivesList.archivesPerPage')}
                labelDisplayedRows={({ from, to, count }) =>
                  `${from}–${to} of ${count !== -1 ? count : `more than ${to}`}`
                }
                sx={{
                  '.MuiTablePagination-toolbar': {
                    minHeight: '52px',
                    paddingLeft: 2,
                    paddingRight: 1,
                  },
                  '.MuiTablePagination-spacer': {
                    display: 'none',
                  },
                  '.MuiTablePagination-selectLabel': {
                    marginTop: 0,
                    marginBottom: 0,
                  },
                  '.MuiTablePagination-displayedRows': {
                    marginTop: 0,
                    marginBottom: 0,
                    marginLeft: 'auto',
                  },
                  '.MuiTablePagination-select': {
                    paddingTop: 1,
                    paddingBottom: 1,
                  },
                  '.MuiTablePagination-actions': {
                    marginLeft: 1,
                  },
                  '@media (max-width: 600px)': {
                    '.MuiTablePagination-selectLabel': {
                      display: 'none',
                    },
                  },
                }}
              />
            </Box>
          )}
        </>
      )}
    </Box>
  )
}
