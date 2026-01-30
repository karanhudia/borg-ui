import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  Button,
  TextField,
  CircularProgress,
  Stack,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  IconButton,
  Chip,
  FormControlLabel,
  Switch,
  Alert,
  Collapse,
  Link,
  FormControl,
  FormLabel,
  RadioGroup,
  Radio,
} from '@mui/material'
import {
  Plus,
  Trash2,
  Edit,
  Bell,
  BellOff,
  TestTube,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Archive,
  RotateCcw,
  Settings,
  Copy,
} from 'lucide-react'
import { notificationsAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate } from '../utils/dateUtils'
import { Repository } from '../types'
import MultiRepositorySelector from './MultiRepositorySelector'

interface NotificationSetting {
  id: number
  name: string
  service_url: string
  enabled: boolean
  title_prefix: string | null
  include_job_name_in_title: boolean
  notify_on_backup_start: boolean
  notify_on_backup_success: boolean
  notify_on_backup_failure: boolean
  notify_on_restore_success: boolean
  notify_on_restore_failure: boolean
  notify_on_check_success: boolean
  notify_on_check_failure: boolean
  notify_on_schedule_failure: boolean
  monitor_all_repositories: boolean
  repositories: Repository[]
  created_at: string
  updated_at: string
  last_used_at: string | null
}

