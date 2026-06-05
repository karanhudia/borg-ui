import { useState } from 'react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import {
  Alert,
  Box,
  Button,
  Chip,
  IconButton,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import {
  CheckCircle2,
  CircleAlert,
  Edit,
  Monitor,
  Plus,
  RefreshCw,
  Server,
  Trash2,
  WifiOff,
} from 'lucide-react'
import ResponsiveDialog from '../components/shared/ResponsiveDialog'
import { useAuth } from '../hooks/useAuth'
import { useRemoteBackends } from '../services/remoteBackends/context'
import type { RemoteBackendClient } from '../services/remoteBackends/types'

interface ClientFormState {
  name: string
  backendUrl: string
}

const emptyForm: ClientFormState = { name: '', backendUrl: '' }

function formatDate(value: string | null | undefined, fallback: string): string {
  if (!value) return fallback
  const date = new Date(value)
  if (Number.isNaN(date.valueOf())) return fallback

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: 'medium',
    timeStyle: 'short',
  }).format(date)
}

function getStatus(client: RemoteBackendClient, t: (key: string) => string) {
  if (client.health.compatibility === 'incompatible') {
    return {
      label: t('remoteClients.status.incompatible'),
      color: 'warning' as const,
      icon: <CircleAlert size={16} />,
    }
  }
  if (client.health.status === 'online') {
    return {
      label: t('remoteClients.status.online'),
      color: 'success' as const,
      icon: <CheckCircle2 size={16} />,
    }
  }
  if (client.health.status === 'offline') {
    return {
      label: t('remoteClients.status.offline'),
      color: 'error' as const,
      icon: <WifiOff size={16} />,
    }
  }
  if (client.health.status === 'checking') {
    return {
      label: t('remoteClients.status.checking'),
      color: 'info' as const,
      icon: <RefreshCw size={16} />,
    }
  }
  return {
    label: t('remoteClients.status.unknown'),
    color: 'default' as const,
    icon: <Server size={16} />,
  }
}

