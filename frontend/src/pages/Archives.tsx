import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  InputAdornment,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  IconButton,
  Alert,
} from '@mui/material'
import {
  Search,
  Folder,
  HardDrive,
  Calendar,
  Trash2,
  RefreshCw,
  AlertCircle,
  FolderOpen,
  Info,
} from 'lucide-react'
import { archivesAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'

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
  const [selectedArchive, setSelectedArchive] = useState<Archive | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get archives for selected repository using new borg list endpoint
  const { data: archives, isLoading: loadingArchives } = useQuery({
    queryKey: ['repository-archives', selectedRepositoryId],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepositoryId!),
    enabled: !!selectedRepositoryId
  })

  // Get repository info using borg info command
  const { data: repositoryInfo, isLoading: loadingRepositoryInfo } = useQuery({
    queryKey: ['repository-info', selectedRepositoryId],
    queryFn: () => repositoriesAPI.getRepositoryInfo(selectedRepositoryId!),
    enabled: !!selectedRepositoryId
  })

  // Get archive-specific info using borg info repo::archive
  const { data: archiveInfo, isLoading: loadingArchiveInfo } = useQuery({
    queryKey: ['archive-info', selectedRepositoryId, selectedArchive?.name],
    queryFn: () => repositoriesAPI.getArchiveInfo(selectedRepositoryId!, selectedArchive!.name),
    enabled: !!selectedRepositoryId && !!selectedArchive
  })

  // Delete archive mutation
  const deleteArchiveMutation = useMutation({
    mutationFn: ({ repository, archive }: { repository: string; archive: string }) =>
      archivesAPI.deleteArchive(repository, archive),
    onSuccess: () => {
      toast.success('Archive deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
      queryClient.invalidateQueries({ queryKey: ['repository-info', selectedRepositoryId] })
    },
    onError: (error: any) => {
      toast.error(`Failed to delete archive: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle repository selection
  const handleRepositorySelect = (repository: Repository) => {
    setSelectedRepositoryId(repository.id)
    setSelectedRepository(repository)
  }

  // Handle archive deletion
  const handleDeleteArchive = (archive: string) => {
    if (selectedRepository) {
      deleteArchiveMutation.mutate({ repository: selectedRepository.path, archive })
      setShowDeleteConfirm(null)
    }
  }

  // Filter archives based on search
  const filteredArchives = archives?.data?.archives?.filter((archive: Archive) =>
    archive.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    archive.archive.toLowerCase().includes(searchQuery.toLowerCase()) ||
    archive.start.includes(searchQuery)
  ) || []

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString()
  }

  // Format bytes to human readable
  const formatBytes = (bytes: number) => {
    if (bytes === 0) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`
  }

  // Get repositories from API response
  const repositories = repositoriesData?.data?.repositories || []

  // Get repository info data
  const repoInfo = repositoryInfo?.data?.info?.repository
  const cacheInfo = repositoryInfo?.data?.info?.cache
  const encryptionInfo = repositoryInfo?.data?.info?.encryption

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Archive Management
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Browse and manage your backup archives
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<RefreshCw size={18} />}
          onClick={() => {
            queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
            queryClient.invalidateQueries({ queryKey: ['repository-info', selectedRepositoryId] })
          }}
        >
          Refresh
        </Button>
      </Box>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={3}>
        {/* Repository Selection */}
        <Box sx={{ flex: { xs: '1 1 100%', lg: '0 0 300px' } }}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Repositories
              </Typography>
              {loadingRepositories ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <CircularProgress size={32} />
                </Box>
              ) : repositories.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    No repositories found
                  </Typography>
                </Box>
              ) : (
                <List sx={{ pt: 2 }}>
                  {repositories.map((repo: Repository) => (
                    <ListItem key={repo.id} disablePadding sx={{ mb: 1 }}>
                      <ListItemButton
                        selected={selectedRepositoryId === repo.id}
                        onClick={() => handleRepositorySelect(repo)}
                        sx={{
                          borderRadius: 1,
                          '&.Mui-selected': {
                            backgroundColor: 'primary.lighter',
                            borderLeft: 3,
                            borderColor: 'primary.main',
                            '&:hover': {
                              backgroundColor: 'primary.lighter',
                            },
                          },
                        }}
                      >
                        <ListItemIcon>
                          <HardDrive size={20} />
                        </ListItemIcon>
                        <ListItemText
                          primary={repo.name}
                          secondary={repo.path}
                          primaryTypographyProps={{ fontWeight: 500, fontSize: '0.875rem' }}
                          secondaryTypographyProps={{ fontSize: '0.75rem' }}
                        />
                      </ListItemButton>
                    </ListItem>
                  ))}
                </List>
              )}
            </CardContent>
          </Card>
        </Box>

        {/* Archives List */}
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
                <Typography variant="h6" fontWeight={600}>
                  Archives
                </Typography>
                {selectedRepository && (
                  <TextField
                    size="small"
                    placeholder="Search archives..."
                    value={searchQuery}
                    onChange={(e) => setSearchQuery(e.target.value)}
                    InputProps={{
                      startAdornment: (
                        <InputAdornment position="start">
                          <Search size={18} />
                        </InputAdornment>
                      ),
                    }}
                    sx={{ width: 250 }}
                  />
                )}
              </Stack>

              {!selectedRepository ? (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <HardDrive size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                  <Typography variant="body1" color="text.secondary">
                    Select a repository to view archives
                  </Typography>
                </Box>
              ) : loadingArchives ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                  <CircularProgress size={48} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Loading archives...
                  </Typography>
                </Box>
              ) : filteredArchives.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <Folder size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                  <Typography variant="body1" color="text.secondary">
                    {searchQuery ? 'No archives found matching your search' : 'No archives found in this repository'}
                  </Typography>
                </Box>
              ) : (
                <Stack spacing={2}>
                  {filteredArchives.map((archive: Archive) => (
                    <Card
                      key={archive.id}
                      variant="outlined"
                      sx={{
                        border: 1,
                        borderColor: selectedArchive?.id === archive.id ? 'primary.main' : 'divider',
                        borderWidth: selectedArchive?.id === archive.id ? 2 : 1,
                        backgroundColor: selectedArchive?.id === archive.id ? 'primary.lighter' : 'transparent',
                        cursor: 'pointer',
                        transition: 'all 0.2s',
                        '&:hover': {
                          borderColor: 'primary.main',
                          backgroundColor: 'primary.lighter',
                        },
                      }}
                      onClick={() => setSelectedArchive(archive)}
                    >
                      <CardContent>
                        <Stack direction="row" justifyContent="space-between" alignItems="center">
                          <Stack direction="row" spacing={2} alignItems="center" sx={{ flex: 1 }}>
                            <FolderOpen size={24} color="#1976d2" />
                            <Box>
                              <Typography variant="body1" fontWeight={500}>
                                {archive.name}
                              </Typography>
                              <Stack direction="row" spacing={2} sx={{ mt: 0.5 }}>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  <Calendar size={14} />
                                  {formatTimestamp(archive.start)}
                                </Typography>
                                <Typography variant="caption" color="text.secondary">
                                  {archive.time}
                                </Typography>
                              </Stack>
                            </Box>
                          </Stack>
                          <IconButton
                            color="error"
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation()
                              setShowDeleteConfirm(archive.archive)
                            }}
                          >
                            <Trash2 size={18} />
                          </IconButton>
                        </Stack>
                      </CardContent>
                    </Card>
                  ))}
                </Stack>
              )}
            </CardContent>
          </Card>
        </Box>
      </Stack>

      {/* Repository Information */}
      {selectedRepository && (
        <Box sx={{ mt: 3 }}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 3 }}>
                <Info size={20} />
                <Typography variant="h6" fontWeight={600}>
                  Repository Information
                </Typography>
              </Stack>

              {loadingRepositoryInfo ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                  <CircularProgress size={48} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Loading repository info...
                  </Typography>
                </Box>
              ) : repoInfo ? (
                <Stack spacing={3}>
                  {/* Repository Details */}
                  <Box>
                    <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                      REPOSITORY DETAILS
                    </Typography>
                    <Stack spacing={2}>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          ID
                        </Typography>
                        <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5, fontFamily: 'monospace', fontSize: '0.875rem' }}>
                          {repoInfo.id || 'N/A'}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Location
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                          {repoInfo.location || selectedRepository.path}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Last Modified
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                          {repoInfo.last_modified ? formatTimestamp(repoInfo.last_modified) : 'N/A'}
                        </Typography>
                      </Box>
                    </Stack>
                  </Box>

                  {/* Storage Statistics */}
                  {cacheInfo && cacheInfo.stats && (
                    <Box>
                      <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                        STORAGE STATISTICS
                      </Typography>
                      <Stack spacing={2}>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Unique Size (Deduplicated)
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {formatBytes(cacheInfo.stats.unique_size || 0)}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Compressed Size
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {formatBytes(cacheInfo.stats.unique_csize || 0)}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Total Chunks
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {(cacheInfo.stats.total_chunks || 0).toLocaleString()}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Unique Chunks
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {(cacheInfo.stats.total_unique_chunks || 0).toLocaleString()}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Compression Ratio
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {cacheInfo.stats.unique_size && cacheInfo.stats.unique_csize
                              ? `${((1 - cacheInfo.stats.unique_csize / cacheInfo.stats.unique_size) * 100).toFixed(1)}%`
                              : 'N/A'}
                          </Typography>
                        </Box>
                      </Stack>
                    </Box>
                  )}

                  {/* Encryption Details */}
                  {encryptionInfo && (
                    <Box>
                      <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                        ENCRYPTION
                      </Typography>
                      <Stack spacing={2}>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Mode
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {encryptionInfo.mode || 'N/A'}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Key ID
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5, fontFamily: 'monospace', fontSize: '0.875rem' }}>
                            {encryptionInfo.keyid || 'N/A'}
                          </Typography>
                        </Box>
                      </Stack>
                    </Box>
                  )}
                </Stack>
              ) : (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <AlertCircle size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                  <Typography variant="body1" color="text.secondary">
                    No repository information available
                  </Typography>
                </Box>
              )}
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Archive Information */}
      {selectedArchive && (
        <Box sx={{ mt: 3 }}>
          <Card>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 3 }}>
                <FolderOpen size={20} />
                <Typography variant="h6" fontWeight={600}>
                  Archive Information
                </Typography>
              </Stack>

              {loadingArchiveInfo ? (
                <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                  <CircularProgress size={48} />
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                    Loading archive info...
                  </Typography>
                </Box>
              ) : archiveInfo?.data?.archive ? (
                <Stack spacing={3}>
                  {/* Archive Details */}
                  <Box>
                    <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                      ARCHIVE DETAILS
                    </Typography>
                    <Stack spacing={2}>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Name
                        </Typography>
                        <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                          {archiveInfo.data.archive.name || selectedArchive.name}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Created
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                          {archiveInfo.data.archive.start ? formatTimestamp(archiveInfo.data.archive.start) : selectedArchive.start}
                        </Typography>
                      </Box>
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Duration
                        </Typography>
                        <Typography variant="body2" sx={{ mt: 0.5 }}>
                          {archiveInfo.data.archive.duration || selectedArchive.time}
                        </Typography>
                      </Box>
                      {archiveInfo.data.archive.command_line && (
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Command Line
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5, fontFamily: 'monospace', fontSize: '0.875rem', wordBreak: 'break-all', bgcolor: 'grey.50', p: 1.5, borderRadius: 1 }}>
                            {archiveInfo.data.archive.command_line.join(' ')}
                          </Typography>
                        </Box>
                      )}
                    </Stack>
                  </Box>

                  {/* Archive Statistics */}
                  {archiveInfo.data.archive.stats && (
                    <Box>
                      <Typography variant="subtitle2" fontWeight={600} color="text.secondary" sx={{ mb: 2 }}>
                        ARCHIVE STATISTICS
                      </Typography>
                      <Stack spacing={2}>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Original Size
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {formatBytes(archiveInfo.data.archive.stats.original_size || 0)}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Compressed Size
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {formatBytes(archiveInfo.data.archive.stats.compressed_size || 0)}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Deduplicated Size
                          </Typography>
                          <Typography variant="body2" fontWeight={500} sx={{ mt: 0.5 }}>
                            {formatBytes(archiveInfo.data.archive.stats.deduplicated_size || 0)}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Total Files
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {(archiveInfo.data.archive.stats.nfiles || 0).toLocaleString()}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="caption" color="text.secondary" display="block">
                            Compression Ratio
                          </Typography>
                          <Typography variant="body2" sx={{ mt: 0.5 }}>
                            {archiveInfo.data.archive.stats.original_size && archiveInfo.data.archive.stats.compressed_size
                              ? `${((1 - archiveInfo.data.archive.stats.compressed_size / archiveInfo.data.archive.stats.original_size) * 100).toFixed(1)}%`
                              : 'N/A'}
                          </Typography>
                        </Box>
                      </Stack>
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
            </CardContent>
          </Card>
        </Box>
      )}

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