const NotificationsTab: React.FC = () => {
  const queryClient = useQueryClient()
  const [showDialog, setShowDialog] = useState(false)
  const [editingNotification, setEditingNotification] = useState<NotificationSetting | null>(null)
  const [deleteConfirm, setDeleteConfirm] = useState<NotificationSetting | null>(null)
  const [testing, setTesting] = useState<number | null>(null)
  const [showExamples, setShowExamples] = useState(false)

  const [formData, setFormData] = useState({
    name: '',
    service_url: '',
    enabled: true,
    title_prefix: '',
    include_job_name_in_title: false,
    notify_on_backup_start: false,
    notify_on_backup_success: false,
    notify_on_backup_failure: true,
    notify_on_restore_success: false,
    notify_on_restore_failure: true,
    notify_on_check_success: false,
    notify_on_check_failure: true,
    notify_on_schedule_failure: true,
    monitor_all_repositories: true,
    repository_ids: [] as number[],
  })

  // Fetch notifications
  const { data: notificationsData, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: async () => {
      const response = await notificationsAPI.list()
      return response.data
    },
  })

  // Fetch repositories for filtering
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.list,
  })

  const repositories = repositoriesData?.data?.repositories || []

  // Create notification
  const createMutation = useMutation({
    mutationFn: notificationsAPI.create,
    onSuccess: () => {
      toast.success('Notification service added successfully')
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      resetForm()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add notification service')
    },
  })

  // Update notification
  const updateMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ id, data }: { id: number; data: any }) => notificationsAPI.update(id, data),
    onSuccess: () => {
      toast.success('Notification service updated successfully')
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      setEditingNotification(null)
      resetForm()
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update notification service')
    },
  })

  // Delete notification
  const deleteMutation = useMutation({
    mutationFn: notificationsAPI.delete,
    onSuccess: () => {
      toast.success('Notification service deleted successfully')
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setDeleteConfirm(null)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete notification service')
    },
  })

  // Test notification
  const testMutation = useMutation({
    mutationFn: (serviceUrl: string) => notificationsAPI.test(serviceUrl),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success('Test notification sent successfully! Check your service.')
      } else {
        toast.error(response.data.message || 'Failed to send test notification')
      }
      setTesting(null)
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to test notification')
      setTesting(null)
    },
  })

  const resetForm = () => {
    setFormData({
      name: '',
      service_url: '',
      enabled: true,
      title_prefix: '',
      include_job_name_in_title: false,
      notify_on_backup_start: false,
      notify_on_backup_success: false,
      notify_on_backup_failure: true,
      notify_on_restore_success: false,
      notify_on_restore_failure: true,
      notify_on_check_success: false,
      notify_on_check_failure: true,
      notify_on_schedule_failure: true,
      monitor_all_repositories: true,
      repository_ids: [],
    })
  }

  const openEditDialog = (notification: NotificationSetting) => {
    setEditingNotification(notification)
    setFormData({
      name: notification.name,
      service_url: notification.service_url,
      enabled: notification.enabled,
      title_prefix: notification.title_prefix || '',
      include_job_name_in_title: notification.include_job_name_in_title || false,
      notify_on_backup_start: notification.notify_on_backup_start,
      notify_on_backup_success: notification.notify_on_backup_success,
      notify_on_backup_failure: notification.notify_on_backup_failure,
      notify_on_restore_success: notification.notify_on_restore_success,
      notify_on_restore_failure: notification.notify_on_restore_failure,
      notify_on_check_success: notification.notify_on_check_success,
      notify_on_check_failure: notification.notify_on_check_failure,
      notify_on_schedule_failure: notification.notify_on_schedule_failure,
      monitor_all_repositories: notification.monitor_all_repositories,
      repository_ids: Array.isArray(notification.repositories)
        ? notification.repositories.map((r) => r.id)
        : [],
    })
    setShowDialog(true)
  }

  const handleDuplicate = (notification: NotificationSetting) => {
    // Clear editing state so it creates a new notification
    setEditingNotification(null)
    // Copy all settings and append "(Copy)" to the name
    setFormData({
      name: `${notification.name} (Copy)`,
      service_url: notification.service_url,
      enabled: notification.enabled,
      title_prefix: notification.title_prefix || '',
      include_job_name_in_title: notification.include_job_name_in_title || false,
      notify_on_backup_start: notification.notify_on_backup_start,
      notify_on_backup_success: notification.notify_on_backup_success,
      notify_on_backup_failure: notification.notify_on_backup_failure,
      notify_on_restore_success: notification.notify_on_restore_success,
      notify_on_restore_failure: notification.notify_on_restore_failure,
      notify_on_check_success: notification.notify_on_check_success,
      notify_on_check_failure: notification.notify_on_check_failure,
      notify_on_schedule_failure: notification.notify_on_schedule_failure,
      monitor_all_repositories: notification.monitor_all_repositories,
      repository_ids: Array.isArray(notification.repositories)
        ? notification.repositories.map((r) => r.id)
        : [],
    })
    setShowDialog(true)
  }

  const handleSubmit = () => {
    if (!formData.name.trim() || !formData.service_url.trim()) {
      toast.error('Name and Service URL are required')
      return
    }

    if (editingNotification) {
      updateMutation.mutate({ id: editingNotification.id, data: formData })
    } else {
      createMutation.mutate(formData)
    }
  }

  const handleTest = (notification: NotificationSetting) => {
    setTesting(notification.id)
    testMutation.mutate(notification.service_url)
  }

  const notifications = notificationsData || []

  return (
    <Box>
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box>
          <Typography variant="h6" fontWeight={600}>
            Notification Services
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Configure notification services for backup and restore alerts
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={() => {
            resetForm()
            setEditingNotification(null)
            setShowDialog(true)
          }}
        >
          Add Service
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2" gutterBottom>
          Get notified about backup failures, restore completions, and scheduled job issues via 100+
          services including Email, Slack, Discord, Telegram, Pushover, and more.
        </Typography>
        <Link
          href="#"
          onClick={(e) => {
            e.preventDefault()
            setShowExamples(!showExamples)
          }}
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}
        >
          {showExamples ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {showExamples ? 'Hide' : 'Show'} Service URL Examples
        </Link>
      </Alert>

      <Collapse in={showExamples}>
        <Card
          sx={{ mb: 3, p: 2, bgcolor: 'background.default', border: 1, borderColor: 'divider' }}
        >
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Apprise URL Examples:
          </Typography>
          <Box
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.75rem',
              bgcolor: 'grey.900',
              color: 'grey.100',
              p: 1.5,
              borderRadius: 1,
              border: '1px solid',
              borderColor: 'grey.700',
              overflow: 'auto',
              lineHeight: 1.4,
            }}
          >
            <Box component="span" sx={{ color: 'grey.400' }}>
              Email (Gmail):{' '}
            </Box>
            <Box component="span">
              mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls
            </Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Slack:{' '}
            </Box>
            <Box component="span">slack://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Discord:{' '}
            </Box>
            <Box component="span">discord://webhook_id/webhook_token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Telegram:{' '}
            </Box>
            <Box component="span">tgram://bot_token/chat_id</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Microsoft Teams:{' '}
            </Box>
            <Box component="span">msteams://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Pushover:{' '}
            </Box>
            <Box component="span">pover://user@token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              ntfy:{' '}
            </Box>
            <Box component="span">ntfy://topic/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              Custom Webhook:{' '}
            </Box>
            <Box component="span">json://hostname/path/to/endpoint</Box>
          </Box>
          <Link
            href="https://github.com/caronc/apprise/wiki"
            target="_blank"
            rel="noopener noreferrer"
            sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1.5 }}
          >
            <ExternalLink size={14} />
            Full Apprise Documentation
          </Link>
        </Card>
      </Collapse>

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : notifications.length === 0 ? (
        <Card sx={{ p: 4, textAlign: 'center' }}>
          <Bell size={48} style={{ opacity: 0.3, margin: '0 auto 16px' }} />
          <Typography variant="h6" gutterBottom>
            No Notification Services Configured
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Add your first notification service to get alerts about backup failures and other
            important events.
          </Typography>
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={() => {
              resetForm()
              setShowDialog(true)
            }}
          >
            Add Service
          </Button>
        </Card>
      ) : (
        <Card>
          <TableContainer>
            <Table>
              <TableHead>
                <TableRow>
                  <TableCell>Service</TableCell>
                  <TableCell>Status</TableCell>
                  <TableCell>Events</TableCell>
                  <TableCell>Repositories</TableCell>
                  <TableCell>Last Used</TableCell>
                  <TableCell align="right">Actions</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {notifications.map((notification: NotificationSetting) => (
                  <TableRow key={notification.id}>
                    <TableCell>
                      <Box>
                        <Typography variant="body2" fontWeight={500}>
                          {notification.name}
                        </Typography>
                        <Typography
                          variant="caption"
                          color="text.secondary"
                          sx={{ fontFamily: 'monospace' }}
                        >
                          {notification.service_url.substring(0, 40)}
                          {notification.service_url.length > 40 && '...'}
                        </Typography>
                      </Box>
                    </TableCell>
                    <TableCell>
                      <Chip
                        icon={notification.enabled ? <Bell size={14} /> : <BellOff size={14} />}
                        label={notification.enabled ? 'Enabled' : 'Disabled'}
                        color={notification.enabled ? 'success' : 'default'}
                        size="small"
                      />
                    </TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} flexWrap="wrap" gap={0.5}>
                        {notification.notify_on_backup_start && (
                          <Chip label="Backup Start" size="small" color="info" variant="outlined" />
                        )}
                        {notification.notify_on_backup_failure && (
                          <Chip label="Backup Fail" size="small" color="error" variant="outlined" />
                        )}
                        {notification.notify_on_backup_success && (
                          <Chip label="Backup OK" size="small" color="success" variant="outlined" />
                        )}
                        {notification.notify_on_restore_failure && (
                          <Chip
                            label="Restore Fail"
                            size="small"
                            color="error"
                            variant="outlined"
                          />
                        )}
                        {notification.notify_on_restore_success && (
                          <Chip
                            label="Restore OK"
                            size="small"
                            color="success"
                            variant="outlined"
                          />
                        )}
                        {notification.notify_on_check_failure && (
                          <Chip label="Check Fail" size="small" color="error" variant="outlined" />
                        )}
                        {notification.notify_on_check_success && (
                          <Chip label="Check OK" size="small" color="success" variant="outlined" />
                        )}
                        {notification.notify_on_schedule_failure && (
                          <Chip
                            label="Scheduler Error"
                            size="small"
                            color="warning"
                            variant="outlined"
                          />
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell>
                      {notification.monitor_all_repositories ? (
                        <Chip label="All Repositories" size="small" variant="outlined" />
                      ) : notification.repositories.length > 0 ? (
                        <Chip
                          label={`${notification.repositories.length} ${
                            notification.repositories.length === 1 ? 'Repository' : 'Repositories'
                          }`}
                          size="small"
                          color="primary"
                          variant="outlined"
                        />
                      ) : (
                        <Chip
                          label="None Selected"
                          size="small"
                          color="warning"
                          variant="outlined"
                        />
                      )}
                    </TableCell>
                    <TableCell>
                      <Typography variant="body2" color="text.secondary">
                        {formatDate(notification.last_used_at)}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Stack direction="row" spacing={0.5} justifyContent="flex-end">
                        <IconButton
                          size="small"
                          onClick={() => handleTest(notification)}
                          disabled={testing === notification.id}
                          title="Send test notification"
                        >
                          {testing === notification.id ? (
                            <CircularProgress size={16} />
                          ) : (
                            <TestTube size={16} />
                          )}
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => handleDuplicate(notification)}
                          color="default"
                          title="Duplicate notification"
                        >
                          <Copy size={16} />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => openEditDialog(notification)}
                          color="primary"
                          title="Edit notification"
                        >
                          <Edit size={16} />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => setDeleteConfirm(notification)}
                          color="error"
                          title="Delete notification"
                        >
                          <Trash2 size={16} />
                        </IconButton>
                      </Stack>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        </Card>
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingNotification ? 'Edit Notification Service' : 'Add Notification Service'}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Service Name"
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder="e.g., Slack - DevOps Channel"
              fullWidth
              required
            />

            <TextField
              label="Service URL"
              value={formData.service_url}
              onChange={(e) => setFormData({ ...formData, service_url: e.target.value })}
              placeholder="e.g., slack://TokenA/TokenB/TokenC/"
              fullWidth
              required
              helperText="Use Apprise URL format. See examples above."
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              <strong>Tip:</strong> For automation and monitoring, use <code>jsons://</code> or{' '}
              <code>json://</code> URLs to automatically receive pure JSON data.
            </Alert>

            <TextField
              label="Title Prefix (Optional)"
              value={formData.title_prefix}
              onChange={(e) => setFormData({ ...formData, title_prefix: e.target.value })}
              placeholder="e.g., [Production] or [Dev]"
              fullWidth
              helperText="Add a custom prefix to all notification titles (e.g., '[Production] ✅ Backup Successful')"
            />

            <Box sx={{ mt: 2, mb: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.enabled}
                    onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  />
                }
                label="Enable notifications"
              />
            </Box>

            <Box sx={{ mt: 2, mb: 1 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                Notification Enhancements
              </Typography>

              <FormControlLabel
                control={
                  <Switch
                    checked={formData.include_job_name_in_title}
                    onChange={(e) =>
                      setFormData({ ...formData, include_job_name_in_title: e.target.checked })
                    }
                  />
                }
                label="Include job/schedule name in title"
              />
              <Typography
                variant="caption"
                sx={{ display: 'block', pl: 4.5, mt: -0.5, mb: 1, color: 'text.secondary' }}
              >
                Adds job or schedule name to notification titles for easier identification (e.g.,
                "✅ Backup Successful - Daily Backup")
              </Typography>
            </Box>

            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
              Notify on:
            </Typography>

            {/* Backup Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Archive size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  Backup Events
                </Typography>
              </Box>
              <Box sx={{ pl: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_backup_start}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_backup_start: e.target.checked })
                      }
                    />
                  }
                  label="Started"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_backup_success}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_backup_success: e.target.checked })
                      }
                    />
                  }
                  label="Success"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_backup_failure}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_backup_failure: e.target.checked })
                      }
                    />
                  }
                  label="Failure"
                />
              </Box>
            </Box>

            {/* Restore Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <RotateCcw size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  Restore Events
                </Typography>
              </Box>
              <Box sx={{ pl: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_restore_success}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_restore_success: e.target.checked })
                      }
                    />
                  }
                  label="Success"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_restore_failure}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_restore_failure: e.target.checked })
                      }
                    />
                  }
                  label="Failure"
                />
              </Box>
            </Box>

            {/* Check Jobs Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Settings size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  Check Jobs
                </Typography>
              </Box>
              <Box sx={{ pl: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_check_success}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_check_success: e.target.checked })
                      }
                    />
                  }
                  label="Success"
                />
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_check_failure}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_check_failure: e.target.checked })
                      }
                    />
                  }
                  label="Failure"
                />
              </Box>
            </Box>

            {/* System Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Settings size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  System Events
                </Typography>
              </Box>
              <Box sx={{ pl: 2 }}>
                <FormControlLabel
                  control={
                    <Switch
                      checked={formData.notify_on_schedule_failure}
                      onChange={(e) =>
                        setFormData({ ...formData, notify_on_schedule_failure: e.target.checked })
                      }
                    />
                  }
                  label="Scheduler Errors"
                />
                <Typography
                  variant="caption"
                  sx={{ display: 'block', pl: 4.5, mt: -0.5, mb: 1, color: 'text.secondary' }}
                >
                  Notifies when the scheduler fails to start a backup (e.g., system errors). Regular
                  backup failures are handled above.
                </Typography>
              </Box>
            </Box>

            {/* Repository Filter Section */}
            <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
              <FormControl component="fieldset">
                <FormLabel component="legend" sx={{ mb: 1 }}>
                  Apply To Repositories
                </FormLabel>
                <RadioGroup
                  value={formData.monitor_all_repositories ? 'all' : 'selected'}
                  onChange={(e) =>
                    setFormData({ ...formData, monitor_all_repositories: e.target.value === 'all' })
                  }
                >
                  <FormControlLabel value="all" control={<Radio />} label="All Repositories" />
                  <FormControlLabel
                    value="selected"
                    control={<Radio />}
                    label="Selected Repositories Only"
                  />
                </RadioGroup>
              </FormControl>

              {!formData.monitor_all_repositories && (
                <Box sx={{ mt: 2 }}>
                  <MultiRepositorySelector
                    repositories={repositories || []}
                    selectedIds={formData.repository_ids}
                    onChange={(ids) => setFormData({ ...formData, repository_ids: ids })}
                    label="Select Repositories"
                    placeholder="Choose repositories to monitor"
                    helperText="Only send notifications for backups from these repositories"
                    allowReorder={false}
                  />
                </Box>
              )}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDialog(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            {createMutation.isPending || updateMutation.isPending ? (
              <CircularProgress size={20} />
            ) : editingNotification ? (
              'Update'
            ) : (
              'Add'
            )}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)}>
        <DialogTitle>Delete Notification Service?</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{deleteConfirm?.name}</strong>? You will no
            longer receive notifications from this service.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirm(null)}>Cancel</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.id)}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? <CircularProgress size={20} /> : 'Delete'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default NotificationsTab
