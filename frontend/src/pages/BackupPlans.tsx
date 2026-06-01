import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Box, Button, DialogActions } from '@mui/material'
import { CalendarClock, Edit, ListChecks } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { isAxiosError } from 'axios'

import RepositoryWizard from '../components/RepositoryWizard'
import { type PruneSettings } from '../components/PruneSettingsInput'
import WizardDialog from '../components/shared/WizardDialog'
import LogViewerDialog from '../components/LogViewerDialog'
import FileExplorerDialog from '../components/FileExplorerDialog'
import { type BackupPlanRunLogJob } from '../components/BackupPlanRunsPanel'
import {
  backupPlansAPI,
  managedAgentsAPI,
  repositoriesAPI,
  type RepositoryData,
  type AgentMachineResponse,
  scriptsAPI,
  sshKeysAPI,
} from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { usePlan } from '../hooks/usePlan'
import { useAnalytics } from '../hooks/useAnalytics'
import { translateBackendKey } from '../utils/translateBackendKey'
import { buildBackupPlanPayload } from '../utils/backupPlanPayload'
import { getCheckFlagDurationConflict } from '../utils/checkFlagConflicts'
import {
  applyRepositorySelectionLimit,
  isRepositorySelectionOverLimit,
} from '../utils/backupPlanRepositorySelection'
import type { BackupPlan, BackupPlanData, BackupPlanRun, Repository } from '../types'
import { BackupPlanWizardStep } from './backup-plans/BackupPlanWizardStep'
import { BackupPlansContent } from './backup-plans/BackupPlansContent'
import { LegacySourceSettingsReviewDialog } from './backup-plans/LegacySourceSettingsReviewDialog'
import {
  getLegacySourceRepositoryReviews,
  type LegacySourceRepositoryReview,
} from './backup-plans/legacySourceSettings'
import { BackupPlanHistoryDialog } from './backup-plans/PlanRunComponents'
import { parseRepositoryFilterId, processBackupPlans } from './backup-plans/helpers'
import { buildRoutePreviews } from './backup-plans/routePreview'
import { formatRunStatus, isActiveRun } from './backup-plans/runStatus'
import {
  createInitialBasicRepositoryState,
  createInitialState,
  getCreatedRepositoryId,
  planToState,
} from './backup-plans/state'
import type {
  BasicRepositoryState,
  ScriptOption,
  SSHConnection,
  WizardState,
} from './backup-plans/types'

const stepDefinitions = [
  { key: 'source', labelKey: 'backupPlans.wizard.steps.sources', icon: <ListChecks size={14} /> },
  {
    key: 'repositories',
    labelKey: 'backupPlans.wizard.steps.repositories',
    icon: <ListChecks size={14} />,
  },
  { key: 'settings', labelKey: 'backupPlans.wizard.steps.settings', icon: <Edit size={14} /> },
  {
    key: 'scripts',
    labelKey: 'backupPlans.wizard.steps.scripts',
    icon: <Edit size={14} />,
  },
  {
    key: 'schedule',
    labelKey: 'backupPlans.wizard.steps.schedule',
    icon: <CalendarClock size={14} />,
  },
  { key: 'review', labelKey: 'backupPlans.wizard.steps.review', icon: <ListChecks size={14} /> },
]

const BACKUP_PLANS_ANALYTICS_SECTION = 'backup_plans'

function errorMessage(error: unknown, fallback: string): string {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
  return translateBackendKey(detail) || fallback
}

