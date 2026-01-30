import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import {
  Alert,
  alpha,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  FormControl,
  InputLabel,
  MenuItem,
  Paper,
  Select,
  Stack,
  Typography,
} from '@mui/material'
import { Clock, Database, Info, Play, RefreshCw, Square } from 'lucide-react'
import { backupAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import {
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
  formatTimeRange,
  parseBytes,
} from '../utils/dateUtils'
import { generateBorgCreateCommand } from '../utils/borgUtils'
import LockErrorDialog from '../components/LockErrorDialog'
import { BackupJob } from '../types'
import BackupJobsTable from '../components/BackupJobsTable'
import { useMatomo } from '../hooks/useMatomo'
import { useAuth } from '../hooks/useAuth'

const Backup: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)
  const queryClient = useQueryClient()
  const location = useLocation()
  const { trackBackup, EventAction } = useMatomo()
  const { user } = useAuth()

  // Handle incoming navigation state (from "Backup Now" button)
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (location.state && (location.state as any).repositoryPath) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return repositoriesData.data.repositories.find((repo: any) => repo.path === selectedRepository)
  }, [selectedRepository, repositoriesData])

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: (repository: string) => backupAPI.startBackup(repository),
    onSuccess: () => {
      toast.success('Backup started successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      trackBackup(
        EventAction.START,
        undefined,
        selectedRepoData?.name,
        parseBytes(selectedRepoData?.total_size)
      )
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
      trackBackup(EventAction.STOP, 'manual')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to cancel backup: ${error.response?.data?.detail || error.message}`)
    },
  })

  // Handle repository selection
  const handleRepositoryChange = (repoPath: string) => {
    setSelectedRepository(repoPath)
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const repo = repositoriesData?.data?.repositories?.find((r: any) => r.path === repoPath)
    if (repo) {
      trackBackup(EventAction.FILTER, undefined, repo.name)
    }
  }

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
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
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
                onChange={(e) => handleRepositoryChange(e.target.value)}
                label="Repository"
                disabled={loadingRepositories}
                sx={{ height: { xs: 48, sm: 56 } }}
              >
                <MenuItem value="" disabled>
                  {loadingRepositories ? 'Loading repositories...' : 'Select a repository...'}
                </MenuItem>
                {repositoriesData?.data?.repositories
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  ?.filter((repo: any) => repo.mode !== 'observe')
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
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

          {
            // eslint-disable-next-line @typescript-eslint/no-explicit-any
            repositoriesData?.data?.repositories?.some((repo: any) => repo.mode === 'observe') &&
              !loadingRepositories && (
                <Alert severity="info" sx={{ mt: 2 }}>
                  <Typography variant="body2">
                    Some repositories are hidden because they are configured for observability only.
                    To create backups, switch them to full mode in Repository settings.
                  </Typography>
                </Alert>
              )
          }

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

      {/* Command Preview Card */}
      {selectedRepoData && (
        <Card sx={{ mb: 3, bgcolor: (theme) => alpha(theme.palette.primary.main, 0.04) }}>
          <CardContent>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
              <Info size={20} color="#1976d2" />
              <Typography variant="h6" fontWeight={600}>
                Command Preview
              </Typography>
            </Stack>
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
                      onClick={() => handleCancelBackup(String(job.id))}
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
              errorInfo: true,
              delete: true,
            }}
            onBreakLock={handleBreakLock}
            isAdmin={user?.is_admin || false}
            getRowKey={(job) => String(job.id)}
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
    </Box>
  )
}

export default Backup
