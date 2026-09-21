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
  Link,
  Stack,
  Tab,
  Tabs,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { Archive as ArchiveIcon, HardDrive, RotateCcw, Trash2 } from 'lucide-react'
import { changeColor } from '../components/archives/changeStyle'
import { archivesAPI, repositoriesAPI, mountsAPI, restoreAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { getBorgVersion } from '../utils/repoCapabilities'
import { translateBackendKey, type BackendDetail } from '../utils/translateBackendKey'
import { parseBackendDate } from '../utils/dateUtils'
import ArchiveStatsHeader, {
  type ArchiveStatsHeaderProps,
} from '../components/archives/ArchiveStatsHeader'
import ArchiveChangesTab from '../components/archives/ArchiveChangesTab'
import ArchiveFilesTab from '../components/archives/ArchiveFilesTab'
import DeleteArchiveDialog from '../components/DeleteArchiveDialog'
import MountArchiveDialog from '../components/MountArchiveDialog'
import MountSuccessToast from '../components/MountSuccessToast'
import RestoreWizard, { type RestoreData } from '../components/RestoreWizard'
import RestoreProgressPanel from '../components/archives/RestoreProgressPanel'
import { cornerStackSx } from '../components/archives/cornerStack'
import { resyncStoredArchives } from '../utils/archiveResync'
import type { RestorePathMetadata } from '../utils/restorePaths'
import type { ArchiveDetailResponse } from '../types/archives'
import type { Archive, Repository } from '@/types'

type DetailTab = 'changes' | 'files'

const DETAIL_TABS: DetailTab[] = ['files', 'changes']

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

  // A tab the page does not have would leave the header without a selected
  // tab and the body without any panel, so anything unknown reads as files.
  const requestedTab = searchParams.get('tab')
  const activeTab: DetailTab = DETAIL_TABS.includes(requestedTab as DetailTab)
    ? (requestedTab as DetailTab)
    : 'files'
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
  // "Restore this" in a file's history points at an older archive of the
  // series. Null means the archive on screen.
  const [restoreFromArchiveId, setRestoreFromArchiveId] = useState<number | null>(null)
  // Bumped when a restore starts so the Files tab drops its selection: a
  // "1 selected, Restore selection" bar left on screen reads as a restore
  // that never went out.
  const [selectionEpoch, setSelectionEpoch] = useState(0)
  // Jobs started from this page, oldest first. Each gets a card in the
  // bottom-right column until dismissed, so a restore never happens unseen
  // and a second one does not erase the first one's outcome.
  const [restoreJobIds, setRestoreJobIds] = useState<number[]>([])
  // The column itself. Held in state, not a ref, so the Files tab re-renders
  // with the node once it exists and can portal its selection bar into it.
  const [cornerStack, setCornerStack] = useState<HTMLDivElement | null>(null)

  const openRestore = (paths?: string[], items?: RestorePathMetadata[], fromArchiveId?: number) => {
    setRestorePreselection(paths && paths.length > 0 ? { paths, items: items ?? [] } : null)
    setRestoreFromArchiveId(
      fromArchiveId != null && fromArchiveId !== archiveId ? fromArchiveId : null
    )
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
  // Spec 6.8. Defaults to `full` while the repository list is still loading,
  // which is the behaviour every install had before the mode existed.
  const indexMode = repository?.index_mode ?? 'full'

  // The archive a restore reads from: the one on screen, unless file history
  // asked for an older one, whose borg id has to be resolved before Borg can
  // be dialled.
  const { data: restoreSourceArchive } = useQuery({
    queryKey: ['archive', repositoryId, restoreFromArchiveId],
    queryFn: () =>
      archivesAPI.getArchive(repositoryId, restoreFromArchiveId as number).then((res) => res.data),
    enabled: validParams && restoreFromArchiveId != null,
  })
  const restoreArchive = restoreFromArchiveId != null ? (restoreSourceArchive ?? null) : archive

  const archiveRef = useMemo(() => {
    if (!archive || !repository) return null
    return getBorgVersion(repository) === 2 ? `aid:${archive.borg_id}` : archive.name
  }, [archive, repository])

  const restoreArchiveRef = useMemo(() => {
    if (!restoreArchive || !repository) return null
    return getBorgVersion(repository) === 2 ? `aid:${restoreArchive.borg_id}` : restoreArchive.name
  }, [restoreArchive, repository])

  const toLegacyArchive = (row: ArchiveDetailResponse | null): Archive | null =>
    row
      ? {
          id: row.borg_id,
          archive: row.name,
          name: row.name,
          start: row.start,
          time: row.start,
        }
      : null

  const legacyArchive: Archive | null = toLegacyArchive(archive ?? null)
  const legacyRestoreArchive: Archive | null = toLegacyArchive(restoreArchive ?? null)

  const deleteMutation = useMutation({
    mutationFn: () => {
      if (!repository || !archiveRef) throw new Error('not ready')
      return new BorgApiClient(repository).deleteArchive(archiveRef)
    },
    onSuccess: (data) => {
      const jobId = data.data.job_id
      toast.success(t('archives.deletionStarted', { id: jobId }))
      setShowDeleteConfirm(false)
      // The Archives page reads the stored list, so the deleted archive stays
      // in it until archive_sync runs again.
      void resyncStoredArchives(queryClient, repositoryId)
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
      if (!repository || !restoreArchiveRef) throw new Error('not ready')
      const destinationPath =
        data.restore_strategy === 'custom' && data.custom_path ? data.custom_path : '/'
      return restoreAPI.startRestore(
        repository.path,
        restoreArchiveRef,
        data.selected_paths,
        destinationPath,
        repository.id,
        data.destination_type,
        data.destination_connection_id,
        data.restore_layout,
        data.path_metadata
      )
    },
    onSuccess: (res) => {
      setShowRestoreWizard(false)
      setSelectionEpoch((n) => n + 1)
      setRestoreJobIds((ids) => [...ids, res.data.job_id])
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
    // The counts are Community (spec 2026-09-21, section 1), so this runs on
    // every plan and the stat card and tab label carry them before the
    // Changes tab is ever opened. A repository that does not index file
    // history has no counts to show (spec 6.8), and showing them on the tab
    // label while the tab itself says the history is not indexed is the
    // contradiction the mode exists to avoid.
    // `!!repository` as well as the mode: `indexMode` falls back to `full`
    // while the repository list loads, and without the guard the query
    // would fire once under that fallback on a repository that indexes no
    // history.
    enabled: validParams && !!archive && !!repository && indexMode === 'full',
  })

  if (!validParams || archiveErrored) {
    return (
      <Box>
        <Alert severity="error">{t('archives.detail.loadFailed')}</Alert>
      </Box>
    )
  }

  if (loadingArchive || !archive) {
    return <Box />
  }

  // Cached data from a previous mode must not outlive the setting.
  const totals = indexMode === 'full' ? changesForLabel?.totals : undefined
  const capability = archive.history_capability ?? 'available'
  const totalsState: ArchiveStatsHeaderProps['totalsState'] =
    capability !== 'available' || indexMode !== 'full'
      ? 'unavailable'
      : archive.history_state !== 'indexed'
        ? 'not_indexed'
        : totals
          ? 'ready'
          : 'loading'
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
    <Box>
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
          flexWrap: 'wrap',
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
            <Typography
              variant="caption"
              sx={{ color: 'text.disabled', mt: 0.25, display: 'block' }}
            >
              {[
                parseBackendDate(archive.start).toLocaleString(),
                archive.hostname &&
                  `${archive.username ? `${archive.username}@` : ''}${archive.hostname}`,
                archive.comment,
              ]
                .filter(Boolean)
                .join(' · ')}
            </Typography>
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
        <Box sx={{ flexBasis: '100%' }}>
          <ArchiveStatsHeader archive={archive} totals={totals} totalsState={totalsState} />
        </Box>
      </Box>

      <Tabs
        value={activeTab}
        onChange={(_e, value) => setActiveTab(value)}
        sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}
      >
        <Tab label={t('archives.detail.tabFiles')} value="files" />
        <Tab label={tabLabel} value="changes" />
      </Tabs>

      <Box sx={{ pt: 1 }}>
        {/* `repository` as well, like the Files tab below: the mode falls
            back to `full` while the repository list loads, and the tab
            would spend a history query under that fallback on a repository
            that indexes none. */}
        {activeTab === 'changes' && repository && (
          <ArchiveChangesTab repositoryId={repositoryId} archive={archive} indexMode={indexMode} />
        )}
        {activeTab === 'files' && repository && (
          <ArchiveFilesTab
            repositoryId={repositoryId}
            repository={repository}
            archive={archive}
            onRestorePaths={(paths, items, fromArchiveId) =>
              openRestore(paths, items, fromArchiveId)
            }
            cornerStack={cornerStack}
            selectionResetToken={selectionEpoch}
          />
        )}
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
            open={showRestoreWizard && legacyRestoreArchive != null}
            onClose={() => setShowRestoreWizard(false)}
            archive={legacyRestoreArchive ?? legacyArchive}
            repository={repository}
            repositoryType={repository.repository_type || 'local'}
            onRestore={(data) => restoreMutation.mutate(data)}
            initialSelectedPaths={restorePreselection?.paths}
            initialSelectedItems={restorePreselection?.items}
          />
        </>
      )}

      <Box ref={setCornerStack} sx={cornerStackSx}>
        {restoreJobIds.map((jobId) => (
          <RestoreProgressPanel
            key={jobId}
            jobId={jobId}
            repositoryId={repositoryId}
            onDismiss={() => setRestoreJobIds((ids) => ids.filter((id) => id !== jobId))}
          />
        ))}
      </Box>
    </Box>
  )
}
