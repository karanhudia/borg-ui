import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { useMatomo } from '../hooks/useMatomo'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Stack,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  InputAdornment,
  Divider,
} from '@mui/material'
import { Add, Storage, FileUpload, Search, FilterList } from '@mui/icons-material'
import { repositoriesAPI, RepositoryData } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useAppState } from '../context/AppContext'
import { AxiosResponse } from 'axios'
import LockErrorDialog from '../components/LockErrorDialog'
import CheckWarningDialog from '../components/CheckWarningDialog'
import CompactWarningDialog from '../components/CompactWarningDialog'
import RepositoryCard from '../components/RepositoryCard'
import RepositoryWizard from '../components/RepositoryWizard'
import PruneRepositoryDialog from '../components/PruneRepositoryDialog'
import RepositoryInfoDialog from '../components/RepositoryInfoDialog'

interface Repository extends RepositoryData {
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
  mode: 'full' | 'observe'
  custom_flags?: string | null
  has_running_maintenance?: boolean
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  hook_timeout?: number
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  bypass_lock?: boolean
  source_ssh_connection_id?: number | null
  repository_type?: 'local' | 'ssh' | 'sftp'
}

interface PruneForm {
  keep_hourly: number
  keep_daily: number
  keep_weekly: number
  keep_monthly: number
  keep_quarterly: number
  keep_yearly: number
  dry_run?: boolean
}

