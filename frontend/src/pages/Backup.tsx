import React, { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  CircularProgress,
  Stack,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableRow,
  Paper,
  Alert,
  Divider,
  alpha,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
} from '@mui/material'
import { Play, Square, Clock, Folder, Database, Info, RefreshCw, AlertCircle } from 'lucide-react'
import { backupAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import {
  formatTimeRange,
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
} from '../utils/dateUtils'
import { generateBorgCreateCommand } from '../utils/borgUtils'
import LockErrorDialog from '../components/LockErrorDialog'
import BackupJobsTable from '../components/BackupJobsTable'
import StatusBadge from '../components/StatusBadge'
import { TerminalLogViewer } from '../components/TerminalLogViewer'

interface BackupJob {
  id: string
  repository: string
  status: 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled'
  started_at: string
  completed_at?: string
  progress?: number
  total_files?: number
  processed_files?: number
  total_size?: string
  processed_size?: string
  error_message?: string
  has_logs?: boolean // Indicates if logs are available for this job
  triggered_by?: string // 'manual' or 'schedule'
  schedule_id?: number | null
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

const Backup: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)
  const [selectedJob, setSelectedJob] = useState<BackupJob | null>(null)
  const queryClient = useQueryClient()
  const location = useLocation()

  // Handle incoming navigation state (from "Backup Now" button)
  useEffect(() => {
    if (location.state && (location.state as any).repositoryPath) {
      setSelectedRepository((location.state as any).repositoryPath)
      // Reset scroll position to top
      window.scrollTo(0, 0)
    }
  }, [location.state])

  // Get backup status and history (manual backups only)
  const { data: backupStatus, isLoading: loadingStatus } = useQuery({
    queryKey: ['backup-status-manual'],
    queryFn: backupAPI.getManualJobs,
    refetchInterval: 1000, // Poll every 1 second for real-time updates
  })

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get selected repository details
  const selectedRepoData = useMemo(() => {
    if (!selectedRepository || !repositoriesData?.data?.repositories) return null
    return repositoriesData.data.repositories.find((repo: any) => repo.path === selectedRepository)
  }, [selectedRepository, repositoriesData])

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: (repository: string) => backupAPI.startBackup(repository),
    onSuccess: () => {
      toast.success('Backup started successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to start backup: ${error.response?.data?.detail || error.message}`)
    },
  })

  // Cancel backup mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success('Backup cancelled successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to cancel backup: ${error.response?.data?.detail || error.message}`)
    },
  })

  // Handle start backup
  const handleStartBackup = () => {
    if (!selectedRepository) {
      toast.error('Please select a repository first')
      return
    }
    startBackupMutation.mutate(selectedRepository)
  }

  // Handle cancel backup
  const handleCancelBackup = (jobId: string) => {
    cancelBackupMutation.mutate(jobId)
  }

  // Handle view logs
  const handleViewLogs = (job: BackupJob) => {
    setSelectedJob(job)
  }

  // Handle close logs dialog
  const handleCloseLogs = () => {
    setSelectedJob(null)
  }

  // Handle download logs
  const handleDownloadLogs = (job: any) => {
    try {
      backupAPI.downloadLogs(job.id)
      toast.success('Downloading logs...')
    } catch (error) {
      toast.error('Failed to download logs')
    }
  }

  // Format file size
  const formatFileSize = (size?: string) => {
    if (!size) return 'Unknown'
    return size
  }

  // Generate borg create command preview
  const getBorgBackupCommand = () => {
    if (!selectedRepoData) return 'Select a repository to see the command'

    return generateBorgCreateCommand({
      repositoryPath: selectedRepoData.path,
      compression: selectedRepoData.compression,
      excludePatterns: selectedRepoData.exclude_patterns,
      sourceDirs: selectedRepoData.source_directories,
      customFlags: selectedRepoData.custom_flags,
      remotePathFlag: selectedRepoData.remote_path
        ? `--remote-path ${selectedRepoData.remote_path} `
        : '',
    })
  }

  const runningJobs =
    backupStatus?.data?.jobs?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = backupStatus?.data?.jobs?.slice(0, 10) || []

  // Handle break lock action
  const handleBreakLock = async (job: BackupJob) => {
    const repoPath = job.error_message?.match(/LOCK_ERROR::(.+)/)?.[1].split('\n')[0]
    const repo = repositoriesData?.data?.repositories?.find((r: any) => r.path === repoPath)
    if (!repo) return

    if (
      window.confirm(
        'Are you CERTAIN no backup is currently running on this repository? Breaking the lock while a backup is running can corrupt your repository!'
      )
    ) {
      try {
        await repositoriesAPI.breakLock(repo.id)
        toast.success('Lock removed successfully! You can now start a new backup.')
        queryClient.invalidateQueries({ queryKey: ['backup-status'] })
      } catch (error: any) {
        toast.error(error.response?.data?.detail || 'Failed to break lock')
      }
    }
  }

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}
      >
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Backup Operations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage and monitor your backup jobs
          </Typography>
        </Box>
        <Stack direction="row" spacing={2} alignItems="center"></Stack>
      </Box>

      {/* Manual Backup Control */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
            <Play size={20} color="#2e7d32" />
            <Typography variant="h6" fontWeight={600}>
              Manual Backup
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Select a repository and start a backup job
          </Typography>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
            <FormControl fullWidth sx={{ minWidth: { xs: '100%', sm: 300 } }}>
              <InputLabel id="repository-select-label">Repository</InputLabel>
              <Select
                labelId="repository-select-label"
                id="repository-select"
                value={selectedRepository}
                onChange={(e) => setSelectedRepository(e.target.value)}
                label="Repository"
                disabled={loadingRepositories}
                sx={{ height: { xs: 48, sm: 56 } }}
              >
                <MenuItem value="" disabled>
                  {loadingRepositories ? 'Loading repositories...' : 'Select a repository...'}
                </MenuItem>
                {repositoriesData?.data?.repositories
                  ?.filter((repo: any) => repo.mode !== 'observe')
                  .map((repo: any) => (
                    <MenuItem
                      key={repo.id}
                      value={repo.path}
                      disabled={repo.has_running_maintenance}
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Database size={16} />
                        <Box>
                          <Typography variant="body2" fontWeight={500}>
                            {repo.name}
                            {repo.has_running_maintenance && (
                              <Typography
                                component="span"
                                variant="caption"
                                color="warning.main"
                                sx={{ ml: 1 }}
                              >
                                (Maintenance Running)
                              </Typography>
                            )}
                          </Typography>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontFamily: 'monospace' }}
                          >
                            {repo.path}
                          </Typography>
                        </Box>
                      </Stack>
                    </MenuItem>
                  ))}
              </Select>
            </FormControl>

            <Button
              variant="contained"
              color="success"
              size="large"
              startIcon={
                startBackupMutation.isPending ? (
                  <CircularProgress size={16} color="inherit" />
                ) : (
                  <Play size={18} />
                )
              }
              onClick={handleStartBackup}
              disabled={startBackupMutation.isPending || !selectedRepository}
              sx={{
                minWidth: { xs: '100%', sm: 180 },
                height: { xs: 48, sm: 56 },
                fontWeight: 600,
              }}
            >
              {startBackupMutation.isPending ? 'Starting...' : 'Start Backup'}
            </Button>
          </Stack>

          {repositoriesData?.data?.repositories?.some((repo: any) => repo.mode === 'observe') &&
            !loadingRepositories && (
              <Alert severity="info" sx={{ mt: 2 }}>
                <Typography variant="body2">
                  Some repositories are hidden because they are configured for observability only.
                  To create backups, switch them to full mode in Repository settings.
                </Typography>
              </Alert>
            )}

          {repositoriesData?.data?.repositories?.length === 0 && !loadingRepositories && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              <Typography variant="body2" fontWeight={500} gutterBottom>
                No Repositories Found
              </Typography>
              <Typography variant="body2">
                Create a repository in the Repositories page before starting a backup
              </Typography>
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Backup Context Card */}
      {selectedRepoData && (
        <Card sx={{ mb: 3, bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04) }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <Info size={20} color="#1976d2" />
              <Typography variant="h6" fontWeight={600}>
                Backup Overview
              </Typography>
            </Stack>

            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Here's what will be backed up and the current backup status
            </Typography>

            {/* Command Preview */}
            <Alert severity="info" sx={{ mb: 3 }}>
              <Typography variant="subtitle2" gutterBottom>
                Command Preview
              </Typography>
              <Box
                sx={{
                  bgcolor: 'grey.900',
                  color: 'grey.100',
                  p: 1.5,
                  borderRadius: 1,
                  fontFamily: 'monospace',
                  fontSize: '0.875rem',
                  overflow: 'auto',
                  whiteSpace: 'pre-wrap',
                  wordBreak: 'break-all',
                }}
              >
                {getBorgBackupCommand()}
              </Box>
            </Alert>

            <Stack spacing={3}>
              {/* Source Directories */}
              <Box>
                <Stack
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  sx={{ mb: 1.5, color: 'text.secondary' }}
                >
                  <Folder size={18} />
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                    Source Directories
                  </Typography>
                </Stack>
                {selectedRepoData.source_directories &&
                selectedRepoData.source_directories.length > 0 ? (
                  <Stack spacing={1} sx={{ pl: 3.5 }}>
                    {selectedRepoData.source_directories.map((dir: string, index: number) => (
                      <Chip
                        key={index}
                        label={dir}
                        size="small"
                        icon={<Folder size={14} />}
                        sx={{ justifyContent: 'flex-start', maxWidth: 'fit-content' }}
                      />
                    ))}
                  </Stack>
                ) : (
                  <Alert severity="warning" sx={{ ml: 3.5 }}>
                    No source directories configured for this repository
                  </Alert>
                )}
              </Box>

              {/* Exclude Patterns */}
              {selectedRepoData.exclude_patterns &&
                selectedRepoData.exclude_patterns.length > 0 && (
                  <>
                    <Divider />
                    <Box>
                      <Stack
                        direction="row"
                        spacing={1}
                        alignItems="center"
                        sx={{ mb: 1.5, color: 'text.secondary' }}
                      >
                        <AlertCircle size={18} />
                        <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                          Exclude Patterns
                        </Typography>
                      </Stack>
                      <Stack spacing={1} sx={{ pl: 3.5 }}>
                        {selectedRepoData.exclude_patterns.map((pattern: string, index: number) => (
                          <Chip
                            key={index}
                            label={pattern}
                            size="small"
                            color="warning"
                            sx={{ justifyContent: 'flex-start', maxWidth: 'fit-content' }}
                          />
                        ))}
                      </Stack>
                    </Box>
                  </>
                )}

              <Divider />

              {/* Repository Info */}
              <Box>
                <Stack
                  direction="row"
                  spacing={1}
                  alignItems="center"
                  sx={{ mb: 1.5, color: 'text.secondary' }}
                >
                  <Database size={18} />
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                    Backup Destination
                  </Typography>
                </Stack>
                <TableContainer sx={{ pl: 3.5 }}>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell
                          sx={{
                            fontWeight: 500,
                            color: 'text.secondary',
                            width: '30%',
                            border: 'none',
                            py: 0.5,
                          }}
                        >
                          Repository Name
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.name}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell
                          sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}
                        >
                          Path
                        </TableCell>
                        <TableCell
                          sx={{
                            border: 'none',
                            py: 0.5,
                            fontFamily: 'monospace',
                            fontSize: '0.875rem',
                          }}
                        >
                          {selectedRepoData.path}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell
                          sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}
                        >
                          Encryption
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.encryption || 'Unknown'}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell
                          sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}
                        >
                          Compression
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.compression || 'lz4'}
                        </TableCell>
                      </TableRow>
                    </TableBody>
                  </Table>
                </TableContainer>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Running Jobs */}
      {runningJobs.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Running Jobs
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Currently active backup operations
            </Typography>

            <Stack spacing={3}>
              {runningJobs.map((job: BackupJob) => (
                <Paper key={job.id} variant="outlined" sx={{ p: 3 }}>
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="flex-start"
                    sx={{ mb: 2 }}
                  >
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Box sx={{ color: 'info.main' }}>
                        <RefreshCw size={20} className="animate-spin" />
                      </Box>
                      <Box>
                        <Typography variant="body1" fontWeight={500}>
                          Backup Job {job.id}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Repository: {job.repository}
                        </Typography>
                      </Box>
                    </Stack>
                    <Button
                      variant="outlined"
                      color="error"
                      size="small"
                      startIcon={<Square size={16} />}
                      onClick={() => handleCancelBackup(job.id)}
                      disabled={cancelBackupMutation.isPending}
                    >
                      Cancel
                    </Button>
                  </Stack>

                  {/* Backup Stage Indicator */}
                  <Box sx={{ mb: 2 }}>
                    <Stack
                      direction="row"
                      justifyContent="space-between"
                      alignItems="center"
                      sx={{ mb: 1.5 }}
                    >
                      <Stack direction="row" spacing={1} alignItems="center">
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: 'info.main',
                            animation: 'pulse 2s ease-in-out infinite',
                            '@keyframes pulse': {
                              '0%, 100%': { opacity: 1 },
                              '50%': { opacity: 0.5 },
                            },
                          }}
                        />
                        <Typography variant="body2" fontWeight={500} color="info.main">
                          {(job.progress || 0) === 0
                            ? 'Initializing backup...'
                            : (job.progress || 0) >= 100
                              ? 'Finalizing...'
                              : 'Processing files...'}
                        </Typography>
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {formatTimeRange(job.started_at, job.completed_at, job.status)}
                      </Typography>
                    </Stack>
                  </Box>

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

                  {/* Job Details with Detailed Stats - Grid Layout to prevent overflow */}
                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: {
                        xs: '1fr',
                        sm: 'repeat(2, 1fr)',
                        md: 'repeat(3, 1fr)',
                        lg: 'repeat(4, 1fr)',
                      },
                      gap: 2,
                      width: '100%',
                    }}
                  >
                    <Box>
                      <Typography variant="body2" color="text.secondary">
                        Files Processed:
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {job.progress_details?.nfiles?.toLocaleString() ||
                          job.processed_files?.toLocaleString() ||
                          '0'}
                        {job.total_files && ` / ${job.total_files.toLocaleString()}`}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="body2" color="text.secondary">
                        Original Size:
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {job.progress_details?.original_size
                          ? formatBytesUtil(job.progress_details.original_size)
                          : formatFileSize(job.processed_size)}
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
                        {job.status === 'running' && job.progress_details?.backup_speed
                          ? `${job.progress_details.backup_speed.toFixed(2)} MB/s`
                          : 'N/A'}
                      </Typography>
                    </Box>
                    {(job.progress_details?.estimated_time_remaining || 0) > 0 && (
                      <Box>
                        <Typography variant="body2" color="text.secondary">
                          ETA:
                        </Typography>
                        <Typography variant="body2" fontWeight={500} color="success.main">
                          {formatDurationSeconds(
                            job.progress_details?.estimated_time_remaining || 0
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
              Recent Jobs
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            History of backup operations
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
            }}
            onViewLogs={handleViewLogs}
            onCancelJob={handleCancelBackup}
            onBreakLock={handleBreakLock}
            onDownloadLogs={handleDownloadLogs}
            getRowKey={(job) => job.id}
            headerBgColor="background.default"
            enableHover={true}
            emptyState={{
              icon: (
                <Box sx={{ color: 'text.disabled' }}>
                  <Clock size={48} />
                </Box>
              ),
              title: 'No backup jobs found',
            }}
          />
        </CardContent>
      </Card>

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          onLockBroken={() => {
            queryClient.invalidateQueries({
              queryKey: ['repository-archives', lockError.repositoryId],
            })
            queryClient.invalidateQueries({ queryKey: ['repository-info', lockError.repositoryId] })
          }}
        />
      )}

      {/* Logs Dialog */}
      <Dialog open={Boolean(selectedJob)} onClose={handleCloseLogs} maxWidth="lg" fullWidth>
        <DialogTitle>
          {selectedJob && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h6">Backup Logs - Job #{selectedJob.id}</Typography>
              <StatusBadge status={selectedJob.status} />
            </Box>
          )}
        </DialogTitle>
        <DialogContent dividers>
          {selectedJob && (
            <TerminalLogViewer
              jobId={String(selectedJob.id)}
              status={selectedJob.status}
              jobType="backup"
              showHeader={false}
              onFetchLogs={async (offset) => {
                const response = await fetch(
                  `/api/activity/backup/${selectedJob.id}/logs?offset=${offset}&limit=500`,
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
          <Button onClick={handleCloseLogs}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Backup
