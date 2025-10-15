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
  Checkbox,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Breadcrumbs,
  Link,
  Stack,
  Alert,
  AlertTitle,
} from '@mui/material'
import {
  Search,
  Folder,
  File,
  HardDrive,
  Calendar,
  Eye,
  ChevronRight,
  RefreshCw,
  CheckCircle,
  Play,
  MapPin,
} from 'lucide-react'
import { restoreAPI, archivesAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface Archive {
  id: string
  name: string
  timestamp: string
  size: string
  file_count: number
  repository: string
}

interface ArchiveFile {
  name: string
  type: 'file' | 'directory'
  size?: string
  path: string
  selected?: boolean
}

const Restore: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [selectedArchive, setSelectedArchive] = useState<string>('')
  const [selectedFiles, setSelectedFiles] = useState<string[]>([])
  const [destinationPath, setDestinationPath] = useState<string>('')
  const [currentPath, setCurrentPath] = useState<string>('')
  const [searchQuery, setSearchQuery] = useState('')
  const [showPreview, setShowPreview] = useState(false)
  const [restoreJobId, setRestoreJobId] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Get archives for selected repository
  const { data: archives, isLoading: loadingArchives } = useQuery({
    queryKey: ['restore-archives', selectedRepository],
    queryFn: () => archivesAPI.listArchives(selectedRepository),
    enabled: !!selectedRepository
  })

  // Get archive contents
  const { data: archiveContents, isLoading: loadingContents } = useQuery({
    queryKey: ['restore-contents', selectedRepository, selectedArchive, currentPath],
    queryFn: () => archivesAPI.listContents(selectedRepository, selectedArchive, currentPath),
    enabled: !!selectedRepository && !!selectedArchive
  })

  // Preview restore mutation
  const previewMutation = useMutation({
    mutationFn: (paths: string[]) =>
      restoreAPI.previewRestore(selectedRepository, selectedArchive, paths),
    onSuccess: () => {
      setShowPreview(true)
      toast.success('Restore preview generated!')
    },
    onError: (error: any) => {
      toast.error(`Failed to generate preview: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Start restore mutation
  const startRestoreMutation = useMutation({
    mutationFn: ({ paths, destination }: { paths: string[]; destination: string }) =>
      restoreAPI.startRestore(selectedRepository, selectedArchive, paths, destination),
    onSuccess: (data: any) => {
      setRestoreJobId(data.data?.job_id)
      toast.success('Restore job started successfully!')
      queryClient.invalidateQueries({ queryKey: ['restore-status'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to start restore: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle repository selection
  const handleRepositorySelect = (repository: string) => {
    setSelectedRepository(repository)
    setSelectedArchive('')
    setSelectedFiles([])
    setCurrentPath('')
    setShowPreview(false)
    setRestoreJobId(null)
  }

  // Handle archive selection
  const handleArchiveSelect = (archive: string) => {
    setSelectedArchive(archive)
    setSelectedFiles([])
    setCurrentPath('')
    setShowPreview(false)
    setRestoreJobId(null)
  }

  // Handle file/folder selection
  const handleFileSelect = (filePath: string) => {
    setSelectedFiles(prev => {
      if (prev.includes(filePath)) {
        return prev.filter(path => path !== filePath)
      } else {
        return [...prev, filePath]
      }
    })
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

  // Handle preview restore
  const handlePreviewRestore = () => {
    if (selectedFiles.length === 0) {
      toast.error('Please select files to restore')
      return
    }
    previewMutation.mutate(selectedFiles)
  }

  // Handle start restore
  const handleStartRestore = () => {
    if (selectedFiles.length === 0) {
      toast.error('Please select files to restore')
      return
    }
    if (!destinationPath.trim()) {
      toast.error('Please specify a destination path')
      return
    }
    startRestoreMutation.mutate({ paths: selectedFiles, destination: destinationPath })
  }

  // Filter archives based on search
  const filteredArchives = archives?.data?.filter((archive: Archive) =>
    archive.name.toLowerCase().includes(searchQuery.toLowerCase()) ||
    archive.timestamp.includes(searchQuery)
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

  // Mock repositories for now
  const mockRepositories = [
    { id: 'repo1', name: 'Default Repository', path: '/backups/default' },
    { id: 'repo2', name: 'Documents Backup', path: '/backups/documents' },
    { id: 'repo3', name: 'System Backup', path: '/backups/system' }
  ]

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Restore Operations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Restore files and folders from backup archives
          </Typography>
        </Box>
        <Button
          variant="outlined"
          startIcon={<RefreshCw size={18} />}
          onClick={() => queryClient.invalidateQueries({ queryKey: ['restore-archives', selectedRepository] })}
        >
          Refresh
        </Button>
      </Box>

      <Stack direction={{ xs: 'column', lg: 'row' }} spacing={3}>
        {/* Repository and Archive Selection */}
        <Box sx={{ flex: { xs: '1 1 100%', lg: '0 0 350px' } }}>
          <Stack spacing={3}>
            {/* Repository Selection */}
            <Card>
              <CardContent>
                <Typography variant="h6" fontWeight={600} gutterBottom>
                  Repository
                </Typography>
                <List>
                  {mockRepositories.map((repo) => (
                    <ListItem key={repo.id} disablePadding sx={{ mb: 1 }}>
                      <ListItemButton
                        selected={selectedRepository === repo.id}
                        onClick={() => handleRepositorySelect(repo.id)}
                        sx={{
                          borderRadius: 1,
                          '&.Mui-selected': {
                            backgroundColor: 'primary.lighter',
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
              </CardContent>
            </Card>

            {/* Archive Selection */}
            {selectedRepository && (
              <Card>
                <CardContent>
                  <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 2 }}>
                    <Typography variant="h6" fontWeight={600}>
                      Archive
                    </Typography>
                    <TextField
                      size="small"
                      placeholder="Search..."
                      value={searchQuery}
                      onChange={(e) => setSearchQuery(e.target.value)}
                      InputProps={{
                        startAdornment: (
                          <InputAdornment position="start">
                            <Search size={16} />
                          </InputAdornment>
                        ),
                      }}
                      sx={{ width: 150 }}
                    />
                  </Stack>

                  {loadingArchives ? (
                    <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 4 }}>
                      <CircularProgress size={32} />
                      <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                        Loading archives...
                      </Typography>
                    </Box>
                  ) : filteredArchives.length === 0 ? (
                    <Box sx={{ textAlign: 'center', py: 4 }}>
                      <Folder size={32} color="rgba(0,0,0,0.3)" style={{ marginBottom: 8 }} />
                      <Typography variant="caption" color="text.secondary">
                        No archives found
                      </Typography>
                    </Box>
                  ) : (
                    <Stack spacing={1}>
                      {filteredArchives.map((archive: Archive) => (
                        <Card
                          key={archive.id}
                          variant="outlined"
                          sx={{
                            cursor: 'pointer',
                            borderColor: selectedArchive === archive.name ? 'primary.main' : 'divider',
                            backgroundColor: selectedArchive === archive.name ? 'primary.lighter' : 'background.paper',
                            '&:hover': { borderColor: 'primary.main' },
                          }}
                          onClick={() => handleArchiveSelect(archive.name)}
                        >
                          <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                            <Stack direction="row" spacing={1} alignItems="center">
                              <Folder size={16} color="#1976d2" />
                              <Box>
                                <Typography variant="body2" fontWeight={500}>
                                  {archive.name}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  <Calendar size={12} />
                                  {formatTimestamp(archive.timestamp)}
                                </Typography>
                              </Box>
                            </Stack>
                          </CardContent>
                        </Card>
                      ))}
                    </Stack>
                  )}
                </CardContent>
              </Card>
            )}
          </Stack>
        </Box>

        {/* File Browser and Selection */}
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                File Selection
              </Typography>
              {selectedArchive && (
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Select files and folders to restore from {selectedArchive}
                </Typography>
              )}

              {!selectedArchive ? (
                <Box sx={{ textAlign: 'center', py: 8 }}>
                  <Folder size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
                  <Typography variant="body1" color="text.secondary">
                    Select an archive to browse files
                  </Typography>
                </Box>
              ) : (
                <>
                  {/* Breadcrumb */}
                  <Breadcrumbs separator={<ChevronRight size={16} />} sx={{ mb: 2, fontSize: '0.875rem' }}>
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
                          '&:hover': { color: 'primary.main' },
                        }}
                      >
                        {part}
                      </Link>
                    ))}
                  </Breadcrumbs>

                  {/* File List */}
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
                      {archiveContents?.data?.map((item: ArchiveFile, index: number) => {
                        const fullPath = currentPath ? `${currentPath}/${item.name}` : item.name
                        const isSelected = selectedFiles.includes(fullPath)

                        return (
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
                            <Checkbox
                              checked={isSelected}
                              onChange={() => handleFileSelect(fullPath)}
                              sx={{ mr: 1 }}
                            />
                            <ListItemButton onClick={() => handleItemClick(item)} disabled={item.type !== 'directory'} sx={{ borderRadius: 1 }}>
                              <ListItemIcon>
                                {item.type === 'directory' ? (
                                  <Folder size={20} color="#1976d2" />
                                ) : (
                                  <File size={20} color="rgba(0,0,0,0.5)" />
                                )}
                              </ListItemIcon>
                              <ListItemText primary={item.name} primaryTypographyProps={{ fontSize: '0.875rem' }} />
                            </ListItemButton>
                          </ListItem>
                        )
                      })}
                    </List>
                  )}
                </>
              )}
            </CardContent>
          </Card>
        </Box>
      </Stack>

      {/* Restore Configuration */}
      {selectedFiles.length > 0 && (
        <Card sx={{ mt: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Restore Configuration
            </Typography>

            <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
              {/* Selected Files */}
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" fontWeight={500} gutterBottom>
                  Selected Files ({selectedFiles.length})
                </Typography>
                <Box
                  sx={{
                    maxHeight: 120,
                    overflowY: 'auto',
                    border: 1,
                    borderColor: 'divider',
                    borderRadius: 1,
                    p: 2,
                    backgroundColor: 'grey.50',
                  }}
                >
                  {selectedFiles.map((file, index) => (
                    <Typography key={index} variant="caption" display="block" sx={{ mb: 0.5 }}>
                      {file}
                    </Typography>
                  ))}
                </Box>
              </Box>

              {/* Destination Path */}
              <Box sx={{ flex: 1 }}>
                <Typography variant="body2" fontWeight={500} gutterBottom>
                  Destination Path
                </Typography>
                <TextField
                  fullWidth
                  value={destinationPath}
                  onChange={(e) => setDestinationPath(e.target.value)}
                  placeholder="/path/to/restore/destination"
                  InputProps={{
                    startAdornment: (
                      <InputAdornment position="start">
                        <MapPin size={18} />
                      </InputAdornment>
                    ),
                  }}
                />
              </Box>
            </Stack>

            {/* Action Buttons */}
            <Stack direction="row" spacing={2} sx={{ mt: 3 }}>
              <Button
                variant="contained"
                color="info"
                startIcon={previewMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Eye size={18} />}
                onClick={handlePreviewRestore}
                disabled={previewMutation.isLoading}
              >
                {previewMutation.isLoading ? 'Generating Preview...' : 'Preview Restore'}
              </Button>

              <Button
                variant="contained"
                color="success"
                startIcon={startRestoreMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Play size={18} />}
                onClick={handleStartRestore}
                disabled={startRestoreMutation.isLoading || !destinationPath.trim()}
              >
                {startRestoreMutation.isLoading ? 'Starting Restore...' : 'Start Restore'}
              </Button>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Restore Preview Dialog */}
      <Dialog open={showPreview} onClose={() => setShowPreview(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Restore Preview</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ pt: 1 }}>
            <Stack direction="row" flexWrap="wrap" spacing={2}>
              <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Files to restore
                </Typography>
                <Typography variant="body2">{selectedFiles.length}</Typography>
              </Box>
              <Box sx={{ flex: '1 1 45%', minWidth: 150 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={600}>
                  Destination
                </Typography>
                <Typography variant="body2">{destinationPath || 'Not specified'}</Typography>
              </Box>
            </Stack>

            <Box>
              <Typography variant="caption" color="text.secondary" fontWeight={600} gutterBottom>
                Selected files
              </Typography>
              <Box
                sx={{
                  maxHeight: 120,
                  overflowY: 'auto',
                  border: 1,
                  borderColor: 'divider',
                  borderRadius: 1,
                  p: 2,
                  backgroundColor: 'grey.50',
                }}
              >
                {selectedFiles.map((file, index) => (
                  <Typography key={index} variant="caption" display="block" sx={{ mb: 0.5 }}>
                    {file}
                  </Typography>
                ))}
              </Box>
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowPreview(false)}>Close</Button>
          <Button
            variant="contained"
            color="success"
            onClick={() => {
              setShowPreview(false)
              handleStartRestore()
            }}
            disabled={!destinationPath.trim()}
          >
            Start Restore
          </Button>
        </DialogActions>
      </Dialog>

      {/* Restore Job Status */}
      {restoreJobId && (
        <Alert severity="success" icon={<CheckCircle size={20} />} sx={{ mt: 3 }}>
          <AlertTitle fontWeight={600}>Restore Job Started</AlertTitle>
          <Typography variant="body2">Job ID: {restoreJobId}</Typography>
          <Typography variant="body2">Check the Backup page to monitor progress</Typography>
        </Alert>
      )}
    </Box>
  )
}

export default Restore
