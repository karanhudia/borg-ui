import React, { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAnalytics } from '../hooks/useAnalytics'
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
import { BorgApiClient } from '../services/borgApi'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAuth } from '../hooks/useAuth'
import { usePermissions } from '../hooks/usePermissions'
import { useAppState } from '../context/AppContext'
import { AxiosResponse } from 'axios'
import LockErrorDialog from '../components/LockErrorDialog'
import CheckWarningDialog from '../components/CheckWarningDialog'
import CompactWarningDialog from '../components/CompactWarningDialog'
import RepositoryCard from '../components/RepositoryCard'
import RepositoryWizard from '../components/RepositoryWizard'
import PruneRepositoryDialog from '../components/PruneRepositoryDialog'
import RepositoryInfoDialog from '../components/RepositoryInfoDialog'
import { getJobDurationSeconds } from '../utils/analyticsProperties'

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
  has_keyfile?: boolean
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  hook_timeout?: number
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  skip_on_hook_failure?: boolean
  bypass_lock?: boolean
  source_ssh_connection_id?: number | null
  repository_type?: 'local' | 'ssh' | 'sftp'
  borg_version?: 1 | 2
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
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const canManageRepositoriesGlobally = hasGlobalPermission('repositories.manage_all')
  const permissions = usePermissions()
  const queryClient = useQueryClient()
  const appState = useAppState()
  const navigate = useNavigate()
  const { trackMaintenance, trackRepository, EventAction } = useAnalytics()
  const maintenanceTrackingRef = useRef<Map<number, { operation: 'Check' | 'Compact' | 'Prune' }>>(
    new Map()
  )

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
    borgVersion?: 1 | 2
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
  const deferredSearchQuery = React.useDeferredValue(searchQuery)

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
    queryFn: () => new BorgApiClient(viewingInfoRepository!).getInfo(),
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
        borgVersion: viewingInfoRepository.borg_version as 1 | 2 | undefined,
      })
    }
  }, [infoError, viewingInfoRepository])

  // Mutations
  const deleteRepositoryMutation = useMutation({
    mutationFn: repositoriesAPI.deleteRepository,
    onSuccess: (_response, repositoryId) => {
      toast.success(t('repositories.toasts.deleted'))
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      const repository = repositories.find((repo: Repository) => repo.id === repositoryId)
      trackRepository(EventAction.DELETE, repository)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('repositories.toasts.deleteFailed')
      )
    },
  })

  const checkRepositoryMutation = useMutation({
    mutationFn: ({ repositoryId, maxDuration }: { repositoryId: number; maxDuration: number }) => {
      const repo = repositories.find((r: Repository) => r.id === repositoryId)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).checkRepository(maxDuration)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (_response: any, variables: { repositoryId: number; maxDuration: number }) => {
      toast.success(t('repositories.toasts.checkStarted'))
      trackMaintenance(EventAction.START, 'Check', checkingRepository || undefined)
      maintenanceTrackingRef.current.set(variables.repositoryId, {
        operation: 'Check',
      })
      setCheckingRepository(null)
      setRepositoriesWithJobs((prev) => new Set(prev).add(variables.repositoryId))
      queryClient.invalidateQueries({ queryKey: ['running-jobs', variables.repositoryId] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const detail =
        translateBackendKey(error.response?.data?.detail) || t('repositories.toasts.checkFailed')
      if (error.response?.status === 409) {
        toast.error(detail, { duration: 5000 })
      } else {
        toast.error(detail)
      }
      setCheckingRepository(null)
    },
  })

  const compactRepositoryMutation = useMutation({
    mutationFn: (repositoryId: number) => {
      const repo = repositories.find((r: Repository) => r.id === repositoryId)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).compact()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (_response: any, repositoryId: number) => {
      toast.success(t('repositories.toasts.compactStarted'))
      trackMaintenance(EventAction.START, 'Compact', compactingRepository || undefined)
      maintenanceTrackingRef.current.set(repositoryId, {
        operation: 'Compact',
      })
      setCompactingRepository(null)
      setRepositoriesWithJobs((prev) => new Set(prev).add(repositoryId))
      queryClient.invalidateQueries({ queryKey: ['running-jobs', repositoryId] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const detail =
        translateBackendKey(error.response?.data?.detail) || t('repositories.toasts.compactFailed')
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
    mutationFn: ({ id, data }: { id: number; data: any }) => {
      const repo = repositories.find((r: Repository) => r.id === id)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).pruneArchives(data)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onSuccess: (response: any) => {
      setPruneResults(response.data)
      if (response.data.dry_run) {
        toast.success(t('repositories.toasts.dryRunCompleted'))
        trackMaintenance(EventAction.COMPLETE, 'Prune', pruningRepository || undefined, {
          mode: 'dry_run',
          status: 'completed',
        })
      } else {
        toast.success(t('repositories.toasts.pruned'))
        trackMaintenance(EventAction.START, 'Prune', pruningRepository || undefined)
        if (pruningRepository) {
          maintenanceTrackingRef.current.set(pruningRepository.id, {
            operation: 'Prune',
          })
        }
        queryClient.invalidateQueries({ queryKey: ['repositories'] })
        queryClient.invalidateQueries({ queryKey: ['repository-archives', pruningRepository?.id] })
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('repositories.toasts.pruneFailed')
      )
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

  const handleJobCompleted = async (repositoryId: number) => {
    const tracked = maintenanceTrackingRef.current.get(repositoryId)
    if (tracked) {
      const repository = repositories.find((repo: Repository) => repo.id === repositoryId)
      try {
        const response =
          tracked.operation === 'Check'
            ? await repositoriesAPI.getRepositoryCheckJobs(repositoryId, 1)
            : tracked.operation === 'Compact'
              ? await repositoriesAPI.getRepositoryCompactJobs(repositoryId, 1)
              : await repositoriesAPI.getRepositoryPruneJobs(repositoryId, 1)
        const latestJob = response.data?.jobs?.[0]

        if (latestJob?.status) {
          const action =
            latestJob.status === 'completed' || latestJob.status === 'completed_with_warnings'
              ? EventAction.COMPLETE
              : EventAction.FAIL
          trackMaintenance(action, tracked.operation, repository, {
            job_id: latestJob.id,
            status: latestJob.status,
            duration_seconds: getJobDurationSeconds(latestJob.started_at, latestJob.completed_at),
            error_present: !!latestJob.error_message,
          })
        }
      } catch {
        // Best-effort analytics should not affect maintenance UX.
      }
      maintenanceTrackingRef.current.delete(repositoryId)
    }

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

  const handleWizardSubmit = async (data: RepositoryData, keyfile?: File | null) => {
    try {
      if (wizardMode === 'edit' && wizardRepository) {
        await repositoriesAPI.updateRepository(wizardRepository.id, data)
        toast.success(t('repositories.toasts.updated'))
      } else if (wizardMode === 'import') {
        // Include keyfile content in the import request so the backend can write it
        // to disk before running `borg info` to verify the repository.
        const importData = { ...data }
        if (keyfile) {
          importData.keyfile_content = await keyfile.text()
        }
        await BorgApiClient.importRepository(importData)
        toast.success(
          keyfile ? t('repositories.toasts.importedWithKeyfile') : t('repositories.toasts.imported')
        )
      } else {
        await BorgApiClient.createRepository(data)
        toast.success(t('repositories.toasts.created'))
      }
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      closeWizard()
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (error: any) {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositories.toasts.wizardFailed', { mode: wizardMode })
      )
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
        let locationKey = t('repositories.groups.localMachine')

        if (repo.path?.startsWith('ssh://')) {
          // Extract hostname from SSH URL: ssh://user@hostname:port/path
          const match = repo.path.match(/ssh:\/\/[^@]+@([^:/]+)/)
          if (match) {
            locationKey = match[1] // hostname
          } else {
            locationKey = t('repositories.groups.remoteSsh')
          }
        }

        if (!locationMap.has(locationKey)) {
          locationMap.set(locationKey, [])
        }
        locationMap.get(locationKey)!.push(repo)
      })

      // Sort location keys: Local Machine first, then alphabetically
      const localMachineKey = t('repositories.groups.localMachine')
      const sortedKeys = Array.from(locationMap.keys()).sort((a, b) => {
        if (a === localMachineKey) return -1
        if (b === localMachineKey) return 1
        return a.localeCompare(b)
      })

      sortedKeys.forEach((key) => {
        const repos = locationMap.get(key)!
        groups.push({ name: key, repositories: repos })
      })
    } else if (groupBy === 'type') {
      const local = sorted.filter((r: Repository) => !r.path?.startsWith('ssh://'))
      const ssh = sorted.filter((r: Repository) => r.path?.startsWith('ssh://'))

      if (local.length > 0)
        groups.push({ name: t('repositories.groups.local'), repositories: local })
      if (ssh.length > 0) groups.push({ name: t('repositories.groups.remote'), repositories: ssh })
    } else if (groupBy === 'mode') {
      const full = sorted.filter((r: Repository) => r.mode === 'full' || !r.mode)
      const observe = sorted.filter((r: Repository) => r.mode === 'observe')

      if (full.length > 0) groups.push({ name: t('repositories.groups.full'), repositories: full })
      if (observe.length > 0)
        groups.push({ name: t('repositories.groups.observeOnly'), repositories: observe })
    }

    return { groups: groups.length > 0 ? groups : [{ name: null, repositories: sorted }] }
  }, [repositoriesData, searchQuery, sortBy, groupBy, t])

  React.useEffect(() => {
    const trimmedQuery = deferredSearchQuery.trim()
    if (!trimmedQuery) return

    const resultCount = processedRepositories.groups.reduce(
      (total, group) => total + group.repositories.length,
      0
    )

    trackRepository(EventAction.SEARCH, undefined, {
      section: 'repositories',
      query_length: trimmedQuery.length,
      result_count: resultCount,
      sort_by: sortBy,
      group_by: groupBy,
    })
  }, [
    deferredSearchQuery,
    groupBy,
    processedRepositories.groups,
    sortBy,
    trackRepository,
    EventAction,
  ])

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
              {t('repositories.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" paragraph>
              {t('repositories.subtitle')}
            </Typography>
          </Box>
          {canManageRepositoriesGlobally && (
            <Stack direction="row" spacing={2}>
              <Button
                variant="contained"
                startIcon={<Add />}
                onClick={() => openWizard('create')}
                sx={{ flexShrink: 0 }}
              >
                {t('repositories.createRepository')}
              </Button>
              <Button
                variant="outlined"
                startIcon={<FileUpload />}
                onClick={() => openWizard('import')}
                sx={{ flexShrink: 0 }}
              >
                {t('repositories.importExisting')}
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
                placeholder={t('repositories.search')}
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
                <InputLabel id="sort-label">{t('repositories.sort.label')}</InputLabel>
                <Select
                  labelId="sort-label"
                  value={sortBy}
                  onChange={(e) => {
                    const nextSort = e.target.value
                    setSortBy(nextSort)
                    const resultCount = processedRepositories.groups.reduce(
                      (total, group) => total + group.repositories.length,
                      0
                    )
                    trackRepository(EventAction.FILTER, undefined, {
                      section: 'repositories',
                      filter_kind: 'sort',
                      sort_by: nextSort,
                      group_by: groupBy,
                      query_length: searchQuery.trim().length,
                      result_count: resultCount,
                    })
                  }}
                  label={t('repositories.sort.label')}
                >
                  <MenuItem value="name-asc">{t('repositories.sort.nameAZ')}</MenuItem>
                  <MenuItem value="name-desc">{t('repositories.sort.nameZA')}</MenuItem>
                  <MenuItem value="last-backup-recent">
                    {t('repositories.sort.lastBackupRecent')}
                  </MenuItem>
                  <MenuItem value="last-backup-oldest">
                    {t('repositories.sort.lastBackupOldest')}
                  </MenuItem>
                  <MenuItem value="created-newest">{t('repositories.sort.createdNewest')}</MenuItem>
                  <MenuItem value="created-oldest">{t('repositories.sort.createdOldest')}</MenuItem>
                </Select>
              </FormControl>

              {/* Group By */}
              <FormControl size="small" sx={{ minWidth: 200 }}>
                <InputLabel id="group-label">{t('repositories.group.label')}</InputLabel>
                <Select
                  labelId="group-label"
                  value={groupBy}
                  onChange={(e) => {
                    const nextGroup = e.target.value
                    setGroupBy(nextGroup)
                    const resultCount = processedRepositories.groups.reduce(
                      (total, group) => total + group.repositories.length,
                      0
                    )
                    trackRepository(EventAction.FILTER, undefined, {
                      section: 'repositories',
                      filter_kind: 'group',
                      sort_by: sortBy,
                      group_by: nextGroup,
                      query_length: searchQuery.trim().length,
                      result_count: resultCount,
                    })
                  }}
                  label={t('repositories.group.label')}
                >
                  <MenuItem value="none">{t('repositories.group.none')}</MenuItem>
                  <MenuItem value="location">{t('repositories.group.hostname')}</MenuItem>
                  <MenuItem value="type">{t('repositories.group.type')}</MenuItem>
                  <MenuItem value="mode">{t('repositories.group.mode')}</MenuItem>
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
            {t('repositories.loading')}
          </Typography>
        </Box>
      ) : repositories.length === 0 ? (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 8 }}>
            <Storage sx={{ fontSize: 64, color: 'text.disabled', mb: 2 }} />
            <Typography variant="h6" gutterBottom>
              {t('repositories.empty.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t('repositories.empty.subtitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {t('repositories.empty.hint')}
            </Typography>
            {canManageRepositoriesGlobally && (
              <Stack direction="row" spacing={2} justifyContent="center">
                <Button
                  variant="contained"
                  startIcon={<Add />}
                  onClick={() => openWizard('create')}
                >
                  {t('repositories.createRepository')}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<FileUpload />}
                  onClick={() => openWizard('import')}
                >
                  {t('repositories.importExisting')}
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
              {t('repositories.noMatch.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              {searchQuery
                ? t('repositories.noMatch.message', { search: searchQuery })
                : t('repositories.noMatch.fallback')}
            </Typography>
            {searchQuery && (
              <Button variant="outlined" onClick={() => setSearchQuery('')}>
                {t('repositories.noMatch.clearSearch')}
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
                    canManageRepository={canManageRepositoriesGlobally}
                    canDo={(action) => permissions.canDo(repository.id, action)}
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
          borgVersion={lockError.borgVersion}
          canBreakLock={canManageRepositoriesGlobally}
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
