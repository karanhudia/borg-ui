import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
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
  Stack,
  InputAdornment,
  Checkbox,
  FormControlLabel,
} from '@mui/material'
import {
  Add,
  Delete,
  Storage,
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
import { generateBorgCreateCommand } from '../utils/borgUtils'
import FileExplorerDialog from '../components/FileExplorerDialog'
import { FolderOpen } from '@mui/icons-material'
import LockErrorDialog from '../components/LockErrorDialog'
import CheckWarningDialog from '../components/CheckWarningDialog'
import CompactWarningDialog from '../components/CompactWarningDialog'
import RepositoryCard from '../components/RepositoryCard'
import AdvancedRepositoryOptions from '../components/AdvancedRepositoryOptions'

interface Repository {
  id: number
  name: string
  path: string
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  last_backup: string | null
  last_check: string | null
  last_compact: string | null
  total_size: string | null
  archive_count: number
  created_at: string
  updated_at: string | null
  mode: 'full' | 'observe' // full: backups + observability, observe: observability-only
  custom_flags?: string | null // Custom command-line flags for borg create
  has_running_maintenance?: boolean
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
  const navigate = useNavigate()
  const [showRepositoryModal, setShowRepositoryModal] = useState(false)
  const [repositoryModalMode, setRepositoryModalMode] = useState<'create' | 'import'>('create')
  const [newlyCreatedRepositoryId, setNewlyCreatedRepositoryId] = useState<number | null>(null)
  const [editingRepository, setEditingRepository] = useState<Repository | null>(null)
  const [viewingInfoRepository, setViewingInfoRepository] = useState<Repository | null>(null)
  const [checkingRepository, setCheckingRepository] = useState<Repository | null>(null)
  const [compactingRepository, setCompactingRepository] = useState<Repository | null>(null)
  const [pruningRepository, setPruningRepository] = useState<Repository | null>(null)
  const [pruneForm, setPruneForm] = useState({
    keep_hourly: 0,
    keep_daily: 7,
    keep_weekly: 4,
    keep_monthly: 6,
    keep_quarterly: 0,
    keep_yearly: 1,
  })
  const [pruneResults, setPruneResults] = useState<any>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)

  // Track repositories with running jobs for polling
  const [repositoriesWithJobs, setRepositoriesWithJobs] = useState<Set<number>>(new Set())

  // Queries
  const { data: repositoriesData, isLoading } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const { data: connectionsData } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
  })

  // Get repository info using borg info command
  const {
    data: repositoryInfo,
    isLoading: loadingInfo,
    error: infoError,
  } = useQuery<any>({
    queryKey: ['repository-info', viewingInfoRepository?.id],
    queryFn: () => repositoriesAPI.getRepositoryInfo(viewingInfoRepository!.id),
    enabled: !!viewingInfoRepository,
    placeholderData: (previousData: any) => previousData, // Keep showing data during dialog close animation (was keepPreviousData in v3)
    retry: false,
  })

  // Handle repository info error
  React.useEffect(() => {
    if (infoError && (infoError as any)?.response?.status === 423 && viewingInfoRepository) {
      setLockError({
        repositoryId: viewingInfoRepository.id,
        repositoryName: viewingInfoRepository.name,
      })
    }
  }, [infoError, viewingInfoRepository])

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
      // Close modal after successful creation
      closeRepositoryModal()
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

      toast.success(`${message}${archiveCount > 0 ? ` (${archiveCount} archives found)` : ''}`, {
        duration: 5000,
      })

      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      // Close modal after successful import
      closeRepositoryModal()
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
    mutationFn: ({ repositoryId, maxDuration }: { repositoryId: number; maxDuration: number }) =>
      repositoriesAPI.checkRepository(repositoryId, maxDuration),
    onSuccess: (_response: any, variables: { repositoryId: number; maxDuration: number }) => {
      toast.success('Check operation started')
      setCheckingRepository(null) // Close dialog
      // Add repository to polling set
      setRepositoriesWithJobs((prev) => new Set(prev).add(variables.repositoryId))
      // Immediately refetch running jobs to show progress
      queryClient.invalidateQueries({ queryKey: ['running-jobs', variables.repositoryId] })
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail || 'Failed to start check'
      // Handle concurrent operation error (409)
      if (error.response?.status === 409) {
        toast.error(detail, { duration: 5000 })
      } else {
        toast.error(detail)
      }
      setCheckingRepository(null)
    },
  })

  const compactRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.compactRepository,
    onSuccess: (_response: any, repositoryId: number) => {
      toast.success('Compact operation started')
      setCompactingRepository(null) // Close dialog
      // Add repository to polling set
      setRepositoriesWithJobs((prev) => new Set(prev).add(repositoryId))
      // Immediately refetch running jobs to show progress
      queryClient.invalidateQueries({ queryKey: ['running-jobs', repositoryId] })
    },
    onError: (error: any) => {
      const detail = error.response?.data?.detail || 'Failed to start compact'
      // Handle concurrent operation error (409)
      if (error.response?.status === 409) {
        toast.error(detail, { duration: 5000 })
      } else {
        toast.error(detail)
      }
      setCompactingRepository(null)
    },
  })

  const pruneRepositoryMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      repositoriesAPI.pruneRepository(id, data),
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

  // Unified form state for create/import
  const [repositoryForm, setRepositoryForm] = useState({
    name: '',
    path: '',
    encryption: 'repokey',
    compression: 'lz4',
    compressionAlgorithm: 'lz4',
    compressionLevel: '',
    compressionAutoDetect: false,
    compressionObfuscate: '',
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
    pre_backup_script: '',
    post_backup_script: '',
    hook_timeout: 300,
    pre_hook_timeout: 300,
    post_hook_timeout: 300,
    continue_on_hook_failure: false,
    mode: 'full' as 'full' | 'observe',
    custom_flags: '',
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
    compressionAlgorithm: 'lz4',
    compressionLevel: '',
    compressionAutoDetect: false,
    compressionObfuscate: '',
    source_directories: [] as string[],
    exclude_patterns: [] as string[],
    remote_path: '',
    pre_backup_script: '',
    post_backup_script: '',
    hook_timeout: 300,
    pre_hook_timeout: 300,
    post_hook_timeout: 300,
    continue_on_hook_failure: false,
    mode: 'full' as 'full' | 'observe',
    custom_flags: '',
  })

  const [editNewSourceDir, setEditNewSourceDir] = useState('')
  const [editNewExcludePattern, setEditNewExcludePattern] = useState('')
  const [showEditSourceDirExplorer, setShowEditSourceDirExplorer] = useState(false)
  const [showEditExcludeExplorer, setShowEditExcludeExplorer] = useState(false)

  // Event handlers
  const handleSubmitRepository = (e: React.FormEvent) => {
    e.preventDefault()
    if (repositoryModalMode === 'create') {
      createRepositoryMutation.mutate(repositoryForm)
    } else {
      importRepositoryMutation.mutate(repositoryForm)
    }
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
    setCheckingRepository(repository)
  }

  const handleConfirmCheck = (maxDuration: number) => {
    if (checkingRepository) {
      checkRepositoryMutation.mutate({ repositoryId: checkingRepository.id, maxDuration })
    }
  }

  const handleCompactRepository = (repository: Repository) => {
    setCompactingRepository(repository)
  }

  const handleConfirmCompact = () => {
    if (compactingRepository) {
      compactRepositoryMutation.mutate(compactingRepository.id)
    }
  }

  const handleJobCompleted = (repositoryId: number) => {
    // Remove from polling set when jobs complete
    setRepositoriesWithJobs((prev) => {
      const newSet = new Set(prev)
      newSet.delete(repositoryId)
      return newSet
    })
  }

  const handlePruneRepository = (repository: Repository) => {
    setPruningRepository(repository)
    setPruneForm({
      keep_hourly: 0,
      keep_daily: 7,
      keep_weekly: 4,
      keep_monthly: 6,
      keep_quarterly: 0,
      keep_yearly: 1,
    })
    setPruneResults(null)
  }

  const handleClosePruneDialog = () => {
    setPruningRepository(null)
    setPruneResults(null)
  }

  const handleBackupNow = (repository: Repository) => {
    navigate('/backup', { state: { repositoryPath: repository.path } })
  }

  const handleViewArchives = (repository: Repository) => {
    navigate('/archives', { state: { repositoryId: repository.id } })
  }

  const handlePruneDryRun = () => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...pruneForm, dry_run: true },
      })
    }
  }

  const handleConfirmPrune = () => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...pruneForm, dry_run: false },
      })
    }
  }

  const openRepositoryModal = (mode: 'create' | 'import') => {
    setRepositoryModalMode(mode)
    setShowRepositoryModal(true)
    setNewlyCreatedRepositoryId(null) // Reset when opening modal
    setRepositoryForm({
      name: '',
      path: '',
      encryption: 'repokey',
      compression: 'lz4',
      compressionAlgorithm: 'lz4',
      compressionLevel: '',
      compressionAutoDetect: false,
      compressionObfuscate: '',
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
      pre_backup_script: '',
      post_backup_script: '',
      hook_timeout: 300,
      pre_hook_timeout: 300,
      post_hook_timeout: 300,
      continue_on_hook_failure: false,
      mode: 'full',
      custom_flags: '',
    })
    setNewSourceDir('')
    setNewExcludePattern('')
  }

  const closeRepositoryModal = () => {
    setShowRepositoryModal(false)
    setNewlyCreatedRepositoryId(null)
  }

  const openEditModal = (repository: Repository) => {
    setEditingRepository(repository)
    const parsed = parseCompressionString(repository.compression)
    setEditForm({
      name: repository.name,
      path: repository.path,
      compression: repository.compression,
      compressionAlgorithm: parsed.algorithm,
      compressionLevel: parsed.level,
      compressionAutoDetect: parsed.autoDetect,
      compressionObfuscate: parsed.obfuscate,
      source_directories: repository.source_directories || [],
      exclude_patterns: repository.exclude_patterns || [],
      remote_path: (repository as any).remote_path || '',
      pre_backup_script: (repository as any).pre_backup_script || '',
      post_backup_script: (repository as any).post_backup_script || '',
      hook_timeout: (repository as any).hook_timeout || 300,
      pre_hook_timeout: (repository as any).pre_hook_timeout || 300,
      post_hook_timeout: (repository as any).post_hook_timeout || 300,
      continue_on_hook_failure: (repository as any).continue_on_hook_failure || false,
      mode: repository.mode || 'full',
      custom_flags: repository.custom_flags || '',
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

  // Auto-detect and parse SSH connection details from path
  const handlePathChange = (newPath: string) => {
    if (newPath.startsWith('ssh://')) {
      // Parse SSH URL: ssh://username@host:port/path
      const match = newPath.match(/ssh:\/\/([^@]+)@([^:]+):(\d+)(.*)/)
      if (match) {
        const [, username, host, port, remotePath] = match

        // Find matching SSH connection to get ssh_key_id
        const connections = connectionsData?.data?.connections || []
        const matchingConnection = connections.find(
          (c: SSHConnection) =>
            c.username === username && c.host === host && c.port === parseInt(port)
        )

        setRepositoryForm({
          ...repositoryForm,
          path: remotePath || '/',
          repository_type: 'ssh',
          username,
          host,
          port: parseInt(port),
          ssh_key_id: matchingConnection?.ssh_key_id || null,
        })
        return
      }
    }

    // Local path
    setRepositoryForm({
      ...repositoryForm,
      path: newPath,
      repository_type: 'local',
    })
  }

  // Generate borg init command preview
  const getBorgInitCommand = () => {
    let repoPath = repositoryForm.path || '/path/to/repository'

    // Build full path for remote repository
    if (
      repositoryForm.repository_type === 'ssh' &&
      repositoryForm.host &&
      repositoryForm.username
    ) {
      repoPath = `ssh://${repositoryForm.username}@${repositoryForm.host}:${repositoryForm.port}${repoPath.startsWith('/') ? '' : '/'}${repoPath}`
    } else if (repositoryForm.repository_type === 'local') {
      repoPath = repoPath || '/path/to/local/repository'
    }

    let command = `borg init --encryption ${repositoryForm.encryption}`

    // Add remote-path if specified
    if (repositoryForm.remote_path) {
      command += ` --remote-path ${repositoryForm.remote_path}`
    }

    command += ` ${repoPath}`

    return command
  }

  // Generate borg create command preview for create/import
  const getBorgCreateCommand = () => {
    let repoPath = repositoryForm.path || '/path/to/repository'

    // Build full path for remote repository
    if (
      repositoryForm.repository_type === 'ssh' &&
      repositoryForm.host &&
      repositoryForm.username
    ) {
      repoPath = `ssh://${repositoryForm.username}@${repositoryForm.host}:${repositoryForm.port}${repoPath.startsWith('/') ? '' : '/'}${repoPath}`
    } else if (repositoryForm.repository_type === 'local') {
      repoPath = repoPath || '/path/to/local/repository'
    }

    return generateBorgCreateCommand({
      repositoryPath: repoPath,
      compression: repositoryForm.compression,
      excludePatterns: repositoryForm.exclude_patterns,
      sourceDirs:
        repositoryForm.source_directories.length > 0
          ? repositoryForm.source_directories
          : ['/path/to/source'],
      customFlags: repositoryForm.custom_flags,
      remotePathFlag: repositoryForm.remote_path
        ? `--remote-path ${repositoryForm.remote_path} `
        : '',
    })
  }

  // Generate borg create command preview for edit
  const getBorgCreateCommandForEdit = () => {
    if (!editingRepository) return ''

    const repoPath = editForm.path || '/path/to/repository'

    return generateBorgCreateCommand({
      repositoryPath: repoPath,
      compression: editForm.compression,
      excludePatterns: editForm.exclude_patterns,
      sourceDirs:
        editForm.source_directories.length > 0 ? editForm.source_directories : ['/path/to/source'],
      customFlags: editForm.custom_flags,
      remotePathFlag: editForm.remote_path ? `--remote-path ${editForm.remote_path} ` : '',
    })
  }

  // Utility functions
  const buildCompressionString = (
    algorithm: string,
    level: string,
    autoDetect: boolean,
    obfuscate: string
  ): string => {
    let parts: string[] = []

    // Add obfuscate prefix if specified
    if (obfuscate) {
      parts.push('obfuscate', obfuscate)
    }

    // Add auto prefix if enabled (but not if algorithm is already 'auto')
    if (autoDetect && algorithm !== 'auto') {
      parts.push('auto')
    }

    // Add algorithm (unless it's 'none')
    if (algorithm !== 'none') {
      parts.push(algorithm)

      // Add level if specified (but not for 'auto' algorithm as it doesn't support levels)
      if (level && algorithm !== 'auto') {
        parts.push(level)
      }
    } else {
      parts.push('none')
    }

    return parts.join(',')
  }

  const parseCompressionString = (
    compression: string
  ): {
    algorithm: string
    level: string
    autoDetect: boolean
    obfuscate: string
  } => {
    const parts = compression.split(',')
    let algorithm = 'lz4'
    let level = ''
    let autoDetect = false
    let obfuscate = ''

    let i = 0

    // Check for obfuscate
    if (parts[i] === 'obfuscate') {
      i++
      if (i < parts.length) {
        obfuscate = parts[i]
        i++
      }
    }

    // Check for auto
    if (parts[i] === 'auto') {
      autoDetect = true
      i++
    }

    // Get algorithm
    if (i < parts.length) {
      algorithm = parts[i]
      i++
    }

    // Get level
    if (i < parts.length) {
      level = parts[i]
    }

    return { algorithm, level, autoDetect, obfuscate }
  }

  const getCompressionLabel = (compression: string) => {
    // Just return the compression string as-is for display
    return compression || 'lz4'
  }

  const repositories = repositoriesData?.data?.repositories || []
  // REMOVED: Config dependency no longer needed
  // const sourceDirectories = getSourceDirectories()

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3 }}>
        <Box
          sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', mb: 2 }}
        >
          <Box sx={{ flex: 1, mr: 2 }}>
            <Typography variant="h4" fontWeight={600} gutterBottom>
              Repository Management
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              A repository is where your backed-up data will be stored. The files from your
              configured sources will be backed up here.
            </Typography>
          </Box>
          {user?.is_admin && (
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => openRepositoryModal('create')}
                sx={{ flexShrink: 0 }}
              >
                Create Repository
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileUpload />}
                onClick={() => openRepositoryModal('import')}
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
                    openRepositoryModal('create')
                    setRepositoryForm({ ...repositoryForm, repository_type: 'local' })
                  }}
                >
                  Create Local Repository
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Wifi />}
                  onClick={() => {
                    openRepositoryModal('create')
                    setRepositoryForm({ ...repositoryForm, repository_type: 'ssh' })
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
            <RepositoryCard
              key={repository.id}
              repository={repository}
              isInJobsSet={repositoriesWithJobs.has(repository.id)}
              onViewInfo={() => setViewingInfoRepository(repository)}
              onCheck={() => handleCheckRepository(repository)}
              onCompact={() => handleCompactRepository(repository)}
              onPrune={() => handlePruneRepository(repository)}
              onEdit={() => openEditModal(repository)}
              onDelete={() => handleDeleteRepository(repository)}
              onBackupNow={() => handleBackupNow(repository)}
              onViewArchives={() => handleViewArchives(repository)}
              getCompressionLabel={getCompressionLabel}
              isAdmin={user?.is_admin || false}
              onJobCompleted={handleJobCompleted}
            />
          ))}
        </Stack>
      )}

      {/* Warning Dialogs */}
      <CheckWarningDialog
        open={!!checkingRepository}
        repositoryName={checkingRepository?.name || ''}
        onConfirm={handleConfirmCheck}
        onCancel={() => setCheckingRepository(null)}
        isLoading={checkRepositoryMutation.isPending}
      />

      <CompactWarningDialog
        open={!!compactingRepository}
        repositoryName={compactingRepository?.name || ''}
        onConfirm={handleConfirmCompact}
        onCancel={() => setCompactingRepository(null)}
        isLoading={compactRepositoryMutation.isPending}
      />

      {/* Create Repository Dialog */}
      <Dialog open={showRepositoryModal} onClose={closeRepositoryModal} maxWidth="md" fullWidth>
        <form onSubmit={handleSubmitRepository}>
          <DialogTitle>
            {repositoryModalMode === 'create' ? 'Create' : 'Import'} Repository
          </DialogTitle>
          <DialogContent>
            {/* Command Preview */}
            <Alert severity="info" sx={{ mb: 2 }}>
              <Typography variant="subtitle2" gutterBottom>
                {repositoryModalMode === 'create'
                  ? 'Commands that will run:'
                  : 'Backup Command Preview:'}
              </Typography>

              {repositoryModalMode === 'create' && (
                <>
                  <Typography variant="caption" display="block" sx={{ mb: 0.5, fontWeight: 600 }}>
                    1. Initialize Repository:
                  </Typography>
                  <Box
                    sx={{
                      bgcolor: 'grey.900',
                      color: 'grey.100',
                      p: 1.5,
                      borderRadius: 1,
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      overflow: 'auto',
                      mb: 2,
                    }}
                  >
                    {getBorgInitCommand()}
                  </Box>
                </>
              )}

              {repositoryForm.mode === 'full' && (
                <>
                  <Typography variant="caption" display="block" sx={{ mb: 0.5, fontWeight: 600 }}>
                    {repositoryModalMode === 'create' ? '2. Create Backup:' : 'Backup Command:'}
                  </Typography>
                  <Box
                    sx={{
                      bgcolor: 'grey.900',
                      color: 'grey.100',
                      p: 1.5,
                      borderRadius: 1,
                      fontFamily: 'monospace',
                      fontSize: '0.875rem',
                      overflow: 'auto',
                    }}
                  >
                    {getBorgCreateCommand()}
                  </Box>
                </>
              )}

              {repositoryModalMode === 'import' && (
                <Typography variant="body2" sx={{ mt: 1.5 }}>
                  This command will be used for future backups. The repository will be verified
                  before import.
                </Typography>
              )}
            </Alert>

            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Name"
                value={repositoryForm.name}
                onChange={(e) => setRepositoryForm({ ...repositoryForm, name: e.target.value })}
                required
                fullWidth
              />

              {/* Repository Mode Selector - Moved to top for clarity */}
              <FormControl fullWidth>
                <InputLabel>Repository Mode</InputLabel>
                <Select
                  value={repositoryForm.mode}
                  label="Repository Mode"
                  onChange={(e) =>
                    setRepositoryForm({
                      ...repositoryForm,
                      mode: e.target.value as 'full' | 'observe',
                    })
                  }
                >
                  <MenuItem value="full">
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        Full Repository
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Create backups and browse existing archives
                      </Typography>
                    </Box>
                  </MenuItem>
                  <MenuItem value="observe">
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        Observability Only
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Browse and restore existing archives only (no backups)
                      </Typography>
                    </Box>
                  </MenuItem>
                </Select>
              </FormControl>

              {repositoryForm.mode === 'observe' && (
                <Alert severity="info">
                  Observability-only repositories can browse and restore existing archives but
                  cannot create new backups or be used in scheduled jobs.
                </Alert>
              )}

              <TextField
                label="Path"
                value={repositoryForm.path}
                onChange={(e) => setRepositoryForm({ ...repositoryForm, path: e.target.value })}
                onBlur={(e) => {
                  // Auto-detect SSH connection details when field loses focus
                  if (e.target.value && e.target.value.startsWith('ssh://')) {
                    handlePathChange(e.target.value)
                  }
                }}
                placeholder="Click browse icon to select path"
                required
                fullWidth
                helperText="Use the browse button to select a path (auto-detects local or SSH)"
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

              {repositoryForm.repository_type === 'ssh' && (
                <Alert severity="info" sx={{ mt: 1 }}>
                  <Typography variant="body2">
                    💡 <strong>Tip:</strong> For easier browsing, configure a mount point for your
                    SSH connections in the SSH Keys page. Without a mount point, the full SSH URL
                    will be displayed.
                  </Typography>
                </Alert>
              )}

              {repositoryModalMode === 'create' && (
                <FormControl fullWidth>
                  <InputLabel>Encryption</InputLabel>
                  <Select
                    value={repositoryForm.encryption}
                    label="Encryption"
                    onChange={(e) =>
                      setRepositoryForm({ ...repositoryForm, encryption: e.target.value })
                    }
                  >
                    <MenuItem value="repokey">Repokey (Recommended)</MenuItem>
                    <MenuItem value="keyfile">Keyfile</MenuItem>
                    <MenuItem value="none">None (Unencrypted)</MenuItem>
                  </Select>
                </FormControl>
              )}

              {/* Compression Settings - Only for full repositories */}
              {repositoryForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom sx={{ mb: 1.5 }}>
                    Compression Settings
                  </Typography>

                  <Stack spacing={2}>
                    <FormControl fullWidth>
                      <InputLabel>Compression Algorithm</InputLabel>
                      <Select
                        value={repositoryForm.compressionAlgorithm}
                        label="Compression Algorithm"
                        onChange={(e) => {
                          const newAlgorithm = e.target.value
                          setRepositoryForm({
                            ...repositoryForm,
                            compressionAlgorithm: newAlgorithm,
                            compression: buildCompressionString(
                              newAlgorithm,
                              repositoryForm.compressionLevel,
                              repositoryForm.compressionAutoDetect,
                              repositoryForm.compressionObfuscate
                            ),
                          })
                        }}
                      >
                        <MenuItem value="none">none - Do not compress</MenuItem>
                        <MenuItem value="lz4">
                          lz4 - Very high speed, very low compression (default)
                        </MenuItem>
                        <MenuItem value="zstd">
                          zstd - Modern wide-range algorithm (default level 3)
                        </MenuItem>
                        <MenuItem value="zlib">
                          zlib - Medium speed, medium compression (default level 6)
                        </MenuItem>
                        <MenuItem value="lzma">
                          lzma - Low speed, high compression (default level 6)
                        </MenuItem>
                        <MenuItem value="auto">auto - Automatic compression selection</MenuItem>
                        <MenuItem value="obfuscate">obfuscate - Obfuscate compressed data</MenuItem>
                      </Select>
                    </FormControl>

                    {repositoryForm.compressionAlgorithm !== 'none' && (
                      <>
                        <TextField
                          label="Compression Level (Optional)"
                          type="number"
                          value={repositoryForm.compressionLevel}
                          onChange={(e) => {
                            const newLevel = e.target.value
                            setRepositoryForm({
                              ...repositoryForm,
                              compressionLevel: newLevel,
                              compression: buildCompressionString(
                                repositoryForm.compressionAlgorithm,
                                newLevel,
                                repositoryForm.compressionAutoDetect,
                                repositoryForm.compressionObfuscate
                              ),
                            })
                          }}
                          placeholder={
                            repositoryForm.compressionAlgorithm === 'zstd'
                              ? '1-22 (default: 3)'
                              : repositoryForm.compressionAlgorithm === 'zlib'
                                ? '0-9 (default: 6)'
                                : repositoryForm.compressionAlgorithm === 'lzma'
                                  ? '0-9 (default: 6, max useful: 6)'
                                  : 'Leave empty for default'
                          }
                          helperText={
                            repositoryForm.compressionAlgorithm === 'zstd'
                              ? 'zstd: Level 1-22. Higher = better compression but slower.'
                              : repositoryForm.compressionAlgorithm === 'zlib'
                                ? 'zlib: Level 0-9. Level 0 means no compression (use "none" instead).'
                                : repositoryForm.compressionAlgorithm === 'lzma'
                                  ? 'lzma: Level 0-9. Levels above 6 are pointless and waste CPU/RAM.'
                                  : 'Leave empty to use default level.'
                          }
                          fullWidth
                        />

                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={repositoryForm.compressionAutoDetect}
                              onChange={(e) => {
                                const newAutoDetect = e.target.checked
                                setRepositoryForm({
                                  ...repositoryForm,
                                  compressionAutoDetect: newAutoDetect,
                                  compression: buildCompressionString(
                                    repositoryForm.compressionAlgorithm,
                                    repositoryForm.compressionLevel,
                                    newAutoDetect,
                                    repositoryForm.compressionObfuscate
                                  ),
                                })
                              }}
                            />
                          }
                          label="Auto-detect compressibility (auto,C[,L])"
                        />
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ mt: -1, mb: 1, display: 'block' }}
                        >
                          Uses lz4 to test if data is compressible. For incompressible data (e.g.,
                          media files), uses "none". For compressible data, uses your selected
                          algorithm.
                        </Typography>

                        <TextField
                          label="Obfuscate Spec (Optional)"
                          type="number"
                          value={repositoryForm.compressionObfuscate}
                          onChange={(e) => {
                            const newObfuscate = e.target.value
                            setRepositoryForm({
                              ...repositoryForm,
                              compressionObfuscate: newObfuscate,
                              compression: buildCompressionString(
                                repositoryForm.compressionAlgorithm,
                                repositoryForm.compressionLevel,
                                repositoryForm.compressionAutoDetect,
                                newObfuscate
                              ),
                            })
                          }}
                          placeholder="e.g., 110, 250"
                          helperText="Obfuscate compressed chunk sizes to make fingerprinting attacks harder. Must be used with encryption. Repo will be bigger."
                          fullWidth
                        />

                        <Alert severity="info" sx={{ mt: 1 }}>
                          Final compression spec: <strong>{repositoryForm.compression}</strong>
                        </Alert>
                      </>
                    )}
                  </Stack>
                </Box>
              )}

              {repositoryForm.encryption !== 'none' && (
                <TextField
                  label="Passphrase"
                  type="password"
                  value={repositoryForm.passphrase}
                  onChange={(e) =>
                    setRepositoryForm({ ...repositoryForm, passphrase: e.target.value })
                  }
                  placeholder="Enter passphrase"
                  fullWidth
                />
              )}

              {/* Source Directories */}
              {repositoryForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Source Directories{' '}
                    <Box component="span" sx={{ color: 'error.main' }}>
                      *
                    </Box>
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 1.5 }}
                  >
                    Specify which directories to backup to this repository (at least one required)
                  </Typography>

                  {repositoryForm.source_directories.length === 0 && (
                    <Alert severity="warning" sx={{ mb: 1.5 }}>
                      At least one source directory is required. Add the directories you want to
                      backup.
                    </Alert>
                  )}

                  {repositoryForm.source_directories.length > 0 && (
                    <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                      {repositoryForm.source_directories.map((dir, index) => (
                        <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                            {dir}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() => {
                              setRepositoryForm({
                                ...repositoryForm,
                                source_directories: repositoryForm.source_directories.filter(
                                  (_, i) => i !== index
                                ),
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
                            setRepositoryForm({
                              ...repositoryForm,
                              source_directories: [
                                ...repositoryForm.source_directories,
                                newSourceDir.trim(),
                              ],
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
                          setRepositoryForm({
                            ...repositoryForm,
                            source_directories: [
                              ...repositoryForm.source_directories,
                              newSourceDir.trim(),
                            ],
                          })
                          setNewSourceDir('')
                        }
                      }}
                    >
                      Add
                    </Button>
                  </Box>
                </Box>
              )}

              {/* Exclude Patterns */}
              {repositoryForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Exclude Patterns (Optional)
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 1.5 }}
                  >
                    Specify patterns to exclude from backup (e.g., *.log, *.tmp, __pycache__,
                    node_modules)
                  </Typography>

                  {repositoryForm.exclude_patterns.length > 0 && (
                    <Stack spacing={0.5} sx={{ mb: 1.5 }}>
                      {repositoryForm.exclude_patterns.map((pattern, index) => (
                        <Box key={index} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <Typography variant="body2" sx={{ fontFamily: 'monospace', flex: 1 }}>
                            {pattern}
                          </Typography>
                          <IconButton
                            size="small"
                            onClick={() => {
                              setRepositoryForm({
                                ...repositoryForm,
                                exclude_patterns: repositoryForm.exclude_patterns.filter(
                                  (_, i) => i !== index
                                ),
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
                            setRepositoryForm({
                              ...repositoryForm,
                              exclude_patterns: [
                                ...repositoryForm.exclude_patterns,
                                newExcludePattern.trim(),
                              ],
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
                          setRepositoryForm({
                            ...repositoryForm,
                            exclude_patterns: [
                              ...repositoryForm.exclude_patterns,
                              newExcludePattern.trim(),
                            ],
                          })
                          setNewExcludePattern('')
                        }
                      }}
                    >
                      Add
                    </Button>
                  </Box>
                </Box>
              )}

              {/* Success Message - shown after repository is created */}
              {newlyCreatedRepositoryId && (
                <Alert severity="success" sx={{ mb: 2 }}>
                  <Typography variant="body2" fontWeight={600} gutterBottom>
                    Repository {repositoryModalMode === 'create' ? 'created' : 'imported'}{' '}
                    successfully!
                  </Typography>
                  <Typography variant="body2">
                    You can now add library scripts below, or click Done to finish.
                  </Typography>
                </Alert>
              )}

              {/* Advanced Options */}
              <AdvancedRepositoryOptions
                repositoryId={newlyCreatedRepositoryId}
                mode={repositoryForm.mode}
                remotePath={repositoryForm.remote_path}
                preBackupScript={repositoryForm.pre_backup_script}
                postBackupScript={repositoryForm.post_backup_script}
                preHookTimeout={repositoryForm.pre_hook_timeout}
                postHookTimeout={repositoryForm.post_hook_timeout}
                continueOnHookFailure={repositoryForm.continue_on_hook_failure}
                customFlags={repositoryForm.custom_flags}
                onRemotePathChange={(value) =>
                  setRepositoryForm({ ...repositoryForm, remote_path: value })
                }
                onPreBackupScriptChange={(value) =>
                  setRepositoryForm({ ...repositoryForm, pre_backup_script: value })
                }
                onPostBackupScriptChange={(value) =>
                  setRepositoryForm({ ...repositoryForm, post_backup_script: value })
                }
                onPreHookTimeoutChange={(value: number) =>
                  setRepositoryForm({ ...repositoryForm, pre_hook_timeout: value })
                }
                onPostHookTimeoutChange={(value: number) =>
                  setRepositoryForm({ ...repositoryForm, post_hook_timeout: value })
                }
                onContinueOnHookFailureChange={(value) =>
                  setRepositoryForm({ ...repositoryForm, continue_on_hook_failure: value })
                }
                onCustomFlagsChange={(value) =>
                  setRepositoryForm({ ...repositoryForm, custom_flags: value })
                }
              />
            </Box>
          </DialogContent>
          <DialogActions>
            {newlyCreatedRepositoryId ? (
              <Button onClick={closeRepositoryModal} variant="contained">
                Done
              </Button>
            ) : (
              <>
                <Button onClick={closeRepositoryModal}>Cancel</Button>
                <Button
                  type="submit"
                  variant="contained"
                  disabled={
                    (repositoryModalMode === 'create'
                      ? createRepositoryMutation.isPending
                      : importRepositoryMutation.isPending) ||
                    (repositoryForm.mode === 'full' &&
                      repositoryForm.source_directories.length === 0)
                  }
                >
                  {repositoryModalMode === 'create'
                    ? createRepositoryMutation.isPending
                      ? 'Creating...'
                      : 'Create'
                    : importRepositoryMutation.isPending
                      ? 'Importing...'
                      : 'Import'}
                </Button>
              </>
            )}
          </DialogActions>
        </form>
      </Dialog>

      {/* Edit Repository Dialog */}
      <Dialog
        open={!!editingRepository}
        onClose={() => setEditingRepository(null)}
        maxWidth="md"
        fullWidth
      >
        <form onSubmit={handleUpdateRepository}>
          <DialogTitle>Edit Repository</DialogTitle>
          <DialogContent>
            {/* Command Preview */}
            <Alert severity="info" sx={{ mb: 2, mt: 1 }}>
              <Typography variant="subtitle2" gutterBottom>
                Backup Command Preview:
              </Typography>

              {editForm.mode === 'full' && (
                <Box
                  sx={{
                    bgcolor: 'grey.900',
                    color: 'grey.100',
                    p: 1.5,
                    borderRadius: 1,
                    fontFamily: 'monospace',
                    fontSize: '0.875rem',
                    overflow: 'auto',
                  }}
                >
                  {getBorgCreateCommandForEdit()}
                </Box>
              )}

              {editForm.mode === 'observe' && (
                <Typography variant="body2" color="text.secondary">
                  Observability-only repositories do not create backups.
                </Typography>
              )}
            </Alert>

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

              {/* Repository Mode */}
              <FormControl fullWidth>
                <InputLabel>Repository Mode</InputLabel>
                <Select
                  value={editForm.mode}
                  label="Repository Mode"
                  onChange={(e) =>
                    setEditForm({ ...editForm, mode: e.target.value as 'full' | 'observe' })
                  }
                >
                  <MenuItem value="full">
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        Full Repository
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        Perform backups and view archives (default)
                      </Typography>
                    </Box>
                  </MenuItem>
                  <MenuItem value="observe">
                    <Box>
                      <Typography variant="body2" fontWeight={600}>
                        Observability Only
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        View-only mode for archives created elsewhere
                      </Typography>
                    </Box>
                  </MenuItem>
                </Select>
              </FormControl>

              {editForm.mode === 'observe' && (
                <Alert severity="info">
                  Observability-only repositories can browse and restore existing archives but
                  cannot create new backups or be used in scheduled jobs.
                </Alert>
              )}

              {/* Compression Settings - Only show for full repositories */}
              {editForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom sx={{ mb: 1.5 }}>
                    Compression Settings
                  </Typography>

                  <Stack spacing={2}>
                    <FormControl fullWidth>
                      <InputLabel>Compression Algorithm</InputLabel>
                      <Select
                        value={editForm.compressionAlgorithm}
                        label="Compression Algorithm"
                        onChange={(e) => {
                          const newAlgorithm = e.target.value
                          setEditForm({
                            ...editForm,
                            compressionAlgorithm: newAlgorithm,
                            compression: buildCompressionString(
                              newAlgorithm,
                              editForm.compressionLevel,
                              editForm.compressionAutoDetect,
                              editForm.compressionObfuscate
                            ),
                          })
                        }}
                      >
                        <MenuItem value="none">none - Do not compress</MenuItem>
                        <MenuItem value="lz4">
                          lz4 - Very high speed, very low compression (default)
                        </MenuItem>
                        <MenuItem value="zstd">
                          zstd - Modern wide-range algorithm (default level 3)
                        </MenuItem>
                        <MenuItem value="zlib">
                          zlib - Medium speed, medium compression (default level 6)
                        </MenuItem>
                        <MenuItem value="lzma">
                          lzma - Low speed, high compression (default level 6)
                        </MenuItem>
                        <MenuItem value="auto">auto - Automatic compression selection</MenuItem>
                        <MenuItem value="obfuscate">obfuscate - Obfuscate compressed data</MenuItem>
                      </Select>
                    </FormControl>

                    {editForm.compressionAlgorithm !== 'none' && (
                      <>
                        <TextField
                          label="Compression Level (Optional)"
                          type="number"
                          value={editForm.compressionLevel}
                          onChange={(e) => {
                            const newLevel = e.target.value
                            setEditForm({
                              ...editForm,
                              compressionLevel: newLevel,
                              compression: buildCompressionString(
                                editForm.compressionAlgorithm,
                                newLevel,
                                editForm.compressionAutoDetect,
                                editForm.compressionObfuscate
                              ),
                            })
                          }}
                          placeholder={
                            editForm.compressionAlgorithm === 'zstd'
                              ? '1-22 (default: 3)'
                              : editForm.compressionAlgorithm === 'zlib'
                                ? '0-9 (default: 6)'
                                : editForm.compressionAlgorithm === 'lzma'
                                  ? '0-9 (default: 6, max useful: 6)'
                                  : 'Leave empty for default'
                          }
                          helperText={
                            editForm.compressionAlgorithm === 'zstd'
                              ? 'zstd: Level 1-22. Higher = better compression but slower.'
                              : editForm.compressionAlgorithm === 'zlib'
                                ? 'zlib: Level 0-9. Level 0 means no compression (use "none" instead).'
                                : editForm.compressionAlgorithm === 'lzma'
                                  ? 'lzma: Level 0-9. Levels above 6 are pointless and waste CPU/RAM.'
                                  : 'Leave empty to use default level.'
                          }
                          fullWidth
                        />

                        <FormControlLabel
                          control={
                            <Checkbox
                              checked={editForm.compressionAutoDetect}
                              onChange={(e) => {
                                const newAutoDetect = e.target.checked
                                setEditForm({
                                  ...editForm,
                                  compressionAutoDetect: newAutoDetect,
                                  compression: buildCompressionString(
                                    editForm.compressionAlgorithm,
                                    editForm.compressionLevel,
                                    newAutoDetect,
                                    editForm.compressionObfuscate
                                  ),
                                })
                              }}
                            />
                          }
                          label="Auto-detect compressibility (auto,C[,L])"
                        />
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ mt: -1, mb: 1, display: 'block' }}
                        >
                          Uses lz4 to test if data is compressible. For incompressible data (e.g.,
                          media files), uses "none". For compressible data, uses your selected
                          algorithm.
                        </Typography>

                        <TextField
                          label="Obfuscate Spec (Optional)"
                          type="number"
                          value={editForm.compressionObfuscate}
                          onChange={(e) => {
                            const newObfuscate = e.target.value
                            setEditForm({
                              ...editForm,
                              compressionObfuscate: newObfuscate,
                              compression: buildCompressionString(
                                editForm.compressionAlgorithm,
                                editForm.compressionLevel,
                                editForm.compressionAutoDetect,
                                newObfuscate
                              ),
                            })
                          }}
                          placeholder="e.g., 110, 250"
                          helperText="Obfuscate compressed chunk sizes to make fingerprinting attacks harder. Must be used with encryption. Repo will be bigger."
                          fullWidth
                        />

                        <Alert severity="info" sx={{ mt: 1 }}>
                          Final compression spec: <strong>{editForm.compression}</strong>
                        </Alert>
                      </>
                    )}
                  </Stack>
                </Box>
              )}

              {/* Source Directories - Only show for full repositories */}
              {editForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Source Directories (Optional)
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 1.5 }}
                  >
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
                                source_directories: editForm.source_directories.filter(
                                  (_, i) => i !== index
                                ),
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
                              source_directories: [
                                ...editForm.source_directories,
                                editNewSourceDir.trim(),
                              ],
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
                            source_directories: [
                              ...editForm.source_directories,
                              editNewSourceDir.trim(),
                            ],
                          })
                          setEditNewSourceDir('')
                        }
                      }}
                    >
                      Add
                    </Button>
                  </Box>
                </Box>
              )}

              {/* Exclude Patterns - Only show for full repositories */}
              {editForm.mode === 'full' && (
                <Box>
                  <Typography variant="subtitle2" gutterBottom>
                    Exclude Patterns (Optional)
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 1.5 }}
                  >
                    Specify patterns to exclude from backup (e.g., *.log, *.tmp, __pycache__,
                    node_modules)
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
                                exclude_patterns: editForm.exclude_patterns.filter(
                                  (_, i) => i !== index
                                ),
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
                              exclude_patterns: [
                                ...editForm.exclude_patterns,
                                editNewExcludePattern.trim(),
                              ],
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
                            exclude_patterns: [
                              ...editForm.exclude_patterns,
                              editNewExcludePattern.trim(),
                            ],
                          })
                          setEditNewExcludePattern('')
                        }
                      }}
                    >
                      Add
                    </Button>
                  </Box>
                </Box>
              )}

              {/* Advanced Options */}
              <AdvancedRepositoryOptions
                repositoryId={editingRepository?.id}
                mode={editForm.mode}
                remotePath={editForm.remote_path}
                preBackupScript={editForm.pre_backup_script}
                postBackupScript={editForm.post_backup_script}
                preHookTimeout={editForm.pre_hook_timeout}
                postHookTimeout={editForm.post_hook_timeout}
                continueOnHookFailure={editForm.continue_on_hook_failure}
                customFlags={editForm.custom_flags}
                onRemotePathChange={(value) => setEditForm({ ...editForm, remote_path: value })}
                onPreBackupScriptChange={(value) =>
                  setEditForm({ ...editForm, pre_backup_script: value })
                }
                onPostBackupScriptChange={(value) =>
                  setEditForm({ ...editForm, post_backup_script: value })
                }
                onPreHookTimeoutChange={(value: number) =>
                  setEditForm({ ...editForm, pre_hook_timeout: value })
                }
                onPostHookTimeoutChange={(value: number) =>
                  setEditForm({ ...editForm, post_hook_timeout: value })
                }
                onContinueOnHookFailureChange={(value) =>
                  setEditForm({ ...editForm, continue_on_hook_failure: value })
                }
                onCustomFlagsChange={(value) => setEditForm({ ...editForm, custom_flags: value })}
              />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditingRepository(null)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={updateRepositoryMutation.isPending}>
              {updateRepositoryMutation.isPending ? 'Updating...' : 'Update'}
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
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 0.5 }}
                  >
                    Repository Location
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{ fontFamily: 'monospace', wordBreak: 'break-all' }}
                  >
                    {repositoryInfo.data.info?.repository?.location || 'N/A'}
                  </Typography>
                </CardContent>
              </Card>

              {/* Storage Statistics */}
              {repositoryInfo.data.info?.cache?.stats &&
              repositoryInfo.data.info.cache.stats.unique_size > 0 ? (
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
                    This repository has been initialized but contains no archives. Storage
                    statistics will appear here after you create your first backup.
                  </Typography>
                </Alert>
              )}
            </Box>
          ) : (
            <Alert severity="error">
              Failed to load repository information. Make sure the repository is accessible and
              properly initialized.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setViewingInfoRepository(null)} variant="contained">
            Close
          </Button>
        </DialogActions>
      </Dialog>

      {/* Prune Repository Dialog */}
      <Dialog open={!!pruningRepository} onClose={handleClosePruneDialog} maxWidth="md" fullWidth>
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
              Pruning automatically deletes old archives based on retention rules. This helps manage
              repository size by keeping only the backups you need.
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
              label="Keep Hourly"
              type="number"
              value={pruneForm.keep_hourly}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_hourly: parseInt(e.target.value) || 0 })
              }
              helperText="Last N hourly backups (0 = disabled)"
              fullWidth
            />
            <TextField
              label="Keep Daily"
              type="number"
              value={pruneForm.keep_daily}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_daily: parseInt(e.target.value) || 0 })
              }
              helperText="Last N daily backups"
              fullWidth
            />
            <TextField
              label="Keep Weekly"
              type="number"
              value={pruneForm.keep_weekly}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_weekly: parseInt(e.target.value) || 0 })
              }
              helperText="Last N weekly backups"
              fullWidth
            />
            <TextField
              label="Keep Monthly"
              type="number"
              value={pruneForm.keep_monthly}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_monthly: parseInt(e.target.value) || 0 })
              }
              helperText="Last N monthly backups"
              fullWidth
            />
            <TextField
              label="Keep Quarterly"
              type="number"
              value={pruneForm.keep_quarterly}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_quarterly: parseInt(e.target.value) || 0 })
              }
              helperText="Last N quarterly backups (0 = disabled)"
              fullWidth
            />
            <TextField
              label="Keep Yearly"
              type="number"
              value={pruneForm.keep_yearly}
              onChange={(e) =>
                setPruneForm({ ...pruneForm, keep_yearly: parseInt(e.target.value) || 0 })
              }
              helperText="Last N yearly backups"
              fullWidth
            />
          </Box>

          <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1, mb: 2 }}>
            <Typography variant="body2" gutterBottom>
              <strong>Repository:</strong> {pruningRepository?.name}
            </Typography>
            <Typography variant="caption" color="text.secondary" display="block">
              Example: With these settings, you'll keep the last 7 daily, 4 weekly, 6 monthly, and 1
              yearly backup. Older archives will be deleted.
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
                        bgcolor: 'action.hover',
                        borderRadius: 1,
                        fontSize: '0.75rem',
                        overflow: 'auto',
                        maxHeight: 200,
                        whiteSpace: 'pre-wrap',
                        wordBreak: 'break-word',
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
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          display="block"
                          gutterBottom
                        >
                          Output:
                        </Typography>
                        <Box
                          component="pre"
                          sx={{
                            p: 1.5,
                            bgcolor: 'background.default',
                            borderRadius: 1,
                            fontSize: '0.75rem',
                            overflow: 'auto',
                            maxHeight: 300,
                            whiteSpace: 'pre-wrap',
                            wordBreak: 'break-word',
                            fontFamily: 'monospace',
                          }}
                        >
                          {pruneResults.prune_result.stdout || 'No output'}
                        </Box>
                      </Box>
                    )}
                    {pruneResults.prune_result?.stderr && (
                      <Box sx={{ mt: 2 }}>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          display="block"
                          gutterBottom
                        >
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
                            fontFamily: 'monospace',
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
                    ✓ Dry run completed successfully. Review the output above to see which archives
                    would be deleted. If everything looks correct, click "Prune Archives" to
                    execute.
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
          <Button onClick={handleClosePruneDialog}>Cancel</Button>
          <Button
            onClick={handlePruneDryRun}
            variant="outlined"
            disabled={pruneRepositoryMutation.isPending}
            startIcon={<Info />}
          >
            Dry Run (Preview)
          </Button>
          <Button
            onClick={handleConfirmPrune}
            variant="contained"
            color="error"
            disabled={pruneRepositoryMutation.isPending}
            startIcon={
              pruneRepositoryMutation.isPending ? <Delete className="animate-spin" /> : <Delete />
            }
          >
            {pruneRepositoryMutation.isPending ? 'Pruning...' : 'Prune Archives'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* File Explorer Dialogs */}
      <FileExplorerDialog
        open={showPathExplorer}
        onClose={() => setShowPathExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            handlePathChange(paths[0])
          }
        }}
        title="Select Repository Path"
        initialPath="/"
        multiSelect={false}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showSourceDirExplorer}
        onClose={() => setShowSourceDirExplorer(false)}
        onSelect={(paths) => {
          setRepositoryForm({
            ...repositoryForm,
            source_directories: [...repositoryForm.source_directories, ...paths],
          })
        }}
        title="Select Source Directories (Local Machine)"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showExcludeExplorer}
        onClose={() => setShowExcludeExplorer(false)}
        onSelect={(paths) => {
          setRepositoryForm({
            ...repositoryForm,
            exclude_patterns: [...repositoryForm.exclude_patterns, ...paths],
          })
        }}
        title="Select Directories to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType={repositoryForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          repositoryForm.repository_type !== 'local' && repositoryForm.ssh_key_id
            ? {
                ssh_key_id: repositoryForm.ssh_key_id,
                host: repositoryForm.host,
                username: repositoryForm.username,
                port: repositoryForm.port,
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
        title="Select Source Directories (Local Machine)"
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
            handlePathChange(paths[0])
          }
        }}
        title="Select Repository Path"
        initialPath="/"
        multiSelect={false}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showImportSourceDirExplorer}
        onClose={() => setShowImportSourceDirExplorer(false)}
        onSelect={(paths) => {
          setRepositoryForm({
            ...repositoryForm,
            source_directories: [...repositoryForm.source_directories, ...paths],
          })
        }}
        title="Select Source Directories (Local Machine)"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showImportExcludeExplorer}
        onClose={() => setShowImportExcludeExplorer(false)}
        onSelect={(paths) => {
          setRepositoryForm({
            ...repositoryForm,
            exclude_patterns: [...repositoryForm.exclude_patterns, ...paths],
          })
        }}
        title="Select Directories to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType={repositoryForm.repository_type === 'local' ? 'local' : 'ssh'}
        sshConfig={
          repositoryForm.repository_type !== 'local' && repositoryForm.ssh_key_id
            ? {
                ssh_key_id: repositoryForm.ssh_key_id,
                host: repositoryForm.host,
                username: repositoryForm.username,
                port: repositoryForm.port,
              }
            : undefined
        }
        selectMode="both"
      />

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          onLockBroken={() => {
            queryClient.invalidateQueries({ queryKey: ['repository-info', lockError.repositoryId] })
          }}
        />
      )}
    </Box>
  )
}
