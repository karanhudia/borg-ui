import { useState, useImperativeHandle, forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Stack,
  Alert,
  Button,
  InputAdornment,
} from '@mui/material'
import { Edit, Trash2, Play, Shield } from 'lucide-react'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import {
  formatDate,
  formatRelativeTime,
  convertCronToUTC,
  convertCronToLocal,
  formatCronHuman,
} from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from '../components/DataTable'
import CronBuilderDialog from './CronBuilderDialog'

interface ScheduledCheck {
  repository_id: number
  repository_name: string
  repository_path: string
  check_cron_expression: string | null
  last_scheduled_check: string | null
  next_scheduled_check: string | null
  check_max_duration: number
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  enabled: boolean
}

export interface ScheduledChecksSectionRef {
  openAddDialog: () => void
}

// eslint-disable-next-line @typescript-eslint/no-empty-object-type
const ScheduledChecksSection = forwardRef<ScheduledChecksSectionRef, {}>((_, ref) => {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [selectedRepositoryId, setSelectedRepositoryId] = useState<number | null>(null)
  const [formData, setFormData] = useState({
    cron_expression: '0 2 * * 0', // Default: Weekly on Sunday at 2 AM
    max_duration: 3600,
  })

  // Fetch repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  const repositories = repositoriesData?.data?.repositories || []

  // Fetch scheduled checks for all repositories
  const { data: scheduledChecks, isLoading } = useQuery({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    queryKey: ['scheduled-checks', repositories.map((r: any) => r.id)],
    queryFn: async () => {
      const checks: ScheduledCheck[] = []
      for (const repo of repositories) {
        try {
          const response = await repositoriesAPI.getCheckSchedule(repo.id)
          if (response.data.enabled) {
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
    mutationFn: async (repoId: number) => {
      return await repositoriesAPI.startCheck(repoId, {})
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
      max_duration: 3600,
    })
    setShowDialog(true)
  }

  const openEditDialog = (check: ScheduledCheck) => {
    setSelectedRepositoryId(check.repository_id)
    // Convert UTC cron expression to local time for editing
    const localCron = check.check_cron_expression
      ? convertCronToLocal(check.check_cron_expression)
      : '0 2 * * 0'
    setFormData({
      cron_expression: localCron,
      max_duration: check.check_max_duration,
    })
    setShowDialog(true)
  }

  // Expose openAddDialog to parent via ref
  useImperativeHandle(ref, () => ({
    openAddDialog,
  }))

  const handleSubmit = () => {
    if (!selectedRepositoryId) {
      toast.error(t('scheduledChecks.validation.selectRepository'))
      return
    }

    // Convert cron expression from local time to UTC before sending to server
    const utcCron = convertCronToUTC(formData.cron_expression)

    updateMutation.mutate({
      repoId: selectedRepositoryId,
      data: {
        ...formData,
        cron_expression: utcCron,
      },
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

  const columns: Column<ScheduledCheck>[] = [
    {
      id: 'repository',
      label: t('scheduledChecks.repository'),
      render: (check) => (
        <Box>
          <Typography variant="body2" fontWeight={500}>
            {check.repository_name}
          </Typography>
          <Typography variant="caption" color="text.secondary">
            {check.repository_path}
          </Typography>
        </Box>
      ),
    },
    {
      id: 'schedule',
      label: t('scheduledChecks.schedule'),
      render: (check) => {
        // Convert UTC cron expression to local time for display
        const localCron = check.check_cron_expression
          ? convertCronToLocal(check.check_cron_expression)
          : t('scheduledChecks.notConfigured')
        const label = check.check_cron_expression ? formatCronHuman(localCron) : localCron
        return <Chip label={label} size="small" color="info" variant="outlined" />
      },
    },
    {
      id: 'last_check',
      label: t('scheduledChecks.lastCheck'),
      render: (check) =>
        check.last_scheduled_check
          ? formatDate(check.last_scheduled_check)
          : t('scheduledChecks.never'),
    },
    {
      id: 'next_check',
      label: t('scheduledChecks.nextCheck'),
      render: (check) =>
        check.next_scheduled_check ? (
          <Box>
            <Typography variant="body2">{formatDate(check.next_scheduled_check)}</Typography>
            <Typography variant="caption" color="primary.main">
              {formatRelativeTime(check.next_scheduled_check)}
            </Typography>
          </Box>
        ) : (
          t('scheduledChecks.notScheduled')
        ),
    },
  ]

  const actions: ActionButton<ScheduledCheck>[] = [
    {
      icon: <Play size={16} />,
      label: t('common.buttons.run'),
      onClick: (check) => runCheckMutation.mutate(check.repository_id),
      color: 'primary',
      tooltip: t('scheduledChecks.tooltips.runNow'),
    },
    {
      icon: <Edit size={16} />,
      label: t('common.buttons.edit'),
      onClick: (check) => openEditDialog(check),
      color: 'default',
      tooltip: t('scheduledChecks.tooltips.editSchedule'),
    },
    {
      icon: <Trash2 size={16} />,
      label: t('common.buttons.delete'),
      onClick: (check) => handleDelete(check),
      color: 'error',
      tooltip: t('scheduledChecks.tooltips.disableSchedule'),
    },
  ]

  return (
    <Box>
      {/* No repositories warning */}
      {repositories.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          {t('scheduledChecks.needRepository')}
        </Alert>
      )}

      {/* Scheduled Checks Table */}
      <Card>
        <CardContent>
          <DataTable
            data={scheduledChecks || []}
            columns={columns}
            actions={actions}
            getRowKey={(check) => check.repository_id.toString()}
            loading={isLoading}
            enableHover={true}
            emptyState={{
              icon: <Shield size={48} />,
              title: t('scheduledChecks.noScheduledChecks'),
              description: t('scheduledChecks.noScheduledChecksDesc'),
            }}
          />
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedRepositoryId
            ? t('scheduledChecks.editCheckSchedule')
            : t('scheduledChecks.addCheckSchedule')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <FormControl fullWidth required size="medium">
              <InputLabel sx={{ fontSize: '1.1rem' }}>{t('scheduledChecks.repository')}</InputLabel>
              <Select
                value={selectedRepositoryId || ''}
                onChange={(e) => setSelectedRepositoryId(Number(e.target.value))}
                label={t('scheduledChecks.repository')}
                disabled={loadingRepositories || repositories.length === 0}
                sx={{ fontSize: '1.1rem', height: { xs: 48, sm: 56 } }}
                MenuProps={{
                  PaperProps: {
                    style: {
                      maxHeight: 400,
                    },
                  },
                }}
              >
                {repositories.length === 0 ? (
                  <MenuItem disabled>
                    <Typography variant="body2" color="text.secondary">
                      {t('scheduledChecks.noRepositoriesAvailable')}
                    </Typography>
                  </MenuItem>
                ) : (
                  // eslint-disable-next-line @typescript-eslint/no-explicit-any
                  repositories.map((repo: any) => (
                    <MenuItem key={repo.id} value={repo.id} sx={{ fontSize: '1rem' }}>
                      <Box>
                        <Typography variant="body2" sx={{ fontSize: '1rem' }}>
                          {repo.name}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ fontSize: '0.85rem' }}
                        >
                          {repo.path}
                        </Typography>
                      </Box>
                    </MenuItem>
                  ))
                )}
              </Select>
            </FormControl>

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

            <TextField
              label={t('scheduledChecks.maxDuration')}
              type="number"
              value={formData.max_duration}
              onChange={(e) => setFormData({ ...formData, max_duration: Number(e.target.value) })}
              helperText={t('scheduledChecks.maxDurationHint')}
              fullWidth
              inputProps={{ min: 60 }}
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              {t('scheduledChecks.notificationHint')}
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDialog(false)}>{t('common.buttons.cancel')}</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!selectedRepositoryId || updateMutation.isPending}
          >
            {selectedRepositoryId ? t('scheduledChecks.update') : t('scheduledChecks.create')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
})

ScheduledChecksSection.displayName = 'ScheduledChecksSection'

export default ScheduledChecksSection
