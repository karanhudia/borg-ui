import { forwardRef, useEffect, useImperativeHandle, useMemo, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  Alert,
  Box,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  IconButton,
  InputAdornment,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
  Autocomplete,
  CircularProgress,
  Tooltip,
} from '@mui/material'
import { Eye, FolderOpen, LifeBuoy } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { repositoriesAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import { translateBackendKey } from '../utils/translateBackendKey'
import {
  formatDateCompact,
  formatScheduledInstantDisplay,
  getBrowserTimeZone,
  getSupportedTimeZones,
} from '../utils/dateUtils'
import { usePermissions } from '../hooks/usePermissions'
import DataTable, { ActionButton, Column } from './DataTable'
import ResponsiveDialog from './ResponsiveDialog'
import RepoSelect from './RepoSelect'
import CronBuilderDialog from './CronBuilderDialog'
import ScheduleRestoreCheckCard from './ScheduleRestoreCheckCard'
import EntityCardSkeleton from './EntityCardSkeleton'
import StatusBadge from './StatusBadge'
import ArchivePathSelector, { type ArchivePathSelectionData } from './ArchivePathSelector'
import LogViewerDialog from './LogViewerDialog'
import RepositoryCell from './RepositoryCell'
import ScheduledInstantTooltip from './ScheduledInstantTooltip'
import type { Archive, Repository } from '../types'

interface ScheduledRestoreCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  restore_check_cron_expression: string | null
  restore_check_timezone?: string | null
  timezone?: string | null
  restore_check_paths: string[]
  restore_check_full_archive: boolean
  restore_check_canary_enabled: boolean
  restore_check_mode: 'canary' | 'probe_paths' | 'full_archive'
  last_restore_check: string | null
  last_scheduled_restore_check: string | null
  next_scheduled_restore_check: string | null
  notify_on_restore_check_success: boolean
  notify_on_restore_check_failure: boolean
  enabled: boolean
  restore_check_schedule_enabled?: boolean
}

interface RestoreCheckJobRow {
  id: number
  repository_id: number
  repository_name: string
  repository_path: string
  status: string
  started_at: string | null
  completed_at: string | null
  archive_name: string | null
  has_logs: boolean
  error_message: string | null
  probe_paths: string[]
  mode: 'canary' | 'probe_paths' | 'full_archive'
}

interface RestoreCheckLogJob extends RestoreCheckJobRow {
  type: 'restore_check'
}

type RestoreCheckMode = 'canary' | 'probe_paths' | 'full_archive'

export interface ScheduledRestoreChecksSectionRef {
  openAddDialog: () => void
  openEditForRepo: (repoId: number) => Promise<void>
}

const DEFAULT_CRON = '0 4 * * 0'

const modeLabelKey: Record<RestoreCheckJobRow['mode'], string> = {
  canary: 'integrity.history.modes.canary',
  probe_paths: 'integrity.history.modes.probePaths',
  full_archive: 'integrity.history.modes.fullArchive',
}

function getArchiveTimestamp(archive: Archive): string {
  return archive.start || archive.time || ''
}

function getArchiveTimeMs(archive: Archive): number {
  const parsedTime = Date.parse(getArchiveTimestamp(archive))
  return Number.isFinite(parsedTime) ? parsedTime : 0
}

function getArchiveName(archive: Archive): string {
  return archive.name || archive.archive || archive.id
}

