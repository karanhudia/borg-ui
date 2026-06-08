import React, { useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useAnalytics } from '../hooks/useAnalytics'
import { Box } from '@mui/material'
import { backupPlansAPI, repositoriesAPI, RepositoryData } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { translateBackendKey } from '../utils/translateBackendKey'
import { useAuth } from '../hooks/useAuth'
import { useLockBreakPermissions } from '../hooks/useLockBreakPermissions'
import { usePlan } from '../hooks/usePlan'
import { usePermissions } from '../hooks/usePermissions'
import { useAppState } from '../context/AppContext'
import { AxiosResponse } from 'axios'
import LockErrorDialog from '../components/LockErrorDialog'
import CheckWarningDialog, {
  type CheckWarningConfirmOptions,
} from '../components/CheckWarningDialog'
import CompactWarningDialog from '../components/CompactWarningDialog'
import RepositoryWizard from '../components/RepositoryWizard'
import PruneRepositoryDialog from '../components/PruneRepositoryDialog'
import RepositoryWipeDialog from '../components/RepositoryWipeDialog'
import PermanentDeleteRepositoryDialog from '../components/PermanentDeleteRepositoryDialog'
import RepositoryInfoDialog from '../components/RepositoryInfoDialog'
import { getJobDurationSeconds } from '../utils/analyticsProperties'
import { CreateBackupPlanDialog } from './repositories-page/CreateBackupPlanDialog'
import { RepositoriesHeader } from './repositories-page/RepositoriesHeader'
import { RepositoryGroups } from './repositories-page/RepositoryGroups'
import { RepositoriesToolbar } from './repositories-page/RepositoriesToolbar'
import {
  getCompressionLabel,
  getCreatedRepositoryId,
  getRepositoryResultCount,
  processRepositories,
} from './repositories-page/helpers'
import type { PruneForm, Repository } from './repositories-page/types'
import type { BackupPlan, RepositoryWipeExecuteRequest, RepositoryWipeJob } from '../types'

const EMPTY_REPOSITORIES: Repository[] = []
const RUNNING_WIPE_STATUSES = new Set(['pending', 'running'])
const TERMINAL_WIPE_STATUSES = new Set([
  'completed',
  'completed_compaction_failed',
  'completed_with_warnings',
  'failed',
  'failed_partial',
  'cancelled',
])
type RcloneRepositoryAction = 'sync' | 'hydrate'

interface MaintenanceJobSummary {
  id: number
  status?: string | null
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
}

function parseBackupPlanFilterId(value: string | null): number | null {
  if (!value) return null
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : null
}

function canPermanentlyDeleteRepository(repository: Repository): boolean {
  const repositoryType = (repository.repository_type || 'local').toLowerCase()
  const storageBackend = (repository.storage_backend || 'local').toLowerCase()
  const executionTarget = (repository.execution_target || 'local').toLowerCase()
  const executorType = (repository.executor_type || 'server').toLowerCase()
  const repositoryPath = repository.path || ''

  return (
    repositoryType === 'local' &&
    storageBackend === 'local' &&
    executionTarget === 'local' &&
    executorType !== 'agent' &&
    !repository.connection_id &&
    !repository.agent_machine_id &&
    !repositoryPath.includes('://')
  )
}

function removeRepositoryFromResponse(data: unknown, repositoryId: number): unknown {
  if (Array.isArray(data)) {
    return data.filter((repository) => repository?.id !== repositoryId)
  }

  if (
    data &&
    typeof data === 'object' &&
    Array.isArray((data as { repositories?: unknown }).repositories)
  ) {
    return {
      ...data,
      repositories: (data as { repositories: Repository[] }).repositories.filter(
        (repository) => repository.id !== repositoryId
      ),
    }
  }

  return data
}

