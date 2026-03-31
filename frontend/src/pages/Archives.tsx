import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Box, Typography, CircularProgress } from '@mui/material'
import { Folder } from 'lucide-react'
import { archivesAPI, repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
import { useRepositoryStats } from '../hooks/useRepositoryStats'
import { BorgApiClient } from '../services/borgApi'
import { translateBackendKey } from '../utils/translateBackendKey'
import RepositorySelectorCard from '../components/RepositorySelectorCard'
import RepositoryStatsGrid from '../components/RepositoryStatsGrid'
import ArchivesList from '../components/ArchivesList'
import LastRestoreSection from '../components/LastRestoreSection'
import DeleteArchiveDialog from '../components/DeleteArchiveDialog'
import MountArchiveDialog from '../components/MountArchiveDialog'
import ArchiveContentsDialog from '../components/ArchiveContentsDialog'
import { toast } from 'react-hot-toast'
import { Archive, Repository } from '@/types'
import LockErrorDialog from '../components/LockErrorDialog'
import { useAnalytics } from '../hooks/useAnalytics'
import RestoreWizard, { RestoreData } from '../components/RestoreWizard'
import { getRepoCapabilities, getBorgVersion } from '../utils/repoCapabilities'

const Archives: React.FC = () => {
  const { t } = useTranslation()
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
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
    queryKey: ['repository-archives', selectedRepositoryId],
    queryFn: () => new BorgApiClient(selectedRepository!).listArchives(),
    enabled: !!selectedRepository,
    retry: false,
  })

  // Handle archives error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (archivesError && (archivesError as any)?.response?.status === 423 && selectedRepositoryId) {
      setLockError({
        repositoryId: selectedRepositoryId,
        repositoryName: selectedRepository?.name || 'Unknown',
        borgVersion: getBorgVersion(selectedRepository),
      })
    }
  }, [archivesError, selectedRepositoryId, selectedRepository])

  // Get repository info for statistics
  const {
    data: repoInfo,
    isLoading: loadingRepoInfo,
    error: repoInfoError,
  } = useQuery({
    queryKey: ['repository-info', selectedRepositoryId],
    queryFn: () => new BorgApiClient(selectedRepository!).getInfo(),
    enabled: !!selectedRepository,
    retry: false,
  })

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
    mutationFn: ({ repository, archive }: { repository: string; archive: string }) =>
      archivesAPI.deleteArchive(repository, archive),
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
    }) => mountsAPI.mountBorgArchive({ repository_id, archive_name, mount_point }),
    onSuccess: (data) => {
      const mountPoint = data.data.mount_point
      const containerName = 'borg-web-ui'
      const accessCommand = `docker exec -it ${containerName} bash -c "cd ${mountPoint} && bash"`

      toast.success(t('archives.mountSuccess', { command: accessCommand }), {
        duration: 15000,
        style: {
          maxWidth: '600px',
          whiteSpace: 'pre-wrap',
          fontFamily: 'monospace',
          fontSize: '13px',
        },
      })
      trackArchive(EventAction.MOUNT, selectedRepository || undefined)
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
    onSuccess: () => {
      toast.success(t('archives.restoreStarted'), {
        duration: 6000, // Show longer so user can read it
      })
      trackArchive(EventAction.START, selectedRepository || undefined)

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
    setSelectedRepositoryId(repositoryId)
    const repo = repositories.find((r: Repository) => r.id === repositoryId)
    setSelectedRepository(repo || null)
    // Track archive listing (selecting a repo to filter/list its archives)
    if (repo) {
      trackArchive(EventAction.FILTER, repo)
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
      mountArchiveMutation.mutate({
        repository_id: selectedRepositoryId,
        archive_name: mountDialogArchive.name,
        mount_point: customMountPoint || undefined,
      })
      setMountDialogArchive(null)
      setCustomMountPoint('')
    }
  }

  // Open mount dialog
  const openMountDialog = (archive: Archive) => {
    setMountDialogArchive(archive)
    // Pre-fill with archive name (sanitized for filesystem)
    const safeName = archive.name.replace(/[/:]/g, '_').replace(/\s+/g, '_')
    setCustomMountPoint(safeName)
  }

  // Open restore wizard directly
  const handleRestoreArchiveClick = React.useCallback(
    (archive: Archive) => {
      setRestoreArchive(archive)
      setShowRestoreWizard(true)
      trackArchive(EventAction.VIEW, selectedRepository || undefined)
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

  // Get repositories from API response
  // eslint-disable-next-line react-hooks/preserve-manual-memoization
  const repositories = React.useMemo(
    () => repositoriesData?.data?.repositories || [],
    [repositoriesData]
  )

  // Handle incoming navigation state (from "View Archives" button)
  useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (location.state && (location.state as any).repositoryId && repositories.length > 0) {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const repositoryId = (location.state as any).repositoryId
      setSelectedRepositoryId(repositoryId)
      const repo = repositories.find((r: Repository) => r.id === repositoryId)
      setSelectedRepository(repo || null)
      // Reset scroll position to top
      window.scrollTo(0, 0)
    }
  }, [location.state, repositories])

  const archivesList = (archives?.data?.archives || []).sort((a: Archive, b: Archive) => {
    // Sort by start date, latest first
    return new Date(b.start).getTime() - new Date(a.start).getTime()
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
    trackArchive(EventAction.VIEW, selectedRepository || undefined)
  }

  const handleRestoreArchive = (archive: Archive) => {
    // Open restore wizard flow instead of navigating to separate page
    handleRestoreArchiveClick(archive)
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          {t('archives.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('archives.subtitle')}
        </Typography>
      </Box>

      {/* Repository Selector */}
      <RepositorySelectorCard
        repositories={repositories}
        value={selectedRepositoryId}
        onChange={(v) => handleRepositoryChange(v as number)}
        loading={loadingRepositories}
      />

      {/* Repository Statistics */}
      {selectedRepositoryId && loadingRepoInfo && (
        <Box
          sx={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '120px',
            mb: 4,
          }}
        >
          <CircularProgress size={48} />
          <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
            {t('archives.loadingStats')}
          </Typography>
        </Box>
      )}
      {selectedRepositoryId && !loadingRepoInfo && repositoryStats && (
        <RepositoryStatsGrid stats={repositoryStats} archivesCount={archivesList.length} />
      )}

      {/* Last Restore Job for Selected Repository */}
      {selectedRepositoryId && restoreJobsData?.data?.jobs && (
        <LastRestoreSection restoreJob={lastRestoreJob} />
      )}

      {/* No Repository Selected State */}
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

      {/* Archives Section */}
      {selectedRepositoryId && (
        <ArchivesList
          archives={archivesList}
          repositoryName={selectedRepository?.name || ''}
          loading={loadingArchives}
          onViewArchive={handleViewArchive}
          onRestoreArchive={handleRestoreArchive}
          onMountArchive={openMountDialog}
          onDeleteArchive={(archiveName) => setShowDeleteConfirm(archiveName)}
          mountDisabled={mountArchiveMutation.isPending}
          canDelete={getRepoCapabilities({ mode: selectedRepository?.mode }).canDelete}
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
            archivesAPI.downloadFile(selectedRepository.path, archiveName, filePath)
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
