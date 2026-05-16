import { useEffect, useMemo, useRef, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Box, Button, DialogActions, useTheme } from '@mui/material'
import { CalendarClock, Edit, ListChecks } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { isAxiosError } from 'axios'

import RepositoryWizard from '../components/RepositoryWizard'
import { type PruneSettings } from '../components/PruneSettingsInput'
import { WizardDialog } from '../components/wizard'
import LogViewerDialog from '../components/LogViewerDialog'
import FileExplorerDialog from '../components/FileExplorerDialog'
import { type BackupPlanRunLogJob } from '../components/BackupPlanRunsPanel'
import {
  backupPlansAPI,
  repositoriesAPI,
  type RepositoryData,
  scriptsAPI,
  sshKeysAPI,
} from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { usePlan } from '../hooks/usePlan'
import { translateBackendKey } from '../utils/translateBackendKey'
import { buildBackupPlanPayload } from '../utils/backupPlanPayload'
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
import type { DatabaseDiscoverySelection } from './backup-plans/sourceDiscovery'

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

function errorMessage(error: unknown, fallback: string): string {
  const detail = isAxiosError(error) ? error.response?.data?.detail : undefined
  return translateBackendKey(detail) || fallback
}

export default function BackupPlans() {
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const { can } = usePlan()
  const canUseMultiRepository = can('backup_plan_multi_repository')
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

  const { data: plansData, isLoading: loadingPlans } = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
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

  const processedPlans = useMemo(() => {
    let filtered = backupPlans

    if (searchQuery.trim()) {
      const query = searchQuery.toLowerCase()
      filtered = filtered.filter(
        (plan) =>
          plan.name.toLowerCase().includes(query) ||
          (plan.description?.toLowerCase().includes(query) ?? false)
      )
    }

    const compareDateDesc = (a?: string | null, b?: string | null) => {
      if (!a && !b) return 0
      if (!a) return 1
      if (!b) return -1
      return new Date(b).getTime() - new Date(a).getTime()
    }
    const compareDateAsc = (a?: string | null, b?: string | null) => -compareDateDesc(a, b)

    const sorted = [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name)
        case 'name-desc':
          return b.name.localeCompare(a.name)
        case 'last-run-recent':
          return compareDateDesc(a.last_run, b.last_run)
        case 'last-run-oldest':
          return compareDateAsc(a.last_run, b.last_run)
        case 'next-run-soonest':
          return compareDateAsc(a.next_run, b.next_run)
        case 'created-newest':
          return compareDateDesc(a.created_at, b.created_at)
        case 'created-oldest':
          return compareDateAsc(a.created_at, b.created_at)
        default:
          return 0
      }
    })

    if (groupBy === 'none') {
      return { groups: [{ name: null as string | null, plans: sorted }] }
    }

    const groups: { name: string; plans: BackupPlan[] }[] = []

    if (groupBy === 'status') {
      const enabled = sorted.filter((p) => p.enabled)
      const disabled = sorted.filter((p) => !p.enabled)
      if (enabled.length > 0) groups.push({ name: t('backupPlans.groups.enabled'), plans: enabled })
      if (disabled.length > 0)
        groups.push({ name: t('backupPlans.groups.disabled'), plans: disabled })
    } else if (groupBy === 'schedule') {
      const scheduled = sorted.filter((p) => p.schedule_enabled)
      const manual = sorted.filter((p) => !p.schedule_enabled)
      if (scheduled.length > 0)
        groups.push({ name: t('backupPlans.groups.scheduled'), plans: scheduled })
      if (manual.length > 0) groups.push({ name: t('backupPlans.groups.manual'), plans: manual })
    } else if (groupBy === 'source') {
      const local = sorted.filter((p) => p.source_type === 'local')
      const remote = sorted.filter((p) => p.source_type === 'remote')
      if (local.length > 0) groups.push({ name: t('backupPlans.groups.localSource'), plans: local })
      if (remote.length > 0)
        groups.push({ name: t('backupPlans.groups.remoteSource'), plans: remote })
    }

    return { groups: groups.length > 0 ? groups : [{ name: null as string | null, plans: sorted }] }
  }, [backupPlans, searchQuery, sortBy, groupBy, t])
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories: Repository[] = useMemo(
    () => repositoriesData?.data?.repositories || [],
    [repositoriesData]
  )
  const { data: sshConnectionsData } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
  })
  const sshConnections: SSHConnection[] = useMemo(() => {
    const connections = sshConnectionsData?.data?.connections
    return Array.isArray(connections) ? connections : []
  }, [sshConnectionsData])
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
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.created'))
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      setWizardOpen(false)
    },
    onError: (error: unknown) => {
      toast.error(errorMessage(error, t('backupPlans.toasts.createFailed')))
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: BackupPlanData }) =>
      backupPlansAPI.update(id, data),
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.updated'))
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

  const openCreateWizard = () => {
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
  }

  const openEditWizard = async (plan: BackupPlan) => {
    const response = await backupPlansAPI.get(plan.id)
    const detailedPlan = response.data as BackupPlan
    setEditingPlan(detailedPlan)
    setWizardState(planToState(detailedPlan))
    setBasicRepositoryState(createInitialBasicRepositoryState())
    setBasicRepositoryOpen(false)
    setLegacySourceReviewOpen(false)
    setActiveStep(0)
    setWizardOpen(true)
  }

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

  const createDiscoveryScript = async (
    selection: DatabaseDiscoverySelection,
    hook: 'pre' | 'post',
    uniqueSuffix: number
  ) => {
    const script = hook === 'pre' ? selection.preBackupScript : selection.postBackupScript
    const planName = wizardState.name.trim() || t('backupPlans.wizard.createTitle')
    const hookLabel =
      hook === 'pre'
        ? t('backupPlans.wizard.sourceDiscovery.scriptName.pre', {
            defaultValue: 'pre-backup',
          })
        : t('backupPlans.wizard.sourceDiscovery.scriptName.post', {
            defaultValue: 'post-backup',
          })
    const response = await scriptsAPI.create({
      name: `${planName} - ${selection.database.engine_label} ${hookLabel} ${uniqueSuffix}`,
      description: script.description,
      content: script.content,
      timeout: script.timeout,
      run_on: script.run_on,
      category: 'custom',
    })

    return Number(response.data.id)
  }

  const applyDatabaseDiscovery = async (selection: DatabaseDiscoverySelection) => {
    const uniqueSuffix = Date.now()
    const preBackupScriptId = await createDiscoveryScript(selection, 'pre', uniqueSuffix)
    const postBackupScriptId = await createDiscoveryScript(selection, 'post', uniqueSuffix)

    setWizardState((prev) => ({
      ...prev,
      sourceType: 'local',
      sourceSshConnectionId: '',
      sourceDirectories: appendUniquePaths(prev.sourceDirectories, selection.sourceDirectories),
      preBackupScriptId,
      postBackupScriptId,
      preBackupScriptParameters: {},
      postBackupScriptParameters: {},
    }))
    await queryClient.invalidateQueries({ queryKey: ['scripts'] })
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
      return Boolean(
        wizardState.name.trim() &&
        wizardState.sourceDirectories.length > 0 &&
        (wizardState.sourceType === 'local' || wizardState.sourceSshConnectionId)
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

  const submitPlan = () => {
    if (isRepositorySelectionOverLimit(wizardState.repositoryIds, canUseMultiRepository)) {
      toast.error(t('backupPlans.toasts.multiRepositoryRequiresPro'))
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
      sshConnections={sshConnections}
      selectedSourceConnection={selectedSourceConnection}
      scripts={scripts}
      loadingRepositories={loadingRepositories}
      loadingScripts={loadingScripts}
      canUseMultiRepository={canUseMultiRepository}
      canUseBorg2={canUseBorg2}
      repositoryCreatePending={repositoryCreateMutation.isPending}
      updateState={updateState}
      updateBasicRepositoryState={updateBasicRepositoryState}
      handleRepositoryIdsChange={handleRepositoryIdsChange}
      handlePruneSettingsChange={handlePruneSettingsChange}
      createBasicRepository={createBasicRepository}
      openSourceExplorer={openSourceExplorer}
      openExcludeExplorer={openExcludeExplorer}
      onApplyDatabaseDiscovery={applyDatabaseDiscovery}
      setBasicRepositoryOpen={setBasicRepositoryOpen}
      setRepositoryWizardOpen={setRepositoryWizardOpen}
      setShowBasicRepositoryPathExplorer={setShowBasicRepositoryPathExplorer}
      t={t}
    />
  )

  const isSubmitting = createMutation.isPending || updateMutation.isPending
  const formatStatusLabel = (status?: string) =>
    status
      ? t(`backupPlans.statuses.${status}`, { defaultValue: formatRunStatus(status) })
      : t('backupPlans.statuses.unknown')

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
        isDark={isDark}
        startingPlanId={startingPlanId}
        highlightedPlanId={highlightedPlanId}
        canUseMultiRepository={canUseMultiRepository}
        cancellingRunId={cancellingRunId}
        runPending={runMutation.isPending}
        togglePending={toggleMutation.isPending}
        toggleVariables={toggleMutation.variables}
        openCreateWizard={openCreateWizard}
        onRunPlan={(planId) => runMutation.mutate(planId)}
        onCancelRun={(runId) => cancelRunMutation.mutate(runId)}
        onViewLogs={(job) => setLogJob(job)}
        onTogglePlan={(planId) => toggleMutation.mutate(planId)}
        onEditPlan={openEditWizard}
        onDeletePlan={(planId) => deleteMutation.mutate(planId)}
        onViewHistory={(planId) => setHistoryPlanId(planId)}
        onViewRepositories={(planId) => navigate(`/repositories?backupPlanId=${planId}`)}
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
