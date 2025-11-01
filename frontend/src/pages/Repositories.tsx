import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import { toast } from 'react-hot-toast'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  Divider,
  Stack,
  Autocomplete,
  InputAdornment,
} from '@mui/material'
import {
  Add,
  Edit,
  Delete,
  CheckCircle as CheckCircleIcon,
  Refresh,
  Storage,
  Shield,
  Description,
  Warning,
  Computer,
  Wifi,
  Info,
  Lock,
  CalendarMonth,
  DataUsage,
  Compress,
  Inventory,
  FileUpload,
} from '@mui/icons-material'
import { repositoriesAPI, sshKeysAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAppState } from '../context/AppContext'
import { formatDateShort, formatBytes } from '../utils/dateUtils'
import FileExplorerDialog from '../components/FileExplorerDialog'
import { FolderOpen } from '@mui/icons-material'

interface Repository {
  id: number
  name: string
  path: string
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  last_backup: string | null
  total_size: string | null
  archive_count: number
  created_at: string
  updated_at: string | null
}

interface SSHKey {
  id: number
  name: string
  key_type: string
  is_active: boolean
}

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  status: string
}

export default function Repositories() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const appState = useAppState()
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [showImportModal, setShowImportModal] = useState(false)
  const [editingRepository, setEditingRepository] = useState<Repository | null>(null)
  const [viewingInfoRepository, setViewingInfoRepository] = useState<Repository | null>(null)
  const [compactingRepository, setCompactingRepository] = useState<Repository | null>(null)
  const [pruningRepository, setPruningRepository] = useState<Repository | null>(null)
  const [pruneForm, setPruneForm] = useState({
    keep_daily: 7,
    keep_weekly: 4,
    keep_monthly: 6,
    keep_yearly: 1,
  })
  const [pruneResults, setPruneResults] = useState<any>(null)

  // Queries
  const { data: repositoriesData, isLoading } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const { data: sshKeysData } = useQuery({
    queryKey: ['ssh-keys'],
    queryFn: sshKeysAPI.getSSHKeys,
  })

  const { data: connectionsData } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
  })

  // Get repository info using borg info command
  const { data: repositoryInfo, isLoading: loadingInfo } = useQuery({
    queryKey: ['repository-info', viewingInfoRepository?.id],
    queryFn: () => repositoriesAPI.getRepositoryInfo(viewingInfoRepository!.id),
    enabled: !!viewingInfoRepository,
  })

  // Get default configuration to show source directories
  // REMOVED: Config dependency no longer needed
  // const { data: defaultConfigData } = useQuery({
  //   queryKey: ['default-config'],
  //   queryFn: async () => {
  //     try {
  //       const response = await configAPI.getDefaultConfig()
  //       return response.data
  //     } catch (error) {
  //       return null
  //     }
  //   },
  //   retry: false,
  // })

  // Mutations
  const createRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.createRepository,
    onSuccess: (response: any) => {
      // Check if repository already existed
      const alreadyExisted = response?.data?.already_existed || false
      const message = response?.data?.message || 'Repository created successfully'

      if (alreadyExisted) {
        toast.success(message, { duration: 5000 })
      } else {
        toast.success(message)
      }

      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      // Invalidate AppContext query to update tab enablement immediately
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      setShowCreateModal(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create repository')
    },
  })

  const importRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.importRepository,
    onSuccess: (response: any) => {
      const message = response?.data?.message || 'Repository imported successfully'
      const archiveCount = response?.data?.repository?.archive_count || 0

      toast.success(`${message}${archiveCount > 0 ? ` (${archiveCount} archives found)` : ''}`, { duration: 5000 })

      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      setShowImportModal(false)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to import repository')
    },
  })

  const updateRepositoryMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      repositoriesAPI.updateRepository(id, data),
    onSuccess: () => {
      toast.success('Repository updated successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      // Invalidate AppContext query to update tab enablement
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      setEditingRepository(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update repository')
    },
  })

  const deleteRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.deleteRepository,
    onSuccess: () => {
      toast.success('Repository deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      // Invalidate AppContext query to update tab enablement
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete repository')
    },
  })

  const checkRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.checkRepository,
    onSuccess: () => {
      toast.success('Repository check completed')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to check repository')
    },
  })

  const compactRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.compactRepository,
    onSuccess: () => {
      toast.success('Repository compaction completed successfully!')
      setCompactingRepository(null)
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['repository-info', compactingRepository?.id] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to compact repository')
    },
  })

  const pruneRepositoryMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => repositoriesAPI.pruneRepository(id, data),
    onSuccess: (response: any) => {
      setPruneResults(response.data)
      if (response.data.dry_run) {
        toast.success('Dry run completed - review results below')
      } else {
        toast.success('Repository pruned successfully!')
        queryClient.invalidateQueries({ queryKey: ['repositories'] })
        queryClient.invalidateQueries({ queryKey: ['repository-archives', pruningRepository?.id] })
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to prune repository')
      setPruneResults(null)
    },
  })

  // Form states
  const [createForm, setCreateForm] = useState({
    name: '',
    path: '',
    encryption: 'repokey',
    compression: 'lz4',
    passphrase: '',
    source_directories: [] as string[],
    exclude_patterns: [] as string[],
    repository_type: 'local',
    host: '',
    port: 22,
    username: '',
    ssh_key_id: null as number | null,
    connection_id: null as number | null,
    remote_path: '',
  })

  const [importForm, setImportForm] = useState({
    name: '',
    path: '',
    passphrase: '',
    compression: 'lz4',
    source_directories: [] as string[],
    exclude_patterns: [] as string[],
    repository_type: 'local',
    host: '',
    port: 22,
    username: '',
    ssh_key_id: null as number | null,
    remote_path: '',
  })

  const [newSourceDir, setNewSourceDir] = useState('')
  const [newExcludePattern, setNewExcludePattern] = useState('')
  const [showPathExplorer, setShowPathExplorer] = useState(false)
  const [showSourceDirExplorer, setShowSourceDirExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)
  const [showImportPathExplorer, setShowImportPathExplorer] = useState(false)
  const [showImportSourceDirExplorer, setShowImportSourceDirExplorer] = useState(false)
  const [showImportExcludeExplorer, setShowImportExcludeExplorer] = useState(false)

  const [editForm, setEditForm] = useState({
    name: '',
    path: '',
    compression: 'lz4',
    source_directories: [] as string[],
    exclude_patterns: [] as string[],
    remote_path: '',
  })

  const [editNewSourceDir, setEditNewSourceDir] = useState('')
  const [editNewExcludePattern, setEditNewExcludePattern] = useState('')
  const [showEditSourceDirExplorer, setShowEditSourceDirExplorer] = useState(false)
  const [showEditExcludeExplorer, setShowEditExcludeExplorer] = useState(false)

  // Event handlers
  const handleCreateRepository = (e: React.FormEvent) => {
    e.preventDefault()
    createRepositoryMutation.mutate(createForm)
  }

  const handleUpdateRepository = (e: React.FormEvent) => {
    e.preventDefault()
    if (editingRepository) {
      updateRepositoryMutation.mutate({
        id: editingRepository.id,
        data: editForm,
      })
    }
  }

  const handleDeleteRepository = (repository: Repository) => {
    if (window.confirm(`Are you sure you want to delete repository "${repository.name}"?`)) {
      deleteRepositoryMutation.mutate(repository.id)
    }
  }

  const handleCheckRepository = (repository: Repository) => {
    checkRepositoryMutation.mutate(repository.id)
  }

  const handleCompactRepository = (repository: Repository) => {
    setCompactingRepository(repository)
  }

  const handleConfirmCompact = () => {
    if (compactingRepository) {
      compactRepositoryMutation.mutate(compactingRepository.id)
    }
  }

  const handlePruneRepository = (repository: Repository) => {
    setPruningRepository(repository)
    setPruneForm({
      keep_daily: 7,
      keep_weekly: 4,
      keep_monthly: 6,
      keep_yearly: 1,
    })
    setPruneResults(null)
  }

  const handleClosePruneDialog = () => {
    setPruningRepository(null)
    setPruneResults(null)
  }

  const handlePruneDryRun = () => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...pruneForm, dry_run: true }
      })
    }
  }

  const handleConfirmPrune = () => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...pruneForm, dry_run: false }
      })
    }
  }

  const handleConnectionSelect = (connection: SSHConnection | null) => {
    if (connection) {
      setCreateForm({
        ...createForm,
        connection_id: connection.id,
        ssh_key_id: connection.ssh_key_id,
        host: connection.host,
        username: connection.username,
        port: connection.port,
      })
    }
  }

  const openCreateModal = () => {
    setShowCreateModal(true)
    setCreateForm({
      name: '',
      path: '',
      encryption: 'repokey',
      compression: 'lz4',
      passphrase: '',
      source_directories: [],
      exclude_patterns: [],
      repository_type: 'local',
      host: '',
      port: 22,
      username: '',
      ssh_key_id: null,
      connection_id: null,
      remote_path: '',
    })
    setNewSourceDir('')
    setNewExcludePattern('')
  }

  const openImportModal = () => {
    setShowImportModal(true)
    setImportForm({
      name: '',
      path: '',
      passphrase: '',
      compression: 'lz4',
      source_directories: [],
      exclude_patterns: [],
      repository_type: 'local',
      host: '',
      port: 22,
      username: '',
      ssh_key_id: null,
      remote_path: '',
    })
    setNewSourceDir('')
    setNewExcludePattern('')
  }

  const handleImportRepository = (e: React.FormEvent) => {
    e.preventDefault()
    importRepositoryMutation.mutate(importForm)
  }

  const openEditModal = (repository: Repository) => {
    setEditingRepository(repository)
    setEditForm({
      name: repository.name,
      path: repository.path,
      compression: repository.compression,
      source_directories: repository.source_directories || [],
      exclude_patterns: repository.exclude_patterns || [],
      remote_path: (repository as any).remote_path || '',
    })
    setEditNewSourceDir('')
    setEditNewExcludePattern('')
  }

  // Parse source directories from configuration (simple regex-based extraction)
  // REMOVED: Config dependency no longer needed
  // const getSourceDirectories = () => {
  //   if (!defaultConfigData || !defaultConfigData.content) {
  //     return []
  //   }
  //   try {
  //     // Simple extraction from YAML content - look for source_directories section
  //     const content = defaultConfigData.content
  //     const sourceMatch = content.match(/source_directories:\s*\n((?:\s+-\s+.+\n?)+)/)
  //     if (!sourceMatch) return []

  //     // Extract paths from the matched lines
  //     const paths: string[] = sourceMatch[1]
  //       .split('\n')
  //       .map((line: string) => line.trim())
  //       .filter((line: string) => line.startsWith('- '))
  //       .map((line: string) => line.substring(2).trim())
  //       .filter((path: string) => path && path !== '')

  //     return paths
  //   } catch (error) {
  //     console.error('Failed to parse source directories:', error)
  //     return []
  //   }
  // }

  // Generate borg init command preview
  const getBorgInitCommand = () => {
    let repoPath = createForm.path || '/path/to/repository'

    // Build full path for remote repository
    if (createForm.repository_type === 'ssh' && createForm.host && createForm.username) {
      repoPath = `ssh://${createForm.username}@${createForm.host}:${createForm.port}${repoPath.startsWith('/') ? '' : '/'}${repoPath}`
    } else if (createForm.repository_type === 'local') {
      repoPath = repoPath || '/path/to/local/repository'
    }

    return `borg init --encryption ${createForm.encryption} ${repoPath}`
  }

  // Utility functions
  const getEncryptionIcon = (encryption: string) => {
    switch (encryption) {
      case 'repokey':
        return <Shield sx={{ fontSize: 20, color: 'success.main' }} />
      case 'keyfile':
        return <Description sx={{ fontSize: 20, color: 'primary.main' }} />
      case 'none':
        return <Warning sx={{ fontSize: 20, color: 'warning.main' }} />
      default:
        return <Shield sx={{ fontSize: 20, color: 'text.disabled' }} />
    }
  }

  const getCompressionLabel = (compression: string) => {
    switch (compression) {
      case 'lz4':
        return 'LZ4 (Fast)'
      case 'zstd':
        return 'Zstandard'
      case 'zlib':
        return 'Zlib'
      case 'none':
        return 'None'
      default:
        return compression
    }
  }

  const repositories = repositoriesData?.data?.repositories || []
  const sshKeys = sshKeysData?.data?.ssh_keys || []
  const connections = connectionsData?.data?.connections || []
  const connectedConnections = connections.filter((c: SSHConnection) => c.status === 'connected')
  // REMOVED: Config dependency no longer needed
  // const sourceDirectories = getSourceDirectories()

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}>
          <Box sx={{ flex: 1, mr: 2 }}>
            <Typography variant="h4" fontWeight={600} gutterBottom>
              Repository Management
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              A repository is where your backed-up data will be stored. The files from your configured sources will be backed up here.
            </Typography>
          </Box>
          {user?.is_admin && (
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={openCreateModal}
                sx={{ flexShrink: 0 }}
              >
                Create Repository
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileUpload />}
                onClick={openImportModal}
                sx={{ flexShrink: 0 }}
              >
                Import Existing
              </Button>
            </Stack>
          )}
        </Box>

        {/* Source Directories Info */}
        {/* REMOVED: Config dependency no longer needed */}
        {/* {sourceDirectories.length > 0 && (
          <Paper sx={{ p: 2, bgcolor: 'primary.50', border: '1px solid', borderColor: 'primary.200' }}>
            <Box sx={{ display: 'flex', alignItems: 'center', mb: 1.5 }}>
              <Info sx={{ fontSize: 20, color: 'primary.600', mr: 1 }} />
              <Typography variant="subtitle2" fontWeight={600} color="primary.700">
                Configured Source Directories
              </Typography>
            </Box>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              These directories will be backed up to your repository:
            </Typography>
            <List dense disablePadding>
              {sourceDirectories.slice(0, 5).map((dir: string, index: number) => (
                <ListItem key={index} disablePadding sx={{ py: 0.5 }}>
                  <ListItemIcon sx={{ minWidth: 32 }}>
                    <Folder sx={{ fontSize: 18, color: 'primary.600' }} />
                  </ListItemIcon>
                  <ListItemText
                    primary={dir}
                    primaryTypographyProps={{
                      variant: 'body2',
                      sx: { fontFamily: 'monospace', color: 'primary.900' }
                    }}
                  />
                </ListItem>
              ))}
              {sourceDirectories.length > 5 && (
                <ListItem disablePadding>
                  <ListItemText
                    primary={`... and ${sourceDirectories.length - 5} more`}
                    primaryTypographyProps={{
                      variant: 'caption',
                      color: 'text.secondary',
                      sx: { pl: 4 }
                    }}
                  />
                </ListItem>
              )}
            </List>
          </Paper>
        )} */}
      </Box>

      {/* Repositories Grid */}
      {isLoading ? (
        <Box sx={{ textAlign: 'center', py: 8 }}>
          <Typography variant="body2" color="text.secondary">
            Loading repositories...
          </Typography>
        </Box>
      ) : repositories.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 8 }}>
            <Storage sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              No Repositories Yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              Create your first Borg repository to start backing up your data.
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Choose between a local repository on this machine or a remote repository via SSH.
            </Typography>
            {user?.is_admin && (
              <Stack direction="row" spacing={2} justifyContent="center">
                <Button
                  variant="contained"
                  startIcon={<Computer />}
                  onClick={() => {
                    openCreateModal()
                    setCreateForm({ ...createForm, repository_type: 'local' })
                  }}
                >
                  Create Local Repository
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Wifi />}
                  onClick={() => {
                    openCreateModal()
                    setCreateForm({ ...createForm, repository_type: 'ssh' })
                  }}
                >
                  Create Remote Repository (SSH)
                </Button>
              </Stack>
            )}
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={2}>
          {repositories.map((repository: Repository) => (
            <Card
              key={repository.id}
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
              <CardContent sx={{ py: 2.5 }}>
                {/* Repository Header */}
                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', mb: 2 }}>
                  <Box sx={{ flex: 1 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Storage sx={{ fontSize: 28, color: 'primary.main' }} />
                      <Typography variant="h5" fontWeight={600}>
                        {repository.name}
                      </Typography>
                      <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, ml: 1 }}>
                        {getEncryptionIcon(repository.encryption)}
                        <Typography variant="caption" color="text.secondary">
                          {repository.encryption}
                        </Typography>
                      </Box>
                    </Box>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ fontFamily: 'monospace', fontSize: '0.85rem', ml: 4.5 }}
                    >
                      {repository.path}
                    </Typography>
                  </Box>
                </Box>

                {/* Repository Stats - Horizontal Layout */}
                <Box sx={{ display: 'flex', gap: 4, mb: 2, ml: 4.5, flexWrap: 'wrap' }}>
                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Archives
                    </Typography>
                    <Typography variant="h6" fontWeight={600}>
                      {repository.archive_count}
                    </Typography>
                  </Box>

                  {repository.last_backup && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Last Backup
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {formatDateShort(repository.last_backup)}
                      </Typography>
                    </Box>
                  )}

                  <Box>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Compression
                    </Typography>
                    <Typography variant="body2" fontWeight={500}>
                      {getCompressionLabel(repository.compression)}
                    </Typography>
                  </Box>

                  {repository.source_directories && repository.source_directories.length > 0 && (
                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Source Paths
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {repository.source_directories.length} {repository.source_directories.length === 1 ? 'path' : 'paths'}
                      </Typography>
                    </Box>
                  )}
                </Box>

                {/* Action Buttons */}
                {user?.is_admin && (
                  <Box sx={{ display: 'flex', gap: 1, ml: 4.5, flexWrap: 'wrap' }}>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Info />}
                      onClick={() => setViewingInfoRepository(repository)}
                      sx={{ textTransform: 'none' }}
                    >
                      Info
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<CheckCircleIcon />}
                      onClick={() => handleCheckRepository(repository)}
                      disabled={checkRepositoryMutation.isLoading}
                      sx={{ textTransform: 'none' }}
                    >
                      Check
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Refresh />}
                      onClick={() => handleCompactRepository(repository)}
                      disabled={compactRepositoryMutation.isLoading}
                      color="warning"
                      sx={{ textTransform: 'none' }}
                    >
                      Compact
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Delete />}
                      onClick={() => handlePruneRepository(repository)}
                      disabled={pruneRepositoryMutation.isLoading}
                      color="secondary"
                      sx={{ textTransform: 'none' }}
                    >
                      Prune
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Edit />}
                      onClick={() => openEditModal(repository)}
                      sx={{ textTransform: 'none' }}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<Delete />}
                      onClick={() => handleDeleteRepository(repository)}
                      color="error"
                      sx={{ textTransform: 'none' }}
                    >
                      Delete
                    </Button>
                  </Box>
                )}
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}

      {/* Create Repository Dialog */}
      <Dialog open={showCreateModal} onClose={() => setShowCreateModal(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleCreateRepository}>
          <DialogTitle>Create Repository</DialogTitle>
          <DialogContent>
            {/* Command Preview */}
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                Command Preview
              </Typography>
              <Box sx={{
                bgcolor: 'grey.900',
                color: 'grey.100',
                p: 1.5,
                borderRadius: 1,
                fontFamily: 'monospace',
                fontSize: '0.875rem',
                overflow: 'auto'
              }}>
                {getBorgInitCommand()}
              </Box>
            </Alert>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                required
                fullWidth
              />

              <FormControl fullWidth>
                <InputLabel>Repository Type</InputLabel>
                <Select
                  value={createForm.repository_type}
                  label="Repository Type"
                  onChange={(e) => setCreateForm({ ...createForm, repository_type: e.target.value })}
                >
                  <MenuItem value="local">Local</MenuItem>
                  <MenuItem value="ssh">SSH</MenuItem>
                  <MenuItem value="sftp">SFTP</MenuItem>
                </Select>
              </FormControl>

              {createForm.repository_type !== 'local' && (
                <>
                  <Alert severity="info">
                    Select an existing SSH connection or enter connection details manually
                  </Alert>

                  <Autocomplete<SSHConnection>
                    options={connectedConnections}
                    getOptionLabel={(option: SSHConnection) => `${option.username}@${option.host}:${option.port} (${option.ssh_key_name})`}
                    onChange={(_, value: SSHConnection | null) => handleConnectionSelect(value)}
                    renderInput={(params) => (
                      <TextField
                        {...params}
                        label="SSH Connection (Optional)"
                        placeholder="Select a connection to auto-fill"
                      />
                    )}
                  />

                  <Divider>OR enter manually</Divider>

                  <TextField
                    label="Host"
                    value={createForm.host}
                    onChange={(e) => setCreateForm({ ...createForm, host: e.target.value })}
                    placeholder="192.168.1.100"
                    required
                    fullWidth
                  />

                  <TextField
                    label="Username"
                    value={createForm.username}
                    onChange={(e) => setCreateForm({ ...createForm, username: e.target.value })}
                    placeholder="user"
                    required
                    fullWidth
                  />

                  <TextField
                    label="Port"
                    type="number"
                    value={createForm.port}
                    onChange={(e) => setCreateForm({ ...createForm, port: parseInt(e.target.value) })}
                    required
                    fullWidth
                  />

                  <FormControl fullWidth required>
                    <InputLabel>SSH Key</InputLabel>
                    <Select
                      value={createForm.ssh_key_id ?? ''}
                      label="SSH Key"
                      onChange={(e) => setCreateForm({ ...createForm, ssh_key_id: e.target.value ? Number(e.target.value) : null })}
                    >
                      <MenuItem value="">Select SSH Key</MenuItem>
                      {sshKeys
                        .filter((key: SSHKey) => key.is_active)
                        .map((key: SSHKey) => (
                          <MenuItem key={key.id} value={key.id.toString()}>
                            {key.name} ({key.key_type})
                          </MenuItem>
                        ))}
                    </Select>
                  </FormControl>

                  <TextField
                    label="Remote Borg Path (Optional)"
                    value={createForm.remote_path}
                    onChange={(e) => setCreateForm({ ...createForm, remote_path: e.target.value })}
                    placeholder="/usr/local/bin/borg"
                    fullWidth
                    helperText="Path to borg executable on remote server. Leave empty if borg is in PATH."
                  />
                </>
              )}

              <TextField
                label="Path"
                value={createForm.path}
                onChange={(e) => setCreateForm({ ...createForm, path: e.target.value })}
                placeholder={createForm.repository_type === 'local' ? '/path/to/repository' : '/path/to/repository'}
                required
                fullWidth
                helperText="Any path is allowed. Directory will be created automatically."
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <IconButton
                        onClick={() => setShowPathExplorer(true)}
                        edge="end"
                        size="small"
                        title="Browse filesystem"
                      >
                        <FolderOpen fontSize="small" />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />

              <FormControl fullWidth>
                <InputLabel>Encryption</InputLabel>
                <Select
                  value={createForm.encryption}
                  label="Encryption"
                  onChange={(e) => setCreateForm({ ...createForm, encryption: e.target.value })}
                >
                  <MenuItem value="repokey">Repokey (Recommended)</MenuItem>
                  <MenuItem value="keyfile">Keyfile</MenuItem>
                  <MenuItem value="none">None (Unencrypted)</MenuItem>
                </Select>
              </FormControl>

              <FormControl fullWidth>
                <InputLabel>Compression</InputLabel>
                <Select
                  value={createForm.compression}
                  label="Compression"
                  onChange={(e) => setCreateForm({ ...createForm, compression: e.target.value })}
                >
                  <MenuItem value="lz4">LZ4 (Fast)</MenuItem>
                  <MenuItem value="zstd">Zstandard</MenuItem>
                  <MenuItem value="zlib">Zlib</MenuItem>
                  <MenuItem value="none">None</MenuItem>
                </Select>
              </FormControl>

              {createForm.encryption !== 'none' && (
                <TextField
                  label="Passphrase"
                  type="password"
                  value={createForm.passphrase}
                  onChange={(e) => setCreateForm({ ...createForm, passphrase: e.target.value })}
                  placeholder="Enter passphrase"
                  fullWidth
                />
              )}

              {/* Source Directories */}
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Source Directories <Box component="span" sx={{ color: 'error.main' }}>*</Box>
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Specify which directories to backup to this repository (at least one required)
                </Typography>

                {createForm.source_directories.length === 0 && (
                  <Alert severity="warning" sx={{ mb: 1.5 }}>
                    At least one source directory is required. Add the directories you want to backup.
                  </Alert>
                )}

                {createForm.source_directories.length > 0 && (
                  <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                    {createForm.source_directories.map((dir, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                          {dir}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => {
                            setCreateForm({
                              ...createForm,
                              source_directories: createForm.source_directories.filter((_, i) => i !== index)
                            })
                          }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    ))}
                  </Stack>
                )}

                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    value={newSourceDir}
                    onChange={(e) => setNewSourceDir(e.target.value)}
                    placeholder="/home/user/documents"
                    size="small"
                    fullWidth
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (newSourceDir.trim()) {
                          setCreateForm({
                            ...createForm,
                            source_directories: [...createForm.source_directories, newSourceDir.trim()]
                          })
                          setNewSourceDir('')
                        }
                      }
                    }}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            onClick={() => setShowSourceDirExplorer(true)}
                            edge="end"
                            size="small"
                            title="Browse directories"
                          >
                            <FolderOpen fontSize="small" />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      if (newSourceDir.trim()) {
                        setCreateForm({
                          ...createForm,
                          source_directories: [...createForm.source_directories, newSourceDir.trim()]
                        })
                        setNewSourceDir('')
                      }
                    }}
                  >
                    Add
                  </Button>
                </Box>
              </Box>

              {/* Exclude Patterns */}
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Exclude Patterns (Optional)
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Specify patterns to exclude from backup (e.g., *.log, *.tmp, __pycache__, node_modules)
                </Typography>

                {createForm.exclude_patterns.length > 0 && (
                  <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                    {createForm.exclude_patterns.map((pattern, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                          {pattern}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => {
                            setCreateForm({
                              ...createForm,
                              exclude_patterns: createForm.exclude_patterns.filter((_, i) => i !== index)
                            })
                          }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    ))}
                  </Stack>
                )}

                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    value={newExcludePattern}
                    onChange={(e) => setNewExcludePattern(e.target.value)}
                    placeholder="*.log or /path/to/exclude"
                    size="small"
                    fullWidth
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (newExcludePattern.trim()) {
                          setCreateForm({
                            ...createForm,
                            exclude_patterns: [...createForm.exclude_patterns, newExcludePattern.trim()]
                          })
                          setNewExcludePattern('')
                        }
                      }
                    }}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            onClick={() => setShowExcludeExplorer(true)}
                            edge="end"
                            size="small"
                            title="Browse directories to exclude"
                          >
                            <FolderOpen fontSize="small" />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      if (newExcludePattern.trim()) {
                        setCreateForm({
                          ...createForm,
                          exclude_patterns: [...createForm.exclude_patterns, newExcludePattern.trim()]
                        })
                        setNewExcludePattern('')
                      }
                    }}
                  >
                    Add
                  </Button>
                </Box>
              </Box>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createRepositoryMutation.isLoading || createForm.source_directories.length === 0}
            >
              {createRepositoryMutation.isLoading ? 'Creating...' : 'Create'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Import Existing Repository Dialog */}
      <Dialog open={showImportModal} onClose={() => setShowImportModal(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleImportRepository}>
          <DialogTitle>Import Existing Repository</DialogTitle>
          <DialogContent>
            <Alert severity="info" sx={{ mb: 2 }}>
              Import a Borg repository that already exists. The repository will be verified before import.
            </Alert>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Repository Name"
                value={importForm.name}
                onChange={(e) => setImportForm({ ...importForm, name: e.target.value })}
                required
                fullWidth
                helperText="A friendly name to identify this repository in the UI"
              />

              <FormControl fullWidth>
                <InputLabel>Repository Type</InputLabel>
                <Select
                  value={importForm.repository_type}
                  label="Repository Type"
                  onChange={(e) => setImportForm({ ...importForm, repository_type: e.target.value })}
                >
                  <MenuItem value="local">Local</MenuItem>
                  <MenuItem value="ssh">SSH</MenuItem>
                </Select>
              </FormControl>

              {importForm.repository_type !== 'local' && (
                <>
                  <TextField
                    label="Host"
                    value={importForm.host}
                    onChange={(e) => setImportForm({ ...importForm, host: e.target.value })}
                    placeholder="192.168.1.100"
                    required
                    fullWidth
                  />

                  <TextField
                    label="Username"
                    value={importForm.username}
                    onChange={(e) => setImportForm({ ...importForm, username: e.target.value })}
                    placeholder="user"
                    required
                    fullWidth
                  />

                  <TextField
                    label="Port"
                    type="number"
                    value={importForm.port}
                    onChange={(e) => setImportForm({ ...importForm, port: parseInt(e.target.value) })}
                    required
                    fullWidth
                  />

                  <FormControl fullWidth>
                    <InputLabel>SSH Key</InputLabel>
                    <Select
                      value={importForm.ssh_key_id ?? ''}
                      label="SSH Key"
                      onChange={(e) => setImportForm({ ...importForm, ssh_key_id: e.target.value ? Number(e.target.value) : null })}
                    >
                      <MenuItem value="">Select SSH Key</MenuItem>
                      {sshKeysData?.data?.ssh_keys?.map((key: SSHKey) => (
                        <MenuItem key={key.id} value={key.id}>
                          {key.name} ({key.key_type})
                        </MenuItem>
                      ))}
                    </Select>
                  </FormControl>

                  <TextField
                    label="Remote Borg Path (Optional)"
                    value={importForm.remote_path}
                    onChange={(e) => setImportForm({ ...importForm, remote_path: e.target.value })}
                    placeholder="/usr/local/bin/borg"
                    fullWidth
                  />
                </>
              )}

              <TextField
                label="Repository Path"
                value={importForm.path}
                onChange={(e) => setImportForm({ ...importForm, path: e.target.value })}
                placeholder={importForm.repository_type === 'local' ? '/local/path/to/existing/repo' : '/path/to/existing/repo'}
                required
                fullWidth
                helperText={importForm.repository_type === 'local' ? 'Full path to the existing Borg repository' : 'Path to repository on remote server'}
                InputProps={{
                  endAdornment: importForm.repository_type === 'local' && (
                    <InputAdornment position="end">
                      <IconButton onClick={() => setShowImportPathExplorer(true)} edge="end">
                        <FolderOpen />
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />

              <TextField
                label="Passphrase"
                type="password"
                value={importForm.passphrase}
                onChange={(e) => setImportForm({ ...importForm, passphrase: e.target.value })}
                placeholder="Repository passphrase (if encrypted)"
                fullWidth
                helperText="Required if the repository is encrypted"
              />

              <FormControl fullWidth>
                <InputLabel>Default Compression</InputLabel>
                <Select
                  value={importForm.compression}
                  label="Default Compression"
                  onChange={(e) => setImportForm({ ...importForm, compression: e.target.value })}
                >
                  <MenuItem value="lz4">LZ4 (Fast)</MenuItem>
                  <MenuItem value="zstd">Zstandard</MenuItem>
                  <MenuItem value="zlib">Zlib</MenuItem>
                  <MenuItem value="none">None</MenuItem>
                </Select>
              </FormControl>

              <Divider />

              <Typography variant="subtitle2" fontWeight={600}>
                Source Directories <Box component="span" sx={{ color: 'error.main' }}>*</Box>
              </Typography>
              <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                Specify which directories to backup to this repository (at least one required)
              </Typography>

              {importForm.source_directories.length === 0 && (
                <Alert severity="warning" sx={{ mb: 1.5 }}>
                  At least one source directory is required. Add the directories you want to backup.
                </Alert>
              )}

              <Box>
                <Typography variant="body2" color="text.secondary" gutterBottom>
                  Directories to backup:
                </Typography>
                {importForm.source_directories.length > 0 && (
                  <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                    {importForm.source_directories.map((dir, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                          {dir}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => {
                            setImportForm({
                              ...importForm,
                              source_directories: importForm.source_directories.filter((_, i) => i !== index)
                            })
                          }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    ))}
                  </Stack>
                )}

                <Stack direction="row" spacing={1}>
                  <TextField
                    size="small"
                    placeholder="/path/to/source"
                    value={newSourceDir}
                    onChange={(e) => setNewSourceDir(e.target.value)}
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (newSourceDir.trim()) {
                          setImportForm({
                            ...importForm,
                            source_directories: [...importForm.source_directories, newSourceDir.trim()]
                          })
                          setNewSourceDir('')
                        }
                      }
                    }}
                    fullWidth
                  />
                  <Button
                    size="small"
                    variant="outlined"
                    onClick={() => {
                      if (newSourceDir.trim()) {
                        setImportForm({
                          ...importForm,
                          source_directories: [...importForm.source_directories, newSourceDir.trim()]
                        })
                        setNewSourceDir('')
                      }
                    }}
                  >
                    Add
                  </Button>
                  <IconButton size="small" onClick={() => setShowImportSourceDirExplorer(true)}>
                    <FolderOpen />
                  </IconButton>
                </Stack>
              </Box>
            </Box>
          </DialogContent>

          <DialogActions>
            <Button onClick={() => setShowImportModal(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={importRepositoryMutation.isLoading || importForm.source_directories.length === 0}
            >
              {importRepositoryMutation.isLoading ? 'Importing...' : 'Import'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Edit Repository Dialog */}
      <Dialog open={!!editingRepository} onClose={() => setEditingRepository(null)} maxWidth="sm" fullWidth>
        <form onSubmit={handleUpdateRepository}>
          <DialogTitle>Edit Repository</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                fullWidth
              />

              <TextField
                label="Path"
                value={editForm.path}
                onChange={(e) => setEditForm({ ...editForm, path: e.target.value })}
                required
                fullWidth
              />

              <FormControl fullWidth>
                <InputLabel>Compression</InputLabel>
                <Select
                  value={editForm.compression}
                  label="Compression"
                  onChange={(e) => setEditForm({ ...editForm, compression: e.target.value })}
                >
                  <MenuItem value="lz4">LZ4 (Fast)</MenuItem>
                  <MenuItem value="zstd">Zstandard</MenuItem>
                  <MenuItem value="zlib">Zlib</MenuItem>
                  <MenuItem value="none">None</MenuItem>
                </Select>
              </FormControl>

              <TextField
                label="Remote Borg Path (Optional)"
                value={editForm.remote_path}
                onChange={(e) => setEditForm({ ...editForm, remote_path: e.target.value })}
                placeholder="/usr/local/bin/borg"
                fullWidth
                helperText="Path to borg executable on remote server. Leave empty if borg is in PATH."
              />

              {/* Source Directories */}
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Source Directories (Optional)
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Specify which directories to backup to this repository
                </Typography>

                {editForm.source_directories.length > 0 && (
                  <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                    {editForm.source_directories.map((dir, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                          {dir}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => {
                            setEditForm({
                              ...editForm,
                              source_directories: editForm.source_directories.filter((_, i) => i !== index)
                            })
                          }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    ))}
                  </Stack>
                )}

                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    value={editNewSourceDir}
                    onChange={(e) => setEditNewSourceDir(e.target.value)}
                    placeholder="/home/user/documents"
                    size="small"
                    fullWidth
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (editNewSourceDir.trim()) {
                          setEditForm({
                            ...editForm,
                            source_directories: [...editForm.source_directories, editNewSourceDir.trim()]
                          })
                          setEditNewSourceDir('')
                        }
                      }
                    }}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            onClick={() => setShowEditSourceDirExplorer(true)}
                            edge="end"
                            size="small"
                            title="Browse directories"
                          >
                            <FolderOpen fontSize="small" />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      if (editNewSourceDir.trim()) {
                        setEditForm({
                          ...editForm,
                          source_directories: [...editForm.source_directories, editNewSourceDir.trim()]
                        })
                        setEditNewSourceDir('')
                      }
                    }}
                  >
                    Add
                  </Button>
                </Box>
              </Box>

              {/* Exclude Patterns */}
              <Box>
                <Typography variant="subtitle2" gutterBottom>
                  Exclude Patterns (Optional)
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Specify patterns to exclude from backup (e.g., *.log, *.tmp, __pycache__, node_modules)
                </Typography>

                {editForm.exclude_patterns.length > 0 && (
                  <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                    {editForm.exclude_patterns.map((pattern, index) => (
                      <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                        <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                          {pattern}
                        </Typography>
                        <IconButton
                          size="small"
                          onClick={() => {
                            setEditForm({
                              ...editForm,
                              exclude_patterns: editForm.exclude_patterns.filter((_, i) => i !== index)
                            })
                          }}
                        >
                          <Delete fontSize="small" />
                        </IconButton>
                      </Box>
                    ))}
                  </Stack>
                )}

                <Box sx={{ display: 'flex', gap: 1 }}>
                  <TextField
                    value={editNewExcludePattern}
                    onChange={(e) => setEditNewExcludePattern(e.target.value)}
                    placeholder="*.log or /path/to/exclude"
                    size="small"
                    fullWidth
                    onKeyPress={(e) => {
                      if (e.key === 'Enter') {
                        e.preventDefault()
                        if (editNewExcludePattern.trim()) {
                          setEditForm({
                            ...editForm,
                            exclude_patterns: [...editForm.exclude_patterns, editNewExcludePattern.trim()]
                          })
                          setEditNewExcludePattern('')
                        }
                      }
                    }}
                    InputProps={{
                      endAdornment: (
                        <InputAdornment position="end">
                          <IconButton
                            onClick={() => setShowEditExcludeExplorer(true)}
                            edge="end"
                            size="small"
                            title="Browse directories to exclude"
                          >
                            <FolderOpen fontSize="small" />
                          </IconButton>
                        </InputAdornment>
                      ),
                    }}
                  />
                  <Button
                    variant="outlined"
                    size="small"
                    onClick={() => {
                      if (editNewExcludePattern.trim()) {
                        setEditForm({
                          ...editForm,
                          exclude_patterns: [...editForm.exclude_patterns, editNewExcludePattern.trim()]
                        })
                        setEditNewExcludePattern('')
                      }
                    }}
                  >
                    Add
                  </Button>
                </Box>
              </Box>

            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditingRepository(null)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={updateRepositoryMutation.isLoading}>
              {updateRepositoryMutation.isLoading ? 'Updating...' : 'Update'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Repository Info Dialog */}
      <Dialog
        open={!!viewingInfoRepository}
        onClose={() => setViewingInfoRepository(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Storage color="primary" />
            <Typography variant="h5" fontWeight={600}>
              {viewingInfoRepository?.name}
            </Typography>
          </Box>
        </DialogTitle>
        <DialogContent>
          {loadingInfo ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <Typography variant="body2" color="text.secondary">
                Loading repository info...
              </Typography>
            </Box>
          ) : repositoryInfo?.data ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
              {/* Repository Details Cards */}
              <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
                {/* Encryption */}
                <Card sx={{ backgroundColor: '#f3e5f5' }}>
                  <CardContent sx={{ py: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                      <Lock sx={{ color: '#7b1fa2', fontSize: 28 }} />
                      <Typography variant="body2" color="text.secondary" fontWeight={500}>
                        Encryption
                      </Typography>
                    </Box>
                    <Typography variant="h6" fontWeight={700} sx={{ color: '#7b1fa2', ml: 5 }}>
                      {repositoryInfo.data.info?.encryption?.mode || 'N/A'}
                    </Typography>
                  </CardContent>
                </Card>

                {/* Last Modified */}
                <Card sx={{ backgroundColor: '#e1f5fe' }}>
                  <CardContent sx={{ py: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 1 }}>
                      <CalendarMonth sx={{ color: '#0277bd', fontSize: 28 }} />
                      <Typography variant="body2" color="text.secondary" fontWeight={500}>
                        Last Modified
                      </Typography>
                    </Box>
                    <Typography variant="body2" fontWeight={600} sx={{ color: '#0277bd', ml: 5 }}>
                      {repositoryInfo.data.info?.repository?.last_modified
                        ? formatDateShort(repositoryInfo.data.info.repository.last_modified)
                        : 'N/A'}
                    </Typography>
                  </CardContent>
                </Card>
              </Box>

              {/* Location */}
              <Card variant="outlined">
                <CardContent sx={{ py: 2 }}>
                  <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                    Repository Location
                  </Typography>
                  <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                    {repositoryInfo.data.info?.repository?.location || 'N/A'}
                  </Typography>
                </CardContent>
              </Card>

              {/* Storage Statistics */}
              {repositoryInfo.data.info?.cache?.stats && repositoryInfo.data.info.cache.stats.unique_size > 0 ? (
                <>
                  <Typography variant="h6" fontWeight={600} sx={{ mt: 1 }}>
                    Storage Statistics
                  </Typography>
                  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: 2 }}>
                    {/* Total Data Size */}
                    <Card sx={{ backgroundColor: '#e8f5e9' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <DataUsage sx={{ color: '#2e7d32', fontSize: 24 }} />
                          <Typography variant="caption" color="text.secondary" fontWeight={500}>
                            Total Size
                          </Typography>
                        </Box>
                        <Typography variant="h6" fontWeight={700} sx={{ color: '#2e7d32' }}>
                          {formatBytes(repositoryInfo.data.info.cache.stats.total_size)}
                        </Typography>
                      </CardContent>
                    </Card>

                    {/* Unique Compressed */}
                    <Card sx={{ backgroundColor: '#e3f2fd' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Compress sx={{ color: '#1565c0', fontSize: 24 }} />
                          <Typography variant="caption" color="text.secondary" fontWeight={500}>
                            Used on Disk
                          </Typography>
                        </Box>
                        <Typography variant="h6" fontWeight={700} sx={{ color: '#1565c0' }}>
                          {formatBytes(repositoryInfo.data.info.cache.stats.unique_csize)}
                        </Typography>
                      </CardContent>
                    </Card>

                    {/* Deduplicated Size */}
                    <Card sx={{ backgroundColor: '#fff3e0' }}>
                      <CardContent sx={{ py: 2 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                          <Inventory sx={{ color: '#e65100', fontSize: 24 }} />
                          <Typography variant="caption" color="text.secondary" fontWeight={500}>
                            Unique Data
                          </Typography>
                        </Box>
                        <Typography variant="h6" fontWeight={700} sx={{ color: '#e65100' }}>
                          {formatBytes(repositoryInfo.data.info.cache.stats.unique_size)}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Box>

                  {/* Chunk Statistics */}
                  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}>
                    <Card variant="outlined">
                      <CardContent sx={{ py: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Total Chunks
                        </Typography>
                        <Typography variant="h6" fontWeight={600}>
                          {repositoryInfo.data.info.cache.stats.total_chunks?.toLocaleString()}
                        </Typography>
                      </CardContent>
                    </Card>

                    <Card variant="outlined">
                      <CardContent sx={{ py: 1.5 }}>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Unique Chunks
                        </Typography>
                        <Typography variant="h6" fontWeight={600}>
                          {repositoryInfo.data.info.cache.stats.total_unique_chunks?.toLocaleString()}
                        </Typography>
                      </CardContent>
                    </Card>
                  </Box>
                </>
              ) : (
                <Alert severity="info" icon={<Info />}>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    No backups yet
                  </Typography>
                  <Typography variant="body2" color="text.secondary">
                    This repository has been initialized but contains no archives. Storage statistics will appear here after you create your first backup.
                  </Typography>
                </Alert>
              )}
            </Box>
          ) : (
            <Alert severity="error">
              Failed to load repository information. Make sure the repository is accessible and properly initialized.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewingInfoRepository(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Compact Repository Dialog */}
      <Dialog
        open={!!compactingRepository}
        onClose={() => setCompactingRepository(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Refresh color="warning" />
            <Typography variant="h6" fontWeight={600}>
              Compact Repository
            </Typography>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 2 }}>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              What does compacting do?
            </Typography>
            <Typography variant="body2">
              Compacting reclaims space from deleted archives. When you delete archives, the space isn't immediately freed.
              Running compact will reorganize repository segments and free up disk space.
            </Typography>
          </Alert>

          <Box sx={{ bgcolor: 'grey.50', p: 2, borderRadius: 1 }}>
            <Typography variant="body2" gutterBottom>
              <strong>Repository:</strong> {compactingRepository?.name}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', fontSize: '0.85rem' }}>
              {compactingRepository?.path}
            </Typography>
          </Box>

          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2">
              This operation can take several minutes depending on repository size. The repository will remain accessible during compaction.
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setCompactingRepository(null)}>
            Cancel
          </Button>
          <Button
            onClick={handleConfirmCompact}
            variant="contained"
            color="warning"
            disabled={compactRepositoryMutation.isLoading}
            startIcon={compactRepositoryMutation.isLoading ? <Refresh className="animate-spin" /> : <Refresh />}
          >
            {compactRepositoryMutation.isLoading ? 'Compacting...' : 'Start Compacting'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Prune Repository Dialog */}
      <Dialog
        open={!!pruningRepository}
        onClose={handleClosePruneDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
            <Delete color="secondary" />
            <Typography variant="h6" fontWeight={600}>
              Prune Archives
            </Typography>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Alert severity="info" sx={{ mb: 3 }}>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              What does pruning do?
            </Typography>
            <Typography variant="body2" gutterBottom>
              Pruning automatically deletes old archives based on retention rules. This helps manage repository size by keeping
              only the backups you need.
            </Typography>
            <Typography variant="body2" fontWeight={600} color="primary.main">
              💡 Tip: Always run "Dry Run" first to preview what will be deleted!
            </Typography>
          </Alert>

          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Retention Policy
          </Typography>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
            Specify how many backups to keep for each time period
          </Typography>

          <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2, mb: 3 }}>
            <TextField
              label="Keep Daily"
              type="number"
              value={pruneForm.keep_daily}
              onChange={(e) => setPruneForm({ ...pruneForm, keep_daily: parseInt(e.target.value) || 0 })}
              helperText="Last N daily backups"
              fullWidth
            />
            <TextField
              label="Keep Weekly"
              type="number"
              value={pruneForm.keep_weekly}
              onChange={(e) => setPruneForm({ ...pruneForm, keep_weekly: parseInt(e.target.value) || 0 })}
              helperText="Last N weekly backups"
              fullWidth
            />
            <TextField
              label="Keep Monthly"
              type="number"
              value={pruneForm.keep_monthly}
              onChange={(e) => setPruneForm({ ...pruneForm, keep_monthly: parseInt(e.target.value) || 0 })}
              helperText="Last N monthly backups"
              fullWidth
            />
            <TextField
              label="Keep Yearly"
              type="number"
              value={pruneForm.keep_yearly}
              onChange={(e) => setPruneForm({ ...pruneForm, keep_yearly: parseInt(e.target.value) || 0 })}
              helperText="Last N yearly backups"
              fullWidth
            />
          </Box>

          <Box sx={{ bgcolor: 'grey.50', p: 2, borderRadius: 1, mb: 2 }}>
            <Typography variant="body2" gutterBottom>
              <strong>Repository:</strong> {pruningRepository?.name}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block">
              Example: With these settings, you'll keep the last 7 daily, 4 weekly, 6 monthly, and 1 yearly backup. Older archives will be deleted.
            </Typography>
          </Box>

          {/* Prune Results Display */}
          {pruneResults && (
            <Box sx={{ mt: 2 }}>
              <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                {pruneResults.dry_run ? 'Dry Run Results (Preview)' : 'Prune Results'}
              </Typography>

              {pruneResults.prune_result?.success === false ? (
                <Alert severity="error" sx={{ mb: 2 }}>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    Operation Failed
                  </Typography>
                  {pruneResults.prune_result?.stderr && (
                    <Box
                      component="pre"
                      sx={{
                        mt: 1,
                        p: 1.5,
                        bgcolor: 'rgba(0,0,0,0.05)',
                        borderRadius: 1,
                        fontSize: '0.75rem',
                        overflow: 'auto',
                        maxHeight: 200,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word'
                      }}
                    >
                      {pruneResults.prune_result.stderr}
                    </Box>
                  )}
                </Alert>
              ) : (
                <Card variant="outlined" sx={{ mb: 2 }}>
                  <CardContent>
                    {pruneResults.prune_result?.stdout && (
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                          Output:
                        </Typography>
                        <Box
                          component="pre"
                          sx={{
                            p: 1.5,
                            bgcolor: 'grey.50',
                            borderRadius: 1,
                            fontSize: '0.75rem',
                            overflow: 'auto',
                            maxHeight: 300,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'monospace'
                          }}
                        >
                          {pruneResults.prune_result.stdout || 'No output'}
                        </Box>
                      </Box>
                    )}
                    {pruneResults.prune_result?.stderr && (
                      <Box sx={{ mt: 2 }}>
                        <Typography variant="caption" color="text.secondary" display="block" gutterBottom>
                          Messages:
                        </Typography>
                        <Box
                          component="pre"
                          sx={{
                            p: 1.5,
                            bgcolor: 'warning.lighter',
                            borderRadius: 1,
                            fontSize: '0.75rem',
                            overflow: 'auto',
                            maxHeight: 200,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'monospace'
                          }}
                        >
                          {pruneResults.prune_result.stderr}
                        </Box>
                      </Box>
                    )}
                  </CardContent>
                </Card>
              )}

              {pruneResults.dry_run && pruneResults.prune_result?.success !== false && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  <Typography variant="body2">
                    ✓ Dry run completed successfully. Review the output above to see which archives would be deleted.
                    If everything looks correct, click "Prune Archives" to execute.
                  </Typography>
                </Alert>
              )}
            </Box>
          )}

          <Alert severity="warning">
            <Typography variant="body2" fontWeight={600} gutterBottom>
              ⚠️ Warning: Deleted archives cannot be recovered!
            </Typography>
            <Typography variant="body2">
              After pruning, run "Compact" to actually free up disk space.
            </Typography>
          </Alert>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleClosePruneDialog}>
            Cancel
          </Button>
          <Button
            onClick={handlePruneDryRun}
            variant="outlined"
            disabled={pruneRepositoryMutation.isLoading}
            startIcon={<Info />}
          >
            Dry Run (Preview)
          </Button>
          <Button
            onClick={handleConfirmPrune}
            variant="contained"
            color="error"
            disabled={pruneRepositoryMutation.isLoading}
            startIcon={pruneRepositoryMutation.isLoading ? <Delete className="animate-spin" /> : <Delete />}
          >
            {pruneRepositoryMutation.isLoading ? 'Pruning...' : 'Prune Archives'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* File Explorer Dialogs */}
      <FileExplorerDialog
        open={showPathExplorer}
        onClose={() => setShowPathExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            setCreateForm({ ...createForm, path: paths[0] })
          }
        }}
        title="Select Repository Path"
        initialPath="/"
        multiSelect={false}
        connectionType={createForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          createForm.repository_type !== 'local' && createForm.ssh_key_id
            ? {
                ssh_key_id: createForm.ssh_key_id,
                host: createForm.host,
                username: createForm.username,
                port: createForm.port,
              }
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showSourceDirExplorer}
        onClose={() => setShowSourceDirExplorer(false)}
        onSelect={(paths) => {
          setCreateForm({
            ...createForm,
            source_directories: [...createForm.source_directories, ...paths],
          })
        }}
        title="Select Source Directories"
        initialPath="/"
        multiSelect={true}
        connectionType={createForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          createForm.repository_type !== 'local' && createForm.ssh_key_id
            ? {
                ssh_key_id: createForm.ssh_key_id,
                host: createForm.host,
                username: createForm.username,
                port: createForm.port,
              }
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showExcludeExplorer}
        onClose={() => setShowExcludeExplorer(false)}
        onSelect={(paths) => {
          setCreateForm({
            ...createForm,
            exclude_patterns: [...createForm.exclude_patterns, ...paths],
          })
        }}
        title="Select Directories to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType={createForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          createForm.repository_type !== 'local' && createForm.ssh_key_id
            ? {
                ssh_key_id: createForm.ssh_key_id,
                host: createForm.host,
                username: createForm.username,
                port: createForm.port,
              }
            : undefined
        }
        selectMode="both"
      />

      {/* Edit Dialog File Explorers */}
      <FileExplorerDialog
        open={showEditSourceDirExplorer}
        onClose={() => setShowEditSourceDirExplorer(false)}
        onSelect={(paths) => {
          setEditForm({
            ...editForm,
            source_directories: [...editForm.source_directories, ...paths],
          })
        }}
        title="Select Source Directories"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showEditExcludeExplorer}
        onClose={() => setShowEditExcludeExplorer(false)}
        onSelect={(paths) => {
          setEditForm({
            ...editForm,
            exclude_patterns: [...editForm.exclude_patterns, ...paths],
          })
        }}
        title="Select Directories to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="both"
      />

      {/* File Explorer Dialogs for Import */}
      <FileExplorerDialog
        open={showImportPathExplorer}
        onClose={() => setShowImportPathExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            setImportForm({ ...importForm, path: paths[0] })
          }
        }}
        title="Select Repository Path"
        initialPath="/"
        multiSelect={false}
        connectionType={importForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          importForm.repository_type !== 'local' && importForm.ssh_key_id
            ? {
                ssh_key_id: importForm.ssh_key_id,
                host: importForm.host,
                username: importForm.username,
                port: importForm.port,
              }
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showImportSourceDirExplorer}
        onClose={() => setShowImportSourceDirExplorer(false)}
        onSelect={(paths) => {
          setImportForm({
            ...importForm,
            source_directories: [...importForm.source_directories, ...paths],
          })
        }}
        title="Select Source Directories"
        initialPath="/"
        multiSelect={true}
        connectionType={importForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          importForm.repository_type !== 'local' && importForm.ssh_key_id
            ? {
                ssh_key_id: importForm.ssh_key_id,
                host: importForm.host,
                username: importForm.username,
                port: importForm.port,
              }
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showImportExcludeExplorer}
        onClose={() => setShowImportExcludeExplorer(false)}
        onSelect={(paths) => {
          setImportForm({
            ...importForm,
            exclude_patterns: [...importForm.exclude_patterns, ...paths],
          })
        }}
        title="Select Directories to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType={importForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          importForm.repository_type !== 'local' && importForm.ssh_key_id
            ? {
                ssh_key_id: importForm.ssh_key_id,
                host: importForm.host,
                username: importForm.username,
                port: importForm.port,
              }
            : undefined
        }
        selectMode="both"
      />
    </Box>
  )
}
