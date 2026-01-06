import { useState, useImperativeHandle, forwardRef } from 'react'
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
} from '@mui/material'
import { Edit, Trash2, Play, Shield } from 'lucide-react'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import {
  formatDate,
  formatRelativeTime,
  convertCronToUTC,
  convertCronToLocal,
} from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from '../components/DataTable'
import CronPickerField from './CronPickerField'

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

const ScheduledChecksSection = forwardRef<ScheduledChecksSectionRef, {}>((_, ref) => {
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
    queryKey: ['scheduled-checks', repositories.map((r: any) => r.id)],
    queryFn: async () => {
      const checks: ScheduledCheck[] = []
      for (const repo of repositories) {
        try {
          const response = await repositoriesAPI.getCheckSchedule(repo.id)
          if (response.data.enabled) {
            checks.push(response.data)
          }
        } catch (err) {
          // Skip repos without check schedules
        }
      }
      return checks
    },
    enabled: repositories.length > 0 && !loadingRepositories,
  })

  // Update check schedule mutation
  const updateMutation = useMutation({
    mutationFn: async ({ repoId, data }: { repoId: number; data: any }) => {
      return await repositoriesAPI.updateCheckSchedule(repoId, data)
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['scheduled-checks'] })
      queryClient.invalidateQueries({ queryKey: ['repositories'] })
      toast.success('Check schedule updated')
      setShowDialog(false)
      setSelectedRepositoryId(null)
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update check schedule')
    },
  })

  // Run check now mutation
  const runCheckMutation = useMutation({
    mutationFn: async (repoId: number) => {
      return await repositoriesAPI.startCheck(repoId, {})
    },
    onSuccess: () => {
      toast.success('Check started')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to start check')
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
      toast.error('Please select a repository')
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
    if (confirm(`Disable scheduled check for ${check.repository_name}?`)) {
      updateMutation.mutate({
        repoId: check.repository_id,
        data: { cron_expression: '' },
      })
    }
  }

  const columns: Column<ScheduledCheck>[] = [
    {
      id: 'repository',
      label: 'Repository',
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
      label: 'Schedule',
      render: (check) => {
        // Convert UTC cron expression to local time for display
        const localCron = check.check_cron_expression
          ? convertCronToLocal(check.check_cron_expression)
          : 'Not configured'
        return (
          <Chip
            label={localCron}
            size="small"
            color="info"
            variant="outlined"
            sx={{ fontFamily: 'monospace' }}
          />
        )
      },
    },
    {
      id: 'last_check',
      label: 'Last Check',
      render: (check) =>
        check.last_scheduled_check ? formatDate(check.last_scheduled_check) : 'Never',
    },
    {
      id: 'next_check',
      label: 'Next Check',
      render: (check) =>
        check.next_scheduled_check ? (
          <Box>
            <Typography variant="body2">{formatDate(check.next_scheduled_check)}</Typography>
            <Typography variant="caption" color="primary.main">
              {formatRelativeTime(check.next_scheduled_check)}
            </Typography>
          </Box>
        ) : (
          'Not scheduled'
        ),
    },
  ]

  const actions: ActionButton<ScheduledCheck>[] = [
    {
      icon: <Play size={16} />,
      label: 'Run Now',
      onClick: (check) => runCheckMutation.mutate(check.repository_id),
      color: 'primary',
      tooltip: 'Run check now',
    },
    {
      icon: <Edit size={16} />,
      label: 'Edit',
      onClick: (check) => openEditDialog(check),
      color: 'default',
      tooltip: 'Edit schedule',
    },
    {
      icon: <Trash2 size={16} />,
      label: 'Delete',
      onClick: (check) => handleDelete(check),
      color: 'error',
      tooltip: 'Disable schedule',
    },
  ]

  return (
    <Box>
      {/* No repositories warning */}
      {repositories.length === 0 && (
        <Alert severity="info" sx={{ mb: 3 }}>
          You need to create at least one repository before scheduling checks.
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
              title: 'No scheduled checks',
              description: 'Configure automatic repository checks to ensure data integrity',
            }}
          />
        </CardContent>
      </Card>

      {/* Add/Edit Dialog */}
      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {selectedRepositoryId ? 'Edit Check Schedule' : 'Add Check Schedule'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={3} sx={{ mt: 1 }}>
            <FormControl fullWidth required size="medium">
              <InputLabel sx={{ fontSize: '1.1rem' }}>Repository</InputLabel>
              <Select
                value={selectedRepositoryId || ''}
                onChange={(e) => setSelectedRepositoryId(Number(e.target.value))}
                label="Repository"
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
                      No repositories available
                    </Typography>
                  </MenuItem>
                ) : (
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

            <CronPickerField
              value={formData.cron_expression}
              onChange={(value) => setFormData({ ...formData, cron_expression: value })}
              label="Check Schedule"
              required={true}
              fullWidth={true}
              size="medium"
            />

            <TextField
              label="Max Duration (seconds)"
              type="number"
              value={formData.max_duration}
              onChange={(e) => setFormData({ ...formData, max_duration: Number(e.target.value) })}
              helperText="Time limit for check operation (3600 = 1 hour)"
              fullWidth
              inputProps={{ min: 60 }}
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              Notification settings for check jobs can be configured in Settings → Notifications
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDialog(false)}>Cancel</Button>
          <Button
            onClick={handleSubmit}
            variant="contained"
            disabled={!selectedRepositoryId || updateMutation.isPending}
          >
            {selectedRepositoryId ? 'Update' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
})

ScheduledChecksSection.displayName = 'ScheduledChecksSection'

export default ScheduledChecksSection
