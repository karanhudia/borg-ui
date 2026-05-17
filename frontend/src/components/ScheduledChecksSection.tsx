import { useState, useImperativeHandle, forwardRef, useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Stack,
  Alert,
  Button,
  InputAdornment,
  Tooltip,
  Select,
  MenuItem,
  Autocomplete,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { Shield, Info } from 'lucide-react'
import { repositoriesAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import RepoSelect from './RepoSelect'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import { getBrowserTimeZone, getSupportedTimeZones } from '../utils/dateUtils'
import CronBuilderDialog from './CronBuilderDialog'
import ScheduleCheckCard from './ScheduleCheckCard'
import EntityCardSkeleton from './EntityCardSkeleton'
import BackupJobsTable from './BackupJobsTable'
import { usePermissions } from '../hooks/usePermissions'
import type { Repository } from '../types'
import type { Job } from '../types/jobs'

interface ScheduledCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  check_cron_expression: string | null
  check_timezone?: string | null
  timezone?: string | null
  last_scheduled_check: string | null
  next_scheduled_check: string | null
  check_max_duration: number
  check_extra_flags?: string | null
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  enabled: boolean
  check_schedule_enabled?: boolean
}

interface CheckHistoryJob extends Job {
  type: 'check'
  scheduled_check: boolean
}

export interface ScheduledChecksSectionRef {
  openAddDialog: () => void
  openEditForRepo: (repoId: number) => Promise<void>
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
const ScheduledChecksSection = forwardRef<ScheduledChecksSectionRef, {}>((_, ref) => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { canDo } = usePermissions()
  const [showDialog, setShowDialog] = useState(false)
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [formData, setFormData] = useState({
    cron_expression: '0 2 * * 0', // Default: Weekly on Sunday at 2 AM
    timezone: getBrowserTimeZone(),
    max_duration: 3600,
    check_extra_flags: '',
  })
  const timezoneOptions = useMemo(
    () => getSupportedTimeZones(formData.timezone),
    [formData.timezone]
  )
  const [historyRepositoryFilter, setHistoryRepositoryFilter] = useState<number | 'all'>('all')
  const [historyStatusFilter, setHistoryStatusFilter] = useState<string | 'all'>('all')

  // Fetch repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = repositoriesData?.data?.repositories || []
  const manageableRepositories = repositories.filter((repo: { id: number }) =>
    canDo(repo.id, 'maintenance')
  )
  const selectedRepository = manageableRepositories.find(
    (repo: Repository) => repo.id === selectedRepositoryId
  ) as Repository | undefined
  const isSelectedRepoBorg2 = selectedRepository?.borg_version === 2

  // Fetch scheduled checks for all repositories
  const { data: scheduledChecks, isLoading } = useQuery({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    queryKey: ['scheduled-checks', repositories.map((r: any) => r.id)],
    queryFn: async () => {
      const checks: ScheduledCheck[] = []
      for (const repo of repositories) {
        try {
          const response = await repositoriesAPI.getCheckSchedule(repo.id)
          // Surface every repo that has a cron configured, even if currently
          // toggled off, so the user can flip it back on without re-entering
          // the schedule.
          if (response.data.check_cron_expression && response.data.check_cron_expression !== '') {
            checks.push(response.data)
          }
        } catch {
          // Skip repos without check schedules
        }
      }
      return checks
    },
    enabled: repositories.length > 0 && !loadingRepositories,
  })

  const { data: checkHistoryData, isLoading: loadingCheckHistory } = useQuery({
    queryKey: [
      'scheduled-check-history',
      manageableRepositories.map((repo: Repository) => repo.id),
    ],
    queryFn: async () => {
      const jobs: CheckHistoryJob[] = []
      for (const repo of manageableRepositories) {
        try {
          const response = await repositoriesAPI.getRepositoryCheckJobs(repo.id, 10, true)
          const repoJobs = response.data.jobs || []
          jobs.push(
            ...repoJobs.map((job: Job & { scheduled_check?: boolean }) => ({
              ...job,
              repository_id: repo.id,
              repository: repo.path,
              repository_path: repo.path,
              type: 'check' as const,
              scheduled_check: Boolean(job.scheduled_check),
            }))
          )
        } catch {
          // Ignore per-repository history failures
        }
      }
      return jobs.sort((a, b) => {
        const aTime = new Date(a.started_at || a.completed_at || 0).getTime()
        const bTime = new Date(b.started_at || b.completed_at || 0).getTime()
        return bTime - aTime
      })
    },
    enabled: manageableRepositories.length > 0 && !loadingRepositories,
    refetchInterval: 5000,
  })

  const checkHistory = checkHistoryData || []
  const filteredCheckHistory = checkHistory.filter((job) => {
    if (historyRepositoryFilter !== 'all' && job.repository_id !== historyRepositoryFilter) {
      return false
    }
    if (historyStatusFilter !== 'all' && job.status !== historyStatusFilter) {
      return false
    }
    return true
  })
  const historyHasFilters = historyRepositoryFilter !== 'all' || historyStatusFilter !== 'all'

  // Update check schedule mutation
  const updateMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: async ({ repoId, data }: { repoId: number; data: any }) => {
      return await repositoriesAPI.updateCheckSchedule(repoId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-checks'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success(t('scheduledChecks.toasts.scheduleUpdated'))
      setShowDialog(false)
      setSelectedRepositoryId(null)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('scheduledChecks.toasts.updateFailed')
      )
    },
  })

  // Run check now mutation
  const runCheckMutation = useMutation({
    mutationFn: async (check: ScheduledCheck) => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const repo = repositories.find((r: any) => r.id === check.repository_id)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).checkRepository({
        maxDuration: check.check_max_duration,
        checkExtraFlags: check.check_extra_flags || '',
      })
    },
    onSuccess: () => {
      toast.success(t('scheduledChecks.toasts.checkStarted'))
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('scheduledChecks.toasts.checkFailed')
      )
    },
  })

  const openAddDialog = () => {
    setSelectedRepositoryId(null)
    setFormData({
      cron_expression: '0 2 * * 0', // Weekly on Sunday at 2 AM
      timezone: getBrowserTimeZone(),
      max_duration: 3600,
      check_extra_flags: '',
    })
    setShowDialog(true)
  }

  const openEditDialog = (check: ScheduledCheck) => {
    setSelectedRepositoryId(check.repository_id)
    setFormData({
      cron_expression: check.check_cron_expression || '0 2 * * 0',
      timezone: check.check_timezone || check.timezone || 'UTC',
      max_duration: check.check_max_duration,
      check_extra_flags: check.check_extra_flags || '',
    })
    setShowDialog(true)
  }

  // Open the edit/add dialog for a specific repository (used by deep-links
  // from the By Plan tab). If the repo already has a check schedule, prefill
  // its current values; otherwise open the add dialog with the repo
  // pre-selected so the user only needs to set the cron.
  const openEditForRepo = async (repoId: number) => {
    try {
      const response = await repositoriesAPI.getCheckSchedule(repoId)
      const data = response.data
      const hasSchedule = data && data.check_cron_expression && data.check_cron_expression !== ''
      setSelectedRepositoryId(repoId)
      if (hasSchedule) {
        setFormData({
          cron_expression: data.check_cron_expression || '0 2 * * 0',
          timezone: data.check_timezone || data.timezone || getBrowserTimeZone(),
          max_duration: data.check_max_duration ?? 3600,
          check_extra_flags: data.check_extra_flags || '',
        })
      } else {
        setFormData({
          cron_expression: '0 2 * * 0',
          timezone: getBrowserTimeZone(),
          max_duration: 3600,
          check_extra_flags: '',
        })
      }
      setShowDialog(true)
    } catch {
      // Fall back to opening the add dialog with the repo preselected
      setSelectedRepositoryId(repoId)
      setFormData({
        cron_expression: '0 2 * * 0',
        timezone: getBrowserTimeZone(),
        max_duration: 3600,
        check_extra_flags: '',
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
      toast.error(t('scheduledChecks.validation.selectRepository'))
      return
    }

    updateMutation.mutate({
      repoId: selectedRepositoryId,
      data: formData,
    })
  }

  const handleDelete = (check: ScheduledCheck) => {
    if (confirm(t('scheduledChecks.confirmDisable', { repositoryName: check.repository_name }))) {
      updateMutation.mutate({
        repoId: check.repository_id,
        data: { cron_expression: '' },
      })
    }
  }

  const handleToggle = (check: ScheduledCheck) => {
    const current = check.check_schedule_enabled ?? check.enabled
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
            {t('scheduledChecks.sectionTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('scheduledChecks.sectionDescription')}
          </Typography>
        </Box>
      </Box>

      {/* No repositories warning */}
      {!loadingRepositories && manageableRepositories.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          {t('scheduledChecks.needRepository')}
        </Alert>
      )}

      {/* Scheduled Checks */}
      {isLoading || loadingRepositories ? (
        <Stack spacing={2}>
          {[0, 1, 2].map((i) => (
            <EntityCardSkeleton
              key={i}
              titleWidth={[170, 190, 140][i]}
              opacity={Math.max(0.4, 1 - i * 0.2)}
            />
          ))}
        </Stack>
      ) : !scheduledChecks || scheduledChecks.length === 0 ? (
        <Box
          sx={{
            py: 6,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            color: 'text.secondary',
          }}
        >
          <Shield size={40} style={{ opacity: 0.25, marginBottom: 12 }} />
          <Typography variant="body1" gutterBottom>
            {t('scheduledChecks.noScheduledChecks')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('scheduledChecks.noScheduledChecksDesc')}
          </Typography>
        </Box>
      ) : (
        <Stack spacing={2}>
          {scheduledChecks.map((check) => (
            <ScheduleCheckCard
              key={check.repository_id}
              check={check}
              canManage={canDo(check.repository_id, 'maintenance')}
              onEdit={() => openEditDialog(check)}
              onDelete={() => handleDelete(check)}
              onRunNow={() => runCheckMutation.mutate(check)}
              onToggle={() => handleToggle(check)}
            />
          ))}
        </Stack>
      )}

      {!loadingRepositories && manageableRepositories.length > 0 && (
        <Box sx={{ mt: 3 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'flex-start',
              justifyContent: 'space-between',
              mb: 2,
              gap: 1,
            }}
          >
            <Box>
              <Typography variant="h6" fontWeight={600}>
                {t('scheduledChecks.historyTitle')}
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {historyHasFilters
                  ? t('scheduledChecks.historyShowingFiltered', {
                      filtered: filteredCheckHistory.length,
                      total: checkHistory.length,
                    })
                  : t('scheduledChecks.historyShowing', {
                      filtered: filteredCheckHistory.length,
                      total: checkHistory.length,
                    })}
              </Typography>
            </Box>

            {historyHasFilters && (
              <Button
                size="small"
                variant="text"
                onClick={() => {
                  setHistoryRepositoryFilter('all')
                  setHistoryStatusFilter('all')
                }}
                sx={{ px: 1, minWidth: 'auto', fontWeight: 700, borderRadius: 2, flexShrink: 0 }}
              >
                {t('common.clearFilters', { defaultValue: 'Clear filters' })}
              </Button>
            )}
          </Box>

          <Box sx={{ mb: 2.5, display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
            <Select
              size="small"
              value={historyRepositoryFilter}
              displayEmpty
              onChange={(e) => setHistoryRepositoryFilter(e.target.value as number | 'all')}
              sx={{ flex: 2, minWidth: { xs: '100%', sm: 220 } }}
            >
              <MenuItem value="all">{t('scheduledChecks.allRepositories')}</MenuItem>
              {manageableRepositories.map((repo: Repository) => (
                <MenuItem key={repo.id} value={repo.id}>
                  {repo.name}
                </MenuItem>
              ))}
            </Select>

            <Select
              size="small"
              value={historyStatusFilter}
              displayEmpty
              onChange={(e) => setHistoryStatusFilter(e.target.value)}
              sx={{ flex: 1, minWidth: { xs: '100%', sm: 160 } }}
            >
              <MenuItem value="all">{t('scheduledChecks.allStatus')}</MenuItem>
              <MenuItem value="completed">{t('backupHistory.completed')}</MenuItem>
              <MenuItem value="failed">{t('backupHistory.failed')}</MenuItem>
              <MenuItem value="cancelled">Cancelled</MenuItem>
              <MenuItem value="running">Running</MenuItem>
            </Select>
          </Box>

          <BackupJobsTable
            jobs={filteredCheckHistory}
            repositories={manageableRepositories}
            loading={loadingCheckHistory}
            actions={{
              viewLogs: true,
              viewArchive: false,
              downloadLogs: true,
              cancel: true,
              errorInfo: true,
              breakLock: false,
              runNow: false,
              delete: true,
            }}
            canDeleteJobs
            emptyState={{
              title: t('scheduledChecks.noHistoryTitle'),
              description: t('scheduledChecks.noHistoryDescription'),
            }}
            tableId="scheduled-check-history"
          />
        </Box>
      )}

      {/* Add/Edit Dialog */}
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
              {selectedRepositoryId ? t('scheduledChecks.update') : t('scheduledChecks.create')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>
          <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span>
              {selectedRepositoryId
                ? t('scheduledChecks.editCheckSchedule')
                : t('scheduledChecks.addCheckSchedule')}
            </span>
            <Tooltip title={t('scheduledChecks.notificationHint')} arrow placement="left">
              <Box
                component="span"
                tabIndex={0}
                aria-label={t('scheduledChecks.notificationHint')}
                sx={{
                  display: 'inline-flex',
                  cursor: 'help',
                  color: 'text.disabled',
                  '&:hover': { color: 'text.secondary' },
                  '&:focus-visible': {
                    outline: '2px solid',
                    outlineColor: 'primary.main',
                    borderRadius: 0.5,
                  },
                }}
              >
                <Info size={16} />
              </Box>
            </Tooltip>
          </Box>
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <RepoSelect
              repositories={manageableRepositories}
              value={selectedRepositoryId || ''}
              onChange={(v) => setSelectedRepositoryId(v ? Number(v) : null)}
              loading={loadingRepositories}
              valueKey="id"
              label={t('scheduledChecks.repository')}
              disabled={manageableRepositories.length === 0}
            />

            <TextField
              label={t('scheduledChecks.checkScheduleLabel')}
              value={formData.cron_expression}
              onChange={(e) => setFormData({ ...formData, cron_expression: e.target.value })}
              required
              fullWidth
              size="medium"
              placeholder="0 2 * * 0"
              InputProps={{
                sx: {
                  fontFamily: 'monospace',
                  fontSize: '1.1rem',
                  letterSpacing: '0.1em',
                },
                endAdornment: (
                  <InputAdornment position="end">
                    <CronBuilderDialog
                      value={formData.cron_expression}
                      onChange={(localCron) =>
                        setFormData({ ...formData, cron_expression: localCron })
                      }
                      label={t('scheduledChecks.checkScheduleLabel')}
                      helperText={t('scheduledChecks.checkScheduleHelperText')}
                      dialogTitle={t('scheduledChecks.checkScheduleBuilderTitle')}
                    />
                  </InputAdornment>
                ),
              }}
              InputLabelProps={{
                sx: { fontSize: '1.1rem' },
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
                  label={t('scheduledChecks.timezoneLabel', { defaultValue: 'Timezone' })}
                  required
                  placeholder="Asia/Kolkata"
                />
              )}
            />

            <TextField
              label={t('scheduledChecks.maxDuration')}
              type="number"
              value={formData.max_duration}
              onChange={(e) => setFormData({ ...formData, max_duration: Number(e.target.value) })}
              helperText={
                isSelectedRepoBorg2
                  ? t('scheduledChecks.maxDurationHintBorg2')
                  : t('scheduledChecks.maxDurationHint')
              }
              fullWidth
              inputProps={{ min: 60 }}
            />

            <TextField
              label={t('scheduledChecks.extraFlags')}
              value={formData.check_extra_flags}
              onChange={(e) => setFormData({ ...formData, check_extra_flags: e.target.value })}
              helperText={t('scheduledChecks.extraFlagsHint')}
              fullWidth
              placeholder="--repair --verify-data"
              inputProps={{ spellCheck: false }}
            />
          </Stack>
        </DialogContent>
      </ResponsiveDialog>
    </Box>
  )
})

ScheduledChecksSection.displayName = 'ScheduledChecksSection'

export default ScheduledChecksSection
