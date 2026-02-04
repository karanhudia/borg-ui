import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Box,
  Typography,
  Button,
  Chip,
  FormControlLabel,
  Switch,
  Tooltip,
  Alert,
  Tabs,
  Tab,
} from '@mui/material'
import { Plus, Edit, Trash2, Play, CheckCircle, XCircle, Copy } from 'lucide-react'
import { scheduleAPI, repositoriesAPI, backupAPI, scriptsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import RepositoryCell from '../components/RepositoryCell'
import { useMatomo } from '../hooks/useMatomo'
import { useAuth } from '../hooks/useAuth'
import {
  formatDate,
  formatRelativeTime,
  formatDurationSeconds,
  convertCronToLocal,
} from '../utils/dateUtils'
import ScheduledChecksSection, {
  ScheduledChecksSectionRef,
} from '../components/ScheduledChecksSection'
import { Column, ActionButton } from '../components/DataTable'
import ScheduleWizard, { ScheduleData } from '../components/ScheduleWizard'
import DeleteScheduleDialog from '../components/DeleteScheduleDialog'
import UpcomingJobsTable from '../components/UpcomingJobsTable'
import BackupHistorySection from '../components/BackupHistorySection'
import RunningBackupsSection from '../components/RunningBackupsSection'
import ScheduledJobsTable from '../components/ScheduledJobsTable'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
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

interface Repository {
  id: number
  name: string
  path: string
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
  const queryClient = useQueryClient()
  const navigate = useNavigate()
  const location = useLocation()
  const { track, EventCategory, EventAction } = useMatomo()
  const { user } = useAuth()

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
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = repositoriesData?.data?.repositories || []

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
      toast.success('Scheduled job created successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.CREATE, 'schedule')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create scheduled job')
    },
  })

  // Update job mutation
  const updateJobMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      scheduleAPI.updateScheduledJob(id, data),
    onSuccess: () => {
      toast.success('Scheduled job updated successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.EDIT, 'schedule')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update scheduled job')
    },
  })

  // Delete job mutation
  const deleteJobMutation = useMutation({
    mutationFn: scheduleAPI.deleteScheduledJob,
    onSuccess: () => {
      toast.success('Scheduled job deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setDeleteConfirmJob(null)
      track(EventCategory.BACKUP, EventAction.DELETE, 'schedule')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete scheduled job')
    },
  })

  // Toggle job mutation
  const toggleJobMutation = useMutation({
    mutationFn: scheduleAPI.toggleScheduledJob,
    onSuccess: () => {
      toast.success('Job status updated')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.EDIT, 'schedule-toggle')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to toggle job')
    },
  })

  // Run job now mutation
  const runJobNowMutation = useMutation({
    mutationFn: scheduleAPI.runScheduledJobNow,
    onSuccess: () => {
      toast.success('Job started successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-scheduled'] })
      track(EventCategory.BACKUP, EventAction.START, 'schedule-manual-run')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run job')
    },
  })

  // Duplicate job mutation
  const duplicateJobMutation = useMutation({
    mutationFn: scheduleAPI.duplicateScheduledJob,
    onSuccess: () => {
      toast.success('Scheduled job duplicated successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      track(EventCategory.BACKUP, EventAction.CREATE, 'schedule-duplicate')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to duplicate job')
    },
  })

  // Cancel backup job mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success('Backup cancelled successfully')
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-scheduled'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to cancel backup')
    },
  })

  const handleDeleteJob = () => {
    if (deleteConfirmJob) {
      deleteJobMutation.mutate(deleteConfirmJob.id)
    }
  }

  const handleToggleJob = (job: ScheduledJob) => {
    toggleJobMutation.mutate(job.id)
  }

  const handleRunJobNow = (job: ScheduledJob) => {
    if (window.confirm(`Run "${job.name}" now?`)) {
      runJobNowMutation.mutate(job.id)
    }
  }

  const handleDuplicateJob = (job: ScheduledJob) => {
    duplicateJobMutation.mutate(job.id)
  }

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

  // Note: Using StatusBadge component for status display instead of individual functions

  const getMaintenanceStatusLabel = (
    maintenanceStatus: string | null | undefined
  ): string | null => {
    if (!maintenanceStatus) return null

    switch (maintenanceStatus) {
      case 'running_prune':
        return 'Pruning archives...'
      case 'prune_completed':
        return 'Prune completed ✓'
      case 'prune_failed':
        return 'Prune failed ✗'
      case 'running_compact':
        return 'Compacting repository...'
      case 'compact_completed':
        return 'Compact completed ✓'
      case 'compact_failed':
        return 'Compact failed ✗'
      case 'maintenance_completed':
        return 'Maintenance completed ✓'
      default:
        return null
    }
  }

  const getMaintenanceStatusColor = (
    maintenanceStatus: string | null | undefined
  ): 'success' | 'info' | 'error' | 'warning' => {
    if (!maintenanceStatus) return 'info'

    if (maintenanceStatus.includes('running')) return 'info'
    if (maintenanceStatus.includes('completed')) return 'success'
    if (maintenanceStatus.includes('failed')) return 'error'
    return 'info'
  }

  const jobs = jobsData?.data?.jobs || []
  const allBackupJobs = backupJobsData?.data?.jobs || []
  const runningBackupJobs = allBackupJobs.filter(
    (job: BackupJob) =>
      job.status === 'running' ||
      (job.maintenance_status && job.maintenance_status.includes('running'))
  )
  const upcomingJobs = upcomingData?.data?.upcoming_jobs || []

  // Scheduled Jobs Table Column Definitions
  const scheduledJobsColumns: Column<ScheduledJob>[] = [
    {
      id: 'status',
      label: 'Status',
      width: '5%',
      render: (job) => (
        <Tooltip title={job.enabled ? 'Enabled' : 'Disabled'} arrow>
          <Box sx={{ display: 'flex', alignItems: 'center', color: 'text.disabled' }}>
            {job.enabled ? <CheckCircle size={18} color="#2e7d32" /> : <XCircle size={18} />}
          </Box>
        </Tooltip>
      ),
    },
    {
      id: 'name',
      label: 'Job Name',
      width: '15%',
      render: (job) => (
        <>
          <Typography variant="body2" fontWeight={500}>
            {job.name}
          </Typography>
          {job.description && (
            <Typography variant="caption" color="text.secondary" display="block">
              {job.description}
            </Typography>
          )}
          {(job.run_prune_after || job.run_compact_after) && (
            <Box sx={{ mt: 0.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {job.run_prune_after && (
                <Tooltip
                  title={`Prune: Keep ${job.prune_keep_hourly > 0 ? `${job.prune_keep_hourly}h/` : ''}${job.prune_keep_daily}d/${job.prune_keep_weekly}w/${job.prune_keep_monthly}m/${job.prune_keep_quarterly > 0 ? `${job.prune_keep_quarterly}q/` : ''}${job.prune_keep_yearly}y`}
                  arrow
                >
                  <Chip
                    label="Prune"
                    size="small"
                    color="primary"
                    variant="outlined"
                    sx={{ height: 18, fontSize: '0.65rem' }}
                  />
                </Tooltip>
              )}
              {job.run_compact_after && (
                <Chip
                  label="Compact"
                  size="small"
                  color="secondary"
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem' }}
                />
              )}
            </Box>
          )}
        </>
      ),
    },
    {
      id: 'repository',
      label: 'Repository',
      width: '30%',
      render: (job) => {
        // Handle multi-repo schedules
        if (job.repository_ids && job.repository_ids.length > 0) {
          const repos =
            repositories?.filter((r: Repository) => job.repository_ids?.includes(r.id)) || []
          if (repos.length === 0) {
            return (
              <Typography variant="caption" color="text.secondary">
                Unknown
              </Typography>
            )
          }
          return (
            <Box>
              {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
              {repos.slice(0, 2).map((repo: any) => (
                <RepositoryCell
                  key={repo.id}
                  repositoryName={repo.name}
                  repositoryPath={repo.path}
                />
              ))}
              {repos.length > 2 && (
                <Typography variant="caption" color="text.secondary">
                  +{repos.length - 2} more
                </Typography>
              )}
            </Box>
          )
        }
        // Handle single-repo schedules (legacy format with repository path)
        if (job.repository) {
          return (
            <RepositoryCell
              repositoryName={getRepositoryName(job.repository)}
              repositoryPath={job.repository}
            />
          )
        }
        // Handle single-repo schedules (new format with repository_id)
        if (job.repository_id) {
          const repo = repositories?.find((r: Repository) => r.id === job.repository_id)
          if (repo) {
            return <RepositoryCell repositoryName={repo.name} repositoryPath={repo.path} />
          }
        }
        return (
          <Typography variant="caption" color="text.secondary">
            Unknown
          </Typography>
        )
      },
    },
    {
      id: 'schedule',
      label: 'Schedule',
      width: '12%',
      render: (job) => {
        const localCron = convertCronToLocal(job.cron_expression)
        return (
          <Chip
            label={localCron}
            size="small"
            variant="outlined"
            color="primary"
            sx={{ fontFamily: 'monospace' }}
          />
        )
      },
    },
    {
      id: 'last_run',
      label: 'Last Run',
      width: '13%',
      render: (job) => (
        <>
          {job.last_run ? (
            <>
              <Typography variant="body2">{formatDate(job.last_run)}</Typography>
              <Typography variant="caption" color="text.secondary" display="block">
                {formatRelativeTime(job.last_run)}
              </Typography>
              {(job.last_prune || job.last_compact) && (
                <Box sx={{ mt: 0.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
                  {job.last_prune && (
                    <Tooltip title={`Last pruned: ${formatDate(job.last_prune)}`} arrow>
                      <Chip
                        label="P"
                        size="small"
                        color="primary"
                        sx={{ height: 16, fontSize: '0.6rem', minWidth: 20 }}
                      />
                    </Tooltip>
                  )}
                  {job.last_compact && (
                    <Tooltip title={`Last compacted: ${formatDate(job.last_compact)}`} arrow>
                      <Chip
                        label="C"
                        size="small"
                        color="secondary"
                        sx={{ height: 16, fontSize: '0.6rem', minWidth: 20 }}
                      />
                    </Tooltip>
                  )}
                </Box>
              )}
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Never
            </Typography>
          )}
        </>
      ),
    },
    {
      id: 'next_run',
      label: 'Next Run',
      width: '13%',
      render: (job) => (
        <>
          {job.next_run ? (
            <>
              <Typography variant="body2" fontWeight={500}>
                {formatDate(job.next_run)}
              </Typography>
              <Typography variant="caption" color="primary.main">
                {formatRelativeTime(job.next_run)}
              </Typography>
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Never
            </Typography>
          )}
        </>
      ),
    },
    {
      id: 'toggle',
      label: 'Enabled',
      width: '7%',
      align: 'center',
      render: (job) => (
        <Tooltip title={job.enabled ? 'Disable' : 'Enable'} arrow>
          <FormControlLabel
            control={
              <Switch
                checked={job.enabled}
                onChange={() => handleToggleJob(job)}
                size="small"
                onClick={(e) => e.stopPropagation()}
              />
            }
            label=""
            sx={{ m: 0 }}
          />
        </Tooltip>
      ),
    },
  ]

  const scheduledJobsActions: ActionButton<ScheduledJob>[] = [
    {
      icon: <Play size={16} />,
      label: 'Run Now',
      onClick: (job) => handleRunJobNow(job),
      color: 'primary',
      disabled: (job) => !job.enabled || runJobNowMutation.isPending,
      tooltip: 'Run Now',
    },
    {
      icon: <Edit size={16} />,
      label: 'Edit',
      onClick: (job) => openEditWizard(job),
      color: 'default',
      tooltip: 'Edit',
    },
    {
      icon: <Copy size={16} />,
      label: 'Duplicate',
      onClick: (job) => handleDuplicateJob(job),
      color: 'default',
      disabled: () => duplicateJobMutation.isPending,
      tooltip: 'Duplicate',
    },
    {
      icon: <Trash2 size={16} />,
      label: 'Delete',
      onClick: (job) => setDeleteConfirmJob(job),
      color: 'error',
      tooltip: 'Delete',
    },
  ]

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Schedule
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage automated backups and repository checks
          </Typography>
        </Box>

        {/* Action Button */}
        {currentTab === 0 ? (
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={openCreateWizard}
            disabled={!repositories || repositories.length === 0}
          >
            Create Backup Schedule
          </Button>
        ) : (
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={() => scheduledChecksSectionRef.current?.openAddDialog()}
            disabled={!repositories || repositories.length === 0}
          >
            Add Check Schedule
          </Button>
        )}
      </Box>

      {/* Tabs */}
      <Box sx={{ borderBottom: 1, borderColor: 'divider', mb: 3 }}>
        <Tabs value={currentTab} onChange={(_, newValue) => setCurrentTab(newValue)}>
          <Tab label="Backup Jobs" />
          <Tab label="Repository Checks" />
        </Tabs>
      </Box>

      {/* Tab Content: Backup Jobs */}
      {currentTab === 0 && (
        <Box>
          {/* No repositories warning */}
          {(!repositories || repositories.length === 0) && (
            <Alert severity="info" sx={{ mb: 3 }}>
              You need to create at least one repository before scheduling backups.
            </Alert>
          )}

          {/* Running Scheduled Jobs */}
          <RunningBackupsSection
            runningBackupJobs={runningBackupJobs}
            getRepositoryName={getRepositoryName}
            formatRelativeTime={formatRelativeTime}
            formatDurationSeconds={formatDurationSeconds}
            getMaintenanceStatusLabel={getMaintenanceStatusLabel}
            getMaintenanceStatusColor={getMaintenanceStatusColor}
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
            columns={scheduledJobsColumns}
            actions={scheduledJobsActions}
            isLoading={isLoading}
          />

          {/* Backup History */}
          <BackupHistorySection
            backupJobs={allBackupJobs}
            scheduledJobs={jobs}
            repositories={repositories}
            isLoading={loadingBackupJobs}
            isAdmin={user?.is_admin || false}
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
        repositories={repositories || []}
        scripts={scriptsData?.data || []}
        onSubmit={handleWizardSubmit}
      />
    </Box>
  )
}

export default Schedule