function parsePaths(rawValue: string): string[] {
  return rawValue
    .split('\n')
    .map((value) => value.trim())
    .filter(Boolean)
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
const ScheduledRestoreChecksSection = forwardRef<ScheduledRestoreChecksSectionRef, {}>((_, ref) => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { canDo } = usePermissions()
  const [showDialog, setShowDialog] = useState(false)
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [showArchivePathPicker, setShowArchivePathPicker] = useState(false)
  const [archiveSelection, setArchiveSelection] = useState<ArchivePathSelectionData>({
    selectedPaths: [],
    selectedItems: [],
  })
  const [selectedLogJob, setSelectedLogJob] = useState<RestoreCheckLogJob | null>(null)
  const [formData, setFormData] = useState({
    cron_expression: DEFAULT_CRON,
    timezone: getBrowserTimeZone(),
    restore_check_paths: '',
    mode: 'canary' as RestoreCheckMode,
  })
  const timezoneOptions = useMemo(
    () => getSupportedTimeZones(formData.timezone),
    [formData.timezone]
  )

  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = (repositoriesData?.data?.repositories || []) as Repository[]
  const manageableRepositories = repositories.filter((repo) => canDo(repo.id, 'maintenance'))
  const selectedRepository = selectedRepositoryId
    ? manageableRepositories.find((repo) => repo.id === selectedRepositoryId)
    : undefined
  const selectedRepositoryIsObserveOnly = selectedRepository?.mode === 'observe'

  useEffect(() => {
    if (!showDialog || !selectedRepositoryIsObserveOnly || formData.mode !== 'canary') {
      return
    }
    setFormData((current) => ({ ...current, mode: 'probe_paths' }))
  }, [formData.mode, selectedRepositoryIsObserveOnly, showDialog])

  const { data: scheduledChecks, isLoading } = useQuery({
    queryKey: ['scheduled-restore-checks', repositories.map((repo) => repo.id)],
    queryFn: async () => {
      const checks: ScheduledRestoreCheck[] = []
      for (const repo of repositories) {
        try {
          const response = await repositoriesAPI.getRestoreCheckSchedule(repo.id)
          // Include disabled-but-configured schedules so the toggle remains
          // reachable; deletion is the only way to fully remove a row.
          if (
            response.data.restore_check_cron_expression &&
            response.data.restore_check_cron_expression !== ''
          ) {
            checks.push(response.data)
          }
        } catch {
          // Skip repositories without a restore check schedule.
        }
      }
      return checks
    },
    enabled: repositories.length > 0 && !loadingRepositories,
  })

  const {
    data: archiveListData,
    isFetching: loadingArchiveList,
    error: archiveListError,
  } = useQuery({
    queryKey: ['scheduled-restore-check-latest-archive', selectedRepositoryId],
    queryFn: async () => {
      if (!selectedRepository) {
        throw new Error('Repository not selected')
      }
      return new BorgApiClient(selectedRepository).listArchives()
    },
    enabled: showArchivePathPicker && !!selectedRepository,
    retry: false,
  })

  const latestArchive = useMemo(() => {
    const archives = (archiveListData?.data?.archives || []) as Archive[]
    return [...archives].sort((left, right) => getArchiveTimeMs(right) - getArchiveTimeMs(left))[0]
  }, [archiveListData?.data?.archives])

  const { data: restoreJobsData, isLoading: loadingRestoreJobs } = useQuery({
    queryKey: ['scheduled-restore-check-history', manageableRepositories.map((repo) => repo.id)],
    queryFn: async () => {
      const jobs: RestoreCheckJobRow[] = []
      await Promise.all(
        manageableRepositories.map(async (repo: Repository) => {
          try {
            const response = await repositoriesAPI.getRepositoryRestoreCheckJobs(repo.id, 5)
            const rows = (response.data.jobs || []).map(
              (job: Omit<RestoreCheckJobRow, 'repository_name' | 'repository_path'>) => ({
                ...job,
                repository_name: repo.name,
                repository_path: repo.path,
              })
            )
            jobs.push(...rows)
          } catch {
            // Ignore repositories without restore check jobs.
          }
        })
      )
      return jobs.sort((left, right) => {
        const leftTime = left.started_at || left.completed_at || ''
        const rightTime = right.started_at || right.completed_at || ''
        return rightTime.localeCompare(leftTime)
      })
    },
    enabled: manageableRepositories.length > 0,
  })

  const restoreJobs = restoreJobsData || []

  const historyColumns: Column<RestoreCheckJobRow>[] = [
    {
      id: 'repository',
      label: t('integrity.history.columns.repository'),
      width: '34%',
      minWidth: '280px',
      render: (row) => (
        <RepositoryCell
          repositoryName={row.repository_name}
          repositoryPath={row.repository_path}
          withIcon={false}
        />
      ),
      mobileFullWidth: true,
    },
    {
      id: 'status',
      label: t('common.status'),
      width: '120px',
      render: (row) => <StatusBadge status={row.status} tooltip={row.error_message || undefined} />,
    },
    {
      id: 'mode',
      label: t('integrity.history.columns.mode'),
      width: '150px',
      render: (row) => (
        <Typography variant="body2" noWrap>
          {t(modeLabelKey[row.mode])}
        </Typography>
      ),
    },
    {
      id: 'archive',
      label: t('integrity.history.columns.archive'),
      width: '28%',
      minWidth: '220px',
      render: (row) => {
        const needsBackupFirst =
          row.mode === 'canary' && Boolean(row.error_message?.includes('Run a backup'))
        const archiveName =
          row.archive_name ||
          (needsBackupFirst ? t('scheduledRestoreChecks.noBackupYet') : t('common.na'))
        return (
          <Tooltip
            title={row.archive_name || row.error_message || ''}
            arrow
            disableHoverListener={!row.archive_name && !row.error_message}
          >
            <Typography
              variant="body2"
              sx={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                maxWidth: '100%',
              }}
            >
              {archiveName}
            </Typography>
          </Tooltip>
        )
      },
    },
    {
      id: 'started',
      label: t('integrity.history.columns.started'),
      width: '170px',
      render: (row) => {
        if (!row.started_at) return t('common.never')

        const startedDisplay = formatScheduledInstantDisplay(row.started_at, 'UTC')
        return (
          <Tooltip
            title={
              <ScheduledInstantTooltip
                display={startedDisplay}
                scheduledLabel="Stored UTC"
                localLabel="Your local timezone"
              />
            }
            arrow
          >
            <Typography variant="body2" noWrap sx={{ display: 'inline-block', cursor: 'help' }}>
              {formatDateCompact(row.started_at)}
            </Typography>
          </Tooltip>
        )
      },
    },
  ]

  const historyActions: ActionButton<RestoreCheckJobRow>[] = [
    {
      icon: <Eye size={18} />,
      label: t('integrity.history.actions.viewLogs'),
      onClick: (row) =>
        setSelectedLogJob({
          ...row,
          type: 'restore_check',
        }),
      color: 'primary',
      tooltip: t('integrity.history.actions.viewLogs'),
      show: (row) => row.has_logs || Boolean(row.error_message) || row.status === 'running',
    },
  ]

  const updateMutation = useMutation({
    mutationFn: async ({ repoId, data }: { repoId: number; data: Record<string, unknown> }) =>
      repositoriesAPI.updateRestoreCheckSchedule(repoId, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-restore-checks'] })
      queryClient.invalidateQueries({ queryKey: ['scheduled-restore-check-history'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(t('scheduledRestoreChecks.toasts.scheduleUpdated'))
      setShowDialog(false)
      setSelectedRepositoryId(null)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('scheduledRestoreChecks.toasts.updateFailed')
      )
    },
  })

  const runRestoreCheckMutation = useMutation({
    mutationFn: (repoId: number) => {
      const matchingCheck = scheduledChecks?.find((check) => check.repository_id === repoId)
      return repositoriesAPI.restoreCheckRepository(repoId, {
        paths:
          matchingCheck?.restore_check_mode === 'probe_paths'
            ? matchingCheck.restore_check_paths
            : [],
        full_archive: matchingCheck?.restore_check_mode === 'full_archive',
      })
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-restore-check-history'] })
      toast.success(t('scheduledRestoreChecks.toasts.restoreCheckStarted'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('scheduledRestoreChecks.toasts.restoreCheckFailed')
      )
    },
  })

  const openAddDialog = () => {
    setSelectedRepositoryId(null)
    setFormData({
      cron_expression: DEFAULT_CRON,
      timezone: getBrowserTimeZone(),
      restore_check_paths: '',
      mode: 'canary',
    })
    setShowDialog(true)
  }

  const openEditDialog = (check: ScheduledRestoreCheck) => {
    const repository = repositories.find((repo) => repo.id === check.repository_id)
    const restoreCheckMode = (check.restore_check_mode || 'canary') as RestoreCheckMode
    setSelectedRepositoryId(check.repository_id)
    setFormData({
      cron_expression: check.restore_check_cron_expression || DEFAULT_CRON,
      timezone: check.restore_check_timezone || check.timezone || 'UTC',
      restore_check_paths: check.restore_check_paths.join('\n'),
      mode:
        repository?.mode === 'observe' && restoreCheckMode === 'canary'
          ? 'probe_paths'
          : restoreCheckMode,
    })
    setShowDialog(true)
  }

  const openArchivePathPicker = () => {
    if (!selectedRepository) {
      toast.error(t('scheduledRestoreChecks.validation.selectRepository'))
      return
    }

    const selectedPaths = parsePaths(formData.restore_check_paths)
    setArchiveSelection({
      selectedPaths,
      selectedItems: selectedPaths.map((path) => ({ path, type: 'file' })),
    })
    setFormData((current) => ({ ...current, mode: 'probe_paths' }))
    setShowArchivePathPicker(true)
  }

  const importArchiveSelection = () => {
    const paths = archiveSelection.selectedPaths || []
    setFormData({
      ...formData,
      mode: 'probe_paths',
      restore_check_paths: paths.join('\n'),
    })
    setShowArchivePathPicker(false)
  }

  // Open the edit/add dialog for a specific repository (used by deep-links
  // from the By Plan tab). Prefills from the repo's existing restore-check
  // schedule when one exists; otherwise pre-selects the repo so the user only
  // needs to fill the remaining fields.
  const openEditForRepo = async (repoId: number) => {
    const repository = repositories.find((repo) => repo.id === repoId)
    try {
      const response = await repositoriesAPI.getRestoreCheckSchedule(repoId)
      const data = response.data
      const hasSchedule =
        data && data.restore_check_cron_expression && data.restore_check_cron_expression !== ''
      setSelectedRepositoryId(repoId)
      if (hasSchedule) {
        const restoreCheckMode = (data.restore_check_mode || 'canary') as RestoreCheckMode
        setFormData({
          cron_expression: data.restore_check_cron_expression || DEFAULT_CRON,
          timezone: data.restore_check_timezone || data.timezone || getBrowserTimeZone(),
          restore_check_paths: (data.restore_check_paths || []).join('\n'),
          mode:
            repository?.mode === 'observe' && restoreCheckMode === 'canary'
              ? 'probe_paths'
              : restoreCheckMode,
        })
      } else {
        setFormData({
          cron_expression: DEFAULT_CRON,
          timezone: getBrowserTimeZone(),
          restore_check_paths: '',
          mode: repository?.mode === 'observe' ? 'probe_paths' : 'canary',
        })
      }
      setShowDialog(true)
    } catch {
      setSelectedRepositoryId(repoId)
      setFormData({
        cron_expression: DEFAULT_CRON,
        timezone: getBrowserTimeZone(),
        restore_check_paths: '',
        mode: repository?.mode === 'observe' ? 'probe_paths' : 'canary',
      })
      setShowDialog(true)
    }
  }

  useImperativeHandle(ref, () => ({
    openAddDialog,
    openEditForRepo,
  }))

  const handleSubmit = () => {
    if (!selectedRepositoryId) {
      toast.error(t('scheduledRestoreChecks.validation.selectRepository'))
      return
    }

    const probePaths =
      formData.mode === 'probe_paths' ? parsePaths(formData.restore_check_paths) : []
    if (formData.mode === 'probe_paths' && probePaths.length === 0) {
      toast.error(t('scheduledRestoreChecks.validation.enterProbePath'))
      return
    }
    if (selectedRepositoryIsObserveOnly && formData.mode === 'canary') {
      toast.error(t('scheduledRestoreChecks.canaryUnavailableObserveOnly'))
      return
    }

    updateMutation.mutate({
      repoId: selectedRepositoryId,
      data: {
        cron_expression: formData.cron_expression,
        timezone: formData.timezone,
        paths: probePaths,
        full_archive: formData.mode === 'full_archive',
      },
    })
  }

  const handleDelete = (check: ScheduledRestoreCheck) => {
    if (
      confirm(t('scheduledRestoreChecks.confirmDisable', { repositoryName: check.repository_name }))
    ) {
      updateMutation.mutate({
        repoId: check.repository_id,
        data: { cron_expression: '' },
      })
    }
  }

  const handleToggle = (check: ScheduledRestoreCheck) => {
    const current = check.restore_check_schedule_enabled ?? check.enabled
    updateMutation.mutate({
      repoId: check.repository_id,
      data: { schedule_enabled: !current },
    })
  }

  return (
    <Box>
      <Box
        sx={{
          mb: 2,
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          alignItems: { xs: 'stretch', sm: 'center' },
          justifyContent: 'space-between',
          gap: 1.5,
        }}
      >
        <Box>
          <Typography variant="h6" fontWeight={600}>
            {t('scheduledRestoreChecks.sectionTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('scheduledRestoreChecks.sectionDescription')}
          </Typography>
        </Box>
      </Box>

      {!loadingRepositories && manageableRepositories.length === 0 ? (
        <Alert severity="info">{t('scheduledRestoreChecks.needRepository')}</Alert>
      ) : (
        <Stack spacing={3}>
          {isLoading || loadingRepositories ? (
            <Stack spacing={2}>
              {[0, 1, 2].map((i) => (
                <EntityCardSkeleton
                  key={i}
                  titleWidth={[180, 150, 200][i]}
                  opacity={Math.max(0.4, 1 - i * 0.2)}
                />
              ))}
            </Stack>
          ) : !scheduledChecks || scheduledChecks.length === 0 ? (
            <Box
              sx={{
                py: 5,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                color: 'text.secondary',
              }}
            >
              <LifeBuoy size={40} style={{ opacity: 0.25, marginBottom: 12 }} />
              <Typography variant="body1" gutterBottom>
                {t('scheduledRestoreChecks.noScheduledChecks')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {t('scheduledRestoreChecks.noScheduledChecksDesc')}
              </Typography>
            </Box>
          ) : (
            <Stack spacing={2}>
              {scheduledChecks.map((check) => (
                <ScheduleRestoreCheckCard
                  key={check.repository_id}
                  check={check}
                  canManage={canDo(check.repository_id, 'maintenance')}
                  onEdit={() => openEditDialog(check)}
                  onDelete={() => handleDelete(check)}
                  onRunNow={() => runRestoreCheckMutation.mutate(check.repository_id)}
                  onToggle={() => handleToggle(check)}
                />
              ))}
            </Stack>
          )}

          <Box>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              {t('integrity.history.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
              {t('integrity.history.description')}
            </Typography>
            <DataTable
              data={restoreJobs}
              columns={historyColumns}
              actions={historyActions}
              getRowKey={(row) => row.id}
              loading={loadingRestoreJobs}
              tableId="schedule-restore-history"
              actionColumnWidth="88px"
              emptyState={{
                icon: <LifeBuoy size={28} />,
                title: t('integrity.history.emptyTitle'),
                description: t('integrity.history.emptyDescription'),
              }}
            />
          </Box>
        </Stack>
      )}

      <ResponsiveDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        maxWidth="sm"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setShowDialog(false)}>{t('common.buttons.cancel')}</Button>
            <Box sx={{ flex: 1 }} />
            <Button
              onClick={handleSubmit}
              variant="contained"
              disabled={!selectedRepositoryId || updateMutation.isPending}
            >
              {selectedRepositoryId
                ? t('scheduledRestoreChecks.update')
                : t('scheduledRestoreChecks.create')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>
          {selectedRepositoryId
            ? t('scheduledRestoreChecks.editRestoreCheckSchedule')
            : t('scheduledRestoreChecks.addRestoreCheckSchedule')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <RepoSelect
              repositories={manageableRepositories}
              value={selectedRepositoryId || ''}
              onChange={(value) => {
                const repoId = value ? Number(value) : null
                const repository = repoId
                  ? manageableRepositories.find((repo) => repo.id === repoId)
                  : undefined
                setSelectedRepositoryId(repoId)
                if (repository?.mode === 'observe') {
                  setFormData((current) =>
                    current.mode === 'canary' ? { ...current, mode: 'probe_paths' } : current
                  )
                }
              }}
              loading={loadingRepositories}
              valueKey="id"
              label={t('scheduledRestoreChecks.repository')}
              disabled={manageableRepositories.length === 0}
            />

            <TextField
              label={t('scheduledRestoreChecks.scheduleLabel')}
              value={formData.cron_expression}
              onChange={(event) =>
                setFormData({ ...formData, cron_expression: event.target.value })
              }
              fullWidth
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <CronBuilderDialog
                      value={formData.cron_expression}
                      onChange={(localCron) =>
                        setFormData({ ...formData, cron_expression: localCron })
                      }
                      label={t('scheduledRestoreChecks.scheduleLabel')}
                      helperText={t('scheduledRestoreChecks.scheduleHelperText')}
                      dialogTitle={t('scheduledRestoreChecks.scheduleBuilderTitle')}
                    />
                  </InputAdornment>
                ),
              }}
            />

            <Autocomplete
              options={timezoneOptions}
              value={formData.timezone}
              onChange={(_, value) => {
                if (value) setFormData({ ...formData, timezone: value })
              }}
              disableClearable
              fullWidth
              size="medium"
              autoHighlight
              renderInput={(params) => (
                <TextField
                  {...params}
                  label={t('scheduledRestoreChecks.timezoneLabel')}
                  required
                  placeholder="Asia/Kolkata"
                />
              )}
            />

            <FormControl>
              <FormLabel>{t('scheduledRestoreChecks.modeLabel')}</FormLabel>
              <RadioGroup
                value={formData.mode}
                onChange={(event) =>
                  setFormData({
                    ...formData,
                    mode: event.target.value as RestoreCheckMode,
                  })
                }
              >
                <FormControlLabel
                  value="canary"
                  control={<Radio />}
                  label={t('scheduledRestoreChecks.modes.canary')}
                  disabled={selectedRepositoryIsObserveOnly}
                />
                <FormControlLabel
                  value="probe_paths"
                  control={<Radio />}
                  label={t('scheduledRestoreChecks.modes.probePaths')}
                />
                <FormControlLabel
                  value="full_archive"
                  control={<Radio />}
                  label={t('scheduledRestoreChecks.modes.fullArchive')}
                />
              </RadioGroup>
            </FormControl>

            {formData.mode === 'probe_paths' && (
              <TextField
                label={t('scheduledRestoreChecks.probePaths')}
                value={formData.restore_check_paths}
                onChange={(event) =>
                  setFormData({ ...formData, restore_check_paths: event.target.value })
                }
                helperText={t('scheduledRestoreChecks.probePathsHint')}
                multiline
                minRows={4}
                fullWidth
                placeholder={'etc/hostname\nvar/lib/app/config.yml'}
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end" sx={{ alignSelf: 'flex-start', mt: 0.5 }}>
                      <Tooltip
                        title={
                          selectedRepository
                            ? t('scheduledRestoreChecks.archivePicker.open')
                            : t('scheduledRestoreChecks.validation.selectRepository')
                        }
                      >
                        <span>
                          <IconButton
                            edge="end"
                            size="small"
                            onClick={openArchivePathPicker}
                            disabled={!selectedRepository}
                            aria-label={t('scheduledRestoreChecks.archivePicker.open')}
                          >
                            <FolderOpen size={18} />
                          </IconButton>
                        </span>
                      </Tooltip>
                    </InputAdornment>
                  ),
                }}
              />
            )}

            {formData.mode === 'full_archive' ? (
              <Alert severity="warning">{t('scheduledRestoreChecks.fullArchiveWarning')}</Alert>
            ) : formData.mode === 'probe_paths' ? (
              <Stack spacing={1}>
                {selectedRepositoryIsObserveOnly && (
                  <Alert severity="info">
                    {t('scheduledRestoreChecks.canaryUnavailableObserveOnly')}
                  </Alert>
                )}
                <Alert severity="info">{t('scheduledRestoreChecks.probeModeHint')}</Alert>
              </Stack>
            ) : (
              <Alert severity="success">{t('scheduledRestoreChecks.canaryModeHint')}</Alert>
            )}
          </Stack>
        </DialogContent>
      </ResponsiveDialog>

      <ResponsiveDialog
        open={showArchivePathPicker}
        onClose={() => setShowArchivePathPicker(false)}
        maxWidth="md"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Typography variant="body2" color="text.secondary">
              {t('scheduledRestoreChecks.archivePicker.selectedCount', {
                count: archiveSelection.selectedPaths.length,
              })}
            </Typography>
            <Box sx={{ flex: 1 }} />
            <Button onClick={() => setShowArchivePathPicker(false)}>
              {t('common.buttons.cancel')}
            </Button>
            <Button
              variant="contained"
              onClick={importArchiveSelection}
              disabled={!latestArchive || archiveSelection.selectedPaths.length === 0}
            >
              {t('scheduledRestoreChecks.archivePicker.import')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle component="div">
          <Typography variant="h6" fontWeight={600}>
            {t('scheduledRestoreChecks.archivePicker.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {latestArchive
              ? t('scheduledRestoreChecks.archivePicker.subtitleWithArchive', {
                  archive: getArchiveName(latestArchive),
                })
              : t('scheduledRestoreChecks.archivePicker.subtitle')}
          </Typography>
        </DialogTitle>
        <DialogContent
          dividers
          sx={{
            height: 620,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {!selectedRepository ? (
            <Alert severity="info">{t('scheduledRestoreChecks.validation.selectRepository')}</Alert>
          ) : loadingArchiveList ? (
            <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'center', flex: 1 }}>
              <CircularProgress size={32} />
            </Box>
          ) : archiveListError ? (
            <Alert severity="error">{t('scheduledRestoreChecks.archivePicker.loadFailed')}</Alert>
          ) : !latestArchive ? (
            <Alert severity="info">{t('scheduledRestoreChecks.archivePicker.noArchives')}</Alert>
          ) : (
            <ArchivePathSelector
              repository={selectedRepository}
              archive={{
                id: latestArchive.id || getArchiveName(latestArchive),
                name: getArchiveName(latestArchive),
              }}
              data={archiveSelection}
              onChange={(changes) => setArchiveSelection((current) => ({ ...current, ...changes }))}
              title={t('scheduledRestoreChecks.archivePicker.browserTitle')}
              subtitle={t('scheduledRestoreChecks.archivePicker.browserSubtitle')}
              helpText={t('scheduledRestoreChecks.archivePicker.browserHelpText')}
            />
          )}
        </DialogContent>
      </ResponsiveDialog>

      <LogViewerDialog
        job={selectedLogJob}
        open={Boolean(selectedLogJob)}
        onClose={() => setSelectedLogJob(null)}
        jobTypeLabel={t('scheduledRestoreChecks.badge.restoreCheck')}
      />
    </Box>
  )
})

ScheduledRestoreChecksSection.displayName = 'ScheduledRestoreChecksSection'

export default ScheduledRestoreChecksSection
