import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Box, Typography, useTheme, alpha } from '@mui/material'
import { Folder } from 'lucide-react'
import { repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
import { useRepositoryStats } from '../hooks/useRepositoryStats'
import { BorgApiClient } from '../services/borgApi'
import { translateBackendKey } from '../utils/translateBackendKey'
import RepositorySelectorCard from '../components/RepositorySelectorCard'
import RepositoryStatsGrid from '../components/RepositoryStatsGrid'
import RepositoryStatsGridSkeleton from '../components/RepositoryStatsGridSkeleton'
import ArchivesList from '../components/ArchivesList'
import LastRestoreSection from '../components/LastRestoreSection'
import DeleteArchiveDialog from '../components/DeleteArchiveDialog'
import MountArchiveDialog from '../components/MountArchiveDialog'
import ArchiveContentsDialog from '../components/ArchiveContentsDialog'
import { toast } from 'react-hot-toast'
import MountSuccessToast from '../components/MountSuccessToast'
import { Archive, Repository } from '@/types'
import LockErrorDialog from '../components/LockErrorDialog'
import { useAnalytics } from '../hooks/useAnalytics'
import RestoreWizard, { RestoreData } from '../components/RestoreWizard'
import { getRepoCapabilities, getBorgVersion } from '../utils/repoCapabilities'
import { usePermissions } from '../hooks/usePermissions'
import { useTrackedJobOutcomes } from '../hooks/useTrackedJobOutcomes'
import { getArchiveAgeBucket, getJobDurationSeconds } from '../utils/analyticsProperties'

interface RestoreJob {
  id: number
  repository: string
  archive: string
  status: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

function getDefaultMountPoint(archiveName: string): string {
  return archiveName.replace(/[/:]/g, '_').replace(/\s+/g, '_')
}

function normalizeRepositoryId(value: number | string | null | undefined): number | null {
  if (typeof value === 'number' && Number.isFinite(value)) return value
  if (typeof value === 'string' && value.trim() !== '') {
    const parsed = Number.parseInt(value, 10)
    return Number.isFinite(parsed) ? parsed : null
  }
  return null
}

const Archives: React.FC = () => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const [searchParams, setSearchParams] = useSearchParams()
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(() => {
    return normalizeRepositoryId(searchParams.get('repo'))
  })
  const [viewArchive, setViewArchive] = useState<Archive | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
    borgVersion?: 1 | 2
  } | null>(null)
  const [mountDialogArchive, setMountDialogArchive] = useState<Archive | null>(null)
  const [customMountPoint, setCustomMountPoint] = useState<string>('')

  // Restore functionality
  const [restoreArchive, setRestoreArchive] = useState<Archive | null>(null)
  const [showRestoreWizard, setShowRestoreWizard] = useState<boolean>(false)

  const queryClient = useQueryClient()
  const location = useLocation()
  const { trackArchive, EventAction } = useAnalytics()
  const permissions = usePermissions()

  // Get repositories list
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = React.useMemo(
    () => repositoriesData?.data?.repositories || [],
    [repositoriesData]
  )
  const selectedRepository = React.useMemo(
    () =>
      selectedRepositoryId
        ? repositories.find((r: Repository) => r.id === selectedRepositoryId) || null
        : null,
    [repositories, selectedRepositoryId]
  )

  // Get repository info for statistics
  const {
    data: repoInfo,
    isLoading: loadingRepoInfo,
    error: repoInfoError,
    isPending: repoInfoPending,
  } = useQuery({
    queryKey: ['repository-info', selectedRepositoryId],
    queryFn: () => new BorgApiClient(selectedRepository!).getInfo(),
    enabled: !!selectedRepository,
    retry: false,
  })

  // Get archives for selected repository after repo info settles
  const {
    data: archives,
    isLoading: loadingArchives,
    error: archivesError,
  } = useQuery({
    queryKey: ['repository-archives', selectedRepositoryId],
    queryFn: () => new BorgApiClient(selectedRepository!).listArchives(),
    enabled: !!selectedRepository && !repoInfoPending,
    retry: false,
  })

  // Handle archives error
  React.useEffect(() => {
    const responseStatus = (archivesError as { response?: { status?: number } } | null)?.response
      ?.status
    if (responseStatus === 423 && selectedRepositoryId) {
      setLockError({
        repositoryId: selectedRepositoryId,
        repositoryName: selectedRepository?.name || 'Unknown',
        borgVersion: getBorgVersion(selectedRepository),
      })
    }
  }, [archivesError, selectedRepositoryId, selectedRepository])

  // Get restore jobs
  const { data: restoreJobsData } = useQuery({
    queryKey: ['restore-jobs'],
    queryFn: restoreAPI.getRestoreJobs,
    refetchInterval: 3000, // Refresh every 3 seconds for live progress
  })

  // Handle repo info error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (repoInfoError && (repoInfoError as any)?.response?.status === 423 && selectedRepositoryId) {
      setLockError({
        repositoryId: selectedRepositoryId,
        repositoryName: selectedRepository?.name || 'Unknown',
        borgVersion: getBorgVersion(selectedRepository),
      })
    }
  }, [repoInfoError, selectedRepositoryId, selectedRepository])

  // Delete archive mutation
  const deleteArchiveMutation = useMutation({
    mutationFn: ({ archive }: { repository: string; archive: string }) =>
      new BorgApiClient(selectedRepository!).deleteArchive(archive),
    onSuccess: (data) => {
      // Backend now returns job_id for background deletion
      toast.success(t('archives.deletionStarted', { id: data.data.job_id }))
      // Refresh archives list and repository stats after a delay to allow deletion to complete
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
        queryClient.invalidateQueries({ queryKey: ['repository-info', selectedRepositoryId] })
      }, 2000)
      setShowDeleteConfirm(null)
      trackArchive(EventAction.DELETE, selectedRepository || undefined)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('archives.toasts.deleteFailed')
      )
    },
  })

  // Mount archive mutation
  const mountArchiveMutation = useMutation({
    mutationFn: ({
      repository_id,
      archive_name,
      mount_point,
    }: {
      repository_id: number
      archive_name: string
      mount_point?: string
      archive_start?: string
      is_custom_mount_point: boolean
    }) => mountsAPI.mountBorgArchive({ repository_id, archive_name, mount_point }),
    onSuccess: (data, variables) => {
      const mountPoint = data.data.mount_point
      const containerName = 'borg-web-ui'
      const accessCommand = `docker exec -it ${containerName} bash -c "cd ${mountPoint} && bash"`

      toast.custom((t) => <MountSuccessToast toastId={t.id} command={accessCommand} />, {
        duration: 15000,
      })
      trackArchive(EventAction.MOUNT, selectedRepository || undefined, {
        operation: 'mount_archive',
        archive_age_bucket: getArchiveAgeBucket(variables.archive_start),
        uses_custom_mount_point: variables.is_custom_mount_point,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const errorDetail = translateBackendKey(error.response?.data?.detail) || error.message
      const isMountTimeout = errorDetail.toLowerCase().includes('mount timeout')

      if (isMountTimeout) {
        toast.error(t('archives.mountTimeout'), {
          duration: 10000,
          style: {
            maxWidth: '500px',
          },
        })
      } else {
        toast.error(t('archives.mountFailed', { error: errorDetail }))
      }
    },
  })

  // Restore mutation
  const restoreMutation = useMutation({
    mutationFn: ({
      repository,
      archive,
      destination,
      paths,
      repository_id,
      destination_type,
      destination_connection_id,
    }: {
      repository: string
      archive: string
      destination: string
      paths: string[]
      repository_id: number
      destination_type: string
      destination_connection_id: number | null
    }) =>
      restoreAPI.startRestore(
        repository,
        archive,
        paths,
        destination,
        repository_id,
        destination_type,
        destination_connection_id
      ),
    onSuccess: (_response, variables) => {
      toast.success(t('archives.restoreStarted'), {
        duration: 6000, // Show longer so user can read it
      })
      trackArchive(EventAction.START, selectedRepository || undefined, {
        operation: 'restore',
        destination_type: variables.destination_type,
        restore_path_count: variables.paths.length,
        uses_custom_destination: variables.destination !== '/',
        archive_age_bucket: getArchiveAgeBucket(restoreArchive?.start),
      })

      setRestoreArchive(null)
      setShowRestoreWizard(false)

      queryClient.refetchQueries({ queryKey: ['restore-jobs'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('archives.toasts.restoreFailed')
      )
    },
  })

  // Handle repository selection
  const handleRepositoryChange = (repositoryId: number) => {
    const normalizedRepositoryId = normalizeRepositoryId(repositoryId)
    setSelectedRepositoryId(normalizedRepositoryId)
    const repo = repositories.find((r: Repository) => r.id === normalizedRepositoryId)

    if (normalizedRepositoryId) {
      setSearchParams({ repo: String(normalizedRepositoryId) }, { replace: true })
    } else {
      setSearchParams({}, { replace: true })
    }
    // Track archive listing (selecting a repo to filter/list its archives)
    if (repo) {
      trackArchive(EventAction.FILTER, repo, { surface: 'archives_page' })
    }
  }

  // Handle archive deletion
  const handleDeleteArchive = (archive: string) => {
    if (selectedRepository) {
      deleteArchiveMutation.mutate({ repository: selectedRepository.path, archive })
    }
  }

  // Handle archive mounting
  const handleMountArchive = () => {
    if (selectedRepositoryId && mountDialogArchive) {
      const defaultMountPoint = getDefaultMountPoint(mountDialogArchive.name)
      mountArchiveMutation.mutate({
        repository_id: selectedRepositoryId,
        archive_name: mountDialogArchive.name,
        mount_point: customMountPoint || undefined,
        archive_start: mountDialogArchive.start,
        is_custom_mount_point: !!customMountPoint && customMountPoint !== defaultMountPoint,
      })
      setMountDialogArchive(null)
      setCustomMountPoint('')
    }
  }

  // Open mount dialog
  const openMountDialog = (archive: Archive) => {
    setMountDialogArchive(archive)
    // Pre-fill with archive name (sanitized for filesystem)
    setCustomMountPoint(getDefaultMountPoint(archive.name))
  }

  // Open restore wizard directly
  const handleRestoreArchiveClick = React.useCallback(
    (archive: Archive) => {
      setRestoreArchive(archive)
      setShowRestoreWizard(true)
      trackArchive(EventAction.VIEW, selectedRepository || undefined, {
        surface: 'restore_wizard',
        operation: 'select_archive',
        archive_age_bucket: getArchiveAgeBucket(archive.start),
      })
    },
    [selectedRepository, trackArchive, EventAction]
  )

  // Handle restore from wizard
  const handleRestoreFromWizard = (data: RestoreData) => {
    if (!selectedRepository || !restoreArchive) {
      toast.error(t('archives.toasts.notSelected'))
      return
    }

    // Determine destination based on restore strategy
    let destinationPath: string
    if (data.restore_strategy === 'custom' && data.custom_path) {
      destinationPath = data.custom_path
    } else {
      // For "original location", extract to root (/)
      destinationPath = '/'
    }

    restoreMutation.mutate({
      repository: selectedRepository.path,
      archive: restoreArchive.name,
      destination: destinationPath,
      paths: data.selected_paths,
      repository_id: selectedRepository.id,
      destination_type: data.destination_type,
      destination_connection_id: data.destination_connection_id,
    })

    setShowRestoreWizard(false)
  }

  useEffect(() => {
    // Handle incoming navigation state (from "View Archives" button)
    const stateRepoId = normalizeRepositoryId(
      (location.state as { repositoryId?: number | string | null } | null)?.repositoryId
    )
    if (stateRepoId) {
      setSelectedRepositoryId(stateRepoId)
      setSearchParams({ repo: String(stateRepoId) }, { replace: true })
      window.scrollTo(0, 0)
    }
  }, [location.state, setSearchParams])

  const archivesList = (archives?.data?.archives || []).sort((a: Archive, b: Archive) => {
    // Sort by start date (borg1) or time (borg2), latest first
    return new Date(b.start || b.time).getTime() - new Date(a.start || a.time).getTime()
  })

  const repositoryStats = useRepositoryStats(repoInfo?.data?.info, selectedRepository?.borg_version)

  // Get last restore job for selected repository
  const lastRestoreJob = React.useMemo(() => {
    if (!selectedRepository || !restoreJobsData?.data?.jobs) return null

    // Filter restore jobs for this repository and get the most recent one
    const repoJobs = restoreJobsData.data.jobs.filter(
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      (job: any) => job.repository === selectedRepository.path
    )

    return repoJobs.length > 0 ? repoJobs[0] : null
  }, [selectedRepository, restoreJobsData])

  // Handle viewing archive contents
  const handleViewArchive = (archive: Archive) => {
    setViewArchive(archive)
    trackArchive(EventAction.VIEW, selectedRepository || undefined, {
      surface: 'archive_contents',
      operation: 'open_archive',
      archive_age_bucket: getArchiveAgeBucket(archive.start),
    })
  }

  const handleRestoreArchive = (archive: Archive) => {
    // Open restore wizard flow instead of navigating to separate page
    handleRestoreArchiveClick(archive)
  }

  useTrackedJobOutcomes<RestoreJob>({
    jobs: restoreJobsData?.data?.jobs,
    onTerminal: (job) => {
      const action =
        job.status === 'completed' || job.status === 'completed_with_warnings'
          ? EventAction.COMPLETE
          : EventAction.FAIL
      const archiveStart = archivesList.find(
        (archive: Archive) => archive.name === job.archive
      )?.start

      trackArchive(action, selectedRepository ?? job.repository, {
        operation: 'restore',
        job_id: job.id,
        status: job.status,
        archive_age_bucket: getArchiveAgeBucket(archiveStart),
        duration_seconds: getJobDurationSeconds(job.started_at, job.completed_at),
        error_present: !!job.error_message,
      })
    },
  })

  const panelSx = {
    borderRadius: 3,
    border: '1px solid',
    borderColor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
    overflow: 'hidden',
  }

  return (
    <Box>
      {/* ── Compact header: title + repo selector inline ── */}
      <Box
        sx={{
          display: 'flex',
          alignItems: { xs: 'flex-start', sm: 'center' },
          flexDirection: { xs: 'column', sm: 'row' },
          gap: 2,
          mb: 3,
        }}
      >
        <Box sx={{ flex: 1, minWidth: 0 }}>
          <Typography variant="h5" fontWeight={700} sx={{ lineHeight: 1.3 }}>
            {t('archives.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('archives.subtitle')}
          </Typography>
        </Box>
        <Box sx={{ width: { xs: '100%', sm: '340px' }, flexShrink: 0 }}>
          <RepositorySelectorCard
            repositories={repositories}
            value={selectedRepositoryId}
            onChange={(v) => handleRepositoryChange(v as number)}
            loading={loadingRepositories}
            sx={{ mb: 0 }}
          />
        </Box>
      </Box>

      {/* ── No repository selected ── */}
      {!selectedRepositoryId && !loadingRepositories && (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            py: 8,
            color: 'text.secondary',
          }}
        >
          <Folder size={48} style={{ marginBottom: 16 }} />
          <Typography variant="body1" color="text.secondary">
            {repositories.length === 0
              ? t('archives.noRepositories')
              : t('archives.selectRepository')}
          </Typography>
        </Box>
      )}

      {/* ── Context panel: stats + last restore ── */}
      {selectedRepositoryId &&
        (loadingRepoInfo || repositoryStats || restoreJobsData?.data?.jobs) && (
          <Box sx={{ ...panelSx, mb: 3 }}>
            {/* Stats */}
            <Box sx={{ p: 2.5 }}>
              {loadingRepoInfo ? (
                <RepositoryStatsGridSkeleton />
              ) : repositoryStats ? (
                <RepositoryStatsGrid
                  stats={repositoryStats}
                  archivesCount={archivesList.length}
                  borgVersion={selectedRepository?.borg_version}
                  archivesLoading={loadingArchives || repoInfoPending}
                />
              ) : null}
            </Box>
            {/* Last Restore */}
            {restoreJobsData?.data?.jobs && (
              <Box
                sx={{
                  px: 2.5,
                  py: 2,
                  borderTop: '1px solid',
                  borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.06),
                  bgcolor: isDark ? alpha('#fff', 0.012) : alpha('#000', 0.01),
                }}
              >
                <LastRestoreSection restoreJob={lastRestoreJob} />
              </Box>
            )}
          </Box>
        )}

      {/* ── Archives list ── */}
      {selectedRepositoryId && (
        <ArchivesList
          archives={archivesList}
          repositoryName={selectedRepository?.name || ''}
          loading={loadingArchives || repoInfoPending}
          onViewArchive={handleViewArchive}
          onRestoreArchive={handleRestoreArchive}
          onMountArchive={openMountDialog}
          onDeleteArchive={(archiveName) => setShowDeleteConfirm(archiveName)}
          mountDisabled={mountArchiveMutation.isPending}
          canDelete={
            getRepoCapabilities({ mode: selectedRepository?.mode }).canDeleteArchive &&
            (selectedRepositoryId
              ? permissions.canDo(selectedRepositoryId, 'delete_archive')
              : false)
          }
        />
      )}

      {/* View Contents Modal */}
      <ArchiveContentsDialog
        open={!!viewArchive}
        archive={viewArchive}
        repository={selectedRepository ?? null}
        onClose={() => setViewArchive(null)}
        onDownloadFile={(archiveName, filePath) => {
          if (selectedRepository) {
            trackArchive(EventAction.DOWNLOAD, selectedRepository, {
              operation: 'download_archive_file',
              archive_age_bucket: getArchiveAgeBucket(viewArchive?.start),
            })
            const archiveRef =
              getBorgVersion(selectedRepository) === 2
                ? (viewArchive?.id ?? archiveName)
                : archiveName
            new BorgApiClient(selectedRepository).downloadFile(archiveRef, filePath)
          }
        }}
      />

      {/* Mount Archive Dialog */}
      <MountArchiveDialog
        open={!!mountDialogArchive}
        archive={mountDialogArchive}
        mountPoint={customMountPoint}
        onMountPointChange={setCustomMountPoint}
        onClose={() => setMountDialogArchive(null)}
        onConfirm={handleMountArchive}
        mounting={mountArchiveMutation.isPending}
      />

      {/* Delete Confirmation Dialog */}
      <DeleteArchiveDialog
        open={!!showDeleteConfirm}
        archiveName={showDeleteConfirm}
        onClose={() => setShowDeleteConfirm(null)}
        onConfirm={handleDeleteArchive}
        deleting={deleteArchiveMutation.isPending}
      />

      {/* Lock Error Dialog */}
      {lockError && (
        <LockErrorDialog
          open={!!lockError}
          onClose={() => setLockError(null)}
          repositoryId={lockError.repositoryId}
          repositoryName={lockError.repositoryName}
          borgVersion={lockError.borgVersion}
          onLockBroken={() => {
            // Invalidate queries to retry
            queryClient.invalidateQueries({
              queryKey: ['repository-archives', lockError.repositoryId],
            })
            queryClient.invalidateQueries({ queryKey: ['repository-info', lockError.repositoryId] })
          }}
        />
      )}

      {/* Restore Wizard */}
      {restoreArchive && selectedRepository && (
        <RestoreWizard
          open={showRestoreWizard}
          onClose={() => setShowRestoreWizard(false)}
          archiveName={restoreArchive.name}
          repositoryId={selectedRepository.id}
          repositoryType={selectedRepository.repository_type || 'local'}
          onRestore={handleRestoreFromWizard}
        />
      )}
    </Box>
  )
}

export default Archives
