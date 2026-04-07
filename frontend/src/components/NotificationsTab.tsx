import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
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
import { translateBackendKey } from '../utils/translateBackendKey'
import { formatDate } from '../utils/dateUtils'
import { Repository } from '../types'
import MultiRepositorySelector from './MultiRepositorySelector'
import { useAnalytics } from '../hooks/useAnalytics'
import DataTable, { ActionButton, Column } from './DataTable'

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
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { trackNotifications, EventAction } = useAnalytics()
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
      toast.success(t('notifications.serviceAddedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      resetForm()
      trackNotifications(EventAction.CREATE, {
        enabled: formData.enabled,
        monitor_all_repositories: formData.monitor_all_repositories,
        repository_count: formData.repository_ids.length,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('notifications.failedToAdd')
      )
    },
  })

  // Update notification
  const updateMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: ({ id, data }: { id: number; data: any }) => notificationsAPI.update(id, data),
    onSuccess: () => {
      toast.success(t('notifications.serviceUpdatedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setShowDialog(false)
      setEditingNotification(null)
      resetForm()
      trackNotifications(EventAction.EDIT, {
        enabled: formData.enabled,
        monitor_all_repositories: formData.monitor_all_repositories,
        repository_count: formData.repository_ids.length,
      })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('notifications.failedToUpdate')
      )
    },
  })

  // Delete notification
  const deleteMutation = useMutation({
    mutationFn: notificationsAPI.delete,
    onSuccess: () => {
      toast.success(t('notifications.serviceDeletedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['notifications'] })
      setDeleteConfirm(null)
      trackNotifications(EventAction.DELETE, {})
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('notifications.failedToDelete')
      )
    },
  })

  // Test notification
  const testMutation = useMutation({
    mutationFn: (serviceUrl: string) => notificationsAPI.test(serviceUrl),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('notifications.testSentSuccessfully'))
      } else {
        toast.error(
          translateBackendKey(response.data.message) || t('notifications.failedToSendTest')
        )
      }
      setTesting(null)
      trackNotifications(EventAction.TEST, { success: !!response.data.success })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(
        translateBackendKey(error.response?.data?.detail) || t('notifications.failedToTest')
      )
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
    trackNotifications(EventAction.VIEW, {
      source: 'duplicate',
      repository_count: notification.repositories.length,
    })
  }

  const handleSubmit = () => {
    if (!formData.name.trim() || !formData.service_url.trim()) {
      toast.error(t('notifications.nameAndUrlRequired'))
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

  const renderEventChips = (notification: NotificationSetting) => (
    <Stack direction="row" spacing={0.5} flexWrap="wrap" gap={0.5}>
      {notification.notify_on_backup_start && (
        <Chip
          label={t('notifications.chip.backupStart')}
          size="small"
          color="info"
          variant="outlined"
        />
      )}
      {notification.notify_on_backup_failure && (
        <Chip
          label={t('notifications.chip.backupFail')}
          size="small"
          color="error"
          variant="outlined"
        />
      )}
      {notification.notify_on_backup_success && (
        <Chip
          label={t('notifications.chip.backupOk')}
          size="small"
          color="success"
          variant="outlined"
        />
      )}
      {notification.notify_on_restore_failure && (
        <Chip
          label={t('notifications.chip.restoreFail')}
          size="small"
          color="error"
          variant="outlined"
        />
      )}
      {notification.notify_on_restore_success && (
        <Chip
          label={t('notifications.chip.restoreOk')}
          size="small"
          color="success"
          variant="outlined"
        />
      )}
      {notification.notify_on_check_failure && (
        <Chip
          label={t('notifications.chip.checkFail')}
          size="small"
          color="error"
          variant="outlined"
        />
      )}
      {notification.notify_on_check_success && (
        <Chip
          label={t('notifications.chip.checkOk')}
          size="small"
          color="success"
          variant="outlined"
        />
      )}
      {notification.notify_on_schedule_failure && (
        <Chip
          label={t('notifications.chip.schedulerError')}
          size="small"
          color="warning"
          variant="outlined"
        />
      )}
    </Stack>
  )

  const columns: Column<NotificationSetting>[] = [
    {
      id: 'service',
      label: t('notifications.table.service'),
      render: (notification) => (
        <Box>
          <Typography variant="body2" fontWeight={500}>
            {notification.name}
          </Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontFamily: 'monospace' }}>
            {notification.service_url.substring(0, 40)}
            {notification.service_url.length > 40 && '...'}
          </Typography>
        </Box>
      ),
    },
    {
      id: 'status',
      label: t('notifications.table.status'),
      render: (notification) => (
        <Chip
          icon={notification.enabled ? <Bell size={14} /> : <BellOff size={14} />}
          label={notification.enabled ? t('notifications.enabled') : t('notifications.disabled')}
          color={notification.enabled ? 'success' : 'default'}
          size="small"
        />
      ),
    },
    {
      id: 'events',
      label: t('notifications.table.events'),
      render: renderEventChips,
    },
    {
      id: 'repositories',
      label: t('notifications.table.repositories'),
      render: (notification) =>
        notification.monitor_all_repositories ? (
          <Chip label={t('notifications.chip.allRepositories')} size="small" variant="outlined" />
        ) : notification.repositories.length > 0 ? (
          <Chip
            label={t('notifications.chip.repositoryCount', {
              count: notification.repositories.length,
            })}
            size="small"
            color="primary"
            variant="outlined"
          />
        ) : (
          <Chip
            label={t('notifications.chip.noneSelected')}
            size="small"
            color="warning"
            variant="outlined"
          />
        ),
    },
    {
      id: 'last_used_at',
      label: t('notifications.table.lastUsed'),
      render: (notification) => (
        <Typography variant="body2" color="text.secondary">
          {formatDate(notification.last_used_at)}
        </Typography>
      ),
    },
  ]

  const actions: ActionButton<NotificationSetting>[] = [
    {
      label: t('notifications.tooltip.sendTest'),
      icon: testing !== null ? <TestTube size={16} /> : <TestTube size={16} />,
      onClick: handleTest,
      disabled: (notification) => testing === notification.id,
      tooltip: t('notifications.tooltip.sendTest'),
    },
    {
      label: t('notifications.tooltip.duplicate'),
      icon: <Copy size={16} />,
      onClick: handleDuplicate,
      tooltip: t('notifications.tooltip.duplicate'),
    },
    {
      label: t('notifications.tooltip.edit'),
      icon: <Edit size={16} />,
      onClick: openEditDialog,
      color: 'primary',
      tooltip: t('notifications.tooltip.edit'),
    },
    {
      label: t('notifications.tooltip.delete'),
      icon: <Trash2 size={16} />,
      onClick: setDeleteConfirm,
      color: 'error',
      tooltip: t('notifications.tooltip.delete'),
    },
  ]

  return (
    <Box>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 1.5,
          mb: 3,
        }}
      >
        <Box>
          <Typography variant="h6" fontWeight={600}>
            {t('notifications.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('notifications.subtitle')}
          </Typography>
        </Box>
        <Button
          variant="contained"
          startIcon={<Plus size={18} />}
          onClick={() => {
            resetForm()
            setEditingNotification(null)
            setShowDialog(true)
            trackNotifications(EventAction.VIEW, { source: 'create_dialog' })
          }}
          sx={{ width: { xs: '100%', sm: 'auto' } }}
        >
          {t('notifications.addService')}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2" gutterBottom>
          {t('notifications.alertDescription')}
        </Typography>
        <Link
          href="#"
          onClick={(e) => {
            e.preventDefault()
            setShowExamples(!showExamples)
            trackNotifications(EventAction.VIEW, {
              source: 'examples',
              expanded: !showExamples,
            })
          }}
          sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 1 }}
        >
          {showExamples ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          {showExamples ? t('notifications.hide') : t('notifications.show')}{' '}
          {t('notifications.serviceUrlExamples')}
        </Link>
      </Alert>

      <Collapse in={showExamples}>
        <Card
          sx={{ mb: 3, p: 2, bgcolor: 'background.default', border: 1, borderColor: 'divider' }}
        >
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            {t('notifications.appriseUrlExamplesTitle')}
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
              {t('notifications.exampleEmailGmail')}{' '}
            </Box>
            <Box component="span">
              mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls
            </Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleSlack')}{' '}
            </Box>
            <Box component="span">slack://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleDiscord')}{' '}
            </Box>
            <Box component="span">discord://webhook_id/webhook_token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleTelegram')}{' '}
            </Box>
            <Box component="span">tgram://bot_token/chat_id</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleMicrosoftTeams')}{' '}
            </Box>
            <Box component="span">msteams://TokenA/TokenB/TokenC/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.examplePushover')}{' '}
            </Box>
            <Box component="span">pover://user@token</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleNtfy')}{' '}
            </Box>
            <Box component="span">ntfy://topic/</Box>
            <br />
            <Box component="span" sx={{ color: 'grey.400' }}>
              {t('notifications.exampleCustomWebhook')}{' '}
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
            {t('notifications.fullAppriseDocumentation')}
          </Link>
        </Card>
      </Collapse>

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}>
          <CircularProgress />
        </Box>
      ) : notifications.length === 0 ? (
        <Card variant="outlined" sx={{ borderRadius: 3, p: 4, textAlign: 'center' }}>
          <Bell size={48} style={{ opacity: 0.3, margin: '0 auto 16px' }} />
          <Typography variant="h6" gutterBottom>
            {t('notifications.noServicesTitle')}
          </Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('notifications.noServicesSubtitle')}
          </Typography>
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={() => {
              resetForm()
              setShowDialog(true)
            }}
          >
            {t('notifications.addService')}
          </Button>
        </Card>
      ) : (
        <DataTable
          data={notifications}
          columns={columns}
          actions={actions}
          getRowKey={(notification) => notification.id}
          variant="outlined"
        />
      )}

      {/* Add/Edit Dialog */}
      <Dialog open={showDialog} onClose={() => setShowDialog(false)} maxWidth="sm" fullWidth>
        <DialogTitle>
          {editingNotification ? t('notifications.editService') : t('notifications.addService')}
        </DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('notifications.form.serviceName')}
              value={formData.name}
              onChange={(e) => setFormData({ ...formData, name: e.target.value })}
              placeholder={t('notifications.form.serviceNamePlaceholder')}
              fullWidth
              required
            />

            <TextField
              label={t('notifications.form.serviceUrl')}
              value={formData.service_url}
              onChange={(e) => setFormData({ ...formData, service_url: e.target.value })}
              placeholder={t('notifications.form.serviceUrlPlaceholder')}
              fullWidth
              required
              helperText={t('notifications.form.serviceUrlHelper')}
            />

            <Alert severity="info" sx={{ mt: 1 }}>
              <strong>{t('notifications.form.tipLabel')}</strong> {t('notifications.form.tipText')}
            </Alert>

            <TextField
              label={t('notifications.form.titlePrefix')}
              value={formData.title_prefix}
              onChange={(e) => setFormData({ ...formData, title_prefix: e.target.value })}
              placeholder={t('notifications.form.titlePrefixPlaceholder')}
              fullWidth
              helperText={t('notifications.form.titlePrefixHelper')}
            />

            <Box sx={{ mt: 2, mb: 2 }}>
              <FormControlLabel
                control={
                  <Switch
                    checked={formData.enabled}
                    onChange={(e) => setFormData({ ...formData, enabled: e.target.checked })}
                  />
                }
                label={t('notifications.form.enableNotifications')}
              />
            </Box>

            <Box sx={{ mt: 2, mb: 1 }}>
              <Typography variant="subtitle2" sx={{ mb: 1 }}>
                {t('notifications.form.notificationEnhancements')}
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
                label={t('notifications.form.includeJobName')}
              />
              <Typography
                variant="caption"
                sx={{ display: 'block', pl: 4.5, mt: -0.5, mb: 1, color: 'text.secondary' }}
              >
                {t('notifications.form.includeJobNameHelper')}
              </Typography>
            </Box>

            <Typography variant="subtitle2" sx={{ mt: 2, mb: 1 }}>
              {t('notifications.form.notifyOn')}
            </Typography>

            {/* Backup Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Archive size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  {t('notifications.category.backupEvents')}
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
                  label={t('notifications.form.started')}
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
                  label={t('notifications.form.success')}
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
                  label={t('notifications.form.failure')}
                />
              </Box>
            </Box>

            {/* Restore Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <RotateCcw size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  {t('notifications.category.restoreEvents')}
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
                  label={t('notifications.form.success')}
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
                  label={t('notifications.form.failure')}
                />
              </Box>
            </Box>

            {/* Check Jobs Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Settings size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  {t('notifications.category.checkJobs')}
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
                  label={t('notifications.form.success')}
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
                  label={t('notifications.form.failure')}
                />
              </Box>
            </Box>

            {/* System Events Category */}
            <Box sx={{ mb: 2 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.5 }}>
                <Settings size={16} />
                <Typography variant="body2" sx={{ fontWeight: 600, color: 'text.secondary' }}>
                  {t('notifications.category.systemEvents')}
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
                  label={t('notifications.form.schedulerErrors')}
                />
                <Typography
                  variant="caption"
                  sx={{ display: 'block', pl: 4.5, mt: -0.5, mb: 1, color: 'text.secondary' }}
                >
                  {t('notifications.form.schedulerErrorsHelper')}
                </Typography>
              </Box>
            </Box>

            {/* Repository Filter Section */}
            <Box sx={{ mt: 3, pt: 2, borderTop: '1px solid', borderColor: 'divider' }}>
              <FormControl component="fieldset">
                <FormLabel component="legend" sx={{ mb: 1 }}>
                  {t('notifications.form.applyToRepositories')}
                </FormLabel>
                <RadioGroup
                  value={formData.monitor_all_repositories ? 'all' : 'selected'}
                  onChange={(e) =>
                    setFormData({ ...formData, monitor_all_repositories: e.target.value === 'all' })
                  }
                >
                  <FormControlLabel
                    value="all"
                    control={<Radio />}
                    label={t('notifications.form.allRepositories')}
                  />
                  <FormControlLabel
                    value="selected"
                    control={<Radio />}
                    label={t('notifications.form.selectedRepositoriesOnly')}
                  />
                </RadioGroup>
              </FormControl>

              {!formData.monitor_all_repositories && (
                <Box sx={{ mt: 2 }}>
                  <MultiRepositorySelector
                    repositories={repositories || []}
                    selectedIds={formData.repository_ids}
                    onChange={(ids) => setFormData({ ...formData, repository_ids: ids })}
                    label={t('notifications.form.selectRepositories')}
                    placeholder={t('notifications.form.selectRepositoriesPlaceholder')}
                    helperText={t('notifications.form.selectRepositoriesHelper')}
                    allowReorder={false}
                  />
                </Box>
              )}
            </Box>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setShowDialog(false)}>{t('notifications.cancel')}</Button>
          <Button
            variant="contained"
            onClick={handleSubmit}
            disabled={createMutation.isPending || updateMutation.isPending}
          >
            {createMutation.isPending || updateMutation.isPending ? (
              <CircularProgress size={20} />
            ) : editingNotification ? (
              t('notifications.update')
            ) : (
              t('notifications.add')
            )}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Confirmation Dialog */}
      <Dialog open={!!deleteConfirm} onClose={() => setDeleteConfirm(null)}>
        <DialogTitle>{t('notifications.deleteServiceTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            Are you sure you want to delete <strong>{deleteConfirm?.name}</strong>? You will no
            longer receive notifications from this service.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteConfirm(null)}>{t('notifications.cancel')}</Button>
          <Button
            color="error"
            variant="contained"
            onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.id)}
            disabled={deleteMutation.isPending}
          >
            {deleteMutation.isPending ? <CircularProgress size={20} /> : t('notifications.delete')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default NotificationsTab
