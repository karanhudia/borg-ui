import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Box, Typography, Button, Alert, Tabs, Tab } from '@mui/material'
import { Plus } from 'lucide-react'
import { scheduleAPI, repositoriesAPI, backupAPI, scriptsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { usePermissions } from '../hooks/usePermissions'
import { translateBackendKey } from '../utils/translateBackendKey'
import ScheduledChecksSection, {
  ScheduledChecksSectionRef,
} from '../components/ScheduledChecksSection'
import ScheduleWizard, { ScheduleData } from '../components/ScheduleWizard'
import DeleteScheduleDialog from '../components/DeleteScheduleDialog'
import UpcomingJobsTable from '../components/UpcomingJobsTable'
import BackupHistorySection from '../components/BackupHistorySection'
import RunningBackupsSection from '../components/RunningBackupsSection'
import ScheduledJobsTable from '../components/ScheduledJobsTable'
import { Repository } from '../types'
import { useTrackedJobOutcomes } from '../hooks/useTrackedJobOutcomes'
import { getJobDurationSeconds } from '../utils/analyticsProperties'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  timezone?: string | null
  repository: string | null // Legacy single-repo
  repository_id: number | null // Single-repo by ID
  repository_ids: number[] | null // Multi-repo
  enabled: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
  updated_at: string | null
  description: string | null
  archive_name_template: string | null
  run_repository_scripts: boolean // Whether to run per-repository scripts
  pre_backup_script_id: number | null // Schedule-level pre-backup script
  post_backup_script_id: number | null // Schedule-level post-backup script
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  last_prune: string | null
  last_compact: string | null
}

interface BackupJob {
  id: string
  repository: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'completed_with_warnings'
  started_at: string
  completed_at?: string
  error_message?: string
  has_logs?: boolean
  maintenance_status?: string | null
  scheduled_job_id?: number | null
  progress_details?: {
    original_size: number
    compressed_size: number
    deduplicated_size: number
    nfiles: number
    current_file: string
    progress_percent: number
    backup_speed: number
    total_expected_size: number
    estimated_time_remaining: number
  }
}

