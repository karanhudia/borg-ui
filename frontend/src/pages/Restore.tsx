import React, { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  CircularProgress,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stack,
  Alert,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Paper,
  Chip,
} from '@mui/material'
import {
  Download,
  Database,
  Archive as ArchiveIcon,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
} from 'lucide-react'
import { restoreAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate, formatBytes as formatBytesUtil, formatTimeRange } from '../utils/dateUtils'
import RepositoryInfo from '../components/RepositoryInfo'
import PathSelectorField from '../components/PathSelectorField'
import LockErrorDialog from '../components/LockErrorDialog'

interface Repository {
  id: number
  name: string
  path: string
  repository_type: 'local' | 'ssh'
  has_running_maintenance?: boolean
}

interface Archive {
  id: string
  archive: string
  name: string
  start: string
  time: string
}

interface RestoreJob {
  id: number
  repository: string
  archive: string
  destination: string
  status: string
  started_at?: string
  completed_at?: string
  progress: number
  error_message?: string
  progress_details?: {
    nfiles: number
    current_file: string
    progress_percent: number
  }
}

const Restore: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [selectedRepoData, setSelectedRepoData] = useState<Repository | null>(null)
  const [restoreArchive, setRestoreArchive] = useState<Archive | null>(null)
  const [destination, setDestination] = useState<string>('')
  const [lockError, setLockError] = useState<{ repositoryId: number, repositoryName: string } | null>(null)
  const queryClient = useQueryClient()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get archives for selected repository
  const { data: archives, isLoading: loadingArchives } = useQuery({
    queryKey: ['repository-archives', selectedRepoData?.id],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepoData!.id),
    enabled: !!selectedRepoData?.id,
    onError: (error: any) => {
      if (error?.response?.status === 423 && selectedRepoData) {
        setLockError({
          repositoryId: selectedRepoData.id,
          repositoryName: selectedRepoData.name
        })
      }
    },
    retry: false
  })

  // Get repository info for statistics
  const { data: repoInfo } = useQuery({
    queryKey: ['repository-info', selectedRepoData?.id],
    queryFn: () => repositoriesAPI.getRepositoryInfo(selectedRepoData!.id),
    enabled: !!selectedRepoData?.id,
    onError: (error: any) => {
      if (error?.response?.status === 423 && selectedRepoData) {
        setLockError({
          repositoryId: selectedRepoData.id,
          repositoryName: selectedRepoData.name
        })
      }
    },
    retry: false
  })

  // Get archive-specific info
  const { data: archiveInfo, isLoading: loadingArchiveInfo } = useQuery({
    queryKey: ['archive-info', selectedRepoData?.id, restoreArchive?.name],
    queryFn: () => repositoriesAPI.getArchiveInfo(selectedRepoData!.id, restoreArchive!.name),
    enabled: !!selectedRepoData && !!restoreArchive,
    onError: (error: any) => {
      if (error?.response?.status === 423 && selectedRepoData) {
        setLockError({
          repositoryId: selectedRepoData.id,
          repositoryName: selectedRepoData.name
        })
      }
    },
    retry: false
  })

  // Get restore jobs with polling
  const { data: restoreJobsData } = useQuery({
    queryKey: ['restore-jobs'],
    queryFn: restoreAPI.getRestoreJobs,
    refetchInterval: 1000, // Poll every 1 second
    staleTime: 0, // Always consider stale so refetchInterval works
    cacheTime: 0, // Don't cache to ensure fresh data
  })

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: ({ repository, archive, destination }: { repository: string; archive: string; destination: string }) =>
      restoreAPI.startRestore(repository, archive, [], destination),
    onSuccess: () => {
      toast.success('Restore job started!')

      setRestoreArchive(null)
      setDestination('')

      // Refetch in background (don't await - let polling handle it)
      queryClient.refetchQueries({ queryKey: ['restore-jobs'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to start restore: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle repository selection
  const handleRepositoryChange = (repoPath: string) => {
    setSelectedRepository(repoPath)
    const repo = repositories.find((r: Repository) => r.path === repoPath)
    setSelectedRepoData(repo || null)
  }

  // Handle restore
  const handleRestore = () => {
    if (!destination) {
      toast.error('Please select a destination path')
      return
    }
    if (selectedRepository && restoreArchive) {
      restoreMutation.mutate({
        repository: selectedRepository,
        archive: restoreArchive.name,
        destination
      })
    }
  }

  // Get repositories from API response
  const repositories = repositoriesData?.data?.repositories || []
  const archivesList = (archives?.data?.archives || []).sort((a: Archive, b: Archive) => {
    return new Date(b.start).getTime() - new Date(a.start).getTime()
  })

  // Get archive statistics
  const archiveStats = useMemo(() => {
    if (!archiveInfo?.data?.archive?.stats) return null
    return archiveInfo.data.archive.stats
  }, [archiveInfo])

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
      default:
        return <Clock size={18} />
    }
  }

  const runningJobs = restoreJobsData?.data?.jobs?.filter((job: RestoreJob) => job.status === 'running' || job.status === 'pending') || []
  const recentJobs = restoreJobsData?.data?.jobs?.slice(0, 10) || []

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Restore Archives
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Select an archive to restore from backup
        </Typography>
      </Box>

      {/* Repository Selector */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
            <Database size={20} color="#2e7d32" />
            <Typography variant="h6" fontWeight={600}>
              Select Repository
            </Typography>
          </Stack>
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
              {repositories.map((repo: Repository) => (
                <MenuItem key={repo.id} value={repo.path} disabled={repo.has_running_maintenance}>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <Database size={16} />
                    <Box>
                      <Typography variant="body2" fontWeight={500}>
                        {repo.name}
                        {repo.has_running_maintenance && <Typography component="span" variant="caption" color="warning.main" sx={{ ml: 1 }}>(Maintenance Running)</Typography>}
                      </Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
                        {repo.path}
                      </Typography>
                    </Box>
                  </Stack>
                </MenuItem>
              ))}
            </Select>
          </FormControl>
        </CardContent>
      </Card>

      {/* Repository Info */}
      {selectedRepoData && repoInfo?.data?.info && (
        <Box sx={{ mb: 3 }}>
          <RepositoryInfo
            repoInfo={repoInfo.data.info}
            archivesCount={archivesList.length}
            loading={loadingArchives}
          />
        </Box>
      )}

      {/* Archives Section */}
      {selectedRepository && (
        <>
          <Alert severity="info" sx={{ mb: 3 }}>
            Select an archive below to restore its contents. The entire archive will be restored to the destination path you specify.
          </Alert>

          {loadingArchives ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading archives...
              </Typography>
            </Box>
          ) : archivesList.length === 0 ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', py: 8 }}>
              <ArchiveIcon size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
              <Typography variant="body1" color="text.secondary">
                No archives found in this repository
              </Typography>
            </Box>
          ) : (
            <TableContainer component={Paper} sx={{ borderRadius: 2, mb: 3 }}>
              <Table>
                <TableHead>
                  <TableRow sx={{ bgcolor: 'grey.50' }}>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Archive Name</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Created</TableCell>
                    <TableCell align="right" sx={{ fontWeight: 600, color: 'text.secondary' }}>Actions</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {archivesList.map((archive: Archive) => (
                    <TableRow
                      key={archive.id}
                      hover
                      sx={{ '&:last-child td': { borderBottom: 0 } }}
                    >
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>
                          {archive.name}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {formatDate(archive.start)}
                        </Typography>
                      </TableCell>
                      <TableCell align="right">
                        <Button
                          variant="contained"
                          color="primary"
                          size="small"
                          startIcon={<Download size={16} />}
                          onClick={() => setRestoreArchive(archive)}
                          sx={{ textTransform: 'none' }}
                        >
                          Restore
                        </Button>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      {/* Running Jobs */}
      {runningJobs.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Active Restores
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Pending and running restore operations
            </Typography>

            <Stack spacing={3}>
              {runningJobs.map((job: RestoreJob) => (
                <Paper key={job.id} variant="outlined" sx={{ p: 3 }}>
                  <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2 }}>
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Box sx={{ color: 'info.main' }}>
                        {getStatusIcon(job.status)}
                      </Box>
                      <Box>
                        <Typography variant="body1" fontWeight={500}>
                          Restore Job #{job.id}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Archive: {job.archive}
                        </Typography>
                        <Typography variant="body2" color="text.secondary">
                          Destination: {job.destination}
                        </Typography>
                      </Box>
                    </Stack>
                  </Stack>

                  <Box sx={{ mb: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
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
                          Restoring files...
                        </Typography>
                      </Stack>
                      <Typography variant="body2" color="text.secondary">
                        {formatTimeRange(job.started_at, job.completed_at, job.status)}
                      </Typography>
                    </Stack>
                  </Box>

                  {job.progress_details?.current_file && (
                    <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
                      <Typography variant="caption" fontWeight={500}>
                        Current File:
                      </Typography>
                      <Typography variant="caption" sx={{ fontFamily: 'monospace', display: 'block', mt: 0.5, wordBreak: 'break-all' }}>
                        {job.progress_details.current_file}
                      </Typography>
                    </Alert>
                  )}

                  <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))', gap: 2 }}>
                    <Box>
                      <Typography variant="body2" color="text.secondary">
                        Files Restored:
                      </Typography>
                      <Typography variant="body2" fontWeight={500}>
                        {job.progress_details?.nfiles?.toLocaleString() || '0'}
                      </Typography>
                    </Box>
                    <Box>
                      <Typography variant="body2" color="text.secondary">
                        Progress:
                      </Typography>
                      <Typography variant="body2" fontWeight={500} color="primary.main">
                        {job.progress_details?.progress_percent?.toFixed(1) || '0'}%
                      </Typography>
                    </Box>
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
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 3 }}>
            <Clock size={20} color="rgba(0,0,0,0.6)" />
            <Typography variant="h6" fontWeight={600}>
              Recent Restores
            </Typography>
          </Stack>

          {recentJobs.length === 0 ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', py: 8 }}>
              <Clock size={48} color="rgba(0,0,0,0.3)" />
              <Typography variant="body1" color="text.secondary" sx={{ mt: 2 }}>
                No restore jobs found
              </Typography>
            </Box>
          ) : (
            <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
              <Table>
                <TableHead>
                  <TableRow sx={{ bgcolor: 'grey.50' }}>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Job ID</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Archive</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Destination</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Status</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Duration</TableCell>
                    <TableCell sx={{ fontWeight: 600, color: 'text.secondary' }}>Started</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {recentJobs.map((job: RestoreJob) => (
                    <TableRow
                      key={job.id}
                      hover
                      sx={{ '&:last-child td': { borderBottom: 0 } }}
                    >
                      <TableCell>
                        <Typography variant="body2" fontWeight={600} color="primary">
                          #{job.id}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" fontWeight={500}>
                          {job.archive}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary" sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}>
                          {job.destination}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Chip
                          icon={getStatusIcon(job.status)}
                          label={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
                          color={getStatusColor(job.status)}
                          size="small"
                          sx={{ fontWeight: 500 }}
                        />
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {formatTimeRange(job.started_at, job.completed_at, job.status)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" color="text.secondary">
                          {job.started_at ? formatDate(job.started_at) : 'N/A'}
                        </Typography>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Restore Dialog */}
      <Dialog
        open={!!restoreArchive}
        onClose={() => !restoreMutation.isLoading && setRestoreArchive(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <Download size={24} />
            <Box>
              <Typography variant="h6" fontWeight={600}>
                Restore Archive
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {restoreArchive?.name}
              </Typography>
            </Box>
          </Stack>
        </DialogTitle>
        <DialogContent>
          {loadingArchiveInfo ? (
            <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 4 }}>
              <CircularProgress size={48} />
              <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
                Loading archive details...
              </Typography>
            </Box>
          ) : (
            <Stack spacing={3}>
              {archiveStats && (
                <Alert severity="info">
                  <Typography variant="body2" fontWeight={500} gutterBottom>
                    Archive Information
                  </Typography>
                  <Typography variant="body2">
                    Files: {archiveStats.nfiles?.toLocaleString() || 'N/A'}
                  </Typography>
                  <Typography variant="body2">
                    Size: {archiveStats.original_size ? formatBytesUtil(archiveStats.original_size) : 'N/A'}
                  </Typography>
                </Alert>
              )}

              <Alert severity="warning">
                <Typography variant="body2" fontWeight={500} gutterBottom>
                  Important
                </Typography>
                <Typography variant="body2">
                  This will restore the entire archive to the destination path. Existing files may be overwritten.
                </Typography>
              </Alert>

              <PathSelectorField
                label="Destination Path"
                value={destination}
                onChange={setDestination}
                placeholder="/path/to/restore/location"
                helperText="Select the directory where you want to restore the archive"
                disabled={restoreMutation.isLoading}
                required
                selectMode="directories"
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRestoreArchive(null)} disabled={restoreMutation.isLoading}>
            Cancel
          </Button>
          <Button
            variant="contained"
            color="primary"
            onClick={handleRestore}
            disabled={restoreMutation.isLoading || !destination}
            startIcon={restoreMutation.isLoading ? <CircularProgress size={16} color="inherit" /> : <Download size={16} />}
          >
            {restoreMutation.isLoading ? 'Starting...' : 'Start Restore'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          onLockBroken={() => {
            queryClient.invalidateQueries(['repository-archives', lockError.repositoryId])
            queryClient.invalidateQueries(['repository-info', lockError.repositoryId])
            queryClient.invalidateQueries(['archive-info', lockError.repositoryId])
          }}
        />
      )}
    </Box>
  )
}

export default Restore
