import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  Button,
  IconButton,
  TextField,
  CircularProgress,
  Skeleton,
  Stack,
  DialogTitle,
  DialogContent,
  DialogActions,
  FormControlLabel,
  Switch,
  Alert,
  Link,
  Tooltip,
  FormControl,
  FormLabel,
  RadioGroup,
  Radio,
  alpha,
} from '@mui/material'
import { Plus, Bell, Info, ExternalLink, Archive, RotateCcw, Settings } from 'lucide-react'
import { notificationsAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import { Repository } from '../types'
import MultiRepositorySelector from './MultiRepositorySelector'
import { useAnalytics } from '../hooks/useAnalytics'
import NotificationCard from './NotificationCard'
import ResponsiveDialog from './ResponsiveDialog'

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
  const [showInfoModal, setShowInfoModal] = useState(false)

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
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
            <Typography variant="h6" fontWeight={600}>
              {t('notifications.title')}
            </Typography>
            <Tooltip title={t('notifications.serviceUrlExamples')} arrow>
              <IconButton
                size="small"
                onClick={() => setShowInfoModal(true)}
                sx={{ color: 'text.disabled', '&:hover': { color: 'text.secondary' }, p: 0.25 }}
              >
                <Info size={14} />
              </IconButton>
            </Tooltip>
          </Box>
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

      {isLoading ? (
        <Stack spacing={2}>
          {[0, 1, 2].map((i) => (
            <Box
              key={i}
              sx={{
                borderRadius: 2,
                bgcolor: 'background.paper',
                overflow: 'hidden',
                boxShadow: (theme) =>
                  theme.palette.mode === 'dark'
                    ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
                    : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
                opacity: Math.max(0.4, 1 - i * 0.2),
              }}
            >
              <Box
                sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}
              >
                {/* Title row */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 1,
                    mb: 1.5,
                  }}
                >
                  <Box sx={{ flex: 1 }}>
                    <Skeleton
                      variant="text"
                      width={[120, 160, 100][i]}
                      height={20}
                      sx={{ transform: 'none', borderRadius: 0.5, mb: 0.4 }}
                    />
                    <Skeleton
                      variant="text"
                      width={[200, 170, 220][i]}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>
                  <Skeleton
                    variant="rounded"
                    width={20}
                    height={20}
                    sx={{ borderRadius: 0.5, flexShrink: 0 }}
                  />
                </Box>

                {/* Stats grid — 4 columns matching EntityCard */}
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
                    borderRadius: 1.5,
                    border: '1px solid',
                    borderColor: 'divider',
                    overflow: 'hidden',
                    mb: 1.5,
                  }}
                >
                  {[0, 1, 2, 3].map((j) => (
                    <Box
                      key={j}
                      sx={{
                        px: 1.5,
                        py: 1.1,
                        borderRight: j < 3 ? '1px solid' : 0,
                        borderColor: 'divider',
                      }}
                    >
                      <Skeleton
                        variant="text"
                        width={38}
                        height={10}
                        sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
                      />
                      <Skeleton
                        variant="text"
                        width={[55, 45, 60, 50][j]}
                        height={16}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Box>
                  ))}
                </Box>

                {/* Event category tags row */}
                <Box sx={{ display: 'flex', gap: 0.75, mb: 1.5 }}>
                  {[52, 56, 46, 62].map((w, j) => (
                    <Skeleton
                      key={j}
                      variant="rounded"
                      width={w}
                      height={20}
                      sx={{ borderRadius: 1 }}
                    />
                  ))}
                </Box>

                {/* Actions row — 4 icon buttons */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    pt: 1.25,
                    borderTop: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  {[0, 1, 2, 3].map((j) => (
                    <Skeleton
                      key={j}
                      variant="rounded"
                      width={32}
                      height={32}
                      sx={{ borderRadius: 1.5 }}
                    />
                  ))}
                </Box>
              </Box>
            </Box>
          ))}
        </Stack>
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
        <Stack spacing={2}>
          {notifications.map((notification: NotificationSetting) => (
            <NotificationCard
              key={notification.id}
              notification={notification}
              onTest={() => handleTest(notification)}
              onEdit={() => openEditDialog(notification)}
              onDuplicate={() => handleDuplicate(notification)}
              onDelete={() => setDeleteConfirm(notification)}
              isTesting={testing === notification.id}
            />
          ))}
        </Stack>
      )}

      {/* Service URL Info Modal */}
      <ResponsiveDialog
        open={showInfoModal}
        onClose={() => setShowInfoModal(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('notifications.appriseUrlExamplesTitle')}</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            {t('notifications.alertDescription')}
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
              lineHeight: 1.8,
            }}
          >
            {[
              {
                label: t('notifications.exampleEmailGmail'),
                value: 'mailto://user:app_password@gmail.com?smtp=smtp.gmail.com&mode=starttls',
              },
              { label: t('notifications.exampleSlack'), value: 'slack://TokenA/TokenB/TokenC/' },
              {
                label: t('notifications.exampleDiscord'),
                value: 'discord://webhook_id/webhook_token',
              },
              { label: t('notifications.exampleTelegram'), value: 'tgram://bot_token/chat_id' },
              {
                label: t('notifications.exampleMicrosoftTeams'),
                value: 'msteams://TokenA/TokenB/TokenC/',
              },
              { label: t('notifications.examplePushover'), value: 'pover://user@token' },
              { label: t('notifications.exampleNtfy'), value: 'ntfy://topic/' },
              {
                label: t('notifications.exampleCustomWebhook'),
                value: 'json://hostname/path/to/endpoint',
              },
            ].map(({ label, value }) => (
              <Box key={value}>
                <Box component="span" sx={{ color: 'grey.500' }}>
                  {label}{' '}
                </Box>
                <Box component="span">{value}</Box>
              </Box>
            ))}
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
        </DialogContent>
      </ResponsiveDialog>

      {/* Add/Edit Dialog */}
      <ResponsiveDialog
        open={showDialog}
        onClose={() => setShowDialog(false)}
        maxWidth="sm"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setShowDialog(false)}>{t('notifications.cancel')}</Button>
            <Box sx={{ flex: 1 }} />
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
        }
      >
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
      </ResponsiveDialog>

      {/* Delete Confirmation Dialog */}
      <ResponsiveDialog
        open={!!deleteConfirm}
        onClose={() => setDeleteConfirm(null)}
        maxWidth="xs"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setDeleteConfirm(null)}>{t('notifications.cancel')}</Button>
            <Box sx={{ flex: 1 }} />
            <Button
              color="error"
              variant="contained"
              onClick={() => deleteConfirm && deleteMutation.mutate(deleteConfirm.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? (
                <CircularProgress size={20} />
              ) : (
                t('notifications.delete')
              )}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('notifications.deleteServiceTitle')}</DialogTitle>
        <DialogContent>
          <Typography>
            {t('notifications.confirmDelete.messagePrefix')} <strong>{deleteConfirm?.name}</strong>
            {t('notifications.confirmDelete.messageSuffix')}
          </Typography>
        </DialogContent>
      </ResponsiveDialog>
    </Box>
  )
}

export default NotificationsTab
