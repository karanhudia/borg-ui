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
  Select,
  MenuItem,
  FormControl,
  InputLabel,
} from '@mui/material'
import {
  Trash2,
  AlertCircle,
  FolderOpen,
  Eye,
  Folder,
  Archive as ArchiveIcon,
  Database,
  Gauge,
  Layers,
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
  const [currentPath, setCurrentPath] = useState<string>('/')
  const queryClient = useQueryClient()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get archives for selected repository
  const { data: archives, isLoading: loadingArchives } = useQuery({
    queryKey: ['repository-archives', selectedRepositoryId],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepositoryId!),
    enabled: !!selectedRepositoryId
  })

  // Get repository info for statistics
  const { data: repoInfo } = useQuery({
    queryKey: ['repository-info', selectedRepositoryId],
    queryFn: () => repositoriesAPI.getRepositoryInfo(selectedRepositoryId!),
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
  const archivesList = (archives?.data?.archives || []).sort((a: Archive, b: Archive) => {
    // Sort by start date, latest first
    return new Date(b.start).getTime() - new Date(a.start).getTime()
  })

  // File browser helper functions
  const getFilesInCurrentPath = () => {
    if (!archiveInfo?.data?.archive?.files) return { folders: [], files: [] }

    const allFiles = archiveInfo.data.archive.files
    const folders: any[] = []
    const files: any[] = []
    const seenFolders = new Set<string>()

    // Normalize current path - remove leading and trailing slashes
    const normalizedPath = currentPath === '/' ? '' : currentPath.replace(/^\/|\/$/g, '')

    allFiles.forEach((file: any) => {
      let filePath = file.path.startsWith('/') ? file.path.substring(1) : file.path

      // Check if file is in current directory
      if (normalizedPath) {
        if (!filePath.startsWith(normalizedPath + '/')) return
        filePath = filePath.substring(normalizedPath.length + 1)
      }

      // Skip if empty after normalization
      if (!filePath) return

      const parts = filePath.split('/')

      if (parts.length === 1) {
        // Direct child - either file or folder
        if (file.type === 'd') {
          if (!seenFolders.has(parts[0])) {
            folders.push({ ...file, name: parts[0], path: file.path })
            seenFolders.add(parts[0])
          }
        } else {
          files.push({ ...file, name: parts[0] })
        }
      } else if (parts.length > 1) {
        // Nested item - show as folder
        const folderName = parts[0]
        if (!seenFolders.has(folderName)) {
          folders.push({
            type: 'd',
            name: folderName,
            path: normalizedPath ? `${normalizedPath}/${folderName}` : folderName
          })
          seenFolders.add(folderName)
        }
      }
    })

    return { folders, files }
  }

  const navigateToPath = (path: string) => {
    setCurrentPath(path)
  }

  const getBreadcrumbs = () => {
    if (currentPath === '/') return [{ label: 'Root', path: '/' }]

    const parts = currentPath.split('/').filter(Boolean)
    const breadcrumbs = [{ label: 'Root', path: '/' }]

    let accumulatedPath = ''
    parts.forEach(part => {
      accumulatedPath += `/${part}`
      breadcrumbs.push({ label: part, path: accumulatedPath })
    })

    return breadcrumbs
  }

  // Reset path when opening a new archive
  const handleViewArchive = (archive: Archive) => {
    setViewArchive(archive)
    setCurrentPath('/')
  }

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
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
            <Database size={20} color="#2e7d32" />
            <Typography variant="h6" fontWeight={600}>
              Select Repository
            </Typography>
          </Stack>
          <FormControl fullWidth sx={{ minWidth: { xs: '100%', sm: 300 } }}>
            <InputLabel id="repository-select-label">Repository</InputLabel>
            <Select
              labelId="repository-select-label"
              value={selectedRepositoryId || ''}
              onChange={(e) => handleRepositoryChange(e.target.value as number)}
              label="Repository"
              disabled={loadingRepositories}
              sx={{ height: { xs: 48, sm: 56 } }}
            >
              <MenuItem value="" disabled>
                {loadingRepositories ? 'Loading repositories...' : 'Select a repository...'}
              </MenuItem>
              {repositories.map((repo: Repository) => (
                <MenuItem key={repo.id} value={repo.id}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Database size={16} />
                    <Box>
                      <Typography variant="body2" fontWeight={500}>{repo.name}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                        {repo.path}
                      </Typography>
                    </Box>
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </CardContent>
      </Card>

      {/* Repository Statistics */}
      {selectedRepositoryId && repoInfo?.data?.info?.cache?.stats && (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(5, 1fr)' }, gap: 2, mb: 4 }}>
          {/* Total Archives */}
          <Card sx={{ backgroundColor: '#e3f2fd' }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <ArchiveIcon size={32} color="#1565c0" />
                <Box>
                  <Typography variant="body2" color="primary.dark" fontWeight={500}>
                    Total Archives
                  </Typography>
                  <Typography variant="h4" fontWeight={700} color="primary.dark">
                    {archivesList.length}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {/* Space Used on Disk */}
          <Card sx={{ backgroundColor: '#e8f5e9' }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <Database size={32} color="#2e7d32" />
                <Box>
                  <Typography variant="body2" color="success.dark" fontWeight={500}>
                    Space Used
                  </Typography>
                  <Typography variant="h4" fontWeight={700} color="success.dark" sx={{ fontSize: '1.5rem' }}>
                    {formatBytesUtil(repoInfo.data.info.cache.stats.unique_csize)}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {/* Space Saved */}
          <Card sx={{ backgroundColor: '#e1f5fe' }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <Database size={32} color="#0277bd" />
                <Box>
                  <Typography variant="body2" sx={{ color: '#0277bd' }} fontWeight={500}>
                    Space Saved
                  </Typography>
                  <Typography variant="h4" fontWeight={700} sx={{ color: '#0277bd', fontSize: '1.5rem' }}>
                    {formatBytesUtil(repoInfo.data.info.cache.stats.total_size - repoInfo.data.info.cache.stats.unique_csize)}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {/* Compression */}
          <Card sx={{ backgroundColor: '#f3e5f5' }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <Gauge size={32} color="#7b1fa2" />
                <Box>
                  <Typography variant="body2" color="purple" fontWeight={500}>
                    Compression
                  </Typography>
                  <Typography variant="h4" fontWeight={700} color="purple">
                    {repoInfo.data.info.cache.stats.unique_size > 0
                      ? `${((1 - repoInfo.data.info.cache.stats.unique_csize / repoInfo.data.info.cache.stats.unique_size) * 100).toFixed(1)}%`
                      : '0%'}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          {/* Deduplication */}
          <Card sx={{ backgroundColor: '#fff3e0' }}>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <Layers size={32} color="#e65100" />
                <Box>
                  <Typography variant="body2" sx={{ color: '#e65100' }} fontWeight={500}>
                    Deduplication
                  </Typography>
                  <Typography variant="h4" fontWeight={700} sx={{ color: '#e65100' }}>
                    {repoInfo.data.info.cache.stats.total_size > 0
                      ? `${((1 - repoInfo.data.info.cache.stats.unique_size / repoInfo.data.info.cache.stats.total_size) * 100).toFixed(1)}%`
                      : '0%'}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Box>
      )}

      {/* No Repository Selected State */}
      {!selectedRepositoryId && !loadingRepositories && (
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
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
                      boxShadow: 1,
                    },
                  }}
                >
                  <CardContent sx={{ py: 2 }}>
                    <Stack direction="row" alignItems="center" justifyContent="space-between">
                      {/* Archive Info */}
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="h6" fontWeight={600} sx={{ mb: 0.5 }}>
                          {archive.name}
                        </Typography>
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Typography variant="body2" color="text.secondary">
                            {formatDate(archive.start)}
                          </Typography>
                        </Stack>
                      </Box>

                      {/* Actions */}
                      <Stack direction="row" spacing={1}>
                        <Button
                          variant="contained"
                          size="small"
                          startIcon={<Eye size={16} />}
                          onClick={() => handleViewArchive(archive)}
                          sx={{ textTransform: 'none' }}
                        >
                          View
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
              {/* Interactive File Browser */}
              {archiveInfo?.data?.archive?.files && archiveInfo.data.archive.files.length > 0 && (
                <Box>
                  {/* Breadcrumb Navigation */}
                  <Box sx={{ mb: 2, display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 0.5 }}>
                    {getBreadcrumbs().map((crumb, index) => (
                      <React.Fragment key={crumb.path}>
                        {index > 0 && (
                          <Typography variant="body2" color="text.secondary">/</Typography>
                        )}
                        <Typography
                          variant="body2"
                          onClick={() => navigateToPath(crumb.path)}
                          sx={{
                            cursor: 'pointer',
                            color: 'primary.main',
                            textDecoration: 'underline',
                            '&:hover': {
                              color: 'primary.dark',
                            },
                          }}
                        >
                          {crumb.label}
                        </Typography>
                      </React.Fragment>
                    ))}
                  </Box>

                  {/* Files and Folders List */}
                  <Box sx={{ maxHeight: 400, overflowY: 'auto' }}>
                    {(() => {
                      const { folders, files } = getFilesInCurrentPath()

                      if (folders.length === 0 && files.length === 0) {
                        return (
                          <Box sx={{ textAlign: 'center', py: 4 }}>
                            <Typography variant="body2" color="text.secondary">
                              This directory is empty
                            </Typography>
                          </Box>
                        )
                      }

                      return (
                        <Stack spacing={0.5}>
                          {/* Folders */}
                          {folders.map((folder, index) => (
                            <Box
                              key={`folder-${index}`}
                              onClick={() => {
                                const newPath = currentPath === '/' ? `/${folder.name}` : `${currentPath}/${folder.name}`
                                navigateToPath(newPath)
                              }}
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                p: 1.5,
                                borderRadius: 1,
                                cursor: 'pointer',
                                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                                '&:hover': {
                                  backgroundColor: 'rgba(59, 130, 246, 0.2)',
                                },
                              }}
                            >
                              <Stack direction="row" spacing={1.5} alignItems="center">
                                <Folder size={20} color="#3b82f6" />
                                <Typography variant="body2" fontWeight={500}>
                                  {folder.name}
                                </Typography>
                              </Stack>
                            </Box>
                          ))}

                          {/* Files */}
                          {files.map((file, index) => (
                            <Box
                              key={`file-${index}`}
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                p: 1.5,
                                borderRadius: 1,
                                backgroundColor: 'rgba(0, 0, 0, 0.02)',
                                '&:hover': {
                                  backgroundColor: 'rgba(0, 0, 0, 0.05)',
                                },
                              }}
                            >
                              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ flex: 1, minWidth: 0 }}>
                                <FolderOpen size={20} color="rgba(0,0,0,0.4)" />
                                <Typography
                                  variant="body2"
                                  sx={{
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                  }}
                                >
                                  {file.name}
                                </Typography>
                              </Stack>
                              <Stack direction="row" spacing={2} alignItems="center">
                                <Typography variant="body2" color="text.secondary" sx={{ minWidth: 60, textAlign: 'right' }}>
                                  {file.size ? formatBytesUtil(file.size) : '0 B'}
                                </Typography>
                                <IconButton
                                  size="small"
                                  sx={{ color: 'text.secondary' }}
                                  onClick={() => {
                                    if (selectedRepository && viewArchive) {
                                      archivesAPI.downloadFile(selectedRepository.path, viewArchive.name, file.path)
                                    }
                                  }}
                                  title="Download file"
                                >
                                  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                    <polyline points="7 10 12 15 17 10" />
                                    <line x1="12" y1="15" x2="12" y2="3" />
                                  </svg>
                                </IconButton>
                              </Stack>
                            </Box>
                          ))}
                        </Stack>
                      )
                    })()}
                  </Box>
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