const Schedule: React.FC = () => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const { canDo } = usePermissions()
  const canManageRepositoriesGlobally = hasGlobalPermission('repositories.manage_all')

  // Determine current tab from URL
  const getCurrentTab = React.useCallback(() => {
    if (location.pathname === '/schedule/checks') return 1
    if (location.pathname === '/schedule/backups') return 0
    return 0 // default to backups
  }, [location.pathname])

  const [currentTab, setCurrentTab] = useState(getCurrentTab())
  const [deleteConfirmJob, setDeleteConfirmJob] = useState<ScheduledJob | null>(null)
  const scheduledChecksSectionRef = useRef<ScheduledChecksSectionRef>(null)

  // Wizard state
  const [showScheduleWizard, setShowScheduleWizard] = useState(false)
  const [wizardMode, setWizardMode] = useState<'create' | 'edit'>('create')
  const [editingJobForWizard, setEditingJobForWizard] = useState<ScheduledJob | undefined>()

  // Backup History filters - load from localStorage
  const [filterSchedule, setFilterSchedule] = useState<number | 'all'>(() => {
    const saved = localStorage.getItem('scheduleBackupHistoryFilterSchedule')
    return saved ? (saved === 'all' ? 'all' : parseInt(saved)) : 'all'
  })
  const [filterRepository, setFilterRepository] = useState<string | 'all'>(() => {
    return localStorage.getItem('scheduleBackupHistoryFilterRepository') || 'all'
  })
  const [filterStatus, setFilterStatus] = useState<string | 'all'>(() => {
    return localStorage.getItem('scheduleBackupHistoryFilterStatus') || 'all'
  })

  // Redirect /schedule to /schedule/backups
  useEffect(() => {
    if (location.pathname === '/schedule') {
      navigate('/schedule/backups', { replace: true })
    }
  }, [location.pathname, navigate])

  // Update URL when tab changes
  useEffect(() => {
    const path = currentTab === 1 ? '/schedule/checks' : '/schedule/backups'
    if (location.pathname !== path && location.pathname !== '/schedule') {
      navigate(path, { replace: true })
    }
  }, [currentTab, navigate, location.pathname])

  // Sync tab with URL changes
  useEffect(() => {
    setCurrentTab(getCurrentTab())
  }, [getCurrentTab])

  // Save filter state to localStorage whenever it changes
  useEffect(() => {
    localStorage.setItem('scheduleBackupHistoryFilterSchedule', String(filterSchedule))
  }, [filterSchedule])

  useEffect(() => {
    localStorage.setItem('scheduleBackupHistoryFilterRepository', filterRepository)
  }, [filterRepository])

  useEffect(() => {
    localStorage.setItem('scheduleBackupHistoryFilterStatus', filterStatus)
  }, [filterStatus])

  // Get scheduled jobs
  const { data: jobsData, isLoading } = useQuery({
    queryKey: ['scheduled-jobs'],
    queryFn: scheduleAPI.getScheduledJobs,
    refetchInterval: 30000, // Refresh every 30 seconds
  })

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = React.useMemo<Repository[]>(
    () => repositoriesData?.data?.repositories ?? [],
    [repositoriesData?.data?.repositories]
  )
  const manageableRepositories = repositories.filter((repo: Repository) =>
    canDo(repo.id, 'maintenance')
  )

  // Get backup jobs history (scheduled only)
  const { data: backupJobsData, isLoading: loadingBackupJobs } = useQuery({
    queryKey: ['backup-jobs-scheduled'],
    queryFn: backupAPI.getScheduledJobs,
    refetchInterval: 3000, // Refresh every 3 seconds
  })

  // Get scripts library
  const { data: scriptsData } = useQuery({
    queryKey: ['scripts'],
    queryFn: () => scriptsAPI.list(),
  })

  // Get upcoming jobs
  const { data: upcomingData } = useQuery({
    queryKey: ['upcoming-jobs'],
    queryFn: () => scheduleAPI.getUpcomingJobs(24),
    refetchInterval: 60000, // Refresh every minute
  })

  // Create job mutation
  const createJobMutation = useMutation({
    mutationFn: scheduleAPI.createScheduledJob,
    onSuccess: () => {
      toast.success(t('schedule.toasts.jobCreated'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.CREATE, { entity: 'schedule' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobCreateFailed')
      )
    },
  })

  // Update job mutation
  const updateJobMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      scheduleAPI.updateScheduledJob(id, data),
    onSuccess: () => {
      toast.success(t('schedule.toasts.jobUpdated'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.EDIT, { entity: 'schedule' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobUpdateFailed')
      )
    },
  })

  // Delete job mutation
  const deleteJobMutation = useMutation({
    mutationFn: scheduleAPI.deleteScheduledJob,
    onSuccess: () => {
      toast.success(t('schedule.toasts.jobDeleted'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setDeleteConfirmJob(null)
      track(EventCategory.BACKUP, EventAction.DELETE, { entity: 'schedule' })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobDeleteFailed')
      )
    },
  })

  // Toggle job mutation
  const toggleJobMutation = useMutation({
    mutationFn: (job: ScheduledJob) => scheduleAPI.toggleScheduledJob(job.id),
    onSuccess: (_response, job) => {
      toast.success(t('schedule.toasts.jobStatusUpdated'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.EDIT, {
        entity: 'schedule',
        operation: 'toggle',
        enabled: !job.enabled,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobToggleFailed')
      )
    },
  })

  // Run job now mutation
  const runJobNowMutation = useMutation({
    mutationFn: (job: ScheduledJob) => scheduleAPI.runScheduledJobNow(job.id),
    onSuccess: (_response, job) => {
      toast.success(t('schedule.toasts.jobStarted'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-scheduled'] })
      track(EventCategory.BACKUP, EventAction.START, {
        entity: 'schedule',
        trigger: 'manual',
        repository_count: job.repository_ids?.length || (job.repository_id ? 1 : 0),
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobRunFailed')
      )
    },
  })

  // Duplicate job mutation
  const duplicateJobMutation = useMutation({
    mutationFn: (job: ScheduledJob) => scheduleAPI.duplicateScheduledJob(job.id),
    onSuccess: (_response, job) => {
      toast.success(t('schedule.toasts.jobDuplicated'))
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.CREATE, {
        entity: 'schedule',
        source: 'duplicate',
        repository_count: job.repository_ids?.length || (job.repository_id ? 1 : 0),
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.jobDuplicateFailed')
      )
    },
  })

  // Cancel backup job mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success(t('schedule.toasts.backupCancelled'))
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-scheduled'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('schedule.toasts.backupCancelFailed')
      )
    },
  })

  const handleDeleteJob = () => {
    if (deleteConfirmJob) {
      deleteJobMutation.mutate(deleteConfirmJob.id)
    }
  }

  const handleToggleJob = (job: ScheduledJob) => {
    toggleJobMutation.mutate(job)
  }

  const handleRunJobNow = (job: ScheduledJob) => {
    if (window.confirm(`Run "${job.name}" now?`)) {
      runJobNowMutation.mutate(job)
    }
  }

  const handleDuplicateJob = (job: ScheduledJob) => {
    duplicateJobMutation.mutate(job)
  }

  useTrackedJobOutcomes<BackupJob>({
    jobs: backupJobsData?.data?.jobs?.filter((job: BackupJob) => job.scheduled_job_id),
    onTerminal: (job) => {
      const scheduledJob = jobsData?.data?.jobs?.find(
        (candidate: ScheduledJob) => candidate.id === job.scheduled_job_id
      )
      const action =
        job.status === 'completed' || job.status === 'completed_with_warnings'
          ? EventAction.COMPLETE
          : EventAction.FAIL

      track(EventCategory.BACKUP, action, {
        entity: 'schedule',
        scheduled_job_id: job.scheduled_job_id,
        schedule_name: scheduledJob?.name ?? null,
        repository_count:
          scheduledJob?.repository_ids?.length || (scheduledJob?.repository_id ? 1 : 0),
        status: job.status,
        job_id: job.id,
        trigger: 'scheduled',
        maintenance_status: job.maintenance_status ?? null,
        duration_seconds: getJobDurationSeconds(job.started_at, job.completed_at),
        error_present: !!job.error_message,
        warning_count: job.status === 'completed_with_warnings' ? 1 : 0,
      })
    },
  })

  // Wizard handlers
  const openCreateWizard = () => {
    setWizardMode('create')
    setEditingJobForWizard(undefined)
    setShowScheduleWizard(true)
  }

  const openEditWizard = (job: ScheduledJob) => {
    setWizardMode('edit')
    setEditingJobForWizard(job)
    setShowScheduleWizard(true)
  }

  const handleWizardSubmit = (data: ScheduleData) => {
    if (wizardMode === 'create') {
      createJobMutation.mutate(data)
    } else if (wizardMode === 'edit' && editingJobForWizard) {
      updateJobMutation.mutate({
        id: editingJobForWizard.id,
        data,
      })
    }
    setShowScheduleWizard(false)
  }

  const getRepositoryName = (path: string) => {
    const repo = repositories?.find((r: Repository) => r.path === path)
    return repo?.name || path
  }

  const canManageJob = React.useCallback(
    (job: ScheduledJob) => {
      const targetRepoIds = job.repository_ids?.length
        ? job.repository_ids
        : job.repository_id
          ? [job.repository_id]
          : repositories
              .filter((repo: Repository) => repo.path === job.repository)
              .map((repo: Repository) => repo.id)
      if (targetRepoIds.length === 0) return canManageRepositoriesGlobally
      return targetRepoIds.every((repoId: number) => canDo(repoId, 'maintenance'))
    },
    [canDo, canManageRepositoriesGlobally, repositories]
  )

  const canCreateSchedule = canManageRepositoriesGlobally || manageableRepositories.length > 0

  const jobs = jobsData?.data?.jobs || []
  const allBackupJobs = backupJobsData?.data?.jobs || []
  const runningBackupJobs = allBackupJobs.filter(
    (job: BackupJob) =>
      job.status === 'running' ||
      (job.maintenance_status && job.maintenance_status.includes('running'))
  )
  const upcomingJobs = upcomingData?.data?.upcoming_jobs || []

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          mb: 3,
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 2,
        }}
      >
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            {t('schedule.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('schedule.subtitle')}
          </Typography>
        </Box>

        {/* Action Button — hidden for viewers */}
        {canCreateSchedule &&
          (currentTab === 0 ? (
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={openCreateWizard}
              disabled={!canCreateSchedule}
              fullWidth
              sx={{
                width: { xs: '100%', sm: 'auto' },
                alignSelf: { xs: 'stretch', sm: 'auto' },
              }}
            >
              {t('schedule.createBackup')}
            </Button>
          ) : (
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={() => scheduledChecksSectionRef.current?.openAddDialog()}
              disabled={!canCreateSchedule}
              fullWidth
              sx={{
                width: { xs: '100%', sm: 'auto' },
                alignSelf: { xs: 'stretch', sm: 'auto' },
              }}
            >
              {t('schedule.addCheck')}
            </Button>
          ))}
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={currentTab} onChange={(_, newValue) => setCurrentTab(newValue)}>
          <Tab label={t('schedule.tabs.backupJobs')} />
          <Tab label={t('schedule.tabs.repositoryChecks')} />
        </Tabs>
      </Box>

      {/* Tab Content: Backup Jobs */}
      {currentTab === 0 && (
        <Box>
          {/* No repositories warning */}
          {!loadingRepositories && (!repositories || repositories.length === 0) && (
            <Alert severity="info" sx={{ mb: 3 }}>
              {t('schedule.noRepositories')}
            </Alert>
          )}

          {/* Running Scheduled Jobs */}
          <RunningBackupsSection
            runningBackupJobs={runningBackupJobs}
            onCancelBackup={(jobId) => cancelBackupMutation.mutate(String(jobId))}
            isCancelling={cancelBackupMutation.isPending}
          />

          {/* Upcoming Jobs Summary */}
          <UpcomingJobsTable
            upcomingJobs={upcomingJobs}
            repositories={repositories}
            isLoading={isLoading}
            getRepositoryName={getRepositoryName}
          />

          {/* Scheduled Jobs Table */}
          <ScheduledJobsTable
            jobs={jobs}
            repositories={repositories}
            isLoading={isLoading}
            canManageJob={canManageJob}
            onEdit={openEditWizard}
            onDelete={setDeleteConfirmJob}
            onDuplicate={handleDuplicateJob}
            onRunNow={handleRunJobNow}
            onToggle={handleToggleJob}
            isRunNowPending={runJobNowMutation.isPending}
            isDuplicatePending={duplicateJobMutation.isPending}
          />

          {/* Backup History */}
          <BackupHistorySection
            backupJobs={allBackupJobs}
            scheduledJobs={jobs}
            repositories={repositories}
            isLoading={loadingBackupJobs}
            canBreakLocks={canManageRepositoriesGlobally}
            canDeleteJobs={canManageRepositoriesGlobally}
            filterSchedule={filterSchedule}
            filterRepository={filterRepository}
            filterStatus={filterStatus}
            onFilterScheduleChange={setFilterSchedule}
            onFilterRepositoryChange={setFilterRepository}
            onFilterStatusChange={setFilterStatus}
          />
        </Box>
      )}

      {/* Tab Content: Repository Checks */}
      {currentTab === 1 && (
        <Box>
          <ScheduledChecksSection ref={scheduledChecksSectionRef} />
        </Box>
      )}

      {/* Delete Confirmation Dialog */}
      <DeleteScheduleDialog
        open={!!deleteConfirmJob}
        job={deleteConfirmJob}
        onClose={() => setDeleteConfirmJob(null)}
        onConfirm={handleDeleteJob}
        isDeleting={deleteJobMutation.isPending}
      />

      {/* Schedule Wizard */}
      <ScheduleWizard
        open={showScheduleWizard}
        onClose={() => setShowScheduleWizard(false)}
        mode={wizardMode}
        scheduledJob={editingJobForWizard}
        repositories={manageableRepositories || []}
        scripts={scriptsData?.data || []}
        onSubmit={handleWizardSubmit}
      />
    </Box>
  )
}

export default Schedule
