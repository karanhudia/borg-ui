import { useState, useImperativeHandle, forwardRef } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Stack,
  Alert,
  Button,
  InputAdornment,
  CircularProgress,
} from '@mui/material'
import { Shield } from 'lucide-react'
import { repositoriesAPI } from '../services/api'
import { BorgApiClient } from '../services/borgApi'
import RepoSelect from './RepoSelect'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import { convertCronToUTC, convertCronToLocal } from '../utils/dateUtils'
import CronBuilderDialog from './CronBuilderDialog'
import ScheduleCheckCard from './ScheduleCheckCard'
import { usePermissions } from '../hooks/usePermissions'

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
  const { canDo } = usePermissions()
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
  const manageableRepositories = repositories.filter((repo: { id: number }) =>
    canDo(repo.id, 'maintenance')
  )

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
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      const repo = repositories.find((r: any) => r.id === repoId)
      if (!repo) throw new Error('Repository not found')
      return new BorgApiClient(repo).checkRepository()
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

  return (
    <Box>
      {/* No repositories warning */}
      {manageableRepositories.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          {t('scheduledChecks.needRepository')}
        </Alert>
      )}

      {/* Scheduled Checks */}
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      ) : !scheduledChecks || scheduledChecks.length === 0 ? (
        <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
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
              onRunNow={() => runCheckMutation.mutate(check.repository_id)}
            />
          ))}
        </Stack>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedRepositoryId
            ? t('scheduledChecks.editCheckSchedule')
            : t('scheduledChecks.addCheckSchedule')}
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