export default function Repositories() {
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const { can } = usePlan()
  const canManageRepositoriesGlobally = hasGlobalPermission('repositories.manage_all')
  const canUseManagedAgents = can('managed_agents')
  const canUseRclone = can('rclone')
  const permissions = usePermissions()
  const queryClient = useQueryClient()
  const appState = useAppState()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
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
  const [wipingRepository, setWipingRepository] = useState<Repository | null>(null)
  const [permanentlyDeletingRepository, setPermanentlyDeletingRepository] =
    useState<Repository | null>(null)
  const [wipePreview, setWipePreview] = useState<RepositoryWipeJob | null>(null)
  const [wipeJob, setWipeJob] = useState<RepositoryWipeJob | null>(null)
  const [planSourceRepository, setPlanSourceRepository] = useState<Repository | null>(null)
  const [backupPlanName, setBackupPlanName] = useState('')
  const [copyExistingSchedule, setCopyExistingSchedule] = useState(true)
  const [disableExistingSchedule, setDisableExistingSchedule] = useState(true)
  const [moveSourceSettings, setMoveSourceSettings] = useState(true)
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [pruneResults, setPruneResults] = useState<any>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
    borgVersion?: 1 | 2
  } | null>(null)

  // Track repositories with running jobs for polling
  const [repositoriesWithJobs, setRepositoriesWithJobs] = useState<Set<number>>(new Set())
  const announcedWipeJobsRef = useRef<Set<number>>(new Set())

  // Filter, sort, and search state
  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<string>(() => {
    return localStorage.getItem('repos_sort') || 'name-asc'
  })
  const [groupBy, setGroupBy] = useState<string>(() => {
    return localStorage.getItem('repos_group') || 'none'
  })
  const deferredSearchQuery = React.useDeferredValue(searchQuery)
  const selectedBackupPlanId = React.useMemo(
    () => parseBackupPlanFilterId(searchParams.get('backupPlanId')),
    [searchParams]
  )

  // Queries
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: repositoriesData, isLoading } = useQuery<AxiosResponse<any>>({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const { canBreakLock, lockBreakingEnabled } = useLockBreakPermissions()

  const { data: backupPlansData, isLoading: loadingBackupPlanFilter } = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
  })

  const backupPlans: BackupPlan[] = React.useMemo(
    () => backupPlansData?.data?.backup_plans || [],
    [backupPlansData]
  )

  const { data: selectedBackupPlanData, isLoading: loadingSelectedBackupPlan } = useQuery({
    queryKey: ['backup-plan', selectedBackupPlanId],
    queryFn: () => backupPlansAPI.get(selectedBackupPlanId!),
    enabled: selectedBackupPlanId !== null,
  })

  const activeWipeJobId =
    wipingRepository && wipeJob && RUNNING_WIPE_STATUSES.has(wipeJob.status) ? wipeJob.id : null

  const { data: wipeJobStatusData } = useQuery({
    queryKey: ['repository-wipe-job', wipingRepository?.id, activeWipeJobId],
    queryFn: async () => {
      const response = await repositoriesAPI.getRepositoryWipeJob(
        wipingRepository!.id,
        activeWipeJobId!
      )
      return response.data
    },
    enabled: Boolean(wipingRepository && activeWipeJobId),
    refetchInterval: (query) => {
      const data = query.state.data as RepositoryWipeJob | undefined
      return !data || RUNNING_WIPE_STATUSES.has(data.status) ? 2000 : false
    },
    refetchIntervalInBackground: true,
    retry: false,
  })

  const selectedBackupPlanRepositoryIds = React.useMemo(() => {
    if (selectedBackupPlanId === null) return undefined
    const repositories = (selectedBackupPlanData?.data as BackupPlan | undefined)?.repositories
    if (!repositories) return undefined

    return new Set(repositories.filter((link) => link.enabled).map((link) => link.repository_id))
  }, [selectedBackupPlanData, selectedBackupPlanId])

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

  const permanentDeleteRepositoryMutation = useMutation({
    mutationFn: ({
      repository,
      confirmationPhrase,
    }: {
      repository: Repository
      confirmationPhrase: string
    }) =>
      repositoriesAPI.permanentlyDeleteRepository(repository.id, {
        confirmation_phrase: confirmationPhrase,
        understood: true,
      }),
    onSuccess: (_response, variables) => {
      toast.success(t('repositories.toasts.permanentlyDeleted'))
      queryClient.setQueryData<AxiosResponse<unknown>>(['repositories'], (current) =>
        current
          ? {
              ...current,
              data: removeRepositoryFromResponse(current.data, variables.repository.id),
            }
          : current
      )
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      appState.refetch()
      setPermanentlyDeletingRepository(null)
      trackRepository(EventAction.DELETE, variables.repository, {
        mode: 'permanent_filesystem',
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositories.toasts.permanentDeleteFailed')
      )
    },
  })

  const checkRepositoryMutation = useMutation({
    mutationFn: ({
      repositoryId,
      maxDuration,
      checkExtraFlags,
    }: {
      repositoryId: number
      maxDuration: number
      checkExtraFlags: string
    }) => {
      const repo = repositories.find((r: Repository) => r.id === repositoryId)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).checkRepository({ maxDuration, checkExtraFlags })
    },
    onSuccess: (
      _response: unknown,
      variables: { repositoryId: number; maxDuration: number; checkExtraFlags: string }
    ) => {
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
      if (response.data.dry_run) {
        setPruneResults(response.data)
        toast.success(t('repositories.toasts.dryRunCompleted'))
        trackMaintenance(EventAction.COMPLETE, 'Prune', pruningRepository || undefined, {
          mode: 'dry_run',
          status: 'completed',
        })
      } else if (response.data.job_id) {
        setPruneResults(null)
        toast.success(t('repositories.toasts.pruneStarted'))
        trackMaintenance(EventAction.START, 'Prune', pruningRepository || undefined)
        if (pruningRepository) {
          maintenanceTrackingRef.current.set(pruningRepository.id, {
            operation: 'Prune',
          })
          setRepositoriesWithJobs((prev) => new Set(prev).add(pruningRepository.id))
          queryClient.invalidateQueries({ queryKey: ['running-jobs', pruningRepository.id] })
          queryClient.invalidateQueries({ queryKey: ['repositories'] })
          queryClient.invalidateQueries({ queryKey: ['repository-archives', pruningRepository.id] })
        }
        setPruningRepository(null)
      } else {
        setPruneResults(response.data)
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

  const wipePreviewMutation = useMutation({
    mutationFn: ({ repository, runCompact }: { repository: Repository; runCompact: boolean }) =>
      repositoriesAPI.previewRepositoryWipe(repository.id, { run_compact: runCompact }),
    onSuccess: (response) => {
      setWipePreview(response.data)
      setWipeJob(null)
      toast.success(t('repositories.toasts.wipePreviewGenerated'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositories.toasts.wipePreviewFailed')
      )
    },
  })

  const executeWipeMutation = useMutation({
    mutationFn: ({
      repository,
      payload,
    }: {
      repository: Repository
      payload: RepositoryWipeExecuteRequest
    }) => repositoriesAPI.executeRepositoryWipe(repository.id, payload),
    onSuccess: (response, variables) => {
      setWipeJob(response.data)
      toast.success(t('repositories.toasts.wipeStarted'))
      setRepositoriesWithJobs((prev) => new Set(prev).add(variables.repository.id))
      queryClient.invalidateQueries({ queryKey: ['running-jobs', variables.repository.id] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      if (error.response?.status === 409) {
        setWipePreview((current) => (current ? { ...current, phase: 'stale' } : current))
      }
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('repositories.toasts.wipeFailed')
      )
    },
  })

  const cancelWipePreviewMutation = useMutation({
    mutationFn: ({ repositoryId, jobId }: { repositoryId: number; jobId: number }) =>
      repositoriesAPI.cancelRepositoryWipeJob(repositoryId, jobId),
    onSuccess: (response) => {
      setWipePreview(response.data)
      setWipeJob(response.data)
      toast.success(t('repositories.toasts.wipeCancelled'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositories.toasts.wipeCancelFailed')
      )
    },
  })

  const createBackupPlanMutation = useMutation({
    mutationFn: ({
      repository,
      name,
      copySchedule,
      disableSchedule,
    }: {
      repository: Repository
      name: string
      copySchedule: boolean
      disableSchedule: boolean
    }) =>
      backupPlansAPI.createFromRepository(repository.id, {
        name: name.trim() || undefined,
        copy_schedule: copySchedule,
        disable_repository_schedule: copySchedule && disableSchedule,
        move_source_settings: moveSourceSettings,
      }),
    onSuccess: (response, variables) => {
      toast.success(t('repositories.toasts.backupPlanCreated'))
      if (
        response.data.copied_schedule_id &&
        variables.disableSchedule &&
        !response.data.repository_schedule_disabled
      ) {
        toast(t('repositories.toasts.sharedScheduleKept'), { icon: 'i' })
      }
      setPlanSourceRepository(null)
      setBackupPlanName('')
      setCopyExistingSchedule(true)
      setDisableExistingSchedule(true)
      setMoveSourceSettings(true)
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      appState.refetch()
      navigate('/backup-plans', {
        state: { highlightPlanId: response.data.backup_plan.id },
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('repositories.toasts.backupPlanCreateFailed')
      )
    },
  })

  const rcloneRepositoryMutation = useMutation({
    mutationFn: ({
      repository,
      action,
    }: {
      repository: Repository
      action: RcloneRepositoryAction
    }) =>
      action === 'sync'
        ? repositoriesAPI.syncRcloneRepository(repository.id)
        : repositoriesAPI.hydrateRcloneRepository(repository.id),
    onSuccess: (_response, variables) => {
      toast.success(
        variables.action === 'sync'
          ? t('repositories.toasts.rcloneSyncCompleted')
          : t('repositories.toasts.rcloneHydrateCompleted')
      )
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any, variables) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          (variables.action === 'sync'
            ? t('repositories.toasts.rcloneSyncFailed')
            : t('repositories.toasts.rcloneHydrateFailed'))
      )
    },
  })

  // Event handlers
  const handleDeleteRepository = (repository: Repository) => {
    if (window.confirm(`Are you sure you want to delete repository "${repository.name}"?`)) {
      deleteRepositoryMutation.mutate(repository.id)
    }
  }

  const handlePermanentDeleteRepository = (repository: Repository) => {
    setPermanentlyDeletingRepository(repository)
  }

  const handleConfirmPermanentDeleteRepository = (confirmationPhrase: string) => {
    if (!permanentlyDeletingRepository) return
    permanentDeleteRepositoryMutation.mutate({
      repository: permanentlyDeletingRepository,
      confirmationPhrase,
    })
  }

  const handleCheckRepository = (repository: Repository) => {
    setCheckingRepository(repository)
  }

  const handleConfirmCheck = ({ maxDuration, checkExtraFlags }: CheckWarningConfirmOptions) => {
    if (checkingRepository) {
      checkRepositoryMutation.mutate({
        repositoryId: checkingRepository.id,
        maxDuration,
        checkExtraFlags,
      })
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
      let toastShown = false
      try {
        const response =
          tracked.operation === 'Check'
            ? await repositoriesAPI.getRepositoryCheckJobs(repositoryId, 1)
            : tracked.operation === 'Compact'
              ? await repositoriesAPI.getRepositoryCompactJobs(repositoryId, 1)
              : await repositoriesAPI.getRepositoryPruneJobs(repositoryId, 1)
        const latestJob = response.data?.jobs?.[0] as MaintenanceJobSummary | undefined

        if (latestJob?.status) {
          if (tracked.operation === 'Check') {
            if (latestJob.status === 'completed') {
              toast.success(t('repositories.toasts.checkCompleted'))
              toastShown = true
            } else if (latestJob.status === 'completed_with_warnings') {
              toast(t('repositories.toasts.checkCompletedWithWarnings'), { icon: '!' })
              toastShown = true
            } else {
              const message = latestJob.error_message
                ? translateBackendKey(latestJob.error_message) || latestJob.error_message
                : t('repositories.toasts.checkRunFailed')
              toast.error(t('repositories.toasts.checkFailedWithMessage', { message }))
              toastShown = true
            }
          }

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
        } else if (tracked.operation === 'Check') {
          toast.success(t('repositories.toasts.checkCompleted'))
          toastShown = true
        }
      } catch {
        if (tracked.operation === 'Check' && !toastShown) {
          toast.success(t('repositories.toasts.checkCompleted'))
        }
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

  const handleWipeRepository = (repository: Repository) => {
    setWipingRepository(repository)
    setWipePreview(null)
    setWipeJob(null)
  }

  const handleBreakLockRepository = (repository: Repository) => {
    setLockError({
      repositoryId: repository.id,
      repositoryName: repository.name,
      borgVersion: repository.borg_version,
    })
  }

  const handleRcloneSync = (repository: Repository) => {
    rcloneRepositoryMutation.mutate({ repository, action: 'sync' })
  }

  const handleRcloneHydrate = (repository: Repository) => {
    rcloneRepositoryMutation.mutate({ repository, action: 'hydrate' })
  }

  const handleCloseWipeDialog = () => {
    setWipingRepository(null)
    if (!wipeJob || TERMINAL_WIPE_STATUSES.has(wipeJob.status)) {
      setWipePreview(null)
      setWipeJob(null)
    }
  }

  const handleGenerateWipePreview = (runCompact: boolean) => {
    if (!wipingRepository) return
    wipePreviewMutation.mutate({ repository: wipingRepository, runCompact })
  }

  const handleExecuteWipe = (payload: RepositoryWipeExecuteRequest) => {
    if (!wipingRepository) return
    executeWipeMutation.mutate({ repository: wipingRepository, payload })
  }

  const handleCancelWipePreview = (jobId: number) => {
    if (!wipingRepository) return
    cancelWipePreviewMutation.mutate({ repositoryId: wipingRepository.id, jobId })
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

  const handleViewBackupPlans = (repository: Repository) => {
    navigate(`/backup-plans?repositoryId=${repository.id}`)
  }

  const handleCreateBackupPlan = (repository: Repository) => {
    if (!repository.source_directories?.length) {
      navigate('/backup-plans', { state: { createPlanForRepositoryId: repository.id } })
      return
    }
    setPlanSourceRepository(repository)
    setBackupPlanName(`${repository.name} Backup Plan`)
    setCopyExistingSchedule(Boolean(repository.has_schedule))
    setDisableExistingSchedule(Boolean(repository.has_schedule))
    setMoveSourceSettings(true)
  }

  const handleConfirmCreateBackupPlan = () => {
    if (!planSourceRepository) return
    createBackupPlanMutation.mutate({
      repository: planSourceRepository,
      name: backupPlanName,
      copySchedule: copyExistingSchedule,
      disableSchedule: disableExistingSchedule,
    })
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
        const response = await BorgApiClient.importRepository(importData)
        toast.success(
          keyfile ? t('repositories.toasts.importedWithKeyfile') : t('repositories.toasts.imported')
        )
        const repositoryId = getCreatedRepositoryId(response)
        if (repositoryId) {
          queryClient.invalidateQueries({ queryKey: ['repositories'] })
          queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
          appState.refetch()
          closeWizard()
          navigate('/backup-plans', { state: { createPlanForRepositoryId: repositoryId } })
          return
        }
      } else {
        const response = await BorgApiClient.createRepository(data)
        toast.success(t('repositories.toasts.created'))
        const repositoryId = getCreatedRepositoryId(response)
        if (repositoryId) {
          queryClient.invalidateQueries({ queryKey: ['repositories'] })
          queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
          appState.refetch()
          closeWizard()
          navigate('/backup-plans', { state: { createPlanForRepositoryId: repositoryId } })
          return
        }
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

  // Save preferences to localStorage
  React.useEffect(() => {
    localStorage.setItem('repos_sort', sortBy)
  }, [sortBy])

  React.useEffect(() => {
    localStorage.setItem('repos_group', groupBy)
  }, [groupBy])

  const repositories: Repository[] = repositoriesData?.data?.repositories || EMPTY_REPOSITORIES
  const repositoriesLoading =
    isLoading || (selectedBackupPlanId !== null && loadingSelectedBackupPlan)

  // Filter, sort, and group repositories
  const processedRepositories = React.useMemo(
    () =>
      processRepositories({
        repositories,
        searchQuery,
        sortBy,
        groupBy,
        backupPlanRepositoryIds: selectedBackupPlanRepositoryIds,
        t,
      }),
    [repositories, searchQuery, sortBy, groupBy, selectedBackupPlanRepositoryIds, t]
  )

  const handleBackupPlanFilterChange = React.useCallback(
    (planId: number | null) => {
      const nextParams = new URLSearchParams(searchParams)
      if (planId === null) {
        nextParams.delete('backupPlanId')
      } else {
        nextParams.set('backupPlanId', String(planId))
      }
      setSearchParams(nextParams, { replace: true })
    },
    [searchParams, setSearchParams]
  )

  React.useEffect(() => {
    const trimmedQuery = deferredSearchQuery.trim()
    if (!trimmedQuery) return

    const resultCount = getRepositoryResultCount(processedRepositories)

    trackRepository(EventAction.SEARCH, undefined, {
      section: 'repositories',
      query_length: trimmedQuery.length,
      result_count: resultCount,
      sort_by: sortBy,
      group_by: groupBy,
    })
  }, [deferredSearchQuery, groupBy, processedRepositories, sortBy, trackRepository, EventAction])

  React.useEffect(() => {
    if (!wipeJobStatusData || !wipingRepository) return
    setWipeJob(wipeJobStatusData)

    if (!TERMINAL_WIPE_STATUSES.has(wipeJobStatusData.status)) return
    if (announcedWipeJobsRef.current.has(wipeJobStatusData.id)) return
    announcedWipeJobsRef.current.add(wipeJobStatusData.id)

    setRepositoriesWithJobs((prev) => {
      const next = new Set(prev)
      next.delete(wipingRepository.id)
      return next
    })
    queryClient.invalidateQueries({ queryKey: ['repositories'] })
    queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
    queryClient.invalidateQueries({ queryKey: ['repository-archives', wipingRepository.id] })
    queryClient.invalidateQueries({ queryKey: ['running-jobs', wipingRepository.id] })
    appState.refetch()

    if (wipeJobStatusData.status === 'completed') {
      toast.success(t('repositories.toasts.wipeSuccess'))
    } else if (wipeJobStatusData.status === 'completed_compaction_failed') {
      toast.error(t('repositories.toasts.wipeCompactFailed'))
    } else if (wipeJobStatusData.status === 'completed_with_warnings') {
      toast(t('repositories.toasts.wipeCompactSkipped'), { icon: '!' })
    } else if (wipeJobStatusData.status !== 'cancelled') {
      toast.error(t('repositories.toasts.wipeFailed'))
    }
  }, [appState, queryClient, t, wipeJobStatusData, wipingRepository])

  return (
    <Box>
      <RepositoriesHeader
        canManageRepositoriesGlobally={canManageRepositoriesGlobally}
        onOpenWizard={openWizard}
      />

      <RepositoriesToolbar
        isVisible={repositoriesLoading || repositories.length > 0}
        searchQuery={searchQuery}
        sortBy={sortBy}
        groupBy={groupBy}
        processedRepositories={processedRepositories}
        backupPlans={backupPlans.map((plan) => ({ id: plan.id, name: plan.name }))}
        backupPlanFilterLoading={loadingBackupPlanFilter}
        selectedBackupPlanId={selectedBackupPlanId}
        onSearchChange={setSearchQuery}
        onSortChange={setSortBy}
        onGroupChange={setGroupBy}
        onBackupPlanFilterChange={handleBackupPlanFilterChange}
        onFilterTracked={(metadata) => {
          trackRepository(EventAction.FILTER, undefined, {
            section: 'repositories',
            ...metadata,
          })
        }}
      />

      <RepositoryGroups
        isLoading={repositoriesLoading}
        repositories={repositories}
        processedRepositories={processedRepositories}
        repositoriesWithJobs={repositoriesWithJobs}
        searchQuery={searchQuery}
        canManageRepositoriesGlobally={canManageRepositoriesGlobally}
        canDo={permissions.canDo}
        canBreakLock={(repository) => canBreakLock({ repository_id: repository.id })}
        onSearchChange={setSearchQuery}
        onOpenWizard={openWizard}
        onViewInfo={setViewingInfoRepository}
        onCheck={handleCheckRepository}
        onCompact={handleCompactRepository}
        onPrune={handlePruneRepository}
        onWipeContents={handleWipeRepository}
        onBreakLock={handleBreakLockRepository}
        onEdit={openEditModal}
        onDelete={handleDeleteRepository}
        onPermanentDelete={handlePermanentDeleteRepository}
        onBackupNow={handleBackupNow}
        onViewArchives={handleViewArchives}
        onViewBackupPlans={handleViewBackupPlans}
        onCreateBackupPlan={handleCreateBackupPlan}
        onRcloneSync={handleRcloneSync}
        onRcloneHydrate={handleRcloneHydrate}
        canPermanentDeleteRepository={canPermanentlyDeleteRepository}
        getCompressionLabel={getCompressionLabel}
        onJobCompleted={handleJobCompleted}
      />

      <CreateBackupPlanDialog
        repository={planSourceRepository}
        backupPlanName={backupPlanName}
        copyExistingSchedule={copyExistingSchedule}
        disableExistingSchedule={disableExistingSchedule}
        moveSourceSettings={moveSourceSettings}
        isPending={createBackupPlanMutation.isPending}
        onClose={() => setPlanSourceRepository(null)}
        onPlanNameChange={setBackupPlanName}
        onCopyExistingScheduleChange={setCopyExistingSchedule}
        onDisableExistingScheduleChange={setDisableExistingSchedule}
        onMoveSourceSettingsChange={setMoveSourceSettings}
        onConfirm={handleConfirmCreateBackupPlan}
      />

      {/* Warning Dialogs */}
      <CheckWarningDialog
        open={!!checkingRepository}
        repositoryName={checkingRepository?.name || ''}
        borgVersion={checkingRepository?.borg_version}
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
        onRunRecoveryCheck={(repository) => handleCheckRepository(repository as Repository)}
        canRunRecoveryCheck={
          viewingInfoRepository ? permissions.canDo(viewingInfoRepository.id, 'maintenance') : false
        }
        isRecoveryCheckStarting={checkRepositoryMutation.isPending}
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

      <RepositoryWipeDialog
        open={!!wipingRepository}
        repository={wipingRepository}
        preview={wipePreview}
        job={wipeJob}
        isPreviewLoading={wipePreviewMutation.isPending}
        isExecuteLoading={executeWipeMutation.isPending}
        onClose={handleCloseWipeDialog}
        onGeneratePreview={handleGenerateWipePreview}
        onExecute={handleExecuteWipe}
        onCancelPreview={handleCancelWipePreview}
      />

      <PermanentDeleteRepositoryDialog
        open={!!permanentlyDeletingRepository}
        repository={permanentlyDeletingRepository}
        isPending={permanentDeleteRepositoryMutation.isPending}
        onClose={() => setPermanentlyDeletingRepository(null)}
        onConfirm={handleConfirmPermanentDeleteRepository}
      />

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          borgVersion={lockError.borgVersion}
          canBreakLock={canBreakLock({ repository_id: lockError.repositoryId })}
          lockBreakingEnabled={lockBreakingEnabled}
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
        canUseManagedAgents={canUseManagedAgents}
        canUseRclone={canUseRclone}
        onSubmit={handleWizardSubmit}
      />
    </Box>
  )
}
