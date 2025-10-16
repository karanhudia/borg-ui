import React, { useState, useMemo } from 'react'
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
  Alert,
  Divider,
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
  Folder,
  Database,
  Archive,
  Info,
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
  progress?: number
  total_files?: number
  processed_files?: number
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

  // Get selected repository details
  const selectedRepoData = useMemo(() => {
    if (!selectedRepository || !repositoriesData?.data?.repositories) return null
    return repositoriesData.data.repositories.find((repo: any) => repo.path === selectedRepository)
  }, [selectedRepository, repositoriesData])

  // Get archives for selected repository
  const { data: archivesData } = useQuery({
    queryKey: ['repository-archives', selectedRepoData?.id],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepoData.id),
    enabled: !!selectedRepoData?.id,
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

  // Format timestamp
  const formatTimestamp = (timestamp: string) => {
    if (!timestamp) return 'Never'
    const date = new Date(timestamp)
    return date.toLocaleString()
  }

  // Format time range (start and end only, no calculation)
  const formatTimeRange = (startTime: string, endTime?: string, status?: string) => {
    const start = new Date(startTime).toLocaleTimeString()

    if (status === 'running') {
      return `Started: ${start}`
    }

    if (!endTime) {
      return `Started: ${start}`
    }

    const end = new Date(endTime).toLocaleTimeString()
    return `${start} - ${end}`
  }

  const runningJobs = backupStatus?.data?.jobs?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = backupStatus?.data?.jobs?.slice(0, 10) || []
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

      {/* Backup Context Card */}
      {selectedRepoData && (
        <Card sx={{ mb: 3, bgcolor: 'rgba(25, 118, 210, 0.04)' }}>
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

            <Stack spacing={3}>
              {/* Source Directories */}
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                  <Folder size={18} color="rgba(0,0,0,0.6)" />
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                    Source Directories
                  </Typography>
                </Stack>
                {selectedRepoData.source_directories && selectedRepoData.source_directories.length > 0 ? (
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

              <Divider />

              {/* Repository Info */}
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                  <Database size={18} color="rgba(0,0,0,0.6)" />
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                    Backup Destination
                  </Typography>
                </Stack>
                <TableContainer sx={{ pl: 3.5 }}>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', width: '30%', border: 'none', py: 0.5 }}>
                          Repository Name
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>{selectedRepoData.name}</TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                          Path
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5, fontFamily: 'monospace', fontSize: '0.875rem' }}>
                          {selectedRepoData.path}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                          Encryption
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.encryption || 'Unknown'}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
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

              <Divider />

              {/* Backup Statistics */}
              <Box>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
                  <Archive size={18} color="rgba(0,0,0,0.6)" />
                  <Typography variant="subtitle2" fontWeight={600} color="text.secondary">
                    Backup Statistics
                  </Typography>
                </Stack>
                <TableContainer sx={{ pl: 3.5 }}>
                  <Table size="small">
                    <TableBody>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', width: '30%', border: 'none', py: 0.5 }}>
                          Last Backup
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.last_backup ? formatTimestamp(selectedRepoData.last_backup) : 'Never'}
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                          Total Archive Count
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.archive_count || 0} archives
                        </TableCell>
                      </TableRow>
                      <TableRow>
                        <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                          Total Repository Size
                        </TableCell>
                        <TableCell sx={{ border: 'none', py: 0.5 }}>
                          {selectedRepoData.total_size || 'Unknown'}
                        </TableCell>
                      </TableRow>
                      {archivesData?.data?.archives && archivesData.data.archives.length > 0 && (
                        <>
                          <TableRow>
                            <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                              Last Archive
                            </TableCell>
                            <TableCell sx={{ border: 'none', py: 0.5 }}>
                              {archivesData.data.archives[0].name}
                            </TableCell>
                          </TableRow>
                          <TableRow>
                            <TableCell sx={{ fontWeight: 500, color: 'text.secondary', border: 'none', py: 0.5 }}>
                              Last Archive Created
                            </TableCell>
                            <TableCell sx={{ border: 'none', py: 0.5 }}>
                              {formatTimestamp(archivesData.data.archives[0].start)}
                            </TableCell>
                          </TableRow>
                        </>
                      )}
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
                        Progress: {job.progress || 0}%
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        {formatTimeRange(job.started_at, job.completed_at, job.status)}
                      </Typography>
                    </Stack>
                    <LinearProgress
                      variant="determinate"
                      value={job.progress || 0}
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
                        {job.processed_files?.toLocaleString() || 'N/A'}
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
                          {formatTimeRange(job.started_at, job.completed_at, job.status)}
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
