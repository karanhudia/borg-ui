import { Box, CircularProgress, Stack, Typography } from '@mui/material'
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
}: ArchivesListProps) {
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
    <>
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
      <Stack spacing={2}>
        {archives.map((archive) => (
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
    </>
  )
}