export function RemoteClientsContent() {
  const { t } = useTranslation()
  const muiTheme = useTheme()
  const {
    activeTarget,
    clients,
    createClient,
    updateClient,
    deleteClient,
    switchTarget,
    checkClient,
  } = useRemoteBackends()
  const [dialogOpen, setDialogOpen] = useState(false)
  const [editingClient, setEditingClient] = useState<RemoteBackendClient | null>(null)
  const [form, setForm] = useState<ClientFormState>(emptyForm)
  const [formError, setFormError] = useState<string | null>(null)
  const [checkingId, setCheckingId] = useState<string | null>(null)

  const openCreateDialog = () => {
    setEditingClient(null)
    setForm(emptyForm)
    setFormError(null)
    setDialogOpen(true)
  }

  const openEditDialog = (client: RemoteBackendClient) => {
    setEditingClient(client)
    setForm({ name: client.name, backendUrl: client.apiBaseUrl })
    setFormError(null)
    setDialogOpen(true)
  }

  const closeDialog = () => {
    setDialogOpen(false)
    setFormError(null)
  }

  const handleSave = () => {
    try {
      if (editingClient) {
        updateClient(editingClient.id, form)
        toast.success(t('remoteClients.toasts.updated'))
      } else {
        createClient(form)
        toast.success(t('remoteClients.toasts.added'))
      }
      closeDialog()
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t('remoteClients.errors.saveFailed'))
    }
  }

  const handleCheck = async (client: RemoteBackendClient) => {
    setCheckingId(client.id)
    try {
      const updated = await checkClient(client.id)
      if (updated.health.status === 'online') {
        toast.success(t('remoteClients.toasts.online', { name: client.name }))
      } else {
        toast.error(
          updated.health.error || t('remoteClients.toasts.unavailable', { name: client.name })
        )
      }
    } catch (error) {
      const message = error instanceof Error ? error.message : t('common.errors.unexpectedError')
      toast.error(t('remoteClients.toasts.checkFailed', { name: client.name, error: message }))
    } finally {
      setCheckingId(null)
    }
  }

  const handleSwitch = (client: RemoteBackendClient) => {
    try {
      switchTarget(client.id)
      toast.success(t('remoteClients.toasts.using', { name: client.name }))
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t('remoteClients.errors.remoteUnavailable')
      )
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', sm: 'center' },
          gap: 2,
          flexDirection: { xs: 'column', sm: 'row' },
        }}
      >
        <Box>
          <Typography variant="h4" sx={{ fontWeight: 800 }}>
            {t('remoteClients.title')}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5, maxWidth: 760 }}>
            {t('remoteClients.description')}
          </Typography>
        </Box>
        <Button variant="contained" startIcon={<Plus size={18} />} onClick={openCreateDialog}>
          {t('remoteClients.addButton')}
        </Button>
      </Box>

      <Paper
        variant="outlined"
        sx={{
          p: 2,
          borderRadius: 2,
          bgcolor: alpha(muiTheme.palette.background.paper, 0.78),
        }}
      >
        <Stack direction="row" spacing={1.25} alignItems="center">
          <Monitor size={18} />
          <Box sx={{ minWidth: 0, flex: 1 }}>
            <Typography variant="subtitle2" sx={{ fontWeight: 800 }}>
              {t('remoteClients.localBackend.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {activeTarget.kind === 'local'
                ? t('remoteClients.localBackend.active')
                : t('remoteClients.localBackend.fallback')}
            </Typography>
          </Box>
          <Chip
            label={
              activeTarget.kind === 'local'
                ? t('remoteClients.labels.activeTarget')
                : t('remoteClients.labels.local')
            }
          />
        </Stack>
      </Paper>

      {clients.length === 0 ? (
        <Paper
          variant="outlined"
          sx={{
            p: 4,
            borderRadius: 2,
            textAlign: 'center',
            bgcolor: alpha(muiTheme.palette.background.paper, 0.72),
          }}
        >
          <Server size={28} />
          <Typography variant="h6" sx={{ mt: 1.5, fontWeight: 800 }}>
            {t('remoteClients.empty.title')}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {t('remoteClients.empty.description')}
          </Typography>
        </Paper>
      ) : (
        <Stack spacing={1.5}>
          {clients.map((client) => {
            const status = getStatus(client, t)
            const active = activeTarget.id === client.id
            const canUse = client.health.compatibility !== 'incompatible'
            return (
              <Paper
                key={client.id}
                variant="outlined"
                sx={{
                  p: 2,
                  borderRadius: 2,
                  bgcolor: active
                    ? alpha(
                        muiTheme.palette.primary.main,
                        muiTheme.palette.mode === 'dark' ? 0.18 : 0.08
                      )
                    : alpha(muiTheme.palette.background.paper, 0.78),
                }}
              >
                <Stack
                  direction={{ xs: 'column', md: 'row' }}
                  spacing={1.5}
                  alignItems={{ xs: 'stretch', md: 'center' }}
                >
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'flex-start',
                      gap: 1.25,
                      flex: 1,
                      minWidth: 0,
                    }}
                  >
                    <Box sx={{ color: 'text.secondary', pt: 0.35 }}>{status.icon}</Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
                        <Typography variant="subtitle1" noWrap sx={{ fontWeight: 800 }}>
                          {client.name}
                        </Typography>
                        {active && (
                          <Chip
                            size="small"
                            label={t('remoteClients.labels.activeTarget')}
                            color="primary"
                          />
                        )}
                        <Chip size="small" label={status.label} color={status.color} />
                      </Stack>
                      <Typography
                        variant="body2"
                        color="text.secondary"
                        sx={{ wordBreak: 'break-all' }}
                      >
                        {client.apiBaseUrl}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {t('remoteClients.lastChecked', {
                          value: formatDate(client.health.checkedAt, t('common.never')),
                        })}
                        {client.health.appVersion
                          ? ` · ${t('remoteClients.version', {
                              version: client.health.appVersion,
                            })}`
                          : ''}
                      </Typography>
                      {client.health.error && (
                        <Alert severity="error" sx={{ mt: 1 }} role="status">
                          {client.health.error}
                        </Alert>
                      )}
                      {client.health.compatibility === 'incompatible' && (
                        <Alert severity="warning" sx={{ mt: 1 }} role="status">
                          {client.health.compatibilityMessage}
                        </Alert>
                      )}
                    </Box>
                  </Box>

                  <Stack
                    direction="row"
                    spacing={1}
                    justifyContent={{ xs: 'flex-start', md: 'flex-end' }}
                  >
                    <Button
                      variant="outlined"
                      size="small"
                      startIcon={<RefreshCw size={15} />}
                      onClick={() => void handleCheck(client)}
                      disabled={checkingId === client.id}
                      aria-label={t('remoteClients.actions.checkAria', { name: client.name })}
                    >
                      {t('remoteClients.actions.check')}
                    </Button>
                    <Button
                      variant={active ? 'contained' : 'outlined'}
                      size="small"
                      disabled={!canUse}
                      onClick={() => handleSwitch(client)}
                      aria-label={t('remoteClients.actions.useAria', { name: client.name })}
                    >
                      {t('remoteClients.actions.use')}
                    </Button>
                    <Tooltip title={t('remoteClients.actions.edit')}>
                      <IconButton
                        size="small"
                        onClick={() => openEditDialog(client)}
                        aria-label={t('remoteClients.actions.editAria', { name: client.name })}
                      >
                        <Edit size={16} />
                      </IconButton>
                    </Tooltip>
                    <Tooltip title={t('remoteClients.actions.delete')}>
                      <IconButton
                        size="small"
                        color="error"
                        onClick={() => deleteClient(client.id)}
                        aria-label={t('remoteClients.actions.deleteAria', { name: client.name })}
                      >
                        <Trash2 size={16} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                </Stack>
              </Paper>
            )
          })}
        </Stack>
      )}

      {dialogOpen && (
        <ResponsiveDialog open={dialogOpen} onClose={closeDialog} maxWidth="sm" fullWidth>
          <Box sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>
              {editingClient
                ? t('remoteClients.dialog.editTitle')
                : t('remoteClients.dialog.addTitle')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {t('remoteClients.dialog.description')}
            </Typography>
            <Stack spacing={2} sx={{ mt: 2.5 }}>
              {formError && (
                <Alert severity="error" role="alert">
                  {formError}
                </Alert>
              )}
              <TextField
                label={t('remoteClients.dialog.nameLabel')}
                value={form.name}
                onChange={(event) =>
                  setForm((current) => ({ ...current, name: event.target.value }))
                }
                fullWidth
              />
              <TextField
                label={t('remoteClients.dialog.urlLabel')}
                value={form.backendUrl}
                onChange={(event) =>
                  setForm((current) => ({ ...current, backendUrl: event.target.value }))
                }
                placeholder="https://client.example.com/api"
                fullWidth
              />
              <Stack direction="row" spacing={1} justifyContent="flex-end">
                <Button onClick={closeDialog}>{t('common.buttons.cancel')}</Button>
                <Button variant="contained" onClick={handleSave}>
                  {t('remoteClients.dialog.save')}
                </Button>
              </Stack>
            </Stack>
          </Box>
        </ResponsiveDialog>
      )}
    </Box>
  )
}

export default function RemoteClients() {
  const { hasGlobalPermission } = useAuth()

  if (!hasGlobalPermission('settings.ssh.manage')) {
    return <Navigate to="/dashboard" replace />
  }

  return <RemoteClientsContent />
}