export default function Repositories() {
  const { user } = useAuth()
  const queryClient = useQueryClient()
  const appState = useAppState()
  const navigate = useNavigate()
  const { trackMaintenance, EventAction } = useMatomo()

  // Wizard state
  const [showWizard, setShowWizard] = useState(false)
  const [wizardMode, setWizardMode] = useState<'create' | 'edit' | 'import'>('create')
  const [wizardRepository, setWizardRepository] = useState<Repository | null>(null)

  // Dialog states
  const [viewingInfoRepository, setViewingInfoRepository] = useState<Repository | null>(null)
  const [checkingRepository, setCheckingRepository] = useState<Repository | null>(null)
  const [compactingRepository, setCompactingRepository] = useState<Repository | null>(null)
  const [pruningRepository, setPruningRepository] = useState<Repository | null>(null)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [pruneResults, setPruneResults] = useState<any>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)

  // Track repositories with running jobs for polling
  const [repositoriesWithJobs, setRepositoriesWithJobs] = useState<Set<number>>(new Set())

  // Filter, sort, and search state
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<string>(() => {
    return localStorage.getItem('repos_sort') || 'name-asc'
  })
  const [groupBy, setGroupBy] = useState<string>(() => {
    return localStorage.getItem('repos_group') || 'none'
  })

  // Queries
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: repositoriesData, isLoading } = useQuery<AxiosResponse<any>>({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get repository info using borg info command
  const {
    data: repositoryInfo,
    isLoading: loadingInfo,
    error: infoError,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } = useQuery<AxiosResponse<{ info: any }>>({
    queryKey: ['repository-info', viewingInfoRepository?.id],
    queryFn: () => repositoriesAPI.getRepositoryInfo(viewingInfoRepository!.id),
    enabled: !!viewingInfoRepository,
    retry: false,
  })

  // Handle repository info error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (infoError && (infoError as any)?.response?.status === 423 && viewingInfoRepository) {
      setLockError({
        repositoryId: viewingInfoRepository.id,
        repositoryName: viewingInfoRepository.name,
      })
    }
  }, [infoError, viewingInfoRepository])

  // Mutations
  const deleteRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.deleteRepository,
    onSuccess: () => {
      toast.success('Repository deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete repository')
    },
  })

  const checkRepositoryMutation = useMutation({
    mutationFn: ({ repositoryId, maxDuration }: { repositoryId: number; maxDuration: number }) =>
      repositoriesAPI.checkRepository(repositoryId, maxDuration),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (_response: any, variables: { repositoryId: number; maxDuration: number }) => {
      toast.success('Check operation started')
      trackMaintenance(EventAction.START, 'Check', checkingRepository?.name)
      setCheckingRepository(null)
      setRepositoriesWithJobs((prev) => new Set(prev).add(variables.repositoryId))
      queryClient.invalidateQueries({ queryKey: ['running-jobs', variables.repositoryId] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const detail = error.response?.data?.detail || 'Failed to start check'
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (_response: any, repositoryId: number) => {
      toast.success('Compact operation started')
      trackMaintenance(EventAction.START, 'Compact', compactingRepository?.name)
      setCompactingRepository(null)
      setRepositoriesWithJobs((prev) => new Set(prev).add(repositoryId))
      queryClient.invalidateQueries({ queryKey: ['running-jobs', repositoryId] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const detail = error.response?.data?.detail || 'Failed to start compact'
      if (error.response?.status === 409) {
        toast.error(detail, { duration: 5000 })
      } else {
        toast.error(detail)
      }
      setCompactingRepository(null)
    },
  })

  const pruneRepositoryMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      repositoriesAPI.pruneRepository(id, data),
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (response: any) => {
      setPruneResults(response.data)
      if (response.data.dry_run) {
        toast.success('Dry run completed - review results below')
      } else {
        toast.success('Repository pruned successfully!')
        trackMaintenance(EventAction.START, 'Prune', pruningRepository?.name)
        queryClient.invalidateQueries({ queryKey: ['repositories'] })
        queryClient.invalidateQueries({ queryKey: ['repository-archives', pruningRepository?.id] })
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to prune repository')
      setPruneResults(null)
    },
  })

  // Event handlers
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
    setRepositoriesWithJobs((prev) => {
      const newSet = new Set(prev)
      newSet.delete(repositoryId)
      return newSet
    })
  }

  const handlePruneRepository = (repository: Repository) => {
    setPruningRepository(repository)
    setPruneResults(null)
  }

  const handleClosePruneDialog = () => {
    setPruningRepository(null)
    setPruneResults(null)
  }

  const handlePruneDryRun = async (form: PruneForm) => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...form, dry_run: true },
      })
    }
  }

  const handleConfirmPrune = async (form: PruneForm) => {
    if (pruningRepository) {
      pruneRepositoryMutation.mutate({
        id: pruningRepository.id,
        data: { ...form, dry_run: false },
      })
    }
  }

  const handleBackupNow = (repository: Repository) => {
    navigate('/backup', { state: { repositoryPath: repository.path } })
  }

  const handleViewArchives = (repository: Repository) => {
    navigate('/archives', { state: { repositoryId: repository.id } })
  }

  // Wizard functions
  const openWizard = (mode: 'create' | 'edit' | 'import', repository?: Repository) => {
    setWizardMode(mode)
    setWizardRepository(repository || null)
    setShowWizard(true)
  }

  const closeWizard = () => {
    setShowWizard(false)
    setWizardRepository(null)
  }

  const handleWizardSubmit = async (data: RepositoryData) => {
    try {
      if (wizardMode === 'edit' && wizardRepository) {
        await repositoriesAPI.updateRepository(wizardRepository.id, data)
        toast.success('Repository updated successfully')
      } else if (wizardMode === 'import') {
        await repositoriesAPI.importRepository(data)
        toast.success('Repository imported successfully')
      } else {
        await repositoriesAPI.createRepository(data)
        toast.success('Repository created successfully')
      }
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      closeWizard()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(error.response?.data?.detail || `Failed to ${wizardMode} repository`)
    }
  }

  const openEditModal = (repository: Repository) => {
    setWizardMode('edit')
    setWizardRepository(repository)
    setShowWizard(true)
  }

  // Utility functions
  const getCompressionLabel = (compression: string) => {
    return compression || 'lz4'
  }

  // Save preferences to localStorage
  React.useEffect(() => {
    localStorage.setItem('repos_sort', sortBy)
  }, [sortBy])

  React.useEffect(() => {
    localStorage.setItem('repos_group', groupBy)
  }, [groupBy])

  // Filter, sort, and group repositories
  const processedRepositories = React.useMemo(() => {
    let filtered = repositoriesData?.data?.repositories || []

    // Search filter
    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter((repo: Repository) => {
        return (
          repo.name?.toLowerCase().includes(query) ||
          repo.path?.toLowerCase().includes(query) ||
          repo.repository_type?.toLowerCase().includes(query)
        )
      })
    }

    // Sort
    const sorted = [...filtered].sort((a: Repository, b: Repository) => {
      switch (sortBy) {
        case 'name-asc':
          return (a.name || '').localeCompare(b.name || '')
        case 'name-desc':
          return (b.name || '').localeCompare(a.name || '')
        case 'last-backup-recent':
          if (!a.last_backup && !b.last_backup) return 0
          if (!a.last_backup) return 1
          if (!b.last_backup) return -1
          return new Date(b.last_backup).getTime() - new Date(a.last_backup).getTime()
        case 'last-backup-oldest':
          if (!a.last_backup && !b.last_backup) return 0
          if (!a.last_backup) return 1
          if (!b.last_backup) return -1
          return new Date(a.last_backup).getTime() - new Date(b.last_backup).getTime()
        case 'created-newest':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
        case 'created-oldest':
          return new Date(a.created_at).getTime() - new Date(b.created_at).getTime()
        default:
          return 0
      }
    })

    // Group
    if (groupBy === 'none') {
      return { groups: [{ name: null, repositories: sorted }] }
    }

    const groups: { name: string; repositories: Repository[] }[] = []

    if (groupBy === 'location') {
      // Group by hostname (for SSH) or "Local"
      const locationMap = new Map<string, Repository[]>()

      sorted.forEach((repo: Repository) => {
        let locationKey = 'Local Machine'

        if (repo.path?.startsWith('ssh://')) {
          // Extract hostname from SSH URL: ssh://user@hostname:port/path
          const match = repo.path.match(/ssh:\/\/[^@]+@([^:/]+)/)
          if (match) {
            locationKey = match[1] // hostname
          } else {
            locationKey = 'Remote (SSH)'
          }
        }

        if (!locationMap.has(locationKey)) {
          locationMap.set(locationKey, [])
        }
        locationMap.get(locationKey)!.push(repo)
      })

      // Sort location keys: Local Machine first, then alphabetically
      const sortedKeys = Array.from(locationMap.keys()).sort((a, b) => {
        if (a === 'Local Machine') return -1
        if (b === 'Local Machine') return 1
        return a.localeCompare(b)
      })

      sortedKeys.forEach((key) => {
        const repos = locationMap.get(key)!
        groups.push({ name: key, repositories: repos })
      })
    } else if (groupBy === 'type') {
      const local = sorted.filter((r: Repository) => !r.path?.startsWith('ssh://'))
      const ssh = sorted.filter((r: Repository) => r.path?.startsWith('ssh://'))

      if (local.length > 0) groups.push({ name: 'Local Repositories', repositories: local })
      if (ssh.length > 0) groups.push({ name: 'Remote Repositories (SSH)', repositories: ssh })
    } else if (groupBy === 'mode') {
      const full = sorted.filter((r: Repository) => r.mode === 'full' || !r.mode)
      const observe = sorted.filter((r: Repository) => r.mode === 'observe')

      if (full.length > 0) groups.push({ name: 'Full Backup Repositories', repositories: full })
      if (observe.length > 0)
        groups.push({ name: 'Observe-Only Repositories', repositories: observe })
    }

    return { groups: groups.length > 0 ? groups : [{ name: null, repositories: sorted }] }
  }, [repositoriesData, searchQuery, sortBy, groupBy])

  const repositories = repositoriesData?.data?.repositories || []

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
                onClick={() => openWizard('create')}
                sx={{ flexShrink: 0 }}
              >
                Create Repository
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileUpload />}
                onClick={() => openWizard('import')}
                sx={{ flexShrink: 0 }}
              >
                Import Existing
              </Button>
            </Stack>
          )}
        </Box>
      </Box>

      {/* Filter, Sort, and Search Bar */}
      {repositories.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent sx={{ '&:last-child': { pb: 2 } }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={2} alignItems="center">
              {/* Search */}
              <TextField
                size="small"
                placeholder="Search repositories..."
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                sx={{ flex: 1, minWidth: 200 }}
                InputProps={{
                  startAdornment: (
                    <InputAdornment position="start">
                      <Search fontSize="small" />
                    </InputAdornment>
                  ),
                }}
              />

              {/* Sort By */}
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="sort-label">Sort By</InputLabel>
                <Select
                  labelId="sort-label"
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  label="Sort By"
                >
                  <MenuItem value="name-asc">Name (A-Z)</MenuItem>
                  <MenuItem value="name-desc">Name (Z-A)</MenuItem>
                  <MenuItem value="last-backup-recent">Last Backup (Recent)</MenuItem>
                  <MenuItem value="last-backup-oldest">Last Backup (Oldest)</MenuItem>
                  <MenuItem value="created-newest">Created (Newest)</MenuItem>
                  <MenuItem value="created-oldest">Created (Oldest)</MenuItem>
                </Select>
              </FormControl>

              {/* Group By */}
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="group-label">Group By</InputLabel>
                <Select
                  labelId="group-label"
                  value={groupBy}
                  onChange={(e) => setGroupBy(e.target.value)}
                  label="Group By"
                >
                  <MenuItem value="none">None</MenuItem>
                  <MenuItem value="location">Location (Hostname)</MenuItem>
                  <MenuItem value="type">Repository Type</MenuItem>
                  <MenuItem value="mode">Backup Mode</MenuItem>
                </Select>
              </FormControl>
            </Stack>
          </CardContent>
        </Card>
      )}

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
              Create a local repository or remote repository via SSH. The type will be automatically
              detected based on the path you provide.
            </Typography>
            {user?.is_admin && (
              <Stack direction="row" spacing={2} justifyContent="center">
                <Button
                  variant="contained"
                  startIcon={<Add />}
                  onClick={() => openWizard('create')}
                >
                  Create Repository
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<FileUpload />}
                  onClick={() => openWizard('import')}
                >
                  Import Existing
                </Button>
              </Stack>
            )}
          </CardContent>
        </Card>
      ) : processedRepositories.groups.length === 0 ||
        processedRepositories.groups.every((g) => g.repositories.length === 0) ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 8 }}>
            <Storage sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              No Matching Repositories
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {searchQuery
                ? `No repositories match "${searchQuery}". Try a different search term.`
                : 'No repositories found.'}
            </Typography>
            {searchQuery && (
              <Button variant="outlined" onClick={() => setSearchQuery('')}>
                Clear Search
              </Button>
            )}
          </CardContent>
        </Card>
      ) : (
        <Stack spacing={3}>
          {processedRepositories.groups.map((group, groupIndex) => (
            <Box key={groupIndex}>
              {/* Group Header */}
              {group.name && (
                <Box sx={{ mb: 2 }}>
                  <Typography
                    variant="h6"
                    sx={{
                      fontSize: '1rem',
                      fontWeight: 600,
                      color: 'primary.main',
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1,
                    }}
                  >
                    <FilterList fontSize="small" />
                    {group.name}
                    <Typography
                      component="span"
                      sx={{ ml: 0.5, fontSize: '0.875rem', color: 'text.secondary' }}
                    >
                      ({group.repositories.length})
                    </Typography>
                  </Typography>
                  <Divider sx={{ mt: 1 }} />
                </Box>
              )}

              {/* Repository Cards */}
              <Stack spacing={2}>
                {group.repositories.map((repository: Repository) => (
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
            </Box>
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

      {/* Repository Info Dialog */}
      <RepositoryInfoDialog
        open={!!viewingInfoRepository}
        repository={viewingInfoRepository}
        repositoryInfo={repositoryInfo?.data?.info || null}
        isLoading={loadingInfo}
        onClose={() => setViewingInfoRepository(null)}
      />

      {/* Prune Repository Dialog */}
      <PruneRepositoryDialog
        open={!!pruningRepository}
        repository={pruningRepository}
        onClose={handleClosePruneDialog}
        onDryRun={handlePruneDryRun}
        onConfirmPrune={handleConfirmPrune}
        isLoading={pruneRepositoryMutation.isPending}
        results={pruneResults}
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

      {/* Repository Wizard */}
      <RepositoryWizard
        open={showWizard}
        onClose={closeWizard}
        mode={wizardMode}
        repository={wizardRepository || undefined}
        onSubmit={handleWizardSubmit}
      />
    </Box>
  )
}
