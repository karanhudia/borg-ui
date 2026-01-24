import React, { useState, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate, useLocation } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Chip,
  FormControlLabel,
  Switch,
  Tooltip,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  InputAdornment,
  Alert,
  Paper,
  Tabs,
  Tab,
  Checkbox,
} from '@mui/material'
import {
  Plus,
  Edit,
  Trash2,
  Play,
  Clock,
  CheckCircle,
  XCircle,
  AlertCircle,
  Calendar,
  RefreshCw,
  X,
  Copy,
} from 'lucide-react'
import { scheduleAPI, repositoriesAPI, backupAPI, scriptsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import RepositoryCell from '../components/RepositoryCell'
import MultiRepositorySelector from '../components/MultiRepositorySelector'
import { useMatomo } from '../hooks/useMatomo'
import {
  formatDate,
  formatRelativeTime,
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
  convertCronToUTC,
  convertCronToLocal,
} from '../utils/dateUtils'
import BackupJobsTable from '../components/BackupJobsTable'
import StatusBadge from '../components/StatusBadge'
import { TerminalLogViewer } from '../components/TerminalLogViewer'
import ScheduledChecksSection, {
  ScheduledChecksSectionRef,
} from '../components/ScheduledChecksSection'
import DataTable, { Column, ActionButton } from '../components/DataTable'

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

  // Determine current tab from URL
  const getCurrentTab = React.useCallback(() => {
    if (location.pathname === '/schedule/checks') return 1
    if (location.pathname === '/schedule/backups') return 0
    return 0 // default to backups
  }, [location.pathname])

  const [currentTab, setCurrentTab] = useState(getCurrentTab())
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null)
  const [showCronBuilder, setShowCronBuilder] = useState(false)
  const [deleteConfirmJob, setDeleteConfirmJob] = useState<ScheduledJob | null>(null)
  const [selectedBackupJob, setSelectedBackupJob] = useState<BackupJob | null>(null)
  const scheduledChecksSectionRef = useRef<ScheduledChecksSectionRef>(null)

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

  // Get cron presets
  const { data: presetsData } = useQuery({
    queryKey: ['cron-presets'],
    queryFn: scheduleAPI.getCronPresets,
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
      setShowCreateModal(false)
      resetCreateForm()
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
      setEditingJob(null)
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

  // Form states
  const [createForm, setCreateForm] = useState({
    name: '',
    cron_expression: '0 2 * * *',
    repository: '', // Keep for backward compatibility
    repository_ids: [] as number[], // Multi-repo selection
    enabled: true,
    description: '',
    archive_name_template: '{job_name}-{now}',
    run_repository_scripts: false,
    pre_backup_script_id: null as number | null,
    post_backup_script_id: null as number | null,
    run_prune_after: false,
    run_compact_after: false,
    prune_keep_hourly: 0,
    prune_keep_daily: 7,
    prune_keep_weekly: 4,
    prune_keep_monthly: 6,
    prune_keep_quarterly: 0,
    prune_keep_yearly: 1,
  })

  const [editForm, setEditForm] = useState({
    name: '',
    cron_expression: '',
    repository: '',
    repository_ids: [] as number[],
    enabled: true,
    description: '',
    archive_name_template: '',
    run_repository_scripts: false,
    pre_backup_script_id: null as number | null,
    post_backup_script_id: null as number | null,
    run_prune_after: false,
    run_compact_after: false,
    prune_keep_hourly: 0,
    prune_keep_daily: 7,
    prune_keep_weekly: 4,
    prune_keep_monthly: 6,
    prune_keep_quarterly: 0,
    prune_keep_yearly: 1,
  })

  const resetCreateForm = () => {
    setCreateForm({
      name: '',
      cron_expression: '0 2 * * *',
      repository: '',
      repository_ids: [],
      enabled: true,
      description: '',
      archive_name_template: '{job_name}-{now}',
      run_repository_scripts: false,
      pre_backup_script_id: null,
      post_backup_script_id: null,
      run_prune_after: false,
      run_compact_after: false,
      prune_keep_hourly: 0,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_quarterly: 0,
      prune_keep_yearly: 1,
    })
  }

  const handleCreateJob = (e: React.FormEvent) => {
    e.preventDefault()
    // Validate that at least one repository is selected
    if (!createForm.repository && createForm.repository_ids.length === 0) {
      toast.error('Please select at least one repository')
      return
    }
    // Convert cron expression from local time to UTC before sending to server
    const utcCron = convertCronToUTC(createForm.cron_expression)

    // Prepare payload - send repository_ids if multi-repo, otherwise send repository
    const payload = {
      ...createForm,
      cron_expression: utcCron,
      // Only send repository_ids if multi-repo (more than one selected)
      repository_ids: createForm.repository_ids.length > 0 ? createForm.repository_ids : undefined,
      // Clear repository if using multi-repo
      repository: createForm.repository_ids.length > 0 ? undefined : createForm.repository,
    }

    createJobMutation.mutate(payload)
  }

  const handleUpdateJob = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editForm.repository && editForm.repository_ids.length === 0) {
      toast.error('Please select a repository')
      return
    }
    if (editingJob) {
      // Convert cron expression from local time to UTC before sending to server
      const utcCron = convertCronToUTC(editForm.cron_expression)

      // Prepare payload - send repository_ids if multi-repo, otherwise send repository
      const payload = {
        ...editForm,
        cron_expression: utcCron,
        // Only send repository_ids if multi-repo (more than one selected)
        repository_ids: editForm.repository_ids.length > 0 ? editForm.repository_ids : undefined,
        // Clear repository if using multi-repo
        repository: editForm.repository_ids.length > 0 ? undefined : editForm.repository,
      }

      updateJobMutation.mutate({
        id: editingJob.id,
        data: payload,
      })
    }
  }

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

  const openCreateModal = () => {
    resetCreateForm()
    setShowCreateModal(true)
  }

  const openEditModal = (job: ScheduledJob) => {
    setEditingJob(job)
    // Convert UTC cron expression from server to local time for editing
    const localCron = convertCronToLocal(job.cron_expression)

    // Handle converting old single-repo format to new multi-repo format
    let repository_ids: number[] = []
    if (job.repository_ids && job.repository_ids.length > 0) {
      // New format: already has repository_ids array
      repository_ids = job.repository_ids
    } else if (job.repository_id) {
      // Old format: single repository_id (integer)
      repository_ids = [job.repository_id]
    } else if (job.repository) {
      // Legacy format: repository path (string) - need to find ID
      const repo = repositories?.find((r: Repository) => r.path === job.repository)
      if (repo) {
        repository_ids = [repo.id]
      }
    }

    setEditForm({
      name: job.name,
      cron_expression: localCron,
      repository: job.repository || '',
      repository_ids: repository_ids,
      enabled: job.enabled,
      description: job.description || '',
      archive_name_template: job.archive_name_template || '{job_name}-{now}',
      run_repository_scripts: job.run_repository_scripts || false,
      pre_backup_script_id: job.pre_backup_script_id || null,
      post_backup_script_id: job.post_backup_script_id || null,
      run_prune_after: job.run_prune_after || false,
      run_compact_after: job.run_compact_after || false,
      prune_keep_hourly: job.prune_keep_hourly ?? 0,
      prune_keep_daily: job.prune_keep_daily ?? 7,
      prune_keep_weekly: job.prune_keep_weekly ?? 4,
      prune_keep_monthly: job.prune_keep_monthly ?? 6,
      prune_keep_quarterly: job.prune_keep_quarterly ?? 0,
      prune_keep_yearly: job.prune_keep_yearly ?? 1,
    })
  }

  const openCronBuilder = () => {
    setShowCronBuilder(true)
  }

  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const applyCronPreset = (preset: any) => {
    if (editingJob) {
      setEditForm({ ...editForm, cron_expression: preset.expression })
    } else {
      setCreateForm({ ...createForm, cron_expression: preset.expression })
    }
    setShowCronBuilder(false)
  }

  const formatCronExpression = (expression: string) => {
    const descriptions: { [key: string]: string } = {
      '0 0 * * *': 'Daily at midnight',
      '0 2 * * *': 'Daily at 2 AM',
      '0 */6 * * *': 'Every 6 hours',
      '0 * * * *': 'Every hour',
      '*/15 * * * *': 'Every 15 minutes',
      '*/5 * * * *': 'Every 5 minutes',
      '* * * * *': 'Every minute',
      '0 0 * * 0': 'Weekly on Sunday',
      '0 0 1 * *': 'Monthly on 1st',
      '0 9 * * 1-5': 'Weekdays at 9 AM',
      '0 6 * * 0,6': 'Weekends at 6 AM',
    }
    return descriptions[expression] || expression
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

  // Apply filters to backup history
  const filteredBackupJobs = allBackupJobs.filter((job: BackupJob) => {
    if (filterSchedule !== 'all' && job.scheduled_job_id !== filterSchedule) return false
    if (filterRepository !== 'all' && job.repository !== filterRepository) return false
    if (filterStatus !== 'all') {
      if (filterStatus === 'completed' && job.status !== 'completed') return false
      if (filterStatus === 'failed' && job.status !== 'failed') return false
      if (filterStatus === 'warning' && job.status !== 'completed_with_warnings') return false
    }
    return true
  })
  const recentBackupJobs = filteredBackupJobs.slice(0, 10)
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
          const repos = repositories?.filter((r: Repository) => job.repository_ids?.includes(r.id)) || []
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
      render: (job) => (
        <>
          <Chip
            label={formatCronExpression(convertCronToLocal(job.cron_expression))}
            size="small"
            variant="outlined"
            color="primary"
          />
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mt: 0.5 }}>
            {convertCronToLocal(job.cron_expression)}
          </Typography>
        </>
      ),
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
      onClick: (job) => openEditModal(job),
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

  // Backup History callbacks
  const handleViewBackupLogs = (job: BackupJob) => {
    setSelectedBackupJob(job)
  }

  const handleCancelBackupJob = (job: BackupJob) => {
    if (window.confirm('Are you sure you want to cancel this backup?')) {
      cancelBackupMutation.mutate(job.id)
    }
  }

  const handleDownloadBackupLogs = (job: BackupJob) => {
    backupAPI.downloadLogs(job.id)
  }

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
            onClick={openCreateModal}
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
          {runningBackupJobs.length > 0 && (
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                  <RefreshCw size={20} color="#1976d2" className="animate-spin" />
                  <Typography variant="h6" fontWeight={600}>
                    Running Scheduled Backups
                  </Typography>
                  <Chip
                    label={`${runningBackupJobs.length} active`}
                    size="small"
                    color="primary"
                    sx={{ ml: 1 }}
                  />
                </Stack>
                <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                  Real-time progress for scheduled backup jobs
                </Typography>

                <Stack spacing={2}>
                  {runningBackupJobs.map((job: BackupJob) => (
                    <Paper
                      key={job.id}
                      elevation={0}
                      sx={{
                        p: 2,
                        border: 1,
                        borderColor: 'primary.main',
                        borderRadius: 2,
                        backgroundColor: 'primary.lighter',
                      }}
                    >
                      {/* Job Header */}
                      <Stack
                        direction="row"
                        justifyContent="space-between"
                        alignItems="center"
                        sx={{ mb: 2 }}
                      >
                        <Stack direction="row" spacing={2} alignItems="center">
                          <Chip
                            icon={<RefreshCw size={14} className="animate-spin" />}
                            label="Running"
                            color="primary"
                            size="small"
                          />
                          <Typography variant="body2" fontWeight={600}>
                            Job #{job.id} - {getRepositoryName(job.repository)}
                          </Typography>
                        </Stack>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Typography variant="caption" color="text.secondary">
                            Started: {formatRelativeTime(job.started_at)}
                          </Typography>
                          <Tooltip title="Cancel Backup" arrow>
                            <IconButton
                              size="small"
                              color="error"
                              onClick={() => {
                                if (
                                  window.confirm(
                                    `Are you sure you want to cancel backup job #${job.id}?`
                                  )
                                ) {
                                  cancelBackupMutation.mutate(job.id)
                                }
                              }}
                              disabled={cancelBackupMutation.isPending}
                              sx={{ ml: 1 }}
                            >
                              <X size={16} />
                            </IconButton>
                          </Tooltip>
                        </Stack>
                      </Stack>

                      {/* Current File Being Processed */}
                      {job.progress_details?.current_file && (
                        <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
                          <Typography variant="caption" fontWeight={500}>
                            Current File:
                          </Typography>
                          <Typography
                            variant="caption"
                            sx={{
                              fontFamily: 'monospace',
                              display: 'block',
                              mt: 0.5,
                              wordBreak: 'break-all',
                            }}
                          >
                            {job.progress_details.current_file}
                          </Typography>
                        </Alert>
                      )}

                      {/* Maintenance Status */}
                      {job.maintenance_status &&
                        getMaintenanceStatusLabel(job.maintenance_status) && (
                          <Alert
                            severity={getMaintenanceStatusColor(job.maintenance_status)}
                            sx={{ mb: 2, py: 0.5 }}
                            icon={
                              job.maintenance_status.includes('running') ? (
                                <RefreshCw size={16} className="animate-spin" />
                              ) : undefined
                            }
                          >
                            <Typography variant="caption" fontWeight={500}>
                              {getMaintenanceStatusLabel(job.maintenance_status)}
                            </Typography>
                          </Alert>
                        )}

                      {/* Job Details Grid */}
                      <Box
                        sx={{
                          display: 'grid',
                          gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                          gap: 2,
                          width: '100%',
                        }}
                      >
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Files Processed:
                          </Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {job.progress_details?.nfiles?.toLocaleString() || '0'}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Original Size:
                          </Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {job.progress_details?.original_size
                              ? formatBytesUtil(job.progress_details.original_size)
                              : 'N/A'}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Compressed:
                          </Typography>
                          <Typography variant="body2" fontWeight={500}>
                            {job.progress_details?.compressed_size !== undefined &&
                              job.progress_details?.compressed_size !== null
                              ? formatBytesUtil(job.progress_details.compressed_size)
                              : 'N/A'}
                          </Typography>
                        </Box>
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Deduplicated:
                          </Typography>
                          <Typography variant="body2" fontWeight={500} color="success.main">
                            {job.progress_details?.deduplicated_size !== undefined &&
                              job.progress_details?.deduplicated_size !== null
                              ? formatBytesUtil(job.progress_details.deduplicated_size)
                              : 'N/A'}
                          </Typography>
                        </Box>
                        {job.progress_details?.total_expected_size &&
                          job.progress_details.total_expected_size > 0 && (
                            <Box>
                              <Typography variant="body2" color="text.secondary">
                                Total Source Size:
                              </Typography>
                              <Typography variant="body2" fontWeight={500} color="info.main">
                                {formatBytesUtil(job.progress_details.total_expected_size)}
                              </Typography>
                            </Box>
                          )}
                        <Box>
                          <Typography variant="body2" color="text.secondary">
                            Speed:
                          </Typography>
                          <Typography variant="body2" fontWeight={500} color="primary.main">
                            {job.progress_details?.backup_speed
                              ? `${job.progress_details.backup_speed.toFixed(2)} MB/s`
                              : 'N/A'}
                          </Typography>
                        </Box>
                        {(job.progress_details?.estimated_time_remaining ?? 0) > 0 && (
                          <Box>
                            <Typography variant="body2" color="text.secondary">
                              ETA:
                            </Typography>
                            <Typography variant="body2" fontWeight={500} color="success.main">
                              {formatDurationSeconds(
                                job.progress_details?.estimated_time_remaining ?? 0
                              )}
                            </Typography>
                          </Box>
                        )}
                      </Box>
                    </Paper>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          )}

          {/* Upcoming Jobs Summary */}
          {upcomingJobs.length > 0 && (
            <Card sx={{ mb: 3 }}>
              <CardContent>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
                  <Calendar size={20} color="#1976d2" />
                  <Typography variant="h6" fontWeight={600}>
                    Upcoming Jobs (Next 24 Hours)
                  </Typography>
                </Stack>
                <Stack spacing={1.5}>
                  {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                  {upcomingJobs.slice(0, 5).map((job: any) => (
                    <Box
                      key={job.id}
                      sx={{
                        p: 2,
                        backgroundColor: 'action.hover',
                        borderRadius: 1,
                        display: 'flex',
                        justifyContent: 'space-between',
                        alignItems: 'center',
                      }}
                    >
                      <Box>
                        <Typography variant="body2" fontWeight={500}>
                          {job.name}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {job.repository_ids && job.repository_ids.length > 0
                            ? `${job.repository_ids.length} repositories`
                            : job.repository_id
                              // eslint-disable-next-line @typescript-eslint/no-explicit-any
                              ? repositories.find((r: any) => r.id === job.repository_id)?.name ||
                              'Unknown'
                              : getRepositoryName(job.repository)}
                        </Typography>
                      </Box>
                      <Box sx={{ textAlign: 'right' }}>
                        <Typography variant="body2" fontWeight={500}>
                          {formatDate(job.next_run)}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          {formatRelativeTime(job.next_run)}
                        </Typography>
                      </Box>
                    </Box>
                  ))}
                </Stack>
              </CardContent>
            </Card>
          )}

          {/* Scheduled Jobs Table */}
          <Card>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                All Scheduled Jobs
              </Typography>

              <Box sx={{ mt: 2 }}>
                <DataTable
                  data={jobs}
                  columns={scheduledJobsColumns}
                  actions={scheduledJobsActions}
                  getRowKey={(job) => job.id}
                  loading={isLoading}
                  enableHover={true}
                  headerBgColor="background.default"
                  emptyState={{
                    icon: <Clock size={48} />,
                    title: 'No scheduled jobs found',
                    description: 'Create your first scheduled backup job',
                  }}
                />
              </Box>
            </CardContent>
          </Card>

          {/* Backup History */}
          <Card sx={{ mt: 3 }}>
            <CardContent>
              <Typography variant="h6" fontWeight={600} gutterBottom>
                Backup History
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Showing {recentBackupJobs.length} of {filteredBackupJobs.length} backup jobs
                {(filterSchedule !== 'all' ||
                  filterRepository !== 'all' ||
                  filterStatus !== 'all') &&
                  ' (filtered)'}
              </Typography>

              {/* Filters */}
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel>Schedule</InputLabel>
                  <Select
                    value={filterSchedule}
                    label="Schedule"
                    onChange={(e) => setFilterSchedule(e.target.value as number | 'all')}
                  >
                    <MenuItem value="all">All Schedules</MenuItem>
                    {jobs.map((job: ScheduledJob) => (
                      <MenuItem key={job.id} value={job.id}>
                        {job.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl size="small" sx={{ minWidth: 200 }}>
                  <InputLabel>Repository</InputLabel>
                  <Select
                    value={filterRepository}
                    label="Repository"
                    onChange={(e) => setFilterRepository(e.target.value)}
                  >
                    <MenuItem value="all">All Repositories</MenuItem>
                    {repositories.map((repo: Repository) => (
                      <MenuItem key={repo.id} value={repo.path}>
                        {repo.name}
                      </MenuItem>
                    ))}
                  </Select>
                </FormControl>

                <FormControl size="small" sx={{ minWidth: 150 }}>
                  <InputLabel>Status</InputLabel>
                  <Select
                    value={filterStatus}
                    label="Status"
                    onChange={(e) => setFilterStatus(e.target.value)}
                  >
                    <MenuItem value="all">All Status</MenuItem>
                    <MenuItem value="completed">Completed</MenuItem>
                    <MenuItem value="failed">Failed</MenuItem>
                    <MenuItem value="warning">Warning</MenuItem>
                  </Select>
                </FormControl>
              </Stack>

              <BackupJobsTable
                jobs={recentBackupJobs}
                repositories={repositories || []}
                loading={loadingBackupJobs}
                actions={{
                  viewLogs: true,
                  cancel: true,
                  downloadLogs: true,
                  errorInfo: true,
                }}
                onViewLogs={handleViewBackupLogs}
                onCancelJob={handleCancelBackupJob}
                onDownloadLogs={handleDownloadBackupLogs}
                getRowKey={(job) => String(job.id)}
                headerBgColor="background.default"
                enableHover={true}
                emptyState={{
                  icon: <Clock size={48} />,
                  title: 'No backup jobs found',
                }}
              />
            </CardContent>
          </Card>
        </Box>
      )}

      {/* Tab Content: Repository Checks */}
      {currentTab === 1 && (
        <Box>
          <ScheduledChecksSection ref={scheduledChecksSectionRef} />
        </Box>
      )}

      {/* Create Job Modal */}
      <Dialog
        open={showCreateModal}
        onClose={() => setShowCreateModal(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Create Scheduled Job</DialogTitle>
        <form onSubmit={handleCreateJob}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Job Name"
                value={createForm.name}
                onChange={(e) => setCreateForm({ ...createForm, name: e.target.value })}
                required
                fullWidth
                placeholder="Daily backup"
                helperText="A descriptive name for this scheduled job"
                size="medium"
                InputProps={{
                  sx: { fontSize: '1.1rem' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <MultiRepositorySelector
                repositories={repositories}
                selectedIds={createForm.repository_ids}
                onChange={(ids) => setCreateForm({ ...createForm, repository_ids: ids })}
                label="Repositories"
                placeholder="Select repositories..."
                helperText="Choose repositories to backup. Use arrows to change backup order for multi-repository schedules."
                required
                size="medium"
                allowReorder={true}
                filterMode="observe"
              />

              <Box>
                <TextField
                  label="Schedule"
                  value={createForm.cron_expression}
                  onChange={(e) =>
                    setCreateForm({ ...createForm, cron_expression: e.target.value })
                  }
                  required
                  fullWidth
                  size="medium"
                  placeholder="0 2 * * *"
                  InputProps={{
                    sx: {
                      fontFamily: 'monospace',
                      fontSize: '1.1rem',
                      letterSpacing: '0.1em',
                    },
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="Choose preset schedule" arrow>
                          <IconButton onClick={openCronBuilder} edge="end">
                            <Clock size={20} />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                  InputLabelProps={{
                    sx: { fontSize: '1.1rem' },
                  }}
                  helperText={
                    <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <CheckCircle size={14} style={{ color: '#2e7d32' }} />
                      <span>{formatCronExpression(createForm.cron_expression)}</span>
                    </Box>
                  }
                />
              </Box>

              <TextField
                label="Description"
                value={createForm.description}
                onChange={(e) => setCreateForm({ ...createForm, description: e.target.value })}
                multiline
                rows={2}
                placeholder="Optional description"
                fullWidth
                size="medium"
                InputProps={{
                  sx: { fontSize: '1.1rem' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <TextField
                label="Archive Name Template"
                value={createForm.archive_name_template}
                onChange={(e) =>
                  setCreateForm({ ...createForm, archive_name_template: e.target.value })
                }
                fullWidth
                size="medium"
                helperText="Customize archive naming. Available placeholders: {job_name}, {now}, {date}, {time}, {timestamp}"
                InputProps={{
                  sx: { fontSize: '1.1rem', fontFamily: 'monospace' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={createForm.enabled}
                    onChange={(e) => setCreateForm({ ...createForm, enabled: e.target.checked })}
                  />
                }
                label="Enable immediately"
              />

              {/* Multi-Repo Scripts Section */}
              {createForm.repository_ids.length > 0 && (
                <Box sx={{ mt: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                    Schedule-Level Scripts
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 2 }}
                  >
                    These scripts run once per schedule (e.g., wake server before all backups,
                    shutdown after)
                  </Typography>

                  <Stack spacing={2}>
                    <FormControl fullWidth size="medium">
                      <InputLabel sx={{ fontSize: '1.1rem' }}>
                        Pre-Backup Script (runs once before all backups)
                      </InputLabel>
                      <Select
                        value={createForm.pre_backup_script_id || ''}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            pre_backup_script_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        label="Pre-Backup Script (runs once before all backups)"
                        sx={{ fontSize: '1.1rem', minHeight: 56 }}
                      >
                        <MenuItem value="">
                          <em>None</em>
                        </MenuItem>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {scriptsData?.data?.map((script: any) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl fullWidth size="medium">
                      <InputLabel sx={{ fontSize: '1.1rem' }}>
                        Post-Backup Script (runs once after all backups)
                      </InputLabel>
                      <Select
                        value={createForm.post_backup_script_id || ''}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            post_backup_script_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        label="Post-Backup Script (runs once after all backups)"
                        sx={{ fontSize: '1.1rem', minHeight: 56 }}
                      >
                        <MenuItem value="">
                          <em>None</em>
                        </MenuItem>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {scriptsData?.data?.map((script: any) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={createForm.run_repository_scripts}
                          onChange={(e) =>
                            setCreateForm({
                              ...createForm,
                              run_repository_scripts: e.target.checked,
                            })
                          }
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body2">Run repository-level scripts</Typography>
                          <Typography variant="caption" color="text.secondary">
                            If enabled, each repository's pre/post scripts will run during its
                            backup
                          </Typography>
                        </Box>
                      }
                    />
                  </Stack>
                </Box>
              )}

              {/* Maintenance Section */}
              <Box sx={{ mt: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                  Maintenance Options
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                  Automatically run prune and compact operations after successful backups
                </Typography>

                <Stack spacing={2}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={createForm.run_prune_after}
                        onChange={(e) =>
                          setCreateForm({ ...createForm, run_prune_after: e.target.checked })
                        }
                      />
                    }
                    label="Run prune after backup"
                  />

                  {createForm.run_prune_after && (
                    <Box
                      sx={{ pl: 4, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}
                    >
                      <TextField
                        label="Keep Hourly"
                        type="number"
                        value={createForm.prune_keep_hourly}
                        onChange={(e) => {
                          const value = parseInt(e.target.value, 10)
                          setCreateForm({
                            ...createForm,
                            prune_keep_hourly: isNaN(value) ? 0 : Math.max(0, value),
                          })
                        }}
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Hourly backups to keep (0 = disabled)"
                      />
                      <TextField
                        label="Keep Daily"
                        type="number"
                        value={createForm.prune_keep_daily}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            prune_keep_daily: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Daily backups to keep"
                      />
                      <TextField
                        label="Keep Weekly"
                        type="number"
                        value={createForm.prune_keep_weekly}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            prune_keep_weekly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Weekly backups to keep"
                      />
                      <TextField
                        label="Keep Monthly"
                        type="number"
                        value={createForm.prune_keep_monthly}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            prune_keep_monthly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Monthly backups to keep"
                      />
                      <TextField
                        label="Keep Quarterly"
                        type="number"
                        value={createForm.prune_keep_quarterly}
                        onChange={(e) => {
                          const value = parseInt(e.target.value, 10)
                          setCreateForm({
                            ...createForm,
                            prune_keep_quarterly: isNaN(value) ? 0 : Math.max(0, value),
                          })
                        }}
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Quarterly backups to keep (0 = disabled)"
                      />
                      <TextField
                        label="Keep Yearly"
                        type="number"
                        value={createForm.prune_keep_yearly}
                        onChange={(e) =>
                          setCreateForm({
                            ...createForm,
                            prune_keep_yearly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Yearly backups to keep"
                      />
                    </Box>
                  )}

                  <FormControlLabel
                    control={
                      <Switch
                        checked={createForm.run_compact_after}
                        onChange={(e) =>
                          setCreateForm({ ...createForm, run_compact_after: e.target.checked })
                        }
                      />
                    }
                    label="Run compact after prune"
                  />
                  {createForm.run_compact_after && (
                    <Alert severity="info" sx={{ ml: 4 }}>
                      Compact will reclaim disk space after removing old archives
                    </Alert>
                  )}
                </Stack>
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowCreateModal(false)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={createJobMutation.isPending}
              startIcon={
                createJobMutation.isPending ? <CircularProgress size={16} /> : <Plus size={16} />
              }
            >
              {createJobMutation.isPending ? 'Creating...' : 'Create Job'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Edit Job Modal */}
      <Dialog open={!!editingJob} onClose={() => setEditingJob(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Edit Scheduled Job</DialogTitle>
        <form onSubmit={handleUpdateJob}>
          <DialogContent>
            <Stack spacing={3}>
              <TextField
                label="Job Name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                fullWidth
                size="medium"
                InputProps={{
                  sx: { fontSize: '1.1rem' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <MultiRepositorySelector
                repositories={repositories}
                selectedIds={editForm.repository_ids}
                onChange={(ids) => setEditForm({ ...editForm, repository_ids: ids })}
                label="Repositories"
                placeholder="Select repositories..."
                helperText="Choose repositories to backup. Use arrows to change backup order for multi-repository schedules."
                required
                size="medium"
                allowReorder={true}
                filterMode="observe"
              />

              <Box>
                <TextField
                  label="Schedule"
                  value={editForm.cron_expression}
                  onChange={(e) => setEditForm({ ...editForm, cron_expression: e.target.value })}
                  required
                  fullWidth
                  size="medium"
                  InputProps={{
                    sx: {
                      fontFamily: 'monospace',
                      fontSize: '1.1rem',
                      letterSpacing: '0.1em',
                    },
                    endAdornment: (
                      <InputAdornment position="end">
                        <Tooltip title="Choose preset schedule" arrow>
                          <IconButton onClick={openCronBuilder} edge="end">
                            <Clock size={20} />
                          </IconButton>
                        </Tooltip>
                      </InputAdornment>
                    ),
                  }}
                  InputLabelProps={{
                    sx: { fontSize: '1.1rem' },
                  }}
                  helperText={
                    <Box component="span" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                      <CheckCircle size={14} style={{ color: '#2e7d32' }} />
                      <span>{formatCronExpression(editForm.cron_expression)}</span>
                    </Box>
                  }
                />
              </Box>

              <TextField
                label="Description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                multiline
                rows={2}
                fullWidth
                size="medium"
                InputProps={{
                  sx: { fontSize: '1.1rem' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <TextField
                label="Archive Name Template"
                value={editForm.archive_name_template}
                onChange={(e) =>
                  setEditForm({ ...editForm, archive_name_template: e.target.value })
                }
                fullWidth
                size="medium"
                helperText="Customize archive naming. Available placeholders: {job_name}, {now}, {date}, {time}, {timestamp}"
                InputProps={{
                  sx: { fontSize: '1.1rem', fontFamily: 'monospace' },
                }}
                InputLabelProps={{
                  sx: { fontSize: '1.1rem' },
                }}
              />

              <FormControlLabel
                control={
                  <Switch
                    checked={editForm.enabled}
                    onChange={(e) => setEditForm({ ...editForm, enabled: e.target.checked })}
                  />
                }
                label="Enabled"
              />

              {/* Multi-Repo Scripts Section */}
              {editForm.repository_ids.length > 0 && (
                <Box sx={{ mt: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                  <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                    Schedule-Level Scripts
                  </Typography>
                  <Typography
                    variant="caption"
                    color="text.secondary"
                    display="block"
                    sx={{ mb: 2 }}
                  >
                    These scripts run once per schedule (e.g., wake server before all backups,
                    shutdown after)
                  </Typography>

                  <Stack spacing={2}>
                    <FormControl fullWidth size="medium">
                      <InputLabel sx={{ fontSize: '1.1rem' }}>
                        Pre-Backup Script (runs once before all backups)
                      </InputLabel>
                      <Select
                        value={editForm.pre_backup_script_id || ''}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            pre_backup_script_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        label="Pre-Backup Script (runs once before all backups)"
                        sx={{ fontSize: '1.1rem', minHeight: 56 }}
                      >
                        <MenuItem value="">
                          <em>None</em>
                        </MenuItem>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {scriptsData?.data?.map((script: any) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControl fullWidth size="medium">
                      <InputLabel sx={{ fontSize: '1.1rem' }}>
                        Post-Backup Script (runs once after all backups)
                      </InputLabel>
                      <Select
                        value={editForm.post_backup_script_id || ''}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            post_backup_script_id: e.target.value ? Number(e.target.value) : null,
                          })
                        }
                        label="Post-Backup Script (runs once after all backups)"
                        sx={{ fontSize: '1.1rem', minHeight: 56 }}
                      >
                        <MenuItem value="">
                          <em>None</em>
                        </MenuItem>
                        {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
                        {scriptsData?.data?.map((script: any) => (
                          <MenuItem key={script.id} value={script.id}>
                            {script.name}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>

                    <FormControlLabel
                      control={
                        <Checkbox
                          checked={editForm.run_repository_scripts}
                          onChange={(e) =>
                            setEditForm({ ...editForm, run_repository_scripts: e.target.checked })
                          }
                        />
                      }
                      label={
                        <Box>
                          <Typography variant="body2">Run repository-level scripts</Typography>
                          <Typography variant="caption" color="text.secondary">
                            If enabled, each repository's pre/post scripts will run during its
                            backup
                          </Typography>
                        </Box>
                      }
                    />
                  </Stack>
                </Box>
              )}

              {/* Maintenance Section */}
              <Box sx={{ mt: 2, p: 2, border: 1, borderColor: 'divider', borderRadius: 1 }}>
                <Typography variant="subtitle2" fontWeight={600} gutterBottom>
                  Maintenance Options
                </Typography>
                <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 2 }}>
                  Automatically run prune and compact operations after successful backups
                </Typography>

                <Stack spacing={2}>
                  <FormControlLabel
                    control={
                      <Switch
                        checked={editForm.run_prune_after}
                        onChange={(e) =>
                          setEditForm({ ...editForm, run_prune_after: e.target.checked })
                        }
                      />
                    }
                    label="Run prune after backup"
                  />

                  {editForm.run_prune_after && (
                    <Box
                      sx={{ pl: 4, display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2 }}
                    >
                      <TextField
                        label="Keep Hourly"
                        type="number"
                        value={editForm.prune_keep_hourly}
                        onChange={(e) => {
                          const value = parseInt(e.target.value, 10)
                          setEditForm({
                            ...editForm,
                            prune_keep_hourly: isNaN(value) ? 0 : Math.max(0, value),
                          })
                        }}
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Hourly backups to keep (0 = disabled)"
                      />
                      <TextField
                        label="Keep Daily"
                        type="number"
                        value={editForm.prune_keep_daily}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            prune_keep_daily: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Daily backups to keep"
                      />
                      <TextField
                        label="Keep Weekly"
                        type="number"
                        value={editForm.prune_keep_weekly}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            prune_keep_weekly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Weekly backups to keep"
                      />
                      <TextField
                        label="Keep Monthly"
                        type="number"
                        value={editForm.prune_keep_monthly}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            prune_keep_monthly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Monthly backups to keep"
                      />
                      <TextField
                        label="Keep Quarterly"
                        type="number"
                        value={editForm.prune_keep_quarterly}
                        onChange={(e) => {
                          const value = parseInt(e.target.value, 10)
                          setEditForm({
                            ...editForm,
                            prune_keep_quarterly: isNaN(value) ? 0 : Math.max(0, value),
                          })
                        }}
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Quarterly backups to keep (0 = disabled)"
                      />
                      <TextField
                        label="Keep Yearly"
                        type="number"
                        value={editForm.prune_keep_yearly}
                        onChange={(e) =>
                          setEditForm({
                            ...editForm,
                            prune_keep_yearly: parseInt(e.target.value) || 0,
                          })
                        }
                        inputProps={{ min: 0 }}
                        size="small"
                        helperText="Yearly backups to keep"
                      />
                    </Box>
                  )}

                  <FormControlLabel
                    control={
                      <Switch
                        checked={editForm.run_compact_after}
                        onChange={(e) =>
                          setEditForm({ ...editForm, run_compact_after: e.target.checked })
                        }
                      />
                    }
                    label="Run compact after prune"
                  />
                  {editForm.run_compact_after && (
                    <Alert severity="info" sx={{ ml: 4 }}>
                      Compact will reclaim disk space after removing old archives
                    </Alert>
                  )}
                </Stack>
              </Box>
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setEditingJob(null)}>Cancel</Button>
            <Button
              type="submit"
              variant="contained"
              disabled={updateJobMutation.isPending}
              startIcon={updateJobMutation.isPending ? <CircularProgress size={16} /> : null}
            >
              {updateJobMutation.isPending ? 'Updating...' : 'Update Job'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Cron Builder Modal */}
      <Dialog
        open={showCronBuilder}
        onClose={() => setShowCronBuilder(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Cron Expression Presets</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mt: 1 }}>
            Select a preset schedule for your backup job
          </Typography>
          <Stack spacing={1} sx={{ mt: 2 }}>
            {/* eslint-disable-next-line @typescript-eslint/no-explicit-any */}
            {presetsData?.data?.presets?.map((preset: any) => (
              <Paper
                key={preset.expression}
                sx={{
                  p: 2,
                  cursor: 'pointer',
                  border: 1,
                  borderColor: 'divider',
                  '&:hover': {
                    backgroundColor: 'action.hover',
                    borderColor: 'primary.main',
                  },
                }}
                onClick={() => applyCronPreset(preset)}
              >
                <Stack direction="row" justifyContent="space-between" alignItems="center">
                  <Box>
                    <Typography variant="body2" fontWeight={500}>
                      {preset.name}
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {preset.description}
                    </Typography>
                  </Box>
                  <Chip
                    label={preset.expression}
                    size="small"
                    variant="outlined"
                    sx={{ fontFamily: 'monospace' }}
                  />
                </Stack>
              </Paper>
            ))}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowCronBuilder(false)}>Close</Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog
        open={!!deleteConfirmJob}
        onClose={() => setDeleteConfirmJob(null)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <Box
              sx={{
                width: 48,
                height: 48,
                borderRadius: '50%',
                backgroundColor: 'error.lighter',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <AlertCircle size={24} color="#d32f2f" />
            </Box>
            <Typography variant="h6" fontWeight={600}>
              Delete Scheduled Job
            </Typography>
          </Stack>
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Are you sure you want to delete the scheduled job{' '}
            <strong>"{deleteConfirmJob?.name}"</strong>?
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            This action cannot be undone. The job will no longer run automatically.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirmJob(null)}>Cancel</Button>
          <Button
            onClick={handleDeleteJob}
            variant="contained"
            color="error"
            disabled={deleteJobMutation.isPending}
            startIcon={
              deleteJobMutation.isPending ? <CircularProgress size={16} /> : <Trash2 size={16} />
            }
          >
            {deleteJobMutation.isPending ? 'Deleting...' : 'Delete Job'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Backup Job Logs Dialog */}
      <Dialog
        open={Boolean(selectedBackupJob)}
        onClose={() => setSelectedBackupJob(null)}
        maxWidth="lg"
        fullWidth
      >
        <DialogTitle>
          {selectedBackupJob && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h6">Backup Logs - Job #{selectedBackupJob.id}</Typography>
              <StatusBadge status={selectedBackupJob.status} />
            </Box>
          )}
        </DialogTitle>
        <DialogContent dividers>
          {selectedBackupJob && (
            <TerminalLogViewer
              jobId={String(selectedBackupJob.id)}
              status={selectedBackupJob.status}
              jobType="backup"
              showHeader={false}
              onFetchLogs={async (offset) => {
                const response = await fetch(
                  `/api/activity/backup/${selectedBackupJob.id}/logs?offset=${offset}&limit=500`,
                  {
                    headers: {
                      Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
                    },
                  }
                )
                if (!response.ok) {
                  throw new Error('Failed to fetch logs')
                }
                return response.json()
              }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setSelectedBackupJob(null)}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Schedule