export default function BackupPlans() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const { t } = useTranslation()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { can } = usePlan()
  const canUseMultiRepository = can('backup_plan_multi_repository')
  const canUseMixedSourceTypes = can('backup_plan_mixed_sources')
  const canUseManagedAgents = can('managed_agents')
  const canUseRclone = can('rclone')
  const canUseBorg2 = can('borg_v2')
  const [wizardOpen, setWizardOpen] = useState(false)
  const [activeStep, setActiveStep] = useState(0)
  const [editingPlan, setEditingPlan] = useState<BackupPlan | null>(null)
  const [wizardState, setWizardState] = useState<WizardState>(() => createInitialState())
  const [repositoryWizardOpen, setRepositoryWizardOpen] = useState(false)
  const [basicRepositoryOpen, setBasicRepositoryOpen] = useState(false)
  const [basicRepositoryState, setBasicRepositoryState] = useState<BasicRepositoryState>(() =>
    createInitialBasicRepositoryState()
  )
  const [showSourceExplorer, setShowSourceExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)
  const [showBasicRepositoryPathExplorer, setShowBasicRepositoryPathExplorer] = useState(false)
  const [startingPlanId, setStartingPlanId] = useState<number | null>(null)
  const [historyPlanId, setHistoryPlanId] = useState<number | null>(null)
  const [highlightedPlanId, setHighlightedPlanId] = useState<number | null>(null)
  const [cancellingRunId, setCancellingRunId] = useState<number | null>(null)
  const [logJob, setLogJob] = useState<BackupPlanRunLogJob | null>(null)
  const [searchQuery, setSearchQuery] = useState('')
  const [legacySourceReviewOpen, setLegacySourceReviewOpen] = useState(false)
  const [legacySourceReviews, setLegacySourceReviews] = useState<LegacySourceRepositoryReview[]>([])
  const [sortBy, setSortBy] = useState<string>(
    () => localStorage.getItem('backup_plans_sort') || 'name-asc'
  )
  const [groupBy, setGroupBy] = useState<string>(
    () => localStorage.getItem('backup_plans_group') || 'none'
  )
  const handledInitialRepositoryRef = useRef(false)
  const trackBackupPlanSubmit = (action: string, data: BackupPlanData) => {
    track(EventCategory.BACKUP, action, {
      entity: 'backup_plan',
      section: BACKUP_PLANS_ANALYTICS_SECTION,
      operation: action === EventAction.CREATE ? 'create_plan' : 'update_plan',
      source_type: data.source_type,
      repository_count: data.repositories.length,
      schedule_enabled: data.schedule_enabled,
      run_repository_scripts: data.run_repository_scripts,
      run_prune_after: data.run_prune_after,
      run_compact_after: data.run_compact_after,
      run_check_after: data.run_check_after,
    })
  }
  const selectedRepositoryFilterId = useMemo(
    () => parseRepositoryFilterId(searchParams.get('repositoryId')),
    [searchParams]
  )

  const { data: plansData, isLoading: loadingPlans } = useQuery({
    queryKey: ['backup-plans', selectedRepositoryFilterId],
    queryFn: () => backupPlansAPI.list(selectedRepositoryFilterId),
  })
  const backupPlans: BackupPlan[] = useMemo(() => plansData?.data?.backup_plans || [], [plansData])

  const { data: runsData } = useQuery({
    queryKey: ['backup-plan-runs'],
    queryFn: () => backupPlansAPI.listRuns(),
    refetchInterval: 2000,
  })
  const backupPlanRuns: BackupPlanRun[] = useMemo(() => runsData?.data?.runs || [], [runsData])
  const latestRunByPlan = useMemo(() => {
    const latest = new Map<number, BackupPlanRun>()
    backupPlanRuns.forEach((run) => {
      if (run.backup_plan_id && !latest.has(run.backup_plan_id)) {
        latest.set(run.backup_plan_id, run)
      }
    })
    return latest
  }, [backupPlanRuns])

  const processedPlans = useMemo(
    () =>
      processBackupPlans({
        backupPlans,
        repositoryFilterId: selectedRepositoryFilterId,
        searchQuery,
        sortBy,
        groupBy,
        t,
      }),
    [backupPlans, selectedRepositoryFilterId, searchQuery, sortBy, groupBy, t]
  )
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = useMemo(
    () => repositoriesData?.data?.repositories || [],
    [repositoriesData]
  )
  const selectedRepositoryFilter = useMemo(() => {
    if (selectedRepositoryFilterId === null) return null
    const repository = repositories.find((repo) => repo.id === selectedRepositoryFilterId)
    return {
      id: selectedRepositoryFilterId,
      name:
        repository?.name ||
        t('backupPlans.filters.repositoryFallback', { id: selectedRepositoryFilterId }),
    }
  }, [repositories, selectedRepositoryFilterId, t])
  const { data: sshConnectionsData } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
  })
  const sshConnections: SSHConnection[] = useMemo(() => {
    const connections = sshConnectionsData?.data?.connections
    return Array.isArray(connections) ? connections : []
  }, [sshConnectionsData])
  const { data: agentMachinesData } = useQuery({
    queryKey: ['managed-agents'],
    queryFn: managedAgentsAPI.listAgents,
    enabled: canUseManagedAgents,
  })
  const agentMachines: AgentMachineResponse[] = useMemo(
    () => agentMachinesData?.data || [],
    [agentMachinesData]
  )
  const { data: scriptsData, isLoading: loadingScripts } = useQuery({
    queryKey: ['scripts'],
    queryFn: () => scriptsAPI.list(),
  })
  const scripts: ScriptOption[] = useMemo(() => {
    const data = scriptsData?.data
    return Array.isArray(data) ? data : []
  }, [scriptsData])

  const fullRepositories = useMemo(
    () => repositories.filter((repo) => repo.mode !== 'observe'),
    [repositories]
  )
  const selectedSourceConnection = useMemo(
    () =>
      wizardState.sourceSshConnectionId
        ? sshConnections.find(
            (connection) => connection.id === wizardState.sourceSshConnectionId
          ) || null
        : null,
    [sshConnections, wizardState.sourceSshConnectionId]
  )
  const sourceExplorerSshConfig = useMemo(
    () =>
      selectedSourceConnection
        ? {
            ssh_key_id: selectedSourceConnection.ssh_key_id,
            host: selectedSourceConnection.host,
            username: selectedSourceConnection.username,
            port: selectedSourceConnection.port,
          }
        : undefined,
    [selectedSourceConnection]
  )
  const wizardSteps = useMemo(
    () =>
      stepDefinitions.map((step) => ({
        key: step.key,
        label: t(step.labelKey),
        icon: step.icon,
      })),
    [t]
  )

  useEffect(() => {
    const state = location.state as { highlightPlanId?: number } | null
    if (!state?.highlightPlanId) return
    setHighlightedPlanId(state.highlightPlanId)
    navigate(location.pathname, { replace: true, state: null })
  }, [location.pathname, location.state, navigate])

  useEffect(() => {
    const state = location.state as { createPlanForRepositoryId?: number } | null
    const repositoryId = state?.createPlanForRepositoryId
    if (!repositoryId || handledInitialRepositoryRef.current || loadingRepositories) return

    const repository = fullRepositories.find((repo) => repo.id === repositoryId)
    const nextState = createInitialState()
    nextState.repositoryIds = [repositoryId]
    if (repository) {
      nextState.name = `${repository.name} Backup Plan`
      nextState.compression = repository.compression || nextState.compression
    }

    setEditingPlan(null)
    setWizardState(nextState)
    setBasicRepositoryState(createInitialBasicRepositoryState())
    setBasicRepositoryOpen(false)
    setShowSourceExplorer(false)
    setShowExcludeExplorer(false)
    setShowBasicRepositoryPathExplorer(false)
    setActiveStep(0)
    setWizardOpen(true)
    handledInitialRepositoryRef.current = true
    navigate(location.pathname, { replace: true, state: null })
  }, [fullRepositories, loadingRepositories, location.pathname, location.state, navigate])

  useEffect(() => {
    localStorage.setItem('backup_plans_sort', sortBy)
  }, [sortBy])

  useEffect(() => {
    localStorage.setItem('backup_plans_group', groupBy)
  }, [groupBy])

  useEffect(() => {
    if (!highlightedPlanId) return
    const frame = requestAnimationFrame(() => {
      document
        .getElementById(`backup-plan-${highlightedPlanId}`)
        ?.scrollIntoView({ block: 'center', behavior: 'smooth' })
    })
    return () => cancelAnimationFrame(frame)
  }, [highlightedPlanId, backupPlans.length])

  const createMutation = useMutation({
    mutationFn: (data: BackupPlanData) => backupPlansAPI.create(data),
    onSuccess: (_response, data) => {
      toast.success(t('backupPlans.toasts.created'))
      trackBackupPlanSubmit(EventAction.CREATE, data)
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      setWizardOpen(false)
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.createFailed')))
    },
  })

  const createScriptMutation = useMutation({
    mutationFn: (data: {
      name: string
      description: string
      content: string
      timeout: number
      run_on: string
      category: string
    }) => scriptsAPI.create(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scripts'] })
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.scriptCreateFailed')))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: BackupPlanData }) =>
      backupPlansAPI.update(id, data),
    onSuccess: (_response, { data }) => {
      toast.success(t('backupPlans.toasts.updated'))
      trackBackupPlanSubmit(EventAction.EDIT, data)
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      setWizardOpen(false)
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.updateFailed')))
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => backupPlansAPI.delete(id),
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.deleted'))
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.deleteFailed')))
    },
  })

  const runMutation = useMutation({
    mutationFn: (id: number) => backupPlansAPI.run(id),
    onMutate: (id) => {
      setStartingPlanId(id)
    },
    onSuccess: (_response, planId) => {
      toast.success(t('backupPlans.toasts.started'))
      if (historyPlanId === planId) setHistoryPlanId(null)
      queryClient.invalidateQueries({ queryKey: ['backup-plan-runs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.startFailed')))
    },
    onSettled: () => {
      setStartingPlanId(null)
    },
  })

  const cancelRunMutation = useMutation({
    mutationFn: (id: number) => backupPlansAPI.cancelRun(id),
    onMutate: (id) => {
      setCancellingRunId(id)
    },
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.cancelled'))
      queryClient.invalidateQueries({ queryKey: ['backup-plan-runs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.cancelFailed')))
    },
    onSettled: () => {
      setCancellingRunId(null)
    },
  })

  const toggleMutation = useMutation({
    mutationFn: (id: number) => backupPlansAPI.toggle(id),
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.toggled'))
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.toggleFailed')))
    },
  })

  const repositoryCreateMutation = useMutation({
    mutationFn: (data: RepositoryData) => BorgApiClient.createRepository(data),
    onSuccess: (response) => {
      toast.success(t('backupPlans.toasts.repositoryCreated'))
      const repositoryId = getCreatedRepositoryId(response)
      if (repositoryId) {
        setWizardState((prev) => {
          const nextIds = prev.repositoryIds.includes(repositoryId)
            ? prev.repositoryIds
            : [...prev.repositoryIds, repositoryId]
          const nextSelection = applyRepositorySelectionLimit(nextIds, canUseMultiRepository)
          if (nextSelection.limited) {
            toast.error(t('backupPlans.toasts.multiRepositoryRequiresPro'))
          }

          return {
            ...prev,
            repositoryIds: nextSelection.ids,
          }
        })
      }
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      queryClient.invalidateQueries({ queryKey: ['app-repositories'] })
      setRepositoryWizardOpen(false)
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.repositoryCreateFailed')))
    },
  })

  // useCallback deps list every setter used so React Compiler-aware lint is
  // satisfied. State setters are reference-stable, so listing them does not
  // cause the callback to be recreated; it just lets the linter verify deps.
  const openCreateWizard = useCallback(() => {
    setEditingPlan(null)
    setWizardState(createInitialState())
    setBasicRepositoryState(createInitialBasicRepositoryState())
    setBasicRepositoryOpen(false)
    setShowSourceExplorer(false)
    setShowExcludeExplorer(false)
    setShowBasicRepositoryPathExplorer(false)
    setLegacySourceReviewOpen(false)
    setActiveStep(0)
    setWizardOpen(true)
  }, [
    setEditingPlan,
    setWizardState,
    setBasicRepositoryState,
    setBasicRepositoryOpen,
    setShowSourceExplorer,
    setShowExcludeExplorer,
    setShowBasicRepositoryPathExplorer,
    setLegacySourceReviewOpen,
    setActiveStep,
    setWizardOpen,
  ])

  const clearRepositoryFilter = useCallback(() => {
    const nextParams = new URLSearchParams(searchParams)
    nextParams.delete('repositoryId')
    setSearchParams(nextParams, { replace: true })
  }, [searchParams, setSearchParams])

  const openEditWizard = useCallback(
    async (plan: BackupPlan) => {
      const response = await backupPlansAPI.get(plan.id)
      const detailedPlan = response.data as BackupPlan
      setEditingPlan(detailedPlan)
      setWizardState(planToState(detailedPlan))
      setBasicRepositoryState(createInitialBasicRepositoryState())
      setBasicRepositoryOpen(false)
      setLegacySourceReviewOpen(false)
      setActiveStep(0)
      setWizardOpen(true)
    },
    [
      setEditingPlan,
      setWizardState,
      setBasicRepositoryState,
      setBasicRepositoryOpen,
      setLegacySourceReviewOpen,
      setActiveStep,
      setWizardOpen,
    ]
  )

  const updateState = (updates: Partial<WizardState>) => {
    setWizardState((prev) => ({ ...prev, ...updates }))
  }

  const updateBasicRepositoryState = (updates: Partial<BasicRepositoryState>) => {
    setBasicRepositoryState((prev) => ({ ...prev, ...updates }))
  }

  const appendUniquePaths = (existing: string[], selected: string[]) => {
    const seen = new Set(existing)
    return [
      ...existing,
      ...selected.filter((path) => {
        if (seen.has(path)) return false
        seen.add(path)
        return true
      }),
    ]
  }

  const requireRemoteSourceConnection = () => {
    if (wizardState.sourceType !== 'remote' || selectedSourceConnection) return true
    toast.error(t('backupPlans.toasts.selectSourceConnection'))
    return false
  }

  const openSourceExplorer = () => {
    if (!requireRemoteSourceConnection()) return
    setShowSourceExplorer(true)
  }

  const openExcludeExplorer = () => {
    if (!requireRemoteSourceConnection()) return
    setShowExcludeExplorer(true)
  }

  const createBasicRepository = async () => {
    await repositoryCreateMutation.mutateAsync({
      name: basicRepositoryState.name.trim(),
      borg_version: basicRepositoryState.borgVersion,
      path: basicRepositoryState.path.trim(),
      encryption: basicRepositoryState.encryption,
      passphrase:
        basicRepositoryState.encryption === 'none' ? undefined : basicRepositoryState.passphrase,
      compression: 'lz4',
      source_directories: [],
      exclude_patterns: [],
      custom_flags: null,
      mode: 'full',
    })
    setBasicRepositoryState(createInitialBasicRepositoryState())
    setBasicRepositoryOpen(false)
  }

  const handleRepositoryIdsChange = (ids: number[]) => {
    const nextSelection = applyRepositorySelectionLimit(ids, canUseMultiRepository)
    if (nextSelection.limited) {
      toast.error(t('backupPlans.toasts.multiRepositoryRequiresPro'))
    }

    setWizardState((prev) => ({
      ...prev,
      repositoryIds: nextSelection.ids,
    }))
  }

  const handlePruneSettingsChange = (values: PruneSettings) => {
    updateState({
      pruneKeepHourly: values.keepHourly,
      pruneKeepDaily: values.keepDaily,
      pruneKeepWeekly: values.keepWeekly,
      pruneKeepMonthly: values.keepMonthly,
      pruneKeepQuarterly: values.keepQuarterly,
      pruneKeepYearly: values.keepYearly,
    })
  }

  const canProceed = () => {
    const stepKey = stepDefinitions[activeStep]?.key
    if (stepKey === 'source') {
      const sourceLocations = wizardState.sourceLocations || []
      const sourceTypes = new Set(sourceLocations.map((location) => location.source_type))
      return Boolean(
        wizardState.name.trim() &&
        wizardState.sourceDirectories.length > 0 &&
        (wizardState.sourceType !== 'remote' || wizardState.sourceSshConnectionId) &&
        (canUseManagedAgents ||
          !sourceLocations.some((location) => location.source_type === 'agent')) &&
        (canUseMixedSourceTypes || sourceTypes.size <= 1)
      )
    }
    if (stepKey === 'repositories') {
      return (
        wizardState.repositoryIds.length > 0 &&
        !isRepositorySelectionOverLimit(wizardState.repositoryIds, canUseMultiRepository)
      )
    }
    if (stepKey === 'settings') {
      if (wizardState.repositoryRunMode === 'parallel' && !canUseMultiRepository) return false
      return true
    }
    if (stepKey === 'schedule') {
      if (
        wizardState.runCheckAfter &&
        getCheckFlagDurationConflict(wizardState.checkExtraFlags, wizardState.checkMaxDuration)
          .length > 0
      ) {
        return false
      }
      return Boolean(!wizardState.scheduleEnabled || wizardState.cronExpression.trim())
    }
    return true
  }

  const savePlan = (clearLegacySourceRepositoryIds: number[]) => {
    const payload = buildBackupPlanPayload(wizardState, clearLegacySourceRepositoryIds)
    if (editingPlan) {
      updateMutation.mutate({ id: editingPlan.id, data: payload })
    } else {
      createMutation.mutate(payload)
    }
  }

  const createSourceScript = async (data: {
    name: string
    description: string
    content: string
    timeout: number
    run_on: string
    category: string
  }) => {
    const response = await createScriptMutation.mutateAsync(data)
    const id = response.data?.id
    if (typeof id !== 'number') {
      throw new Error('Script creation response did not include an id')
    }
    return { id }
  }

  const submitPlan = () => {
    if (isRepositorySelectionOverLimit(wizardState.repositoryIds, canUseMultiRepository)) {
      toast.error(t('backupPlans.toasts.multiRepositoryRequiresPro'))
      return
    }
    const sourceLocations = wizardState.sourceLocations || []
    if (
      !canUseManagedAgents &&
      sourceLocations.some((location) => location.source_type === 'agent')
    ) {
      toast.error(t('backupPlans.sourceChooser.managedAgentRequiresPro'))
      return
    }
    if (
      !canUseMixedSourceTypes &&
      new Set(sourceLocations.map((location) => location.source_type)).size > 1
    ) {
      toast.error(t('backupPlans.sourceChooser.mixedSourceTypesRequiresPro'))
      return
    }
    const selectedRepositories = wizardState.repositoryIds
      .map((repositoryId) => fullRepositories.find((repository) => repository.id === repositoryId))
      .filter((repository): repository is Repository => Boolean(repository))
    const unsupportedRoute = buildRoutePreviews(
      selectedRepositories,
      wizardState,
      agentMachines
    ).find((route) => !route.supported)
    if (unsupportedRoute?.messageKey) {
      toast.error(t(unsupportedRoute.messageKey, unsupportedRoute.messageParams))
      return
    }

    const legacyReviews = getLegacySourceRepositoryReviews(
      fullRepositories,
      wizardState.repositoryIds,
      wizardState.sourceDirectories
    )
    if (legacyReviews.length > 0) {
      setLegacySourceReviews(legacyReviews)
      setLegacySourceReviewOpen(true)
      return
    }

    savePlan([])
  }

  const renderWizardStep = () => (
    <BackupPlanWizardStep
      activeStep={activeStep}
      stepDefinitions={stepDefinitions}
      wizardState={wizardState}
      basicRepositoryState={basicRepositoryState}
      basicRepositoryOpen={basicRepositoryOpen}
      fullRepositories={fullRepositories}
      repositories={repositories}
      agentMachines={agentMachines}
      sshConnections={sshConnections}
      selectedSourceConnection={selectedSourceConnection}
      scripts={scripts}
      loadingRepositories={loadingRepositories}
      loadingScripts={loadingScripts}
      canUseMultiRepository={canUseMultiRepository}
      canUseBorg2={canUseBorg2}
      canUseManagedAgents={canUseManagedAgents}
      canUseMixedSourceTypes={canUseMixedSourceTypes}
      repositoryCreatePending={repositoryCreateMutation.isPending}
      updateState={updateState}
      onCreateScript={createSourceScript}
      updateBasicRepositoryState={updateBasicRepositoryState}
      handleRepositoryIdsChange={handleRepositoryIdsChange}
      handlePruneSettingsChange={handlePruneSettingsChange}
      createBasicRepository={createBasicRepository}
      openSourceExplorer={openSourceExplorer}
      openExcludeExplorer={openExcludeExplorer}
      setBasicRepositoryOpen={setBasicRepositoryOpen}
      setRepositoryWizardOpen={setRepositoryWizardOpen}
      setShowBasicRepositoryPathExplorer={setShowBasicRepositoryPathExplorer}
      t={t}
    />
  )

  const isSubmitting =
    createMutation.isPending || updateMutation.isPending || createScriptMutation.isPending

  // React Query mutation OBJECTS are new references on every render; only
  // `.mutate` is reference-stable across renders (documented as such in v5).
  // Depending on the whole mutation object made these useCallbacks recreate
  // each render, defeating React.memo on BackupPlansContent. Dep on `.mutate`
  // directly so the callbacks are actually stable.
  const runMutate = runMutation.mutate
  const cancelRunMutate = cancelRunMutation.mutate
  const toggleMutate = toggleMutation.mutate
  const deleteMutate = deleteMutation.mutate
  const handleRunPlan = useCallback((planId: number) => runMutate(planId), [runMutate])
  const handleCancelRun = useCallback((runId: number) => cancelRunMutate(runId), [cancelRunMutate])
  const handleTogglePlan = useCallback((planId: number) => toggleMutate(planId), [toggleMutate])
  const handleDeletePlan = useCallback((planId: number) => deleteMutate(planId), [deleteMutate])
  const handleViewRepositories = useCallback(
    (planId: number) => navigate(`/repositories?backupPlanId=${planId}`),
    [navigate]
  )
  const formatStatusLabel = useCallback(
    (status?: string) =>
      status
        ? t(`backupPlans.statuses.${status}`, { defaultValue: formatRunStatus(status) })
        : t('backupPlans.statuses.unknown'),
    [t]
  )

  return (
    <Box>
      <BackupPlansContent
        loadingPlans={loadingPlans}
        backupPlans={backupPlans}
        processedPlans={processedPlans}
        latestRunByPlan={latestRunByPlan}
        backupPlanRuns={backupPlanRuns}
        searchQuery={searchQuery}
        setSearchQuery={setSearchQuery}
        sortBy={sortBy}
        setSortBy={setSortBy}
        groupBy={groupBy}
        setGroupBy={setGroupBy}
        repositoryFilter={selectedRepositoryFilter}
        onClearRepositoryFilter={clearRepositoryFilter}
        startingPlanId={startingPlanId}
        highlightedPlanId={highlightedPlanId}
        canUseMultiRepository={canUseMultiRepository}
        cancellingRunId={cancellingRunId}
        runPending={runMutation.isPending}
        togglePending={toggleMutation.isPending}
        toggleVariables={toggleMutation.variables}
        openCreateWizard={openCreateWizard}
        onRunPlan={handleRunPlan}
        onCancelRun={handleCancelRun}
        onViewLogs={setLogJob}
        onTogglePlan={handleTogglePlan}
        onEditPlan={openEditWizard}
        onDeletePlan={handleDeletePlan}
        onViewHistory={setHistoryPlanId}
        onViewRepositories={handleViewRepositories}
        formatStatusLabel={formatStatusLabel}
        t={t}
      />

      <WizardDialog
        open={wizardOpen}
        onClose={() => {
          setLegacySourceReviewOpen(false)
          setWizardOpen(false)
        }}
        title={
          editingPlan ? t('backupPlans.wizard.editTitle') : t('backupPlans.wizard.createTitle')
        }
        steps={wizardSteps}
        currentStep={activeStep}
        onStepClick={setActiveStep}
        stepContentSx={{ minHeight: { xs: 'auto', md: 520 } }}
        footer={
          <DialogActions>
            <Button onClick={() => setWizardOpen(false)} disabled={isSubmitting}>
              {t('common.buttons.cancel')}
            </Button>
            <Button
              onClick={() => setActiveStep((prev) => Math.max(0, prev - 1))}
              disabled={activeStep === 0 || isSubmitting}
            >
              {t('common.buttons.back')}
            </Button>
            {activeStep < stepDefinitions.length - 1 ? (
              <Button
                variant="contained"
                onClick={() => setActiveStep((prev) => prev + 1)}
                disabled={!canProceed()}
              >
                {t('common.buttons.next')}
              </Button>
            ) : (
              <Button variant="contained" onClick={submitPlan} disabled={isSubmitting}>
                {editingPlan
                  ? t('backupPlans.wizard.updatePlan')
                  : t('backupPlans.wizard.createPlan')}
              </Button>
            )}
          </DialogActions>
        }
      >
        {renderWizardStep()}
      </WizardDialog>

      <LegacySourceSettingsReviewDialog
        open={legacySourceReviewOpen}
        reviews={legacySourceReviews}
        saving={isSubmitting}
        onCancel={() => setLegacySourceReviewOpen(false)}
        onSaveWithoutClearing={() => {
          setLegacySourceReviewOpen(false)
          savePlan([])
        }}
        onSaveAndClear={(repositoryIds) => {
          setLegacySourceReviewOpen(false)
          savePlan(repositoryIds)
        }}
        t={t}
      />

      <RepositoryWizard
        open={repositoryWizardOpen}
        onClose={() => setRepositoryWizardOpen(false)}
        mode="create"
        canUseManagedAgents={canUseManagedAgents}
        canUseRclone={canUseRclone}
        onSubmit={async (data) => {
          await repositoryCreateMutation.mutateAsync(data)
        }}
      />

      <FileExplorerDialog
        key={`plan-source-explorer-${wizardState.sourceType}-${wizardState.sourceSshConnectionId || 'local'}`}
        open={showSourceExplorer}
        onClose={() => setShowSourceExplorer(false)}
        onSelect={(paths) => {
          updateState({
            sourceDirectories: appendUniquePaths(wizardState.sourceDirectories, paths),
          })
          setShowSourceExplorer(false)
        }}
        title={t('backupPlans.wizard.fileExplorer.sourceTitle')}
        initialPath={
          wizardState.sourceType === 'remote' ? selectedSourceConnection?.default_path || '/' : '/'
        }
        multiSelect
        connectionType={wizardState.sourceType === 'remote' ? 'ssh' : 'local'}
        sshConfig={wizardState.sourceType === 'remote' ? sourceExplorerSshConfig : undefined}
        selectMode="both"
        showSshMountPoints={false}
      />

      <FileExplorerDialog
        key={`plan-exclude-explorer-${wizardState.sourceType}-${wizardState.sourceSshConnectionId || 'local'}`}
        open={showExcludeExplorer}
        onClose={() => setShowExcludeExplorer(false)}
        onSelect={(paths) => {
          updateState({
            excludePatterns: appendUniquePaths(wizardState.excludePatterns, paths),
          })
          setShowExcludeExplorer(false)
        }}
        title={t('backupPlans.wizard.fileExplorer.excludeTitle')}
        initialPath={
          wizardState.sourceType === 'remote' ? selectedSourceConnection?.default_path || '/' : '/'
        }
        multiSelect
        connectionType={wizardState.sourceType === 'remote' ? 'ssh' : 'local'}
        sshConfig={wizardState.sourceType === 'remote' ? sourceExplorerSshConfig : undefined}
        selectMode="both"
        showSshMountPoints={false}
      />

      <FileExplorerDialog
        open={showBasicRepositoryPathExplorer}
        onClose={() => setShowBasicRepositoryPathExplorer(false)}
        onSelect={(paths) => {
          if (paths[0]) {
            updateBasicRepositoryState({ path: paths[0] })
          }
          setShowBasicRepositoryPathExplorer(false)
        }}
        title={t('backupPlans.wizard.fileExplorer.repositoryTitle')}
        initialPath="/"
        multiSelect={false}
        connectionType="local"
        selectMode="directories"
        showSshMountPoints={false}
      />

      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={() => setLogJob(null)} />

      <BackupPlanHistoryDialog
        plan={backupPlans.find((p) => p.id === historyPlanId) || null}
        runs={
          historyPlanId
            ? backupPlanRuns.filter(
                (r) => r.backup_plan_id === historyPlanId && !isActiveRun(r.status)
              )
            : []
        }
        cancellingRunId={cancellingRunId}
        onClose={() => setHistoryPlanId(null)}
        onViewLogs={(job) => setLogJob(job)}
        onCancel={(runId) => cancelRunMutation.mutate(runId)}
        t={t}
      />
    </Box>
  )
}
