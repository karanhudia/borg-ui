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
} from 'lucide-react'
import { notificationsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate } from '../utils/dateUtils'

interface NotificationSetting {
  id: number
  name: string
  service_url: string
  enabled: boolean
  title_prefix: string | null
  notify_on_backup_success: boolean
  notify_on_backup_failure: boolean
  notify_on_restore_success: boolean
  notify_on_restore_failure: boolean
  notify_on_schedule_failure: boolean
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
    notify_on_backup_success: false,
    notify_on_backup_failure: true,
    notify_on_restore_success: false,
    notify_on_restore_failure: true,
    notify_on_schedule_failure: true,
  })

  // Fetch notifications
  const { data: notificationsData, isLoading } = useQuery({
    queryKey: ['notifications'],
    queryFn: async () => {
      const response = await notificationsAPI.list()
      return response.data
    },
  })

  // Create notification
  const createMutation = useMutation({
    mutationFn: notificationsAPI.create,
    onSuccess: () => {
      toast.success('Notification service added successfully')
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      resetForm()
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to add notification service')
    },
  })

  // Update notification
  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) => notificationsAPI.update(id, data),
    onSuccess: () => {
      toast.success('Notification service updated successfully')
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      setEditingNotification(null)
      resetForm()
    },
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
      notify_on_backup_success: false,
      notify_on_backup_failure: true,
      notify_on_restore_success: false,
      notify_on_restore_failure: true,
      notify_on_schedule_failure: true,
    })
  }

  const openEditDialog = (notification: NotificationSetting) => {
    setEditingNotification(notification)
    setFormData({
      name: notification.name,
      service_url: notification.service_url,
      enabled: notification.enabled,
      title_prefix: notification.title_prefix || '',
      notify_on_backup_success: notification.notify_on_backup_success,
      notify_on_backup_failure: notification.notify_on_backup_failure,
      notify_on_restore_success: notification.notify_on_restore_success,
      notify_on_restore_failure: notification.notify_on_restore_failure,
      notify_on_schedule_failure: notification.notify_on_schedule_failure,
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
          Get notified about backup failures, restore completions, and scheduled job issues via 100+ services
          including Email, Slack, Discord, Telegram, Pushover, and more.
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
        <Card sx={{ mb: 3, p: 2, bgcolor: 'background.default', border: 1, borderColor: 'divider' }}>
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            Apprise URL Examples:
          </Typography>
          <Box sx={{
            fontFamily: 'monospace',
            fontSize: '0.75rem',
            bgcolor: 'grey.900',
            color: 'grey.100',
            p: 1.5,
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'grey.700',
            overflow: 'auto',
            lineHeight: 1.4
          }}>
            <Box component="span" sx={{ color: 'grey.400' }}>Email (Gmail): </Box>
            <Box component="span">mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Slack: </Box>
            <Box component="span">slack://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Discord: </Box>
            <Box component="span">discord://webhook_id/webhook_token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Telegram: </Box>
            <Box component="span">tgram://bot_token/chat_id</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Microsoft Teams: </Box>
            <Box component="span">msteams://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Pushover: </Box>
            <Box component="span">pover://user@token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>ntfy: </Box>
            <Box component="span">ntfy://topic/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>Custom Webhook: </Box>
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
            Add your first notification service to get alerts about backup failures and other important events.
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
                        <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
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
                        {notification.notify_on_backup_failure && (
                          <Chip label="Backup Fail" size="small" color="error" variant="outlined" />
                        )}
                        {notification.notify_on_backup_success && (
                          <Chip label="Backup OK" size="small" color="success" variant="outlined" />
                        )}
                        {notification.notify_on_restore_failure && (
                          <Chip label="Restore Fail" size="small" color="error" variant="outlined" />
                        )}
                        {notification.notify_on_restore_success && (
                          <Chip label="Restore OK" size="small" color="success" variant="outlined" />
                        )}
                        {notification.notify_on_schedule_failure && (
                          <Chip label="Schedule Fail" size="small" color="error" variant="outlined" />
                        )}
                      </Stack>
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
                          onClick={() => openEditDialog(notification)}
                          color="primary"
                        >
                          <Edit size={16} />
                        </IconButton>
                        <IconButton
                          size="small"
                          onClick={() => setDeleteConfirm(notification)}
                          color="error"
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

            <TextField
              label="Title Prefix (Optional)"
              value={formData.title_prefix}
              onChange={(e) => setFormData({ ...formData, title_prefix: e.target.value })}
              placeholder="e.g., [Production] or [Dev]"
              fullWidth
              helperText="Add a custom prefix to all notification titles (e.g., '[Production] ✅ Backup Successful')"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.enabled}
                  onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                />
              }
              label="Enable notifications"
            />

            <Typography variant="subtitle2" sx={{ mt: 2 }}>
              Notify on:
            </Typography>

            <FormControlLabel
              control={
                <Switch
                  checked={formData.notify_on_backup_failure}
                  onChange={(e) =>
                    setFormData({ ...formData, notify_on_backup_failure: e.target.checked })
                  }
                />
              }
              label="Backup Failures (Critical)"
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
              label="Backup Success"
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
              label="Restore Failures"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.notify_on_restore_success}
                  onChange={(e) =>
                    setFormData({ ...formData, notify_on_restore_success: e.target.checked })
                  }
                />
              }
              label="Restore Success"
            />

            <FormControlLabel
              control={
                <Switch
                  checked={formData.notify_on_schedule_failure}
                  onChange={(e) =>
                    setFormData({ ...formData, notify_on_schedule_failure: e.target.checked })
                  }
                />
              }
              label="Scheduled Backup Failures"
            />
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
            Are you sure you want to delete <strong>{deleteConfirm?.name}</strong>? You will no longer
            receive notifications from this service.
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
