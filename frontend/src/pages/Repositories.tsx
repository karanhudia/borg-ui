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
} from '@mui/icons-material'
import { repositoriesAPI, sshKeysAPI } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAppState } from '../context/AppContext'

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
  const [editingRepository, setEditingRepository] = useState<Repository | null>(null)
  const [viewingInfoRepository, setViewingInfoRepository] = useState<Repository | null>(null)

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
      toast.success('Repository compaction completed')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to compact repository')
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

  const [newSourceDir, setNewSourceDir] = useState('')
  const [newExcludePattern, setNewExcludePattern] = useState('')

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
    if (window.confirm(`Are you sure you want to compact repository "${repository.name}"?`)) {
      compactRepositoryMutation.mutate(repository.id)
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
            <Button
              variant="contained"
              startIcon={<Add />}
              onClick={openCreateModal}
              sx={{ flexShrink: 0 }}
            >
              Create Repository
            </Button>
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
        <Stack direction={{ xs: 'column', md: 'row' }} flexWrap="wrap" spacing={3}>
          {repositories.map((repository: Repository) => (
            <Box key={repository.id} sx={{ flex: { xs: '1 1 100%', md: '1 1 calc(33.333% - 16px)' }, minWidth: 300 }}>
              <Card>
                <CardContent>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', mb: 2 }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
                      <Storage color="primary" />
                      <Typography variant="h6" fontWeight={600}>
                        {repository.name}
                      </Typography>
                    </Box>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      {getEncryptionIcon(repository.encryption)}
                      <Typography variant="caption" color="text.secondary">
                        {repository.encryption}
                      </Typography>
                    </Box>
                  </Box>

                  <Box sx={{ mb: 2 }}>
                    <Typography variant="caption" color="text.secondary" display="block">
                      Path
                    </Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}>
                      {repository.path}
                    </Typography>
                  </Box>

                  <Stack spacing={1.5}>
                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block">
                        Compression
                      </Typography>
                      <Typography variant="body2">
                        {getCompressionLabel(repository.compression)}
                      </Typography>
                    </Box>

                    <Box>
                      <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                        Archives
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {repository.archive_count}
                      </Typography>
                    </Box>

                    {repository.last_backup && (
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Last Backup
                        </Typography>
                        <Typography variant="body2">
                          {new Date(repository.last_backup).toLocaleDateString()}
                        </Typography>
                      </Box>
                    )}

                    {repository.total_size && (
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block">
                          Total Size
                        </Typography>
                        <Typography variant="body2">{repository.total_size}</Typography>
                      </Box>
                    )}

                    {repository.source_directories && repository.source_directories.length > 0 && (
                      <Box>
                        <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 0.5 }}>
                          Source Paths ({repository.source_directories.length})
                        </Typography>
                        <Stack spacing={0.5}>
                          {repository.source_directories.slice(0, 3).map((dir: string, index: number) => (
                            <Typography
                              key={index}
                              variant="body2"
                              sx={{
                                fontFamily: 'monospace',
                                fontSize: '0.75rem',
                                color: 'text.secondary',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap'
                              }}
                            >
                              {dir}
                            </Typography>
                          ))}
                          {repository.source_directories.length > 3 && (
                            <Typography variant="caption" color="text.secondary" sx={{ fontStyle: 'italic' }}>
                              +{repository.source_directories.length - 3} more
                            </Typography>
                          )}
                        </Stack>
                      </Box>
                    )}
                  </Stack>

                  {user?.is_admin && (
                    <>
                      <Divider sx={{ my: 2 }} />
                      <Stack direction="row" spacing={1} justifyContent="space-between">
                        <Box sx={{ display: 'flex', gap: 1 }}>
                          <Button
                            size="small"
                            startIcon={<Info />}
                            onClick={() => setViewingInfoRepository(repository)}
                          >
                            Info
                          </Button>
                          <Button
                            size="small"
                            startIcon={<CheckCircleIcon />}
                            onClick={() => handleCheckRepository(repository)}
                            disabled={checkRepositoryMutation.isLoading}
                          >
                            Check
                          </Button>
                          <Button
                            size="small"
                            startIcon={<Refresh />}
                            onClick={() => handleCompactRepository(repository)}
                            disabled={compactRepositoryMutation.isLoading}
                            color="warning"
                          >
                            Compact
                          </Button>
                        </Box>
                        <Box sx={{ display: 'flex', gap: 0.5 }}>
                          <IconButton
                            size="small"
                            onClick={() => openEditModal(repository)}
                          >
                            <Edit fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            color="error"
                            onClick={() => handleDeleteRepository(repository)}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        </Box>
                      </Stack>
                    </>
                  )}
                </CardContent>
              </Card>
            </Box>
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
                placeholder={createForm.repository_type === 'local' ? '/path/to/repository' : '/mnt/backup/repo'}
                required
                fullWidth
                helperText="Any path is allowed. Directory will be created automatically."
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
                  Source Directories (Optional)
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1.5 }}>
                  Specify which directories to backup to this repository
                </Typography>

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
                    placeholder="*.log"
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
            <Button type="submit" variant="contained" disabled={createRepositoryMutation.isLoading}>
              {createRepositoryMutation.isLoading ? 'Creating...' : 'Create'}
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
                    placeholder="*.log"
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
          Repository Information: {viewingInfoRepository?.name}
        </DialogTitle>
        <DialogContent>
          {loadingInfo ? (
            <Box sx={{ textAlign: 'center', py: 4 }}>
              <Typography variant="body2" color="text.secondary">
                Loading repository info...
              </Typography>
            </Box>
          ) : repositoryInfo?.data ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, mt: 1 }}>
              {/* Repository Details */}
              <Box>
                <Typography variant="h6" gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                  <Storage /> Repository Details
                </Typography>
                <Stack spacing={1.5} sx={{ bgcolor: 'grey.50', p: 2, borderRadius: 1 }}>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">Location</Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', wordBreak: 'break-all', maxWidth: '60%', textAlign: 'right' }}>
                      {repositoryInfo.data.info?.repository?.location || 'N/A'}
                    </Typography>
                  </Box>
                  <Divider />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">Repository ID</Typography>
                    <Typography variant="body2" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                      {repositoryInfo.data.info?.repository?.id?.substring(0, 16) || 'N/A'}...
                    </Typography>
                  </Box>
                  <Divider />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">Last Modified</Typography>
                    <Typography variant="body2">
                      {repositoryInfo.data.info?.repository?.last_modified
                        ? (() => {
                            const date = new Date(repositoryInfo.data.info.repository.last_modified + (repositoryInfo.data.info.repository.last_modified.endsWith('Z') ? '' : 'Z'))
                            const day = date.getDate()
                            const getOrdinalSuffix = (d: number) => {
                              if (d > 3 && d < 21) return 'th'
                              switch (d % 10) {
                                case 1: return 'st'
                                case 2: return 'nd'
                                case 3: return 'rd'
                                default: return 'th'
                              }
                            }
                            const month = date.toLocaleString('en-US', { month: 'long' })
                            const year = date.getFullYear()
                            const time = date.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit', second: '2-digit', hour12: true })
                            return `${day}${getOrdinalSuffix(day)} ${month} ${year}, ${time}`
                          })()
                        : 'N/A'}
                    </Typography>
                  </Box>
                  <Divider />
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">Encryption Mode</Typography>
                    <Typography variant="body2" sx={{ fontWeight: 500 }}>
                      {repositoryInfo.data.info?.encryption?.mode || 'N/A'}
                    </Typography>
                  </Box>
                </Stack>
              </Box>

              {/* Storage Statistics */}
              <Box>
                <Typography variant="h6" gutterBottom>
                  Storage Statistics
                </Typography>
                {repositoryInfo.data.info?.cache?.stats && repositoryInfo.data.info.cache.stats.unique_size > 0 ? (
                  <Stack spacing={1.5} sx={{ bgcolor: 'grey.50', p: 2, borderRadius: 1 }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Unique Data (Deduplicated)</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {(repositoryInfo.data.info.cache.stats.unique_size / (1024 * 1024)).toFixed(2)} MB
                      </Typography>
                    </Box>
                    <Divider />
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Unique Compressed Size</Typography>
                      <Typography variant="body2" sx={{ fontWeight: 500 }}>
                        {(repositoryInfo.data.info.cache.stats.unique_csize / (1024 * 1024)).toFixed(2)} MB
                      </Typography>
                    </Box>
                    <Divider />
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Total Data Size</Typography>
                      <Typography variant="body2">
                        {(repositoryInfo.data.info.cache.stats.total_size / (1024 * 1024)).toFixed(2)} MB
                      </Typography>
                    </Box>
                    <Divider />
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Total Chunks</Typography>
                      <Typography variant="body2">
                        {repositoryInfo.data.info.cache.stats.total_chunks?.toLocaleString()}
                      </Typography>
                    </Box>
                    <Divider />
                    <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                      <Typography variant="body2" color="text.secondary">Unique Chunks</Typography>
                      <Typography variant="body2">
                        {repositoryInfo.data.info.cache.stats.total_unique_chunks?.toLocaleString()}
                      </Typography>
                    </Box>
                  </Stack>
                ) : (
                  <Alert severity="info" sx={{ bgcolor: 'grey.50' }}>
                    <Typography variant="body2" gutterBottom>
                      <strong>No backups yet</strong>
                    </Typography>
                    <Typography variant="body2" color="text.secondary">
                      This repository has been initialized but contains no archives. Storage statistics will appear here after you create your first backup.
                    </Typography>
                  </Alert>
                )}
              </Box>

              <Alert severity="info" sx={{ mt: 1 }}>
                This information is retrieved from <code>borg info --json</code> command
              </Alert>
            </Box>
          ) : (
            <Alert severity="error">
              Failed to load repository information. Make sure the repository is accessible and properly initialized.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewingInfoRepository(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
