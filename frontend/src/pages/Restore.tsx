import React, { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
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
  Paper,
  Chip,
} from '@mui/material'
import {
  Database,
  Archive as ArchiveIcon,
  RefreshCw,
  CheckCircle,
  AlertCircle,
  Clock,
  RotateCcw,
} from 'lucide-react'
import { restoreAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { useMatomo } from '../hooks/useMatomo'
import { formatDate, formatBytes as formatBytesUtil, formatTimeRange } from '../utils/dateUtils'
import RepositoryInfo from '../components/RepositoryInfo'
import PathSelectorField from '../components/PathSelectorField'
import LockErrorDialog from '../components/LockErrorDialog'
import { Archive, Repository } from '../types'
import ArchiveBrowserDialog from '../components/ArchiveBrowserDialog'
import DataTable, { Column, ActionButton } from '../components/DataTable'

interface RestoreJob {
  id: number
  repository: string
  archive: string
  destination: string
  status: string
  started_at?: string
  completed_at?: string
  progress?: number
  error?: string
  progress_details?: {
    nfiles: number
    current_file: string
    progress_percent: number
  }
}

const Restore: React.FC = () => {
  const { trackArchive, EventAction } = useMatomo()
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [selectedRepoData, setSelectedRepoData] = useState<Repository | null>(null)
  const [restoreArchive, setRestoreArchive] = useState<Archive | null>(null)
  const [destination, setDestination] = useState<string>('')
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [showBrowser, setShowBrowser] = useState<boolean>(false)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)
  const queryClient = useQueryClient()
  const location = useLocation()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get archives for selected repository
  const {
    data: archives,
    isLoading: loadingArchives,
    error: archivesError,
  } = useQuery({
    queryKey: ['repository-archives', selectedRepoData?.id],
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepoData!.id),
    enabled: !!selectedRepoData?.id,
    retry: false,
  })

  // Handle archives error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (archivesError && (archivesError as any)?.response?.status === 423 && selectedRepoData) {
      setLockError({
        repositoryId: selectedRepoData.id,
        repositoryName: selectedRepoData.name,
      })
    }
  }, [archivesError, selectedRepoData])

  // Get repository info for statistics
  const { data: repoInfo, error: repoInfoError } = useQuery({
    queryKey: ['repository-info', selectedRepoData?.id],
    queryFn: () => repositoriesAPI.getRepositoryInfo(selectedRepoData!.id),
    enabled: !!selectedRepoData?.id,
    retry: false,
  })

  // Handle repo info error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (repoInfoError && (repoInfoError as any)?.response?.status === 423 && selectedRepoData) {
      setLockError({
        repositoryId: selectedRepoData.id,
        repositoryName: selectedRepoData.name,
      })
    }
  }, [repoInfoError, selectedRepoData])

  // Get archive-specific info
  const {
    data: archiveInfo,
    isLoading: loadingArchiveInfo,
    error: archiveInfoError,
  } = useQuery({
    queryKey: ['archive-info', selectedRepoData?.id, restoreArchive?.name],
    queryFn: () => repositoriesAPI.getArchiveInfo(selectedRepoData!.id, restoreArchive!.name),
    enabled: !!selectedRepoData && !!restoreArchive,
    retry: false,
  })

  // Handle archive info error
  React.useEffect(() => {
    if (
      archiveInfoError &&
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (archiveInfoError as any)?.response?.status === 423 &&
      selectedRepoData
    ) {
      setLockError({
        repositoryId: selectedRepoData.id,
        repositoryName: selectedRepoData.name,
      })
    }
  }, [archiveInfoError, selectedRepoData])

  // Get restore jobs with polling
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const { data: restoreJobsData } = useQuery<any>({
    queryKey: ['restore-jobs'],
    queryFn: restoreAPI.getRestoreJobs,
    refetchInterval: 1000, // Poll every 1 second
    staleTime: 0, // Always consider stale so refetchInterval works
    gcTime: 0, // Don't cache to ensure fresh data (was cacheTime in v3)
  })

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: ({
      repository,
      archive,
      destination,
      paths,
    }: {
      repository: string
      archive: string
      destination: string
      paths: string[]
    }) => restoreAPI.startRestore(repository, archive, paths, destination),
    onSuccess: () => {
      toast.success('Restore job started!')
      // Track restore started
      trackArchive(EventAction.START, selectedRepoData?.name)

      setRestoreArchive(null)
      setDestination('')
      setSelectedPaths([])

      // Refetch in background (don't await - let polling handle it)
      queryClient.refetchQueries({ queryKey: ['restore-jobs'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to start restore: ${error.response?.data?.detail || error.message}`)
    },
  })

  // Handle repository selection
  const handleRepositoryChange = (repoPath: string) => {
    setSelectedRepository(repoPath)
    const repo = repositories.find((r: Repository) => r.path === repoPath)
    setSelectedRepoData(repo || null)
    // Track archive listing (selecting a repo to filter/list its archives for restore)
    if (repo) {
      trackArchive(EventAction.FILTER, repo.name)
    }
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
        destination,
        paths: selectedPaths,
      })
    }
  }

  // Handle archive browser path selection
  const handlePathsSelected = (paths: string[]) => {
    setSelectedPaths(paths)
    setShowBrowser(false)
  }

  // Open archive browser when restore archive is set
  const handleRestoreArchiveClick = React.useCallback(
    (archive: Archive) => {
      setRestoreArchive(archive)
      setSelectedPaths([]) // Reset paths
      setShowBrowser(true)
      // Track viewing archive for restore
      trackArchive(EventAction.VIEW, selectedRepoData?.name)
    },
    [
      setRestoreArchive,
      setSelectedPaths,
      setShowBrowser,
      trackArchive,
      selectedRepoData,
      EventAction,
    ]
  )

  // Get repositories from API response
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const repositories = React.useMemo(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    () => (repositoriesData as any)?.repositories || [],
    [repositoriesData]
  )
  const archivesList = (archives?.data?.archives || []).sort((a: Archive, b: Archive) => {
    return new Date(b.start).getTime() - new Date(a.start).getTime()
  })

  // Handle incoming navigation state (from "Restore" button in Archives)
  useEffect(() => {
    if (location.state && repositories.length > 0) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const state = location.state as any
      if (state.repositoryPath && state.repositoryId) {
        // Set repository
        setSelectedRepository(state.repositoryPath)
        const repo = repositories.find((r: Repository) => r.id === state.repositoryId)
        setSelectedRepoData(repo || null)

        // Reset scroll position to top
        window.scrollTo(0, 0)
      }
    }
  }, [location.state, repositories])

  // Handle archive selection when archives are loaded
  useEffect(() => {
    if (location.state && archivesList.length > 0) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const state = location.state as any
      if (state.archiveName && selectedRepoData) {
        const archive = archivesList.find((a: Archive) => a.name === state.archiveName)
        if (archive) {
          // Auto-open the restore dialog for this archive
          handleRestoreArchiveClick(archive)
        }
      }
    }
  }, [archivesList, location.state, selectedRepoData, handleRestoreArchiveClick])

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

  const runningJobs =
    restoreJobsData?.data?.jobs?.filter(
      (job: RestoreJob) => job.status === 'running' || job.status === 'pending'
    ) || []
  const recentJobs = restoreJobsData?.data?.jobs?.slice(0, 10) || []

  // Archives table columns
  const archivesColumns: Column<Archive>[] = [
    {
      id: 'name',
      label: 'Archive Name',
      render: (archive) => (
        <Typography variant="body2" fontWeight={500}>
          {archive.name}
        </Typography>
      ),
    },
    {
      id: 'created',
      label: 'Created',
      render: (archive) => (
        <Typography variant="body2" color="text.secondary">
          {formatDate(archive.start)}
        </Typography>
      ),
    },
  ]

  // Archives table actions
  const archivesActions: ActionButton<Archive>[] = [
    {
      icon: <RotateCcw size={16} />,
      label: 'Restore',
      onClick: (archive) => handleRestoreArchiveClick(archive),
      color: 'primary',
      tooltip: 'Restore this archive',
    },
  ]

  // Recent Restore Jobs table columns
  const restoreJobsColumns: Column<RestoreJob>[] = [
    {
      id: 'id',
      label: 'Job ID',
      render: (job) => (
        <Typography variant="body2" fontWeight={600} color="primary">
          #{job.id}
        </Typography>
      ),
    },
    {
      id: 'archive',
      label: 'Archive',
      render: (job) => (
        <Typography variant="body2" fontWeight={500}>
          {job.archive}
        </Typography>
      ),
    },
    {
      id: 'destination',
      label: 'Destination',
      render: (job) => (
        <Typography
          variant="body2"
          color="text.secondary"
          sx={{ fontFamily: 'monospace', fontSize: '0.75rem' }}
        >
          {job.destination}
        </Typography>
      ),
    },
    {
      id: 'status',
      label: 'Status',
      render: (job) => (
        <Chip
          icon={getStatusIcon(job.status)}
          label={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
          color={getStatusColor(job.status)}
          size="small"
          sx={{ fontWeight: 500 }}
        />
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      render: (job) => (
        <Typography variant="body2" color="text.secondary">
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      ),
    },
    {
      id: 'started',
      label: 'Started',
      render: (job) => (
        <Typography variant="body2" color="text.secondary">
          {job.started_at ? formatDate(job.started_at) : 'N/A'}
        </Typography>
      ),
    },
  ]

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
            Select an archive below to restore its contents. The entire archive will be restored to
            the destination path you specify.
          </Alert>

          <Box sx={{ mb: 3 }}>
            <DataTable
              data={archivesList}
              columns={archivesColumns}
              actions={archivesActions}
              getRowKey={(archive) => archive.id}
              loading={loadingArchives}
              emptyState={{
                icon: <ArchiveIcon size={48} />,
                title: 'No archives found in this repository',
              }}
              headerBgColor="background.default"
              enableHover={true}
            />
          </Box>
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
                  <Stack
                    direction="row"
                    justifyContent="space-between"
                    alignItems="flex-start"
                    sx={{ mb: 2 }}
                  >
                    <Stack direction="row" spacing={2} alignItems="center">
                      <Box sx={{ color: 'info.main' }}>{getStatusIcon(job.status)}</Box>
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

                  <Box
                    sx={{
                      display: 'grid',
                      gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                      gap: 2,
                    }}
                  >
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
          <Stack
            direction="row"
            spacing={1.5}
            alignItems="center"
            sx={{ mb: 3, color: 'text.secondary' }}
          >
            <Clock size={20} />
            <Typography variant="h6" fontWeight={600}>
              Recent Restores
            </Typography>
          </Stack>

          <DataTable
            data={recentJobs}
            columns={restoreJobsColumns}
            getRowKey={(job) => job.id.toString()}
            emptyState={{
              icon: <Clock size={48} />,
              title: 'No restore jobs found',
            }}
            headerBgColor="background.default"
            enableHover={true}
            variant="outlined"
          />
        </CardContent>
      </Card>

      {/* Restore Dialog */}
      <Dialog
        open={!!restoreArchive}
        onClose={() => !restoreMutation.isPending && setRestoreArchive(null)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>
          <Stack direction="row" spacing={2} alignItems="center">
            <RotateCcw size={24} />
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
                    Size:{' '}
                    {archiveStats.original_size
                      ? formatBytesUtil(archiveStats.original_size)
                      : 'N/A'}
                  </Typography>
                </Alert>
              )}

              {selectedPaths.length > 0 ? (
                <Alert severity="success">
                  <Typography variant="body2" fontWeight={500} gutterBottom>
                    Selected Items ({selectedPaths.length})
                  </Typography>
                  <Box
                    sx={{
                      maxHeight: 150,
                      overflow: 'auto',
                      mt: 1,
                      p: 1,
                      bgcolor: 'background.default',
                      borderRadius: 1,
                      border: 1,
                      borderColor: 'divider',
                    }}
                  >
                    {selectedPaths.map((path, index) => (
                      <Typography
                        key={index}
                        variant="caption"
                        sx={{
                          display: 'block',
                          fontFamily: 'monospace',
                          fontSize: '0.7rem',
                          mb: 0.5,
                        }}
                      >
                        {path}
                      </Typography>
                    ))}
                  </Box>
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => setShowBrowser(true)}
                    sx={{ mt: 1 }}
                  >
                    Change Selection
                  </Button>
                </Alert>
              ) : (
                <Alert severity="warning">
                  <Typography variant="body2" fontWeight={500} gutterBottom>
                    Important
                  </Typography>
                  <Typography variant="body2">
                    This will restore the entire archive to the destination path. Existing files may
                    be overwritten.
                  </Typography>
                  <Button
                    size="small"
                    variant="text"
                    onClick={() => setShowBrowser(true)}
                    sx={{ mt: 1 }}
                  >
                    Select Specific Files/Folders
                  </Button>
                </Alert>
              )}

              <PathSelectorField
                label="Destination Path"
                value={destination}
                onChange={setDestination}
                placeholder="/path/to/restore/location"
                helperText="Select the directory where you want to restore the archive"
                disabled={restoreMutation.isPending}
                required
                selectMode="directories"
              />
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              trackArchive(EventAction.STOP, selectedRepoData?.name)
              setRestoreArchive(null)
            }}
            disabled={restoreMutation.isPending}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="primary"
            onClick={handleRestore}
            disabled={restoreMutation.isPending || !destination}
            startIcon={
              restoreMutation.isPending ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <RotateCcw size={16} />
              )
            }
          >
            {restoreMutation.isPending ? 'Starting...' : 'Start Restore'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Archive Browser Dialog */}
      {restoreArchive && selectedRepoData && (
        <ArchiveBrowserDialog
          open={showBrowser}
          onClose={() => setShowBrowser(false)}
          repositoryId={selectedRepoData.id}
          archiveName={restoreArchive.name}
          onSelect={handlePathsSelected}
          initialSelectedPaths={selectedPaths}
        />
      )}

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
            queryClient.invalidateQueries({ queryKey: ['archive-info', lockError.repositoryId] })
          }}
        />
      )}
    </Box>
  )
}

export default Restore
