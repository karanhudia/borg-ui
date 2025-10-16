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
  Breadcrumbs,
  Link,
  Stack,
  IconButton,
  Alert,
} from '@mui/material'
import {
  Search,
  Folder,
  File,
  HardDrive,
  Calendar,
  Trash2,
  ChevronRight,
  RefreshCw,
  AlertCircle,
  FolderOpen,
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

interface ArchiveFile {
  name: string
  type: 'file' | 'directory'
  size?: string
  path: string
  children?: ArchiveFile[]
}

const Archives: React.FC = () => {
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [selectedArchive, setSelectedArchive] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [currentPath, setCurrentPath] = useState<string>('')
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

  // Get archive details (keeping old API for now)
  const { data: archiveDetails, isLoading: loadingDetails } = useQuery({
    queryKey: ['archive-details', selectedRepository?.path, selectedArchive],
    queryFn: () => archivesAPI.getArchiveInfo(selectedRepository!.path, selectedArchive),
    enabled: !!selectedRepository && !!selectedArchive
  })

  // Get archive contents (keeping old API for now)
  const { data: archiveContents, isLoading: loadingContents } = useQuery({
    queryKey: ['archive-contents', selectedRepository?.path, selectedArchive, currentPath],
    queryFn: () => archivesAPI.listContents(selectedRepository!.path, selectedArchive, currentPath),
    enabled: !!selectedRepository && !!selectedArchive
  })

  // Delete archive mutation (keeping old API for now)
  const deleteArchiveMutation = useMutation({
    mutationFn: ({ repository, archive }: { repository: string; archive: string }) =>
      archivesAPI.deleteArchive(repository, archive),
    onSuccess: () => {
      toast.success('Archive deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
      setSelectedArchive('')
    },
    onError: (error: any) => {
      toast.error(`Failed to delete archive: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle repository selection
  const handleRepositorySelect = (repository: Repository) => {
    setSelectedRepositoryId(repository.id)
    setSelectedRepository(repository)
    setSelectedArchive('')
    setCurrentPath('')
  }

  // Handle archive selection
  const handleArchiveSelect = (archive: string) => {
    setSelectedArchive(archive)
    setCurrentPath('')
  }

  // Handle file/folder click
  const handleItemClick = (item: ArchiveFile) => {
    if (item.type === 'directory') {
      const newPath = currentPath ? `${currentPath}/${item.name}` : item.name
      setCurrentPath(newPath)
    }
  }

  // Handle navigation breadcrumb
  const handleBreadcrumbClick = (index: number) => {
    if (index === 0) {
      setCurrentPath('')
    } else {
      const pathParts = currentPath.split('/')
      const newPath = pathParts.slice(0, index).join('/')
      setCurrentPath(newPath)
    }
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

  // Format file size
  const formatFileSize = (size?: string) => {
    if (!size) return 'Unknown'
    return size
  }

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    return new Date(timestamp).toLocaleString()
  }

  // Get breadcrumb parts
  const breadcrumbParts = currentPath ? ['root', ...currentPath.split('/')] : ['root']

  // Get repositories from API response
  const repositories = repositoriesData?.data?.repositories || []

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
          onClick={() => queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })}
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
                        cursor: 'pointer',
                        border: selectedArchive === archive.archive ? 2 : 1,
                        borderColor: selectedArchive === archive.archive ? 'primary.main' : 'divider',
                        backgroundColor: selectedArchive === archive.archive ? 'primary.lighter' : 'background.paper',
                        '&:hover': {
                          borderColor: 'primary.main',
                          backgroundColor: 'action.hover',
                        },
                      }}
                      onClick={() => handleArchiveSelect(archive.archive)}
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

      {/* Archive Details and File Browser */}
      {selectedArchive && (
        <Stack direction={{ xs: 'column', lg: 'row' }} spacing={3} sx={{ mt: 3 }}>
          {/* Archive Details */}
          <Box sx={{ flex: 1 }}>
            <Card>
              <CardContent>
                <Typography variant="h6" fontWeight={600} gutterBottom>
                  Archive Details
                </Typography>
                {loadingDetails ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                    <CircularProgress size={48} />
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                      Loading details...
                    </Typography>
                  </Box>
                ) : archiveDetails?.data ? (
                  <Stack direction="row" flexWrap="wrap" spacing={2} sx={{ mt: 2 }}>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Name
                      </Typography>
                      <Typography variant="body2">{archiveDetails.data.name}</Typography>
                    </Box>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Created
                      </Typography>
                      <Typography variant="body2">{formatTimestamp(archiveDetails.data.timestamp)}</Typography>
                    </Box>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Size
                      </Typography>
                      <Typography variant="body2">{formatFileSize(archiveDetails.data.size)}</Typography>
                    </Box>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Compressed
                      </Typography>
                      <Typography variant="body2">{formatFileSize(archiveDetails.data.compressed_size)}</Typography>
                    </Box>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Deduplicated
                      </Typography>
                      <Typography variant="body2">{formatFileSize(archiveDetails.data.deduplicated_size)}</Typography>
                    </Box>
                    <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>
                        Files
                      </Typography>
                      <Typography variant="body2">{archiveDetails.data.file_count?.toLocaleString() || 'Unknown'}</Typography>
                    </Box>
                  </Stack>
                ) : (
                  <Box sx={{ textAlign: 'center', py: 8 }}>
                    <AlertCircle size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                    <Typography variant="body1" color="text.secondary">
                      No details available
                    </Typography>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Box>

          {/* File Browser */}
          <Box sx={{ flex: 1 }}>
            <Card>
              <CardContent>
                <Typography variant="h6" fontWeight={600} gutterBottom>
                  File Browser
                </Typography>

                {/* Breadcrumb */}
                <Breadcrumbs
                  separator={<ChevronRight size={16} />}
                  sx={{ my: 2, fontSize: '0.875rem' }}
                >
                  {breadcrumbParts.map((part, index) => (
                    <Link
                      key={index}
                      component="button"
                      variant="body2"
                      onClick={() => handleBreadcrumbClick(index)}
                      sx={{
                        textDecoration: 'none',
                        color: index === breadcrumbParts.length - 1 ? 'text.primary' : 'text.secondary',
                        fontWeight: index === breadcrumbParts.length - 1 ? 600 : 400,
                        '&:hover': {
                          color: 'primary.main',
                        },
                      }}
                    >
                      {part}
                    </Link>
                  ))}
                </Breadcrumbs>

                {loadingContents ? (
                  <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
                    <CircularProgress size={48} />
                    <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                      Loading contents...
                    </Typography>
                  </Box>
                ) : archiveContents?.data?.length === 0 ? (
                  <Box sx={{ textAlign: 'center', py: 8 }}>
                    <Folder size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                    <Typography variant="body1" color="text.secondary">
                      This directory is empty
                    </Typography>
                  </Box>
                ) : (
                  <List>
                    {archiveContents?.data?.map((item: ArchiveFile, index: number) => (
                      <ListItem
                        key={index}
                        disablePadding
                        secondaryAction={
                          item.size && (
                            <Typography variant="caption" color="text.secondary">
                              {formatFileSize(item.size)}
                            </Typography>
                          )
                        }
                      >
                        <ListItemButton
                          onClick={() => handleItemClick(item)}
                          disabled={item.type !== 'directory'}
                          sx={{ borderRadius: 1 }}
                        >
                          <ListItemIcon>
                            {item.type === 'directory' ? (
                              <Folder size={20} color="#1976d2" />
                            ) : (
                              <File size={20} color="rgba(0,0,0,0.5)" />
                            )}
                          </ListItemIcon>
                          <ListItemText
                            primary={item.name}
                            primaryTypographyProps={{ fontSize: '0.875rem' }}
                          />
                        </ListItemButton>
                      </ListItem>
                    ))}
                  </List>
                )}
              </CardContent>
            </Card>
          </Box>
        </Stack>
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
