import { useMemo, useState } from 'react'
import { useParams, useSearchParams, Link as RouterLink } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import {
  Alert,
  Box,
  Breadcrumbs,
  Button,
  Chip,
  Link,
  Stack,
  Tab,
  Tabs,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Archive as ArchiveIcon, HardDrive, RotateCcw, Trash2 } from 'lucide-react'
import { formatBytes, formatDurationSeconds } from '../utils/dateUtils'
import { changeColor } from '../components/archives/changeStyle'
import { archivesAPI, repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { getBorgVersion } from '../utils/repoCapabilities'
import { translateBackendKey, type BackendDetail } from '../utils/translateBackendKey'
import { parseBackendDate } from '../utils/dateUtils'
import ArchiveInfoTab from '../components/archives/ArchiveInfoTab'
import ArchiveChangesTab from '../components/archives/ArchiveChangesTab'
import ArchiveFilesTab from '../components/archives/ArchiveFilesTab'
import DeleteArchiveDialog from '../components/DeleteArchiveDialog'
import MountArchiveDialog from '../components/MountArchiveDialog'
import MountSuccessToast from '../components/MountSuccessToast'
import RestoreWizard, { type RestoreData } from '../components/RestoreWizard'
import type { RestorePathMetadata } from '../utils/restorePaths'
import type { Archive, Repository } from '@/types'

type DetailTab = 'changes' | 'files' | 'info'

function getDefaultMountPoint(archiveName: string): string {
  return archiveName.replace(/[/:]/g, '_').replace(/\s+/g, '_')
}

export default function ArchiveDetail() {
  const { t } = useTranslation()
  const theme = useTheme()
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
  const [restorePreselection, setRestorePreselection] = useState<{
    paths: string[]
    items: RestorePathMetadata[]
  } | null>(null)

  const openRestore = (paths?: string[], items?: RestorePathMetadata[]) => {
    setRestorePreselection(paths && paths.length > 0 ? { paths, items: items ?? [] } : null)
    setShowRestoreWizard(true)
  }

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

  const { data: changesForLabel } = useQuery({
    queryKey: ['archive-changes', repositoryId, archiveId, archive?.predecessor_id, []],
    queryFn: () =>
      archivesAPI
        .getChanges(repositoryId, archiveId, {
          compare_to: archive?.predecessor_id ?? undefined,
        })
        .then((res) => res.data),
    enabled: validParams && !!archive,
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

  const totals = changesForLabel?.totals
  const tabLabel = (
    <Box
      component="span"
      sx={{ display: 'inline-flex', alignItems: 'center', gap: 1 }}
      aria-label={t('archives.detail.tabChangesWithCounts', {
        added: totals?.added ?? 0,
        removed: totals?.removed ?? 0,
        modified: totals?.modified ?? 0,
      })}
    >
      {t('archives.detail.tabChangesLabel')}
      {totals && (
        <Box
          component="span"
          sx={{
            display: 'inline-flex',
            gap: 0.75,
            fontSize: '0.75rem',
            fontWeight: 600,
            fontVariantNumeric: 'tabular-nums',
            fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace',
          }}
        >
          <Box
            component="span"
            sx={{ color: totals.added ? changeColor(theme, 'added') : 'text.disabled' }}
          >
            +{totals.added}
          </Box>
          <Box
            component="span"
            sx={{ color: totals.removed ? changeColor(theme, 'removed') : 'text.disabled' }}
          >
            −{totals.removed}
          </Box>
          <Box
            component="span"
            sx={{ color: totals.modified ? changeColor(theme, 'modified') : 'text.disabled' }}
          >
            ~{totals.modified}
          </Box>
        </Box>
      )}
    </Box>
  )

  return (
    <Box sx={{ p: 3 }}>
      <Breadcrumbs sx={{ mb: 2 }}>
        <Link component={RouterLink} to="/archives" underline="hover">
          {t('archives.title')}
        </Link>
        <Typography color="text.primary">{repository?.name || repositoryId}</Typography>
      </Breadcrumbs>

      <Box
        sx={{
          border: 1,
          borderColor: 'divider',
          borderRadius: 2,
          bgcolor: 'background.paper',
          p: 2.5,
          mb: 3,
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          gap: 2,
          alignItems: { md: 'flex-start' },
          justifyContent: 'space-between',
        }}
      >
        <Stack direction="row" spacing={2} sx={{ minWidth: 0, alignItems: 'flex-start' }}>
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: '14px',
              bgcolor: alpha(theme.palette.primary.main, 0.1),
              color: 'primary.main',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            <ArchiveIcon size={24} />
          </Box>
          <Box sx={{ minWidth: 0 }}>
            <Typography
              variant="h5"
              sx={{ fontWeight: 700, wordBreak: 'break-word', lineHeight: 1.3 }}
            >
              {archive.name}
            </Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary', mt: 0.25 }}>
              {parseBackendDate(archive.start).toLocaleString()}
            </Typography>
            <Stack direction="row" spacing={1} useFlexGap sx={{ flexWrap: 'wrap', mt: 1.5 }}>
              {[
                { label: t('archives.detail.series'), value: archive.series, key: 'secondary' },
                {
                  label: t('archives.detail.files'),
                  value: archive.nfiles?.toLocaleString() ?? null,
                  key: 'primary',
                },
                {
                  label: t('archives.detail.originalSize'),
                  value: archive.original_size != null ? formatBytes(archive.original_size) : null,
                  key: 'success',
                },
                {
                  label: t('archives.detail.deduplicatedSize'),
                  value:
                    archive.deduplicated_size != null
                      ? formatBytes(archive.deduplicated_size)
                      : null,
                  key: 'info',
                },
                {
                  label: t('archives.detail.duration'),
                  value:
                    archive.duration_seconds != null
                      ? formatDurationSeconds(archive.duration_seconds)
                      : null,
                  key: 'warning',
                },
              ]
                .filter((pill) => pill.value)
                .map((pill) => {
                  const color = theme.palette[pill.key as 'primary'].main
                  return (
                    <Chip
                      key={pill.label}
                      size="small"
                      label={
                        <Box component="span" sx={{ display: 'inline-flex', gap: 0.75 }}>
                          <Box component="span" sx={{ color: alpha(color, 0.85), fontWeight: 500 }}>
                            {pill.label}
                          </Box>
                          <Box component="span" sx={{ fontWeight: 700, color }}>
                            {pill.value}
                          </Box>
                        </Box>
                      }
                      sx={{
                        bgcolor: alpha(color, theme.palette.mode === 'dark' ? 0.16 : 0.09),
                        height: 26,
                        '& .MuiChip-label': { px: 1.25 },
                      }}
                    />
                  )
                })}
            </Stack>
          </Box>
        </Stack>
        <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
          <Button
            variant="contained"
            disableElevation
            startIcon={<RotateCcw size={16} />}
            onClick={() => openRestore()}
          >
            {t('archives.detail.restore')}
          </Button>
          <Button
            variant="outlined"
            startIcon={<HardDrive size={16} />}
            onClick={() => {
              setCustomMountPoint(getDefaultMountPoint(archive.name))
              setShowMountDialog(true)
            }}
          >
            {t('archives.detail.mount')}
          </Button>
          <Button
            variant="outlined"
            color="error"
            startIcon={<Trash2 size={16} />}
            onClick={() => setShowDeleteConfirm(true)}
          >
            {t('archives.detail.delete')}
          </Button>
        </Stack>
      </Box>

      <Tabs
        value={activeTab}
        onChange={(_e, value) => setActiveTab(value)}
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label={tabLabel} value="changes" />
        <Tab label={t('archives.detail.tabFiles')} value="files" />
        <Tab label={t('archives.detail.tabInfo')} value="info" />
      </Tabs>

      <Box sx={{ pt: 1 }}>
        {activeTab === 'changes' && (
          <ArchiveChangesTab repositoryId={repositoryId} archive={archive} />
        )}
        {activeTab === 'files' && repository && (
          <ArchiveFilesTab
            repositoryId={repositoryId}
            repository={repository}
            archive={archive}
            onRestorePaths={(paths, items) => openRestore(paths, items)}
          />
        )}
        {activeTab === 'info' && <ArchiveInfoTab archive={archive} />}
      </Box>

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
            initialSelectedPaths={restorePreselection?.paths}
            initialSelectedItems={restorePreselection?.items}
          />
        </>
      )}
    </Box>
  )
}
