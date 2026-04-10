import React, { useEffect, useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Card,
  CardContent,
  CircularProgress,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
  useTheme,
  alpha,
} from '@mui/material'
import {
  Clock,
  Eye,
  Info,
  Play,
  RefreshCw,
  Square,
  HardDrive,
  FileText,
  Archive,
  Zap,
  Activity,
  Database,
} from 'lucide-react'
import { backupAPI, repositoriesAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { toast } from 'react-hot-toast'
import {
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
  formatTimeRange,
} from '../utils/dateUtils'
import { translateBackendKey } from '../utils/translateBackendKey'
import { BackupJob, Repository } from '../types'
import BackupJobsTable from '../components/BackupJobsTable'
import RepoSelect from '../components/RepoSelect'
import LogViewerDialog from '../components/LogViewerDialog'
import CommandPreview from '../components/CommandPreview'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { usePermissions } from '../hooks/usePermissions'
import { getRepoCapabilities } from '../utils/repoCapabilities'
import { useTrackedJobOutcomes } from '../hooks/useTrackedJobOutcomes'
import { getJobDurationSeconds } from '../utils/analyticsProperties'

// Emerald green — matches the "Backup Now" button in RepositoryCard for visual continuity
const ACCENT_BACKUP = '#059669'

const Backup: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('')
  const [logJob, setLogJob] = useState<BackupJob | null>(null)
  const queryClient = useQueryClient()
  const location = useLocation()
  const { trackBackup, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageRepositoryOperations = hasGlobalPermission('repositories.manage_all')
  const permissions = usePermissions()
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const getVisibleRunningJobStats = (job: BackupJob) =>
    [
      {
        key: 'filesProcessed',
        label: t('backup.runningJobs.progress.filesProcessed'),
        value:
          job.progress_details?.nfiles?.toLocaleString() ||
          job.processed_files?.toLocaleString() ||
          '0',
      },
      {
        key: 'originalSize',
        label: t('backup.runningJobs.progress.originalSize'),
        value: job.progress_details?.original_size
          ? formatBytesUtil(job.progress_details.original_size)
          : formatFileSize(job.processed_size),
      },
      {
        key: 'compressed',
        label: t('backup.runningJobs.progress.compressed'),
        value:
          job.progress_details?.compressed_size !== undefined
            ? formatBytesUtil(job.progress_details.compressed_size)
            : null,
      },
      {
        key: 'deduplicated',
        label: t('backup.runningJobs.progress.deduplicated'),
        value:
          job.progress_details?.deduplicated_size !== undefined
            ? formatBytesUtil(job.progress_details.deduplicated_size)
            : null,
        valueColor: 'success.main',
      },
      {
        key: 'totalSourceSize',
        label: t('backup.runningJobs.progress.totalSourceSize'),
        value:
          job.progress_details?.total_expected_size && job.progress_details.total_expected_size > 0
            ? formatBytesUtil(job.progress_details.total_expected_size)
            : 'Unknown',
        valueColor: 'success.main',
      },
      {
        key: 'speed',
        label: t('backup.runningJobs.progress.speed'),
        value:
          job.status === 'running' && job.progress_details?.backup_speed
            ? `${job.progress_details.backup_speed.toFixed(2)} MB/s`
            : 'N/A',
        valueColor: 'primary.main',
      },
      {
        key: 'eta',
        label: t('backup.runningJobs.progress.eta'),
        value:
          (job.progress_details?.estimated_time_remaining || 0) > 0
            ? formatDurationSeconds(job.progress_details?.estimated_time_remaining || 0)
            : 'N/A',
        valueColor: 'success.main',
      },
    ].filter((stat) => stat.value !== null)

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
  const { data: backupStatusResponse, isLoading: loadingStatus } = useQuery({
    queryKey: ['backup-status-manual'],
    queryFn: backupAPI.getManualJobs,
    refetchInterval: 1000, // Poll every 1 second for real-time updates
  })
  const backupStatus = backupStatusResponse?.data?.jobs

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  // Get selected repository details
  const selectedRepoData = useMemo(() => {
    if (!selectedRepository || !repositoriesData?.data?.repositories) return null
    return repositoriesData.data.repositories.find(
      (repo: Repository) => repo.path === selectedRepository
    )
  }, [selectedRepository, repositoriesData])

  const canStartBackup = selectedRepoData ? permissions.canDo(selectedRepoData.id, 'backup') : false

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: () => {
      if (!selectedRepoData) {
        throw new Error('Repository not selected')
      }
      return new BorgApiClient(selectedRepoData).runBackup()
    },
    onSuccess: () => {
      toast.success(t('backup.toasts.started'))
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      trackBackup(EventAction.START, undefined, selectedRepoData || undefined)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backup.toasts.startFailed')
      )
    },
  })

  // Cancel backup mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success(t('backup.toasts.cancelled'))
      queryClient.invalidateQueries({ queryKey: ['backup-status-manual'] })
      trackBackup(EventAction.STOP, 'manual')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('backup.toasts.cancelFailed')
      )
    },
  })

  // Log viewer handlers
  const handleViewLogs = (job: BackupJob) => {
    setLogJob(job)
  }

  const handleCloseLogs = () => {
    setLogJob(null)
  }

  // Handle repository selection
  const handleRepositoryChange = (repoPath: string) => {
    setSelectedRepository(repoPath)
    const repo = repositoriesData?.data?.repositories?.find((r: Repository) => r.path === repoPath)
    if (repo) {
      trackBackup(EventAction.FILTER, undefined, repo)
    }
  }

  // Handle start backup
  const handleStartBackup = () => {
    if (!selectedRepository) {
      toast.error(t('backup.toasts.selectRepository'))
      return
    }
    startBackupMutation.mutate()
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

  const runningJobs = backupStatus?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = backupStatus || []

  useTrackedJobOutcomes<BackupJob>({
    jobs: recentJobs,
    onTerminal: (job) => {
      const repository = repositoriesData?.data?.repositories?.find(
        (repo: Repository) => repo.path === job.repository
      )
      const action =
        job.status === 'completed' || job.status === 'completed_with_warnings'
          ? EventAction.COMPLETE
          : EventAction.FAIL

      trackBackup(action, 'manual', repository ?? job.repository, {
        trigger: 'manual',
        job_id: job.id,
        status: job.status,
        has_logs: !!job.has_logs,
        maintenance_status: job.maintenance_status ?? null,
        duration_seconds: getJobDurationSeconds(job.started_at, job.completed_at),
        warning_count: job.status === 'completed_with_warnings' ? 1 : 0,
        error_present: !!job.error_message,
      })
    },
  })

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          mb: 4,
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'flex-start' },
          gap: 2,
        }}
      >
        <Box>
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
            <Typography variant="h4" fontWeight={600}>
              {t('backup.title')}
            </Typography>
            {repositoriesData?.data?.repositories?.some(
              (repo: Repository) => !getRepoCapabilities(repo).canBackup
            ) &&
              !loadingRepositories && (
                <Tooltip
                  title={t('backup.manualBackup.observeOnlyHidden')}
                  arrow
                  enterTouchDelay={0}
                  leaveTouchDelay={4000}
                >
                  <IconButton
                    size="small"
                    aria-label={t('backup.manualBackup.observeOnlyHidden')}
                    sx={{
                      color: 'text.disabled',
                      '&:hover': { color: 'text.secondary' },
                      p: 0,
                      display: 'flex',
                      alignItems: 'center',
                    }}
                  >
                    <Info size={16} />
                  </IconButton>
                </Tooltip>
              )}
          </Stack>
          <Typography variant="body2" color="text.secondary">
            {t('backup.subtitle')}
          </Typography>
        </Box>
        <Stack direction="row" spacing={2} alignItems="center"></Stack>
      </Box>

      {/* Manual Backup Control */}
      <Box sx={{ mb: 4 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
          <RepoSelect
            repositories={(repositoriesData?.data?.repositories ?? []).filter(
              // eslint-disable-next-line @typescript-eslint/no-explicit-any
              (repo: any) =>
                getRepoCapabilities(repo).canBackup && permissions.canDo(repo.id, 'backup')
            )}
            value={selectedRepository}
            onChange={(v) => handleRepositoryChange(v as string)}
            loading={loadingRepositories}
            valueKey="path"
            label={t('backup.manualBackup.repository')}
            loadingLabel={t('backup.manualBackup.loadingRepositories')}
            placeholderLabel={t('backup.manualBackup.selectRepository')}
            maintenanceLabel={t('backup.manualBackup.maintenanceRunning')}
          />

          <Button
            variant="contained"
            color="success"
            size="medium"
            startIcon={
              startBackupMutation.isPending ? (
                <CircularProgress size={16} color="inherit" />
              ) : (
                <Play size={18} />
              )
            }
            onClick={handleStartBackup}
            disabled={startBackupMutation.isPending || !selectedRepository || !canStartBackup}
            sx={{
              minWidth: { xs: '100%', sm: 160 },
              fontWeight: 600,
              flexShrink: 0,
            }}
          >
            {startBackupMutation.isPending
              ? t('backup.manualBackup.starting')
              : t('backup.manualBackup.startBackup')}
          </Button>
        </Stack>

        {repositoriesData?.data?.repositories?.length === 0 && !loadingRepositories && (
          <Alert severity="warning" sx={{ mt: 2 }}>
            <Typography variant="body2" fontWeight={500} gutterBottom>
              {t('backup.manualBackup.noRepositories.title')}
            </Typography>
            <Typography variant="body2">
              {t('backup.manualBackup.noRepositories.subtitle')}
            </Typography>
          </Alert>
        )}
      </Box>

      {/* Command Preview Card */}
      {selectedRepoData && (
        <CommandPreview
          mode="import"
          displayMode="backup-only"
          borgVersion={selectedRepoData.borg_version}
          repositoryPath={selectedRepoData.path}
          compression={selectedRepoData.compression}
          excludePatterns={selectedRepoData.exclude_patterns}
          sourceDirs={selectedRepoData.source_directories}
          customFlags={selectedRepoData.custom_flags ?? ''}
          remotePath={selectedRepoData.remote_path ?? ''}
          repositoryMode="full"
          dataSource="local"
        />
      )}

      {/* Running Jobs */}
      {runningJobs.length > 0 && (
        <Card sx={{ mb: 3 }}>
          <CardContent>
            {/* Section Header */}
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
              <Box sx={{ color: ACCENT_BACKUP, display: 'flex' }}>
                <RefreshCw size={16} className="animate-spin" />
              </Box>
              <Typography variant="h6" fontWeight={600}>
                {t('backup.runningJobs.title')}
              </Typography>
              <Box
                sx={{
                  px: 0.8,
                  py: 0.15,
                  borderRadius: '10px',
                  bgcolor: alpha(ACCENT_BACKUP, 0.1),
                  border: `1px solid ${alpha(ACCENT_BACKUP, 0.22)}`,
                }}
              >
                <Typography
                  sx={{
                    fontSize: '0.7rem',
                    fontWeight: 700,
                    color: ACCENT_BACKUP,
                    lineHeight: 1.5,
                  }}
                >
                  {runningJobs.length}
                </Typography>
              </Box>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
              {t('backup.runningJobs.subtitle')}
            </Typography>

            <Stack spacing={2}>
              {runningJobs.map((job: BackupJob) => {
                const visibleStats = getVisibleRunningJobStats(job)
                const progress = job.progress || 0
                const stageLabel =
                  progress === 0
                    ? t('backup.runningJobs.progress.initializing')
                    : progress >= 100
                      ? t('backup.runningJobs.progress.finalizing')
                      : t('backup.runningJobs.progress.processing')

                const statIconComponents = [
                  <FileText size={11} />,
                  <HardDrive size={11} />,
                  <Archive size={11} />,
                  <Zap size={11} />,
                  <Database size={11} />,
                  <Activity size={11} />,
                  <Clock size={11} />,
                ]
                const statColors = [
                  ACCENT_BACKUP,
                  theme.palette.primary.main,
                  theme.palette.secondary.main,
                  theme.palette.success.main,
                  theme.palette.warning.main,
                  theme.palette.primary.main,
                  theme.palette.success.main,
                ]

                return (
                  <Box
                    key={job.id}
                    sx={{
                      position: 'relative',
                      borderRadius: 2,
                      bgcolor: isDark ? alpha(ACCENT_BACKUP, 0.07) : alpha(ACCENT_BACKUP, 0.05),
                      overflow: 'hidden',
                      boxShadow: isDark
                        ? `inset 0 0 0 1px ${alpha('#fff', 0.05)}`
                        : `inset 0 0 0 1px ${alpha('#000', 0.04)}`,
                    }}
                  >
                    {/* Ambient glow blob */}
                    <Box
                      sx={{
                        position: 'absolute',
                        top: -60,
                        right: -40,
                        width: 200,
                        height: 140,
                        borderRadius: '50%',
                        bgcolor: alpha(ACCENT_BACKUP, isDark ? 0.1 : 0.05),
                        filter: 'blur(55px)',
                        pointerEvents: 'none',
                        animation: 'blobPulseJob 3s ease-in-out infinite',
                        '@keyframes blobPulseJob': {
                          '0%, 100%': { opacity: 1 },
                          '50%': { opacity: 0.25 },
                        },
                      }}
                    />

                    <Box sx={{ px: { xs: 1.75, sm: 2.25 }, pt: 2, pb: 2 }}>
                      {/* Header */}
                      <Box
                        sx={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'flex-start',
                          gap: 2,
                          mb: 2,
                          flexWrap: { xs: 'wrap', sm: 'nowrap' },
                        }}
                      >
                        {/* Left: Job identity */}
                        <Box sx={{ minWidth: 0, flex: 1 }}>
                          <Stack
                            direction="row"
                            spacing={0.75}
                            alignItems="center"
                            sx={{ mb: 0.5, flexWrap: 'wrap', gap: 0.5 }}
                          >
                            <Box
                              sx={{
                                width: 7,
                                height: 7,
                                borderRadius: '50%',
                                bgcolor: ACCENT_BACKUP,
                                flexShrink: 0,
                                animation: 'liveDot 2s ease-in-out infinite',
                                '@keyframes liveDot': {
                                  '0%, 100%': { opacity: 1, transform: 'scale(1)' },
                                  '50%': { opacity: 0.45, transform: 'scale(0.82)' },
                                },
                              }}
                            />
                            <Typography variant="body1" fontWeight={700} sx={{ lineHeight: 1.3 }}>
                              {t('backup.runningJobs.jobTitle', { id: job.id })}
                            </Typography>
                            <Box
                              sx={{
                                px: 0.8,
                                py: 0.2,
                                borderRadius: 0.75,
                                bgcolor: alpha(ACCENT_BACKUP, 0.1),
                                border: `1px solid ${alpha(ACCENT_BACKUP, 0.2)}`,
                              }}
                            >
                              <Typography
                                sx={{
                                  fontSize: '0.62rem',
                                  fontWeight: 700,
                                  color: ACCENT_BACKUP,
                                  lineHeight: 1,
                                  textTransform: 'uppercase',
                                  letterSpacing: '0.05em',
                                }}
                              >
                                {stageLabel}
                              </Typography>
                            </Box>
                          </Stack>
                          <Typography
                            sx={{
                              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                              fontSize: '0.69rem',
                              color: 'text.disabled',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                            }}
                          >
                            {job.repository}
                          </Typography>
                        </Box>

                        {/* Right: Actions */}
                        <Stack direction="row" spacing={0.75} alignItems="center" flexShrink={0}>
                          <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ display: { xs: 'none', sm: 'block' }, mr: 0.5 }}
                          >
                            {formatTimeRange(job.started_at, job.completed_at, job.status)}
                          </Typography>
                          <Button
                            variant="outlined"
                            size="small"
                            startIcon={<Eye size={13} />}
                            onClick={() => handleViewLogs(job)}
                            sx={{
                              height: 28,
                              fontSize: '0.75rem',
                              px: 1.25,
                              borderColor: alpha(ACCENT_BACKUP, 0.28),
                              color: ACCENT_BACKUP,
                              '&:hover': {
                                bgcolor: alpha(ACCENT_BACKUP, 0.07),
                                borderColor: alpha(ACCENT_BACKUP, 0.5),
                              },
                            }}
                          >
                            {t('backup.runningJobs.viewLogs')}
                          </Button>
                          <Button
                            variant="outlined"
                            size="small"
                            startIcon={<Square size={13} />}
                            color="error"
                            onClick={() => handleCancelBackup(String(job.id))}
                            disabled={cancelBackupMutation.isPending}
                            sx={{ height: 28, fontSize: '0.75rem', px: 1.25 }}
                          >
                            {t('backup.runningJobs.cancel')}
                          </Button>
                        </Stack>
                      </Box>

                      {/* Real progress bar — only shown when total source size is known */}
                      {(() => {
                        const processed = job.progress_details?.original_size ?? 0
                        const total = job.progress_details?.total_expected_size ?? 0
                        if (processed <= 0 || total <= 0) return null
                        const pct = Math.min(100, (processed / total) * 100)
                        return (
                          <Box sx={{ mb: 1.5 }}>
                            <Stack
                              direction="row"
                              justifyContent="space-between"
                              alignItems="center"
                              sx={{ mb: 0.5 }}
                            >
                              <Typography
                                sx={{
                                  fontSize: '0.68rem',
                                  fontWeight: 600,
                                  color: ACCENT_BACKUP,
                                  letterSpacing: '0.02em',
                                }}
                              >
                                {pct.toFixed(1)}%
                              </Typography>
                              <Typography sx={{ fontSize: '0.65rem', color: 'text.disabled' }}>
                                {t('backup.runningJobs.progress.totalSourceSize')}
                              </Typography>
                            </Stack>
                            <LinearProgress
                              variant="determinate"
                              value={pct}
                              sx={{
                                height: 4,
                                borderRadius: 2,
                                bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
                                '& .MuiLinearProgress-bar': {
                                  borderRadius: 2,
                                  bgcolor: ACCENT_BACKUP,
                                },
                              }}
                            />
                          </Box>
                        )
                      })()}

                      {/* Stats Band */}
                      {visibleStats.length > 0 && (
                        <Box
                          sx={{
                            display: 'grid',
                            gridTemplateColumns: {
                              xs: 'repeat(2, 1fr)',
                              sm: 'repeat(auto-fit, minmax(130px, 1fr))',
                            },
                            borderRadius: 1.5,
                            overflow: 'hidden',
                            mb: job.progress_details?.current_file ? 1.5 : 0,
                            bgcolor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                            gap: '1px',
                            // Orphan fix: last item alone in its row (odd position) spans both columns on mobile
                            '& > :last-child:nth-child(odd)': {
                              gridColumn: { xs: 'span 2', sm: 'auto' },
                            },
                          }}
                        >
                          {visibleStats.map((stat, i) => {
                            const statColor = statColors[i] ?? ACCENT_BACKUP
                            return (
                              <Box
                                key={stat.key}
                                sx={{
                                  px: 1.5,
                                  py: 1.1,
                                  bgcolor: isDark ? alpha(ACCENT_BACKUP, 0.04) : 'background.paper',
                                }}
                              >
                                <Box
                                  sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.35 }}
                                >
                                  <Box
                                    sx={{
                                      color: alpha(statColor, 0.7),
                                      display: 'flex',
                                      alignItems: 'center',
                                    }}
                                  >
                                    {statIconComponents[i]}
                                  </Box>
                                  <Typography
                                    sx={{
                                      fontSize: '0.58rem',
                                      fontWeight: 700,
                                      textTransform: 'uppercase',
                                      letterSpacing: '0.07em',
                                      color: alpha(statColor, 0.7),
                                      lineHeight: 1,
                                    }}
                                  >
                                    {stat.label}
                                  </Typography>
                                </Box>
                                <Typography
                                  variant="body2"
                                  fontWeight={600}
                                  noWrap
                                  sx={{
                                    fontVariantNumeric: 'tabular-nums',
                                    fontSize: '0.85rem',
                                    color: stat.valueColor || 'text.primary',
                                  }}
                                >
                                  {stat.value}
                                </Typography>
                              </Box>
                            )
                          })}
                        </Box>
                      )}

                      {/* Current File Terminal Box */}
                      {job.progress_details?.current_file && (
                        <Box
                          sx={{
                            px: 1.5,
                            py: 0.875,
                            borderRadius: 1,
                            bgcolor: isDark ? alpha('#000', 0.3) : alpha('#000', 0.03),
                            border: '1px solid',
                            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                            display: 'flex',
                            alignItems: 'center',
                            gap: 1,
                            overflow: 'hidden',
                          }}
                        >
                          <Box
                            sx={{
                              color: alpha(ACCENT_BACKUP, 0.65),
                              display: 'flex',
                              flexShrink: 0,
                            }}
                          >
                            <FileText size={13} />
                          </Box>
                          <Typography
                            sx={{
                              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                              fontSize: '0.72rem',
                              color: 'text.secondary',
                              overflow: 'hidden',
                              textOverflow: 'ellipsis',
                              whiteSpace: 'nowrap',
                              flex: 1,
                              minWidth: 0,
                            }}
                          >
                            {job.progress_details.current_file}
                          </Typography>
                        </Box>
                      )}
                    </Box>
                  </Box>
                )
              })}
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
              {t('backup.recentJobs.title')}
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            {t('backup.recentJobs.subtitle')}
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
            canBreakLocks={canManageRepositoryOperations}
            canDeleteJobs={canManageRepositoryOperations}
            getRowKey={(job) => String(job.id)}
            headerBgColor="background.default"
            enableHover={true}
            tableId="backup"
            emptyState={{
              icon: (
                <Box sx={{ color: 'text.disabled' }}>
                  <Clock size={48} />
                </Box>
              ),
              title: t('backup.recentJobs.empty'),
            }}
          />
        </CardContent>
      </Card>

      {/* Log Viewer Dialog */}
      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={handleCloseLogs} />
    </Box>
  )
}

export default Backup
