import React, { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useLocation } from 'react-router-dom'
import { Box, Typography, CircularProgress } from '@mui/material'
import { Folder } from 'lucide-react'
import { archivesAPI, repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
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
import { useMatomo } from '../hooks/useMatomo'
import ArchiveBrowserDialog from '../components/ArchiveBrowserDialog'
import RestoreWizard, { RestoreData } from '../components/RestoreWizard'

const Archives: React.FC = () => {
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [selectedRepository, setSelectedRepository] = useState<Repository | null>(null)
  const [viewArchive, setViewArchive] = useState<Archive | null>(null)
  const [showDeleteConfirm, setShowDeleteConfirm] = useState<string | null>(null)
  const [lockError, setLockError] = useState<{
    repositoryId: number
    repositoryName: string
  } | null>(null)
  const [mountDialogArchive, setMountDialogArchive] = useState<Archive | null>(null)
  const [customMountPoint, setCustomMountPoint] = useState<string>('')

  // Restore functionality
  const [restoreArchive, setRestoreArchive] = useState<Archive | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [showBrowser, setShowBrowser] = useState<boolean>(false)
  const [showRestoreWizard, setShowRestoreWizard] = useState<boolean>(false)

  const queryClient = useQueryClient()
  const location = useLocation()
  const { trackArchive, EventAction } = useMatomo()

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
    queryFn: () => repositoriesAPI.listRepositoryArchives(selectedRepositoryId!),
    enabled: !!selectedRepositoryId,
    retry: false,
  })

  // Handle archives error
  React.useEffect(() => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    if (archivesError && (archivesError as any)?.response?.status === 423 && selectedRepositoryId) {
      setLockError({
        repositoryId: selectedRepositoryId,
        repositoryName: selectedRepository?.name || 'Unknown',
      })
    }
  }, [archivesError, selectedRepositoryId, selectedRepository?.name])

  // Get repository info for statistics
  const {
    data: repoInfo,
    isLoading: loadingRepoInfo,
    error: repoInfoError,
  } = useQuery({
    queryKey: ['repository-info', selectedRepositoryId],
    queryFn: () => repositoriesAPI.getRepositoryInfo(selectedRepositoryId!),
    enabled: !!selectedRepositoryId,
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
      })
    }
  }, [repoInfoError, selectedRepositoryId, selectedRepository?.name])

  // Delete archive mutation
  const deleteArchiveMutation = useMutation({
    mutationFn: ({ repository, archive }: { repository: string; archive: string }) =>
      archivesAPI.deleteArchive(repository, archive),
    onSuccess: (data) => {
      // Backend now returns job_id for background deletion
      toast.success(`Archive deletion started in background (Job ID: ${data.data.job_id})`)
      // Refresh archives list after a delay to allow deletion to complete
      setTimeout(() => {
        queryClient.invalidateQueries({ queryKey: ['repository-archives', selectedRepositoryId] })
      }, 2000)
      setShowDeleteConfirm(null)
      trackArchive(EventAction.DELETE, selectedRepository?.name)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to delete archive: ${error.response?.data?.detail || error.message}`)
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

      toast.success(
        `Archive mounted successfully!\n\nMount is inside the container. To access files, run:\n\n${accessCommand}`,
        {
          duration: 15000,
          style: {
            maxWidth: '600px',
            whiteSpace: 'pre-wrap',
            fontFamily: 'monospace',
            fontSize: '13px',
          },
        }
      )
      trackArchive(EventAction.MOUNT, selectedRepository?.name)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      const errorDetail = error.response?.data?.detail || error.message
      const isMountTimeout = errorDetail.toLowerCase().includes('mount timeout')

      if (isMountTimeout) {
        toast.error(
          `Mount timeout: Large repositories may need more time to mount. ` +
            `Go to Settings > System to increase the Mount Timeout value.`,
          {
            duration: 10000,
            style: {
              maxWidth: '500px',
            },
          }
        )
      } else {
        toast.error(`Failed to mount archive: ${errorDetail}`)
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
    }: {
      repository: string
      archive: string
      destination: string
      paths: string[]
    }) => restoreAPI.startRestore(repository, archive, paths, destination),
    onSuccess: () => {
      toast.success('Restore job started! Check the Activity tab to monitor progress.', {
        duration: 6000, // Show longer so user can read it
      })
      trackArchive(EventAction.START, selectedRepository?.name)

      setRestoreArchive(null)
      setSelectedPaths([])
      setShowRestoreWizard(false)

      queryClient.refetchQueries({ queryKey: ['restore-jobs'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(`Failed to start restore: ${error.response?.data?.detail || error.message}`)
    },
  })

  // Handle repository selection
  const handleRepositoryChange = (repositoryId: number) => {
    setSelectedRepositoryId(repositoryId)
    const repo = repositories.find((r: Repository) => r.id === repositoryId)
    setSelectedRepository(repo || null)
    // Track archive listing (selecting a repo to filter/list its archives)
    if (repo) {
      trackArchive(EventAction.FILTER, repo.name)
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

  // Handle archive browser path selection
  const handlePathsSelected = (paths: string[]) => {
    setSelectedPaths(paths)
    setShowBrowser(false)
    setShowRestoreWizard(true)
  }

  // Open archive browser for restore
  const handleRestoreArchiveClick = React.useCallback(
    (archive: Archive) => {
      // Always reset paths when opening browser
      setSelectedPaths([])
      setRestoreArchive(archive)
      setShowBrowser(true)
      setShowRestoreWizard(false)
      trackArchive(EventAction.VIEW, selectedRepository?.name)
    },
    [selectedRepository, trackArchive, EventAction]
  )

  // Handle restore from wizard
  const handleRestoreFromWizard = (data: RestoreData) => {
    if (!selectedRepository || !restoreArchive) {
      toast.error('Repository or archive not selected')
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
      paths: selectedPaths,
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
    trackArchive(EventAction.VIEW, selectedRepository?.name)
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
          Archive Browser
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Browse and manage your backup archives
        </Typography>
      </Box>

      {/* Repository Selector */}
      <RepositorySelectorCard
        repositories={repositories}
        selectedRepositoryId={selectedRepositoryId}
        onRepositoryChange={handleRepositoryChange}
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
            Loading repository statistics...
          </Typography>
        </Box>
      )}
      {selectedRepositoryId && !loadingRepoInfo && repoInfo?.data?.info?.cache?.stats && (
        <RepositoryStatsGrid
          stats={repoInfo.data.info.cache.stats}
          archivesCount={archivesList.length}
        />
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
              ? 'No repositories found. Create a repository first.'
              : 'Select a repository to view its archives'}
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
        />
      )}

      {/* View Contents Modal */}
      <ArchiveContentsDialog
        open={!!viewArchive}
        archive={viewArchive}
        repositoryId={selectedRepositoryId}
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
          onLockBroken={() => {
            // Invalidate queries to retry
            queryClient.invalidateQueries({
              queryKey: ['repository-archives', lockError.repositoryId],
            })
            queryClient.invalidateQueries({ queryKey: ['repository-info', lockError.repositoryId] })
          }}
        />
      )}

      {/* Archive Browser Dialog */}
      {restoreArchive && selectedRepository && (
        <ArchiveBrowserDialog
          open={showBrowser}
          onClose={() => setShowBrowser(false)}
          repositoryId={selectedRepository.id}
          archiveName={restoreArchive.name}
          onSelect={handlePathsSelected}
          initialSelectedPaths={selectedPaths}
        />
      )}

      {/* Restore Wizard */}
      {restoreArchive && selectedRepository && (
        <RestoreWizard
          open={showRestoreWizard}
          onClose={() => {
            setShowRestoreWizard(false)
            // Allow user to go back to browser by reopening it
            setShowBrowser(true)
          }}
          archiveName={restoreArchive.name}
          repositoryId={selectedRepository.id}
          selectedFiles={selectedPaths.map((path) => ({
            path,
            mode: '',
            user: '',
            group: '',
            size: 0,
            mtime: '',
            healthy: true,
          }))}
          onRestore={handleRestoreFromWizard}
        />
      )}
    </Box>
  )
}

export default Archives
