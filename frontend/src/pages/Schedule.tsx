import React, { useState, useEffect } from 'react'
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
  Download,
  X,
} from 'lucide-react'
import { scheduleAPI, repositoriesAPI, backupAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import {
  formatDate,
  formatRelativeTime,
  formatTimeRange,
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
  convertCronToUTC,
  convertCronToLocal,
} from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from '../components/DataTable'
import ScheduledChecksSection from '../components/ScheduledChecksSection'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  repository: string | null
  enabled: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
  updated_at: string | null
  description: string | null
  archive_name_template: string | null
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
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  started_at: string
  completed_at?: string
  error_message?: string
  has_logs?: boolean
  maintenance_status?: string | null
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

  // Determine current tab from URL
  const getCurrentTab = () => {
    if (location.pathname === '/schedule/checks') return 1
    if (location.pathname === '/schedule/backups') return 0
    return 0 // default to backups
  }

  const [currentTab, setCurrentTab] = useState(getCurrentTab())
  const [showCreateModal, setShowCreateModal] = useState(false)
  const [editingJob, setEditingJob] = useState<ScheduledJob | null>(null)
  const [showCronBuilder, setShowCronBuilder] = useState(false)
  const [deleteConfirmJob, setDeleteConfirmJob] = useState<ScheduledJob | null>(null)

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
  }, [location.pathname])

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
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to create scheduled job')
    },
  })

  // Update job mutation
  const updateJobMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      scheduleAPI.updateScheduledJob(id, data),
    onSuccess: () => {
      toast.success('Scheduled job updated successfully')
      queryClient.invalidateQueries({ queryKey: ['scheduled-jobs'] })
      queryClient.invalidateQueries({ queryKey: ['upcoming-jobs'] })
      setEditingJob(null)
    },
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
    },
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
    },
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
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to run job')
    },
  })

  // Cancel backup job mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success('Backup cancelled successfully')
      queryClient.invalidateQueries({ queryKey: ['backup-jobs-scheduled'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to cancel backup')
    },
  })

  // Form states
  const [createForm, setCreateForm] = useState({
    name: '',
    cron_expression: '0 2 * * *',
    repository: '',
    enabled: true,
    description: '',
    archive_name_template: '{job_name}-{now}',
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
    enabled: true,
    description: '',
    archive_name_template: '',
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
      enabled: true,
      description: '',
      archive_name_template: '{job_name}-{now}',
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
    if (!createForm.repository) {
      toast.error('Please select a repository')
      return
    }
    // Convert cron expression from local time to UTC before sending to server
    const utcCron = convertCronToUTC(createForm.cron_expression)
    createJobMutation.mutate({
      ...createForm,
      cron_expression: utcCron,
    })
  }

  const handleUpdateJob = (e: React.FormEvent) => {
    e.preventDefault()
    if (!editForm.repository) {
      toast.error('Please select a repository')
      return
    }
    if (editingJob) {
      // Convert cron expression from local time to UTC before sending to server
      const utcCron = convertCronToUTC(editForm.cron_expression)
      updateJobMutation.mutate({
        id: editingJob.id,
        data: {
          ...editForm,
          cron_expression: utcCron,
        },
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

  const openCreateModal = () => {
    resetCreateForm()
    setShowCreateModal(true)
  }

  const openEditModal = (job: ScheduledJob) => {
    setEditingJob(job)
    // Convert UTC cron expression from server to local time for editing
    const localCron = convertCronToLocal(job.cron_expression)
    setEditForm({
      name: job.name,
      cron_expression: localCron,
      repository: job.repository || '',
      enabled: job.enabled,
      description: job.description || '',
      archive_name_template: job.archive_name_template || '{job_name}-{now}',
      run_prune_after: job.run_prune_after || false,
      run_compact_after: job.run_compact_after || false,
      prune_keep_hourly: job.prune_keep_hourly || 0,
      prune_keep_daily: job.prune_keep_daily || 7,
      prune_keep_weekly: job.prune_keep_weekly || 4,
      prune_keep_monthly: job.prune_keep_monthly || 6,
      prune_keep_quarterly: job.prune_keep_quarterly || 0,
      prune_keep_yearly: job.prune_keep_yearly || 1,
    })
  }

  const openCronBuilder = () => {
    setShowCronBuilder(true)
  }

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
    const repos = repositoriesData?.data?.repositories || []
    const repo = repos.find((r: any) => r.path === path)
    return repo?.name || path
  }

  const getBackupStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={18} />
      case 'running':
        return <Clock size={18} />
      case 'failed':
        return <XCircle size={18} />
      case 'cancelled':
        return <AlertCircle size={18} />
      default:
        return <Clock size={18} />
    }
  }

  const getBackupStatusColor = (
    status: string
  ): 'success' | 'info' | 'error' | 'warning' | 'default' => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'running':
        return 'info'
      case 'failed':
        return 'error'
      case 'cancelled':
        return 'warning'
      default:
        return 'default'
    }
  }

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
  const repositories = repositoriesData?.data?.repositories || []
  const allBackupJobs = backupJobsData?.data?.jobs || []
  const runningBackupJobs = allBackupJobs.filter(
    (job: BackupJob) =>
      job.status === 'running' ||
      (job.maintenance_status && job.maintenance_status.includes('running'))
  )
  const recentBackupJobs = allBackupJobs.slice(0, 10)
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
      render: (job) => (
        <>
          <Typography variant="body2">{getRepositoryName(job.repository || '')}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.7rem' }}>
            {job.repository}
          </Typography>
        </>
      ),
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
      icon: <Trash2 size={16} />,
      label: 'Delete',
      onClick: (job) => setDeleteConfirmJob(job),
      color: 'error',
      tooltip: 'Delete',
    },
  ]

  // Backup History Table Column Definitions
  const backupHistoryColumns: Column<BackupJob>[] = [
    {
      id: 'id',
      label: 'Job ID',
      render: (job) => (
        <Chip
          label={`#${job.id}`}
          size="small"
          variant="outlined"
          sx={{ fontFamily: 'monospace' }}
        />
      ),
    },
    {
      id: 'repository',
      label: 'Repository',
      render: (job) => (
        <>
          <Typography variant="body2">{getRepositoryName(job.repository)}</Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            {job.repository}
          </Typography>
          {job.maintenance_status && (
            <Box sx={{ mt: 0.5, display: 'flex', gap: 0.5, flexWrap: 'wrap' }}>
              {(job.maintenance_status.includes('prune') ||
                job.maintenance_status === 'maintenance_completed') && (
                <Chip
                  label={job.maintenance_status.includes('prune_failed') ? 'Prune ✗' : 'Prune ✓'}
                  size="small"
                  color={job.maintenance_status.includes('prune_failed') ? 'error' : 'success'}
                  variant="outlined"
                  sx={{ height: 18, fontSize: '0.65rem' }}
                />
              )}
              {(job.maintenance_status.includes('compact') ||
                job.maintenance_status === 'maintenance_completed') && (
                <Chip
                  label={
                    job.maintenance_status.includes('compact_failed') ? 'Compact ✗' : 'Compact ✓'
                  }
                  size="small"
                  color={job.maintenance_status.includes('compact_failed') ? 'error' : 'success'}
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
      id: 'status',
      label: 'Status',
      render: (job) => (
        <>
          <Chip
            icon={getBackupStatusIcon(job.status)}
            label={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
            size="small"
            color={getBackupStatusColor(job.status)}
            sx={{ minWidth: 100 }}
          />
          {job.maintenance_status && job.maintenance_status.includes('running') && (
            <Chip
              icon={<RefreshCw size={12} className="animate-spin" />}
              label={job.maintenance_status === 'running_prune' ? 'Pruning' : 'Compacting'}
              size="small"
              color="info"
              sx={{ minWidth: 90, mt: 0.5, display: 'block' }}
            />
          )}
        </>
      ),
    },
    {
      id: 'started_at',
      label: 'Started',
      render: (job) => (
        <>
          <Typography variant="body2">{formatDate(job.started_at)}</Typography>
          <Typography variant="caption" color="text.secondary">
            {formatRelativeTime(job.started_at)}
          </Typography>
        </>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      render: (job) => (
        <Typography variant="body2">
          {job.completed_at ? formatTimeRange(job.started_at, job.completed_at) : 'Running...'}
        </Typography>
      ),
    },
  ]

  // Backup History Table Action Buttons
  const backupHistoryActions: ActionButton<BackupJob>[] = [
    {
      icon: <X size={16} />,
      label: 'Cancel Backup',
      onClick: (job) => {
        if (window.confirm('Are you sure you want to cancel this backup?')) {
          cancelBackupMutation.mutate(job.id)
        }
      },
      color: 'error',
      disabled: () => cancelBackupMutation.isPending,
      show: (job) => job.status === 'running',
    },
    {
      icon: <Download size={16} />,
      label: 'Download Logs',
      onClick: (job) => backupAPI.downloadLogs(job.id),
      color: 'primary',
      show: (job) => !!job.has_logs,
    },
    {
      icon: <AlertCircle size={16} />,
      label: 'Error',
      onClick: () => {},
      color: 'error',
      show: (job) => !!job.error_message,
      tooltip: (job) => job.error_message || 'Error',
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
          {/* Action Button */}
          <Box sx={{ mb: 3, display: 'flex', justifyContent: 'flex-end' }}>
            <Button
              variant="contained"
              startIcon={<Plus size={18} />}
              onClick={openCreateModal}
              disabled={repositories.length === 0}
            >
              Create Backup Schedule
            </Button>
          </Box>

          {/* No repositories warning */}
          {repositories.length === 0 && (
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
                          {getRepositoryName(job.repository)}
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
                Recent backup jobs from scheduled tasks
              </Typography>

              <DataTable
                data={recentBackupJobs}
                columns={backupHistoryColumns}
                actions={backupHistoryActions}
                getRowKey={(job) => job.id}
                loading={loadingBackupJobs}
                enableHover={true}
                headerBgColor="background.default"
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
          <ScheduledChecksSection />
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

              <FormControl fullWidth required size="medium">
                <InputLabel sx={{ fontSize: '1.1rem' }}>Repository</InputLabel>
                <Select
                  value={createForm.repository}
                  onChange={(e) => setCreateForm({ ...createForm, repository: e.target.value })}
                  label="Repository"
                  sx={{ fontSize: '1.1rem', height: { xs: 48, sm: 56 } }}
                  MenuProps={{
                    PaperProps: {
                      style: {
                        maxHeight: 400,
                      },
                    },
                  }}
                >
                  {repositories
                    .filter((repo: any) => repo.mode !== 'observe')
                    .map((repo: any) => (
                      <MenuItem key={repo.id} value={repo.path} sx={{ fontSize: '1rem' }}>
                        <Box>
                          <Typography variant="body2" sx={{ fontSize: '1rem' }}>
                            {repo.name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontSize: '0.85rem' }}
                          >
                            {repo.path}
                          </Typography>
                        </Box>
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>

              {repositories.some((repo: any) => repo.mode === 'observe') && (
                <Alert severity="info">
                  Observability-only repositories cannot be used for scheduled backups.
                </Alert>
              )}

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
                          const value = parseInt(e.target.value, 10);
                          setCreateForm({
                            ...createForm,
                            prune_keep_hourly: isNaN(value) ? 0 : Math.max(0, value),
                          });
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
                          const value = parseInt(e.target.value, 10);
                          setCreateForm({
                            ...createForm,
                            prune_keep_quarterly: isNaN(value) ? 0 : Math.max(0, value),
                          });
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

              <FormControl fullWidth required size="medium">
                <InputLabel sx={{ fontSize: '1.1rem' }}>Repository</InputLabel>
                <Select
                  value={editForm.repository}
                  onChange={(e) => setEditForm({ ...editForm, repository: e.target.value })}
                  label="Repository"
                  sx={{ fontSize: '1.1rem', height: { xs: 48, sm: 56 } }}
                  MenuProps={{
                    PaperProps: {
                      style: {
                        maxHeight: 400,
                      },
                    },
                  }}
                >
                  {repositories
                    .filter((repo: any) => repo.mode !== 'observe')
                    .map((repo: any) => (
                      <MenuItem key={repo.id} value={repo.path} sx={{ fontSize: '1rem' }}>
                        <Box>
                          <Typography variant="body2" sx={{ fontSize: '1rem' }}>
                            {repo.name}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontSize: '0.85rem' }}
                          >
                            {repo.path}
                          </Typography>
                        </Box>
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>

              {repositories.some((repo: any) => repo.mode === 'observe') && (
                <Alert severity="info">
                  Observability-only repositories cannot be used for scheduled backups.
                </Alert>
              )}

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
                          const value = parseInt(e.target.value, 10);
                          setEditForm({
                            ...editForm,
                            prune_keep_hourly: isNaN(value) ? 0 : Math.max(0, value),
                          });
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
                          const value = parseInt(e.target.value, 10);
                          setEditForm({
                            ...editForm,
                            prune_keep_quarterly: isNaN(value) ? 0 : Math.max(0, value),
                          });
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
    </Box>
  )
}

export default Schedule
