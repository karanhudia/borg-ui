import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  IconButton,
  MenuItem,
  Stack,
  Tab,
  Tabs,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { Clock, Info, Play } from 'lucide-react'
import { backupAPI, backupPlansAPI, repositoriesAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import { BackupJob, Repository } from '../types'
import type { BackupPlan, BackupPlanRun } from '../types'
import BackupJobsTable from '../components/BackupJobsTable'
import RepoSelect from '../components/RepoSelect'
import LogViewerDialog from '../components/LogViewerDialog'
import CommandPreview from '../components/CommandPreview'
import RunningBackupsSection from '../components/RunningBackupsSection'
import BackupPlanRunsPanel, { type BackupPlanRunLogJob } from '../components/BackupPlanRunsPanel'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { usePermissions } from '../hooks/usePermissions'
import { getRepoCapabilities } from '../utils/repoCapabilities'
import { useTrackedJobOutcomes } from '../hooks/useTrackedJobOutcomes'
import { getJobDurationSeconds } from '../utils/analyticsProperties'

type BackupTab = 'plans' | 'legacy'

// Emerald green — matches the "Backup Now" button in RepositoryCard for visual continuity
const Backup: React.FC = () => {
  const [activeTab, setActiveTab] = useState<BackupTab>('plans')
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [selectedBackupPlanId, setSelectedBackupPlanId] = useState<number | ''>('')
  const [logJob, setLogJob] = useState<BackupPlanRunLogJob | null>(null)
  const queryClient = useQueryClient()
  const location = useLocation()
  const navigate = useNavigate()
  const { trackBackup, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageRepositoryOperations = hasGlobalPermission('repositories.manage_all')
  const permissions = usePermissions()
  const { t } = useTranslation()

  // Handle incoming navigation state (from "Backup Now" button)
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (location.state && (location.state as any).repositoryPath) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      setSelectedRepository((location.state as any).repositoryPath)
      setActiveTab('legacy')
      // Reset scroll position to top
      window.scrollTo(0, 0)
    }
  }, [location.state])

  // Get backup status and history (manual backups only) for the selected repository
  const { data: backupStatusResponse, isLoading: loadingStatus } = useQuery({
    queryKey: ['backup-status-manual', selectedRepository],
    queryFn: () => backupAPI.getManualJobs(selectedRepository),
    enabled: Boolean(selectedRepository),
    refetchInterval: 1000, // Poll every 1 second for real-time updates
  })
  const backupStatus = backupStatusResponse?.data?.jobs

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const { data: backupPlansData, isLoading: loadingBackupPlans } = useQuery({
    queryKey: ['backup-plans'],
    queryFn: () => backupPlansAPI.list(),
  })
  const { data: backupPlanRunsData, isLoading: loadingBackupPlanRuns } = useQuery({
    queryKey: ['backup-plan-runs'],
    queryFn: () => backupPlansAPI.listRuns(),
    refetchInterval: 2000,
  })

  const backupPlans = useMemo<BackupPlan[]>(
    () => backupPlansData?.data?.backup_plans ?? [],
    [backupPlansData?.data?.backup_plans]
  )
  const backupPlanRuns = useMemo<BackupPlanRun[]>(
    () => backupPlanRunsData?.data?.runs ?? [],
    [backupPlanRunsData?.data?.runs]
  )
  const runnableBackupPlans = useMemo(
    () => backupPlans.filter((plan) => plan.enabled),
    [backupPlans]
  )
  const selectedBackupPlan = useMemo(
    () => runnableBackupPlans.find((plan) => plan.id === selectedBackupPlanId) || null,
    [runnableBackupPlans, selectedBackupPlanId]
  )

  useEffect(() => {
    if (runnableBackupPlans.length === 0) {
      if (selectedBackupPlanId !== '') setSelectedBackupPlanId('')
      return
    }

    if (
      !selectedBackupPlanId ||
      !runnableBackupPlans.some((plan) => plan.id === selectedBackupPlanId)
    ) {
      setSelectedBackupPlanId(runnableBackupPlans[0].id)
    }
  }, [runnableBackupPlans, selectedBackupPlanId])

  // Get selected repository details
  const selectedRepoData = useMemo(() => {
    if (!selectedRepository || !repositoriesData?.data?.repositories) return null
    return repositoriesData.data.repositories.find(
      (repo: Repository) => repo.path === selectedRepository
    )
  }, [selectedRepository, repositoriesData])

  const canStartBackup = selectedRepoData ? permissions.canDo(selectedRepoData.id, 'backup') : false

  const runBackupPlanMutation = useMutation({
    mutationFn: (planId: number) => backupPlansAPI.run(planId),
    onSuccess: (_response, planId) => {
      toast.success(t('backup.planRun.toasts.started'))
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      queryClient.invalidateQueries({ queryKey: ['backup-plan-runs'] })
      trackBackup(EventAction.START, 'backup_plan', selectedBackupPlan || undefined, {
        trigger: 'manual',
        backup_plan_id: planId,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backup.planRun.toasts.startFailed')
      )
    },
  })

  const cancelBackupPlanRunMutation = useMutation({
    mutationFn: (runId: number) => backupPlansAPI.cancelRun(runId),
    onSuccess: () => {
      toast.success(t('backupPlans.toasts.cancelled'))
      queryClient.invalidateQueries({ queryKey: ['backup-plan-runs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-plans'] })
      trackBackup(EventAction.STOP, 'backup_plan')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backupPlans.toasts.cancelFailed')
      )
    },
  })

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: () => {
      if (!selectedRepoData) {
        throw new Error('Repository not selected')
      }
      return new BorgApiClient(selectedRepoData).runBackup()
    },
    onSuccess: () => {
      toast.success(t('backup.toasts.started'))
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      trackBackup(EventAction.START, undefined, selectedRepoData || undefined)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backup.toasts.startFailed')
      )
    },
  })

  // Cancel backup mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success(t('backup.toasts.cancelled'))
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      trackBackup(EventAction.STOP, 'manual')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backup.toasts.cancelFailed')
      )
    },
  })

  // Log viewer handlers
  const handleViewLogs = (job: BackupPlanRunLogJob) => {
    setLogJob(job)
  }

  const handleCloseLogs = () => {
    setLogJob(null)
  }

  // Handle repository selection
  const handleRepositoryChange = (repoPath: string) => {
    setSelectedRepository(repoPath)
    const repo = repositoriesData?.data?.repositories?.find((r: Repository) => r.path === repoPath)
    if (repo) {
      trackBackup(EventAction.FILTER, undefined, repo)
    }
  }

  // Handle start backup
  const handleStartBackup = () => {
    if (!selectedRepository) {
      toast.error(t('backup.toasts.selectRepository'))
      return
    }
    startBackupMutation.mutate()
  }

  const handleStartBackupPlan = () => {
    if (!selectedBackupPlanId) {
      toast.error(t('backup.planRun.toasts.selectPlan'))
      return
    }
    runBackupPlanMutation.mutate(selectedBackupPlanId)
  }

  const runningJobs = backupStatus?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = selectedRepository ? backupStatus || [] : []
  const legacyBackupRepositories = useMemo(
    () =>
      (repositoriesData?.data?.repositories ?? []).filter(
        (repo: Repository) =>
          getRepoCapabilities(repo).canBackup &&
          permissions.canDo(repo.id, 'backup') &&
          Array.isArray(repo.source_directories) &&
          repo.source_directories.length > 0
      ),
    [permissions, repositoriesData?.data?.repositories]
  )

  useEffect(() => {
    if (
      !loadingRepositories &&
      selectedRepository &&
      !legacyBackupRepositories.some((repo: Repository) => repo.path === selectedRepository)
    ) {
      setSelectedRepository('')
    }
  }, [legacyBackupRepositories, loadingRepositories, selectedRepository])

  useTrackedJobOutcomes<BackupJob>({
    jobs: recentJobs,
    onTerminal: (job) => {
      const repository = repositoriesData?.data?.repositories?.find(
        (repo: Repository) => repo.path === job.repository
      )
      const action =
        job.status === 'completed' || job.status === 'completed_with_warnings'
          ? EventAction.COMPLETE
          : EventAction.FAIL

      trackBackup(action, 'manual', repository ?? job.repository, {
        trigger: 'manual',
        job_id: job.id,
        status: job.status,
        has_logs: !!job.has_logs,
        maintenance_status: job.maintenance_status ?? null,
        duration_seconds: getJobDurationSeconds(job.started_at, job.completed_at),
        warning_count: job.status === 'completed_with_warnings' ? 1 : 0,
        error_present: !!job.error_message,
      })
    },
  })

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          mb: 4,
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'flex-start' },
          gap: 2,
        }}
      >
        <Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h4" fontWeight={600}>
              {t('backup.title')}
            </Typography>
            {repositoriesData?.data?.repositories?.some(
              (repo: Repository) => !getRepoCapabilities(repo).canBackup
            ) &&
              !loadingRepositories && (
                <Tooltip
                  title={t('backup.manualBackup.observeOnlyHidden')}
                  arrow
                  enterTouchDelay={0}
                  leaveTouchDelay={4000}
                >
                  <IconButton
                    size="small"
                    aria-label={t('backup.manualBackup.observeOnlyHidden')}
                    sx={{
                      color: 'text.disabled',
                      '&:hover': { color: 'text.secondary' },
                      p: 0,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <Info size={16} />
                  </IconButton>
                </Tooltip>
              )}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {t('backup.subtitle')}
          </Typography>
        </Box>
        <Stack direction="row" spacing={2} alignItems="center"></Stack>
      </Box>

      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs
          value={activeTab}
          aria-label={t('backup.tabs.ariaLabel')}
          onChange={(_, value: BackupTab) => setActiveTab(value)}
        >
          <Tab value="plans" label={t('backup.tabs.backupPlans')} />
          <Tab value="legacy" label={t('backup.tabs.legacyBackup')} />
        </Tabs>
      </Box>

      {activeTab === 'plans' && (
        <Stack spacing={4}>
          <Box>
            <Stack spacing={2.5}>
              <Box>
                <Typography variant="h6" fontWeight={600}>
                  {t('backup.planRun.title')}
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  {t('backup.planRun.description')}
                </Typography>
              </Box>

              {runnableBackupPlans.length === 0 && !loadingBackupPlans ? (
                <Alert
                  severity="info"
                  action={
                    <Button color="inherit" size="small" onClick={() => navigate('/backup-plans')}>
                      {t('backup.planRun.createAction')}
                    </Button>
                  }
                >
                  {t('backup.planRun.empty')}
                </Alert>
              ) : (
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
                  <TextField
                    select
                    fullWidth
                    label={t('backup.planRun.selectLabel')}
                    value={selectedBackupPlanId}
                    onChange={(event) => setSelectedBackupPlanId(Number(event.target.value))}
                    disabled={loadingBackupPlans || runnableBackupPlans.length === 0}
                    sx={{
                      minWidth: { xs: '100%', sm: 300 },
                      '& .MuiInputBase-root': {
                        minHeight: { xs: 52, sm: 58 },
                      },
                      '& .MuiSelect-select': {
                        display: 'flex',
                        alignItems: 'center',
                      },
                    }}
                  >
                    {runnableBackupPlans.map((plan) => (
                      <MenuItem key={plan.id} value={plan.id}>
                        {plan.name}
                      </MenuItem>
                    ))}
                  </TextField>
                  <Button
                    variant="contained"
                    color="success"
                    size="medium"
                    startIcon={
                      runBackupPlanMutation.isPending ? (
                        <CircularProgress size={16} color="inherit" />
                      ) : (
                        <Play size={18} />
                      )
                    }
                    onClick={handleStartBackupPlan}
                    disabled={
                      runBackupPlanMutation.isPending || loadingBackupPlans || !selectedBackupPlanId
                    }
                    sx={{
                      minWidth: { xs: '100%', sm: 180 },
                      fontWeight: 600,
                      flexShrink: 0,
                    }}
                  >
                    {runBackupPlanMutation.isPending
                      ? t('backup.planRun.starting')
                      : t('backup.planRun.run')}
                  </Button>
                </Stack>
              )}
            </Stack>
          </Box>

          <BackupPlanRunsPanel
            runs={
              selectedBackupPlanId
                ? backupPlanRuns.filter((run) => run.backup_plan_id === selectedBackupPlanId)
                : []
            }
            plans={selectedBackupPlan ? [selectedBackupPlan] : []}
            loading={loadingBackupPlanRuns}
            cancellingRunId={
              cancelBackupPlanRunMutation.isPending
                ? Number(cancelBackupPlanRunMutation.variables)
                : null
            }
            onCancel={(runId) => cancelBackupPlanRunMutation.mutate(runId)}
            onViewLogs={handleViewLogs}
          />
        </Stack>
      )}

      {activeTab === 'legacy' && (
        <Box>
          <Alert severity="info" sx={{ mb: 3 }}>
            {t('backup.legacyManual.notice')}
          </Alert>

          {/* Legacy Manual Backup Control */}
          <Box sx={{ mb: 4 }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
              <RepoSelect
                repositories={legacyBackupRepositories}
                value={selectedRepository}
                onChange={(v) => handleRepositoryChange(v as string)}
                loading={loadingRepositories}
                valueKey="path"
                label={t('backup.manualBackup.repository')}
                loadingLabel={t('backup.manualBackup.loadingRepositories')}
                placeholderLabel={t('backup.manualBackup.selectRepository')}
                maintenanceLabel={t('backup.manualBackup.maintenanceRunning')}
              />

              <Button
                variant="contained"
                color="success"
                size="medium"
                startIcon={
                  startBackupMutation.isPending ? (
                    <CircularProgress size={16} color="inherit" />
                  ) : (
                    <Play size={18} />
                  )
                }
                onClick={handleStartBackup}
                disabled={startBackupMutation.isPending || !selectedRepository || !canStartBackup}
                sx={{
                  minWidth: { xs: '100%', sm: 160 },
                  fontWeight: 600,
                  flexShrink: 0,
                }}
              >
                {startBackupMutation.isPending
                  ? t('backup.manualBackup.starting')
                  : t('backup.manualBackup.startBackup')}
              </Button>
            </Stack>

            {repositoriesData?.data?.repositories?.length === 0 && !loadingRepositories && (
              <Alert severity="warning" sx={{ mt: 2 }}>
                <Typography variant="body2" fontWeight={500} gutterBottom>
                  {t('backup.manualBackup.noRepositories.title')}
                </Typography>
                <Typography variant="body2">
                  {t('backup.manualBackup.noRepositories.subtitle')}
                </Typography>
              </Alert>
            )}

            {repositoriesData?.data?.repositories?.length > 0 &&
              legacyBackupRepositories.length === 0 &&
              !loadingRepositories && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  {t('backup.legacyManual.empty')}
                </Alert>
              )}
          </Box>

          {/* Command Preview Card */}
          {selectedRepoData && (
            <CommandPreview
              mode="import"
              displayMode="backup-only"
              borgVersion={selectedRepoData.borg_version}
              repositoryPath={selectedRepoData.path}
              archiveName="manual-backup-{now}"
              compression={selectedRepoData.compression}
              excludePatterns={selectedRepoData.exclude_patterns}
              sourceDirs={selectedRepoData.source_directories}
              customFlags={selectedRepoData.custom_flags ?? ''}
              remotePath={selectedRepoData.remote_path ?? ''}
              repositoryMode="full"
              dataSource="local"
            />
          )}

          {/* Running Jobs */}
          <RunningBackupsSection
            runningBackupJobs={runningJobs}
            onCancelBackup={(jobId) => cancelBackupMutation.mutate(String(jobId))}
            isCancelling={cancelBackupMutation.isPending}
            onViewLogs={handleViewLogs}
          />

          {/* Recent Jobs */}
          <Card>
            <CardContent>
              <Stack
                direction="row"
                spacing={1.5}
                alignItems="center"
                sx={{ mb: 1, color: 'text.secondary' }}
              >
                <Clock size={20} />
                <Typography variant="h6" fontWeight={600}>
                  {t('backup.recentJobs.title')}
                </Typography>
              </Stack>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
                {t('backup.recentJobs.subtitle')}
              </Typography>

              <BackupJobsTable
                jobs={recentJobs}
                repositories={repositoriesData?.data?.repositories || []}
                loading={loadingStatus}
                actions={{
                  viewLogs: true,
                  cancel: true,
                  breakLock: true,
                  downloadLogs: true,
                  errorInfo: true,
                  delete: true,
                }}
                canBreakLocks={canManageRepositoryOperations}
                canDeleteJobs={canManageRepositoryOperations}
                getRowKey={(job) => String(job.id)}
                headerBgColor="background.default"
                enableHover={true}
                tableId="backup"
                emptyState={{
                  icon: (
                    <Box sx={{ color: 'text.disabled' }}>
                      <Clock size={48} />
                    </Box>
                  ),
                  title: t('backup.recentJobs.empty'),
                }}
              />
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Log Viewer Dialog */}
      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={handleCloseLogs} />
    </Box>
  )
}

export default Backup
