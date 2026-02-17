import React, { useState, useMemo } from 'react'
import {
  Box,
  CircularProgress,
  Stack,
  Typography,
  TablePagination,
  Paper,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  ToggleButtonGroup,
  ToggleButton,
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
  defaultRowsPerPage?: number
  rowsPerPageOptions?: number[]
}

export default function ArchivesList({
  archives,
  repositoryName,
  loading,
  onViewArchive,
  onRestoreArchive,
  onMountArchive,
  onDeleteArchive,
  mountDisabled = false,
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

  // Loading State
  if (loading) {
    return (
      <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
        <CircularProgress size={48} />
        <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
          Loading archives...
        </Typography>
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
          No archives found in this repository
        </Typography>
      </Box>
    )
  }

  // Archives List
  return (
    <Box>
      {/* Header with count and controls */}
      <Box
        sx={{
          mb: 3,
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="h6" fontWeight={600}>
            Archives for {repositoryName}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {filter === 'all' || sortedArchives.length === archives.length
              ? `${archives.length} ${archives.length === 1 ? 'archive' : 'archives'}`
              : `${sortedArchives.length} of ${archives.length} ${
                  archives.length === 1 ? 'archive' : 'archives'
                }`}
          </Typography>
        </Box>

        {/* View controls */}
        <Box sx={{ display: 'flex', gap: 2, alignItems: 'center' }}>
          {/* Sort control - only show in flat view */}
          {!groupingEnabled && (
            <FormControl size="small" sx={{ minWidth: 180 }}>
              <InputLabel>Sort by</InputLabel>
              <Select value={sortBy} label="Sort by" onChange={handleSortChange}>
                <MenuItem value="date-desc">Newest first</MenuItem>
                <MenuItem value="date-asc">Oldest first</MenuItem>
              </Select>
            </FormControl>
          )}

          {/* Filter control */}
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Filter</InputLabel>
            <Select value={filter} label="Filter" onChange={handleFilterChange}>
              <MenuItem value="all">All Archives</MenuItem>
              <MenuItem value="scheduled">Scheduled</MenuItem>
              <MenuItem value="manual">Manual</MenuItem>
            </Select>
          </FormControl>

          {/* View mode toggle */}
          <ToggleButtonGroup
            value={groupingEnabled ? 'grouped' : 'flat'}
            exclusive
            onChange={handleViewModeChange}
            size="small"
          >
            <ToggleButton value="grouped">
              <Layers size={18} style={{ marginRight: 6 }} />
              Grouped
            </ToggleButton>
            <ToggleButton value="flat">
              <List size={18} style={{ marginRight: 6 }} />
              List
            </ToggleButton>
          </ToggleButtonGroup>
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
            No {filter === 'scheduled' ? 'scheduled' : 'manual'} archives found
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            Try selecting a different filter
          </Typography>
        </Box>
      ) : groupingEnabled && groupedArchives ? (
        <Stack spacing={2} sx={{ mb: 2 }}>
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
              <AccordionDetails sx={{ pt: 2, pb: 2 }}>
                <Stack spacing={2}>
                  {group.archives.map((archive) => (
                    <ArchiveCard
                      key={archive.id}
                      archive={archive}
                      onView={onViewArchive}
                      onRestore={onRestoreArchive}
                      onMount={onMountArchive}
                      onDelete={onDeleteArchive}
                      mountDisabled={mountDisabled}
                    />
                  ))}
                </Stack>
              </AccordionDetails>
            </Accordion>
          ))}
        </Stack>
      ) : (
        <>
          {/* Flat paginated list */}
          <Stack spacing={2} sx={{ mb: 2 }}>
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
                />
              ))}
          </Stack>

          {/* Pagination */}
          {sortedArchives.length > 0 && (
            <Paper
              variant="outlined"
              sx={{
                borderRadius: 2,
              }}
            >
              <TablePagination
                component="div"
                count={sortedArchives.length}
                page={page}
                onPageChange={handleChangePage}
                rowsPerPage={rowsPerPage}
                onRowsPerPageChange={handleChangeRowsPerPage}
                rowsPerPageOptions={rowsPerPageOptions}
                labelRowsPerPage="Archives per page:"
                labelDisplayedRows={({ from, to, count }) =>
                  `${from}–${to} of ${count !== -1 ? count : `more than ${to}`}`
                }
                sx={{
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
                    width: '70px',
                    textAlign: 'left',
                  },
                  '.MuiTablePagination-actions': {
                    marginLeft: 2,
                  },
                }}
              />
            </Paper>
          )}
        </>
      )}
    </Box>
  )
}
