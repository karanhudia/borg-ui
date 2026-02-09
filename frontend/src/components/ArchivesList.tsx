import { useState } from 'react'
import { Box, CircularProgress, Stack, Typography, TablePagination, Paper } from '@mui/material'
import { FolderOpen } from 'lucide-react'
import ArchiveCard from './ArchiveCard'
import { Archive } from '../types'

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
  // Load saved rows per page from localStorage
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

  // Pagination state
  const [page, setPage] = useState(0)
  const [rowsPerPage, setRowsPerPage] = useState(getInitialRowsPerPage)

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage)
  }

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    const newRowsPerPage = parseInt(event.target.value, 10)
    setRowsPerPage(newRowsPerPage)
    setPage(0) // Reset to first page
    localStorage.setItem('archives-list-rows-per-page', String(newRowsPerPage))
  }

  // Calculate paginated archives
  const paginatedArchives = archives.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage)
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
      {/* Header with count */}
      <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Typography variant="h6" fontWeight={600}>
          Archives for {repositoryName}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {archives.length} {archives.length === 1 ? 'archive' : 'archives'}
        </Typography>
      </Box>

      {/* Archives List */}
      <Stack spacing={2} sx={{ mb: 2 }}>
        {paginatedArchives.map((archive) => (
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
      {archives.length > 0 && (
        <Paper
          variant="outlined"
          sx={{
            borderRadius: 2,
          }}
        >
          <TablePagination
            component="div"
            count={archives.length}
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
    </Box>
  )
}
