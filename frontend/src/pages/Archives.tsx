import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  IconButton,
  Alert,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Select,
  MenuItem,
  FormControl,
} from '@mui/material'
import {
  Trash2,
  AlertCircle,
  FolderOpen,
  Lock,
  RefreshCw,
  Eye,
  Folder,
} from 'lucide-react'
import { archivesAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate, formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface Repository {
  id: number
  name: string
  path: string
}

interface Archive {
  id: string
  archive: string
  name: string
  start: string
  time: string
}

const Archives: React.FC = () => {
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [viewArchive, setViewArchive] = useState<Archive | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get archives for selected repository
  const { data: archives, isLoading: loadingArchives, refetch: refetchArchives } = useQuery({
    queryKey: ['repository-archives', selectedRepositoryId],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepositoryId!),
    enabled: !!selectedRepositoryId
  })

  // Get archive-specific info for modal
  const { data: archiveInfo, isLoading: loadingArchiveInfo } = useQuery({
    queryKey: ['archive-info', selectedRepositoryId, viewArchive?.name],
    queryFn: () => repositoriesAPI.getArchiveInfo(selectedRepositoryId!, viewArchive!.name),
    enabled: !!selectedRepositoryId && !!viewArchive
  })

  // Delete archive mutation
  const deleteArchiveMutation = useMutation({
    mutationFn: ({ repository, archive }: { repository: string; archive: string }) =>
      archivesAPI.deleteArchive(repository, archive),
    onSuccess: () => {
      toast.success('Archive deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
      setShowDeleteConfirm(null)
    },
    onError: (error: any) => {
      toast.error(`Failed to delete archive: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle repository selection
  const handleRepositoryChange = (repositoryId: number) => {
    setSelectedRepositoryId(repositoryId)
    const repo = repositories.find((r: Repository) => r.id === repositoryId)
    setSelectedRepository(repo || null)
  }

  // Handle archive deletion
  const handleDeleteArchive = (archive: string) => {
    if (selectedRepository) {
      deleteArchiveMutation.mutate({ repository: selectedRepository.path, archive })
    }
  }

  // Get repositories from API response
  const repositories = repositoriesData?.data?.repositories || []
  const archivesList = archives?.data?.archives || []

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Archive Browser
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browse and manage your backup archives
        </Typography>
      </Box>

      {/* Repository Selector */}
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 3 }}>
        <Box sx={{ flex: 1 }}>
          <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>
            Select Repository
          </Typography>
          <FormControl fullWidth>
            <Select
              value={selectedRepositoryId || ''}
              onChange={(e) => handleRepositoryChange(e.target.value as number)}
              displayEmpty
              disabled={loadingRepositories || repositories.length === 0}
              sx={{
                backgroundColor: 'background.paper',
                '& .MuiOutlinedInput-notchedOutline': {
                  borderColor: 'divider',
                },
              }}
            >
              <MenuItem value="" disabled>
                {loadingRepositories ? 'Loading repositories...' : 'Select a repository'}
              </MenuItem>
              {repositories.map((repo: Repository) => (
                <MenuItem key={repo.id} value={repo.id}>
                  {repo.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
        {selectedRepositoryId && (
          <Button
            variant="contained"
            startIcon={<RefreshCw size={18} />}
            onClick={() => refetchArchives()}
            sx={{ mt: 3.5 }}
          >
            Refresh
          </Button>
        )}
      </Stack>

      {/* No Repository Selected State */}
      {!selectedRepositoryId && !loadingRepositories && (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <Folder size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
          <Typography variant="body1" color="text.secondary">
            {repositories.length === 0
              ? 'No repositories found. Create a repository first.'
              : 'Select a repository to view its archives'}
          </Typography>
        </Box>
      )}

      {/* Archives Section */}
      {selectedRepositoryId && (
        <>
          {/* Header with count */}
          <Box sx={{ mb: 2, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <Typography variant="h6" fontWeight={600}>
              Archives for {selectedRepository?.name}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {archivesList.length} {archivesList.length === 1 ? 'archive' : 'archives'}
            </Typography>
          </Box>

          {/* Info Banner */}
          <Alert severity="info" sx={{ mb: 3 }}>
            Showing the most recent archives. Use the Borg command line to view older archives if needed.
          </Alert>

          {/* Loading State */}
          {loadingArchives ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading archives...
              </Typography>
            </Box>
          ) : archivesList.length === 0 ? (
            /* Empty State */
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <FolderOpen size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
              <Typography variant="body1" color="text.secondary">
                No archives found in this repository
              </Typography>
            </Box>
          ) : (
            /* Archives List */
            <Stack spacing={2}>
              {archivesList.map((archive: Archive) => (
                <Card
                  key={archive.id}
                  variant="outlined"
                  sx={{
                    border: 1,
                    borderColor: 'divider',
                    transition: 'all 0.2s',
                    '&:hover': {
                      borderColor: 'primary.main',
                      backgroundColor: 'action.hover',
                    },
                  }}
                >
                  <CardContent>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      {/* Archive Icon and Info */}
                      <Stack direction="row" spacing={2} alignItems="center" sx={{ flex: 1 }}>
                        <Lock size={24} color="rgba(0,0,0,0.4)" />
                        <Box>
                          <Typography variant="body1" fontWeight={500}>
                            {archive.name}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Created: {formatDate(archive.start)}
                          </Typography>
                        </Box>
                      </Stack>

                      {/* Actions */}
                      <Stack direction="row" spacing={1}>
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Eye size={16} />}
                          onClick={() => setViewArchive(archive)}
                        >
                          View Contents
                        </Button>
                        <IconButton
                          color="error"
                          size="small"
                          onClick={() => setShowDeleteConfirm(archive.archive)}
                        >
                          <Trash2 size={18} />
                        </IconButton>
                      </Stack>
                    </Stack>
                  </CardContent>
                </Card>
              ))}
            </Stack>
          )}
        </>
      )}

      {/* View Contents Modal */}
      <Dialog
        open={!!viewArchive}
        onClose={() => setViewArchive(null)}
        maxWidth="md"
        fullWidth
        PaperProps={{
          sx: {
            maxHeight: '80vh'
          }
        }}
      >
        <DialogTitle>
          <Stack direction="row" alignItems="center" spacing={2}>
            <FolderOpen size={24} />
            <Box>
              <Typography variant="h6" fontWeight={600}>
                Archive Contents
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {viewArchive?.name}
              </Typography>
            </Box>
          </Stack>
        </DialogTitle>
        <DialogContent>
          {loadingArchiveInfo ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading archive details...
              </Typography>
            </Box>
          ) : archiveInfo?.data?.archive ? (
            <Stack spacing={3}>
              {/* Archive Details */}
              <Box>
                <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                  ARCHIVE DETAILS
                </Typography>
                <TableContainer>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', width: '30%' }}>Name</TableCell>
                        <TableCell>{archiveInfo.data.archive.name || viewArchive?.name}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Created</TableCell>
                        <TableCell>{archiveInfo.data.archive.start ? formatDate(archiveInfo.data.archive.start) : (viewArchive?.start ? formatDate(viewArchive.start) : 'N/A')}</TableCell>
                      </TableRow>
                      {archiveInfo.data.archive.command_line && (
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Command Line</TableCell>
                          <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.875rem', wordBreak: 'break-all' }}>
                            {archiveInfo.data.archive.command_line.join(' ')}
                          </TableCell>
                        </TableRow>
                      )}
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>

              {/* Archive Statistics */}
              {archiveInfo.data.archive.stats && (
                <Box>
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                    ARCHIVE STATISTICS
                  </Typography>
                  <TableContainer>
                    <Table size="small">
                      <TableBody>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary', width: '30%' }}>Original Size</TableCell>
                          <TableCell>{formatBytesUtil(archiveInfo.data.archive.stats.original_size || 0)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Compressed Size</TableCell>
                          <TableCell>{formatBytesUtil(archiveInfo.data.archive.stats.compressed_size || 0)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Deduplicated Size</TableCell>
                          <TableCell>{formatBytesUtil(archiveInfo.data.archive.stats.deduplicated_size || 0)}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Total Files</TableCell>
                          <TableCell>{(archiveInfo.data.archive.stats.nfiles || 0).toLocaleString()}</TableCell>
                        </TableRow>
                        <TableRow>
                          <TableCell sx={{ fontWeight: 500, color: 'text.secondary' }}>Compression Ratio</TableCell>
                          <TableCell>
                            {archiveInfo.data.archive.stats.original_size && archiveInfo.data.archive.stats.compressed_size
                              ? `${((1 - archiveInfo.data.archive.stats.compressed_size / archiveInfo.data.archive.stats.original_size) * 100).toFixed(1)}%`
                              : 'N/A'}
                          </TableCell>
                        </TableRow>
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              )}

              {/* File Listing */}
              {archiveInfo?.data?.archive?.files && archiveInfo.data.archive.files.length > 0 && (
                <Box>
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                    FILE LISTING ({archiveInfo.data.archive.file_count || archiveInfo.data.archive.files.length} files)
                  </Typography>
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Showing first {archiveInfo.data.archive.files.length} files from this archive
                  </Alert>
                  <TableContainer sx={{ maxHeight: 400 }}>
                    <Table size="small" stickyHeader>
                      <TableBody>
                        {archiveInfo.data.archive.files.map((file: any, index: number) => (
                          <TableRow key={index}>
                            <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', py: 0.5 }}>
                              {file.type === 'd' ? '📁' : '📄'}
                            </TableCell>
                            <TableCell sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all', py: 0.5 }}>
                              {file.path}
                            </TableCell>
                            <TableCell sx={{ fontSize: '0.75rem', py: 0.5, whiteSpace: 'nowrap' }}>
                              {file.type === '-' ? formatBytesUtil(file.size || 0) : '-'}
                            </TableCell>
                            <TableCell sx={{ fontSize: '0.75rem', py: 0.5, color: 'text.secondary', whiteSpace: 'nowrap' }}>
                              {file.mtime ? new Date(file.mtime).toLocaleDateString() : ''}
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Box>
              )}
            </Stack>
          ) : (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <AlertCircle size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
              <Typography variant="body1" color="text.secondary">
                No archive information available
              </Typography>
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewArchive(null)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                backgroundColor: 'error.lighter',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AlertCircle size={24} color="#d32f2f" />
            </Box>
            <Typography variant="h6" fontWeight={600}>
              Delete Archive
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            This action cannot be undone!
          </Alert>
          <Typography variant="body2">
            Are you sure you want to delete the archive <strong>"{showDeleteConfirm}"</strong>?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDeleteConfirm(null)}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={() => handleDeleteArchive(showDeleteConfirm!)}
            disabled={deleteArchiveMutation.isLoading}
            startIcon={deleteArchiveMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Trash2 size={16} />}
          >
            {deleteArchiveMutation.isLoading ? 'Deleting...' : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Archives
