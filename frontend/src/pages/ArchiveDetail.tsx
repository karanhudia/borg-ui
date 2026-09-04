import { useMemo, useState } from 'react'
import { useParams, useSearchParams, Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { Alert, Box, Breadcrumbs, Button, Link, Stack, Tab, Tabs, Typography } from '@mui/material'
import { archivesAPI, repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { getBorgVersion } from '../utils/repoCapabilities'
import { translateBackendKey, type BackendDetail } from '../utils/translateBackendKey'
import { parseBackendDate } from '../utils/dateUtils'
import ArchiveInfoTab from '../components/archives/ArchiveInfoTab'
import DeleteArchiveDialog from '../components/DeleteArchiveDialog'
import MountArchiveDialog from '../components/MountArchiveDialog'
import MountSuccessToast from '../components/MountSuccessToast'
import RestoreWizard, { type RestoreData } from '../components/RestoreWizard'
import type { Archive, Repository } from '@/types'

type DetailTab = 'changes' | 'files' | 'info'

function getDefaultMountPoint(archiveName: string): string {
  return archiveName.replace(/[/:]/g, '_').replace(/\s+/g, '_')
}

export default function ArchiveDetail() {
  const { t } = useTranslation()
  const { repositoryId: repositoryIdParam, archiveId: archiveIdParam } = useParams()
  const [searchParams, setSearchParams] = useSearchParams()
  const queryClient = useQueryClient()

  const repositoryId = Number(repositoryIdParam)
  const archiveId = Number(archiveIdParam)
  const validParams = Number.isFinite(repositoryId) && Number.isFinite(archiveId)

  const activeTab = (searchParams.get('tab') as DetailTab | null) || 'changes'
  const setActiveTab = (tab: DetailTab) => {
    setSearchParams((prev) => {
      const next = new URLSearchParams(prev)
      next.set('tab', tab)
      return next
    })
  }

  const [showDeleteConfirm, setShowDeleteConfirm] = useState(false)
  const [showMountDialog, setShowMountDialog] = useState(false)
  const [customMountPoint, setCustomMountPoint] = useState('')
  const [showRestoreWizard, setShowRestoreWizard] = useState(false)

  const {
    data: archive,
    isLoading: loadingArchive,
    isError: archiveErrored,
  } = useQuery({
    queryKey: ['archive', repositoryId, archiveId],
    queryFn: () => archivesAPI.getArchive(repositoryId, archiveId).then((res) => res.data),
    enabled: validParams,
  })

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
    enabled: validParams,
  })

  const repository: Repository | null = useMemo(() => {
    const repositories = repositoriesData?.data?.repositories || []
    return repositories.find((r: Repository) => r.id === repositoryId) || null
  }, [repositoriesData, repositoryId])

  const archiveRef = useMemo(() => {
    if (!archive || !repository) return null
    return getBorgVersion(repository) === 2 ? `aid:${archive.borg_id}` : archive.name
  }, [archive, repository])

  const legacyArchive: Archive | null = archive
    ? {
        id: archive.borg_id,
        archive: archive.name,
        name: archive.name,
        start: archive.start,
        time: archive.start,
      }
    : null

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!repository || !archiveRef) throw new Error('not ready')
      return new BorgApiClient(repository).deleteArchive(archiveRef)
    },
    onSuccess: (data) => {
      const jobId = data.data.job_id
      toast.success(t('archives.deletionStarted', { id: jobId }))
      setShowDeleteConfirm(false)
      queryClient.invalidateQueries({ queryKey: ['repository-archives', repositoryId] })
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: BackendDetail } } }
      toast.error(
        translateBackendKey(err.response?.data?.detail) || t('archives.toasts.deleteFailed')
      )
    },
  })

  const mountMutation = useMutation({
    mutationFn: () =>
      mountsAPI.mountBorgArchive({
        repository_id: repositoryId,
        archive_name: archive!.name,
        mount_point: customMountPoint || undefined,
      }),
    onSuccess: (data) => {
      const mountPoint = data.data.mount_point
      const containerName = 'borg-web-ui'
      const accessCommand = `docker exec -it ${containerName} bash -c "cd ${mountPoint} && bash"`
      toast.custom((tst) => <MountSuccessToast toastId={tst.id} command={accessCommand} />, {
        duration: 15000,
      })
      setShowMountDialog(false)
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: BackendDetail } }; message?: string }
      const errorDetail = translateBackendKey(err.response?.data?.detail) || err.message || ''
      toast.error(t('archives.mountFailed', { error: errorDetail }))
    },
  })

  const restoreMutation = useMutation({
    mutationFn: (data: RestoreData) => {
      if (!repository || !archiveRef) throw new Error('not ready')
      const destinationPath =
        data.restore_strategy === 'custom' && data.custom_path ? data.custom_path : '/'
      return restoreAPI.startRestore(
        repository.path,
        archiveRef,
        data.selected_paths,
        destinationPath,
        repository.id,
        data.destination_type,
        data.destination_connection_id,
        data.restore_layout,
        data.path_metadata
      )
    },
    onSuccess: () => {
      toast.success(t('archives.restoreStarted'), { duration: 6000 })
      setShowRestoreWizard(false)
      queryClient.refetchQueries({ queryKey: ['restore-jobs'] })
    },
    onError: (error: unknown) => {
      const err = error as { response?: { data?: { detail?: BackendDetail } } }
      toast.error(
        translateBackendKey(err.response?.data?.detail) || t('archives.toasts.restoreFailed')
      )
    },
  })

  if (!validParams || archiveErrored) {
    return (
      <Box sx={{ p: 3 }}>
        <Alert severity="error">{t('archives.detail.loadFailed')}</Alert>
      </Box>
    )
  }

  if (loadingArchive || !archive) {
    return <Box sx={{ p: 3 }} />
  }

  const tabLabel =
    activeTab === 'changes'
      ? t('archives.detail.tabChangesWithCounts', { added: 0, removed: 0, modified: 0 })
      : t('archives.detail.tabChanges')

  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/archives" underline="hover">
          {t('archives.title')}
        </Link>
        <Typography color="text.primary">{repository?.name || repositoryId}</Typography>
      </Breadcrumbs>

      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        spacing={2}
        sx={{ mb: 2, alignItems: { sm: 'center' } }}
      >
        <Box sx={{ flexGrow: 1 }}>
          <Typography variant="h5">{archive.name}</Typography>
          <Typography variant="body2" color="text.secondary">
            {parseBackendDate(archive.start).toLocaleString()}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Button variant="outlined" onClick={() => setShowRestoreWizard(true)}>
            {t('archives.detail.restore')}
          </Button>
          <Button
            variant="outlined"
            onClick={() => {
              setCustomMountPoint(getDefaultMountPoint(archive.name))
              setShowMountDialog(true)
            }}
          >
            {t('archives.detail.mount')}
          </Button>
          <Button variant="outlined" color="error" onClick={() => setShowDeleteConfirm(true)}>
            {t('archives.detail.delete')}
          </Button>
        </Stack>
      </Stack>

      <Tabs value={activeTab} onChange={(_e, value) => setActiveTab(value)} sx={{ mb: 2 }}>
        <Tab label={tabLabel} value="changes" />
        <Tab label={t('archives.detail.tabFiles')} value="files" />
        <Tab label={t('archives.detail.tabInfo')} value="info" />
      </Tabs>

      {activeTab === 'changes' && <Box />}
      {activeTab === 'files' && <Box />}
      {activeTab === 'info' && <ArchiveInfoTab archive={archive} />}

      {repository && legacyArchive && (
        <>
          <DeleteArchiveDialog
            open={showDeleteConfirm}
            archiveName={archive.name}
            onClose={() => setShowDeleteConfirm(false)}
            onConfirm={() => deleteMutation.mutate()}
            deleting={deleteMutation.isPending}
          />
          <MountArchiveDialog
            open={showMountDialog}
            archive={legacyArchive}
            mountPoint={customMountPoint}
            onMountPointChange={setCustomMountPoint}
            onClose={() => setShowMountDialog(false)}
            onConfirm={() => mountMutation.mutate()}
            mounting={mountMutation.isPending}
          />
          <RestoreWizard
            open={showRestoreWizard}
            onClose={() => setShowRestoreWizard(false)}
            archive={legacyArchive}
            repository={repository}
            repositoryType={repository.repository_type || 'local'}
            onRestore={(data) => restoreMutation.mutate(data)}
          />
        </>
      )}
    </Box>
  )
}
