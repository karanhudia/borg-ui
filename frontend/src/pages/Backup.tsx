import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
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
  LinearProgress,
  CircularProgress,
  Stack,
  Chip,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Paper,
} from '@mui/material'
import {
  Play,
  Square,
  Clock,
  CheckCircle,
  AlertCircle,
  RefreshCw,
  FileText,
  HardDrive,
} from 'lucide-react'
import { backupAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useBackupProgress } from '../hooks/useSSE'
import TerminalLogViewer from '../components/TerminalLogViewer'

interface BackupJob {
  id: string
  repository: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  started_at: string
  completed_at?: string
  progress: number
  total_files?: number
  processed_files: number
  total_size?: string
  processed_size?: string
  error_message?: string
}

const Backup: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [showJobDetails, setShowJobDetails] = useState<string | null>(null)
  const queryClient = useQueryClient()

  // Real-time backup progress
  const { progress: realtimeProgress, isConnected } = useBackupProgress()

  // Get backup status and history
  const { data: backupStatus, isLoading: loadingStatus } = useQuery({
    queryKey: ['backup-status'],
    queryFn: backupAPI.getAllJobs,
    refetchInterval: realtimeProgress ? 0 : 5000 // Use real-time updates if available, otherwise poll
  })

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: (repository: string) => backupAPI.startBackup(repository),
    onSuccess: () => {
      toast.success('Backup started successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to start backup: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Cancel backup mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success('Backup cancelled successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to cancel backup: ${error.response?.data?.detail || error.message}`)
    }
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

  // Fetch logs for TerminalLogViewer
  const fetchJobLogs = async (jobId: string, offset: number) => {
    const response = await backupAPI.streamLogs(jobId, offset)
    return response.data
  }

  // Get status color for Chip
  const getStatusColor = (status: string): 'info' | 'success' | 'error' | 'default' => {
    switch (status) {
      case 'running':
        return 'info'
      case 'completed':
        return 'success'
      case 'failed':
        return 'error'
      case 'cancelled':
        return 'default'
      default:
        return 'default'
    }
  }

  // Get status icon
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <RefreshCw size={18} className="animate-spin" />
      case 'completed':
        return <CheckCircle size={18} />
      case 'failed':
        return <AlertCircle size={18} />
      case 'cancelled':
        return <Square size={18} />
      default:
        return <Clock size={18} />
    }
  }

  // Format file size
  const formatFileSize = (size?: string) => {
    if (!size) return 'Unknown'
    return size
  }

  // Format duration
  const formatDuration = (startTime: string, endTime?: string) => {
    const start = new Date(startTime)
    const end = endTime ? new Date(endTime) : new Date()
    const diff = Math.floor((end.getTime() - start.getTime()) / 1000)

    const hours = Math.floor(diff / 3600)
    const minutes = Math.floor((diff % 3600) / 60)
    const seconds = diff % 60

    if (hours > 0) {
      return `${hours}h ${minutes}m ${seconds}s`
    } else if (minutes > 0) {
      return `${minutes}m ${seconds}s`
    } else {
      return `${seconds}s`
    }
  }

  const runningJobs = backupStatus?.data?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = backupStatus?.data?.slice(0, 10) || []
  const selectedJob = recentJobs.find((j: BackupJob) => j.id === showJobDetails)

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4, display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            Backup Operations
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage and monitor your backup jobs
          </Typography>
        </Box>
        <Stack direction="row" spacing={2} alignItems="center">
          {/* Real-time connection status */}
          {isConnected ? (
            <Chip
              icon={<RefreshCw size={14} className="animate-spin" />}
              label="Live Updates"
              color="success"
              size="small"
            />
          ) : (
            <Chip
              icon={<Clock size={14} />}
              label="Polling"
              color="default"
              size="small"
            />
          )}

          <Button
            variant="outlined"
            startIcon={<RefreshCw size={18} />}
            onClick={() => queryClient.invalidateQueries({ queryKey: ['backup-status'] })}
          >
            Refresh
          </Button>
        </Stack>
      </Box>

      {/* Manual Backup Control */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            Manual Backup
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Start a new backup job
          </Typography>

          <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems={{ xs: 'stretch', sm: 'flex-end' }}>
            <FormControl fullWidth>
              <InputLabel>Repository</InputLabel>
              <Select
                value={selectedRepository}
                onChange={(e) => setSelectedRepository(e.target.value)}
                label="Repository"
                disabled={loadingRepositories}
              >
                <MenuItem value="">
                  {loadingRepositories ? 'Loading repositories...' : 'Select a repository...'}
                </MenuItem>
                {repositoriesData?.data?.repositories?.map((repo: any) => (
                  <MenuItem key={repo.id} value={repo.path}>
                    {repo.name} ({repo.path})
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Button
              variant="contained"
              color="success"
              startIcon={startBackupMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Play size={18} />}
              onClick={handleStartBackup}
              disabled={startBackupMutation.isLoading || !selectedRepository}
              sx={{ minWidth: 180 }}
            >
              {startBackupMutation.isLoading ? 'Starting...' : 'Start Backup'}
            </Button>
          </Stack>
        </CardContent>
      </Card>

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
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Box sx={{ color: 'info.main' }}>
                        {getStatusIcon(job.status)}
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
                      disabled={cancelBackupMutation.isLoading}
                    >
                      Cancel
                    </Button>
                  </Stack>

                  {/* Progress Bar */}
                  <Box sx={{ mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        Progress: {job.progress}%
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatDuration(job.started_at)}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={job.progress}
                      sx={{ height: 8, borderRadius: 1 }}
                    />
                  </Box>

                  {/* Job Details */}
                  <Stack direction="row" spacing={2}>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        Files:
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {job.processed_files.toLocaleString()}
                        {job.total_files && ` / ${job.total_files.toLocaleString()}`}
                      </Typography>
                    </Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" color="text.secondary">
                        Size:
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {formatFileSize(job.processed_size)}
                        {job.total_size && ` / ${formatFileSize(job.total_size)}`}
                      </Typography>
                    </Box>
                  </Stack>
                </Paper>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Recent Jobs */}
      <Card>
        <CardContent>
          <Typography variant="h6" fontWeight={600} gutterBottom>
            Recent Jobs
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            History of backup operations
          </Typography>

          {loadingStatus ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading backup history...
              </Typography>
            </Box>
          ) : recentJobs.length === 0 ? (
            <Box sx={{ textAlign: 'center', py: 8 }}>
              <FileText size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
              <Typography variant="body1" color="text.secondary">
                No backup jobs found
              </Typography>
            </Box>
          ) : (
            <TableContainer>
              <Table>
                <TableHead>
                  <TableRow>
                    <TableCell>Job ID</TableCell>
                    <TableCell>Repository</TableCell>
                    <TableCell>Status</TableCell>
                    <TableCell>Started</TableCell>
                    <TableCell>Duration</TableCell>
                    <TableCell>Progress</TableCell>
                    <TableCell>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recentJobs.map((job: BackupJob) => (
                    <TableRow key={job.id} hover>
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>
                          {job.id}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <HardDrive size={16} color="rgba(0,0,0,0.4)" />
                          <Typography variant="body2">{job.repository}</Typography>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Chip
                          icon={getStatusIcon(job.status)}
                          label={job.status}
                          color={getStatusColor(job.status)}
                          size="small"
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {new Date(job.started_at).toLocaleString()}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2">
                          {formatDuration(job.started_at, job.completed_at)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Box sx={{ width: 60 }}>
                            <LinearProgress
                              variant="determinate"
                              value={job.progress}
                              sx={{ height: 6, borderRadius: 1 }}
                            />
                          </Box>
                          <Typography variant="body2">{job.progress}%</Typography>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Stack direction="row" spacing={1}>
                          <Button
                            size="small"
                            onClick={() => setShowJobDetails(showJobDetails === job.id ? null : job.id)}
                          >
                            {showJobDetails === job.id ? 'Hide' : 'Details'}
                          </Button>
                          {job.status === 'running' && (
                            <Button
                              size="small"
                              color="error"
                              onClick={() => handleCancelBackup(job.id)}
                            >
                              Cancel
                            </Button>
                          )}
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Log Viewer Dialog */}
      {showJobDetails && selectedJob && (
        <Dialog
          open={!!showJobDetails}
          onClose={() => setShowJobDetails(null)}
          maxWidth="lg"
          fullWidth
        >
          <DialogTitle>
            Backup Job {selectedJob.id} Logs
          </DialogTitle>
          <DialogContent>
            <TerminalLogViewer
              jobId={selectedJob.id}
              status={selectedJob.status}
              onFetchLogs={(offset) => fetchJobLogs(selectedJob.id, offset)}
            />
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowJobDetails(null)}>Close</Button>
          </DialogActions>
        </Dialog>
      )}
    </Box>
  )
}

export default Backup
