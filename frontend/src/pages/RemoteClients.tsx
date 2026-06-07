import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { Plus, Server } from 'lucide-react'
import ResponsiveDialog from '../components/shared/ResponsiveDialog'
import PlanGate from '../components/shared/PlanGate'
import EmptyStateCard from '../components/EmptyStateCard'
import LocalServerCard from '../components/LocalServerCard'
import RemoteClientCard from '../components/RemoteClientCard'
import { useAuth } from '../hooks/useAuth'
import { useRemoteBackends } from '../services/remoteBackends/context'
import { LOCAL_BACKEND_ID } from '../services/remoteBackends/storage'
import type { RemoteBackendClient } from '../services/remoteBackends/types'

interface ClientFormState {
  name: string
  backendUrl: string
}

const emptyForm: ClientFormState = { name: '', backendUrl: '' }

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
  const [deletingClient, setDeletingClient] = useState<RemoteBackendClient | null>(null)
  const [isSaving, setIsSaving] = useState(false)
  const [isDeleting, setIsDeleting] = useState(false)
  const saveInFlightRef = useRef(false)
  const deleteInFlightRef = useRef(false)

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
    if (saveInFlightRef.current) return
    setDialogOpen(false)
    setFormError(null)
  }

  const handleSave = async () => {
    if (saveInFlightRef.current) return
    saveInFlightRef.current = true
    setIsSaving(true)
    let saved = false
    try {
      if (editingClient) {
        await updateClient(editingClient.id, form)
        toast.success(t('remoteClients.toasts.updated'))
      } else {
        await createClient(form)
        toast.success(t('remoteClients.toasts.added'))
      }
      saved = true
    } catch (error) {
      setFormError(error instanceof Error ? error.message : t('remoteClients.errors.saveFailed'))
    } finally {
      saveInFlightRef.current = false
      setIsSaving(false)
      if (saved) {
        closeDialog()
      }
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

  const handleSwitchTarget = (targetId: string, name: string) => {
    try {
      switchTarget(targetId)
      toast.success(t('remoteClients.toasts.using', { name }))
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t('remoteClients.errors.remoteUnavailable')
      )
    }
  }

  const handleSwitch = (client: RemoteBackendClient) => {
    handleSwitchTarget(client.id, client.name)
  }

  const handleSwitchLocal = () => {
    handleSwitchTarget(LOCAL_BACKEND_ID, t('remoteClients.localBackend.title'))
  }

  const closeDeleteDialog = () => {
    if (deleteInFlightRef.current) return
    setDeletingClient(null)
  }

  const handleDelete = async () => {
    if (!deletingClient) return
    if (deleteInFlightRef.current) return
    deleteInFlightRef.current = true
    setIsDeleting(true)
    try {
      await deleteClient(deletingClient.id)
      toast.success(t('remoteClients.toasts.deleted'))
      setDeletingClient(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('common.errors.unexpectedError'))
    } finally {
      deleteInFlightRef.current = false
      setIsDeleting(false)
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

      <LocalServerCard active={activeTarget.kind === 'local'} onUse={handleSwitchLocal} />

      {clients.length > 0 && (
        <Box
          sx={{
            display: 'grid',
            gap: 2,
            gridTemplateColumns: { xs: '1fr', md: 'repeat(auto-fit, minmax(320px, 1fr))' },
          }}
        >
          {clients.map((client) => (
            <RemoteClientCard
              key={client.id}
              client={client}
              active={activeTarget.id === client.id}
              checking={checkingId === client.id}
              onCheck={(c) => void handleCheck(c)}
              onUse={handleSwitch}
              onEdit={openEditDialog}
              onDelete={setDeletingClient}
            />
          ))}
        </Box>
      )}

      {clients.length === 0 && (
        <Paper
          variant="outlined"
          sx={{
            p: 4,
            borderRadius: 2,
            textAlign: 'center',
            bgcolor: alpha(muiTheme.palette.background.paper, 0.72),
          }}
        >
          <EmptyStateCard
            inline
            icon={<Server size={32} />}
            title={t('remoteClients.empty.title')}
            description={t('remoteClients.empty.description')}
          />
        </Paper>
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
                <Button onClick={closeDialog} disabled={isSaving}>
                  {t('common.buttons.cancel')}
                </Button>
                <Button variant="contained" onClick={() => void handleSave()} disabled={isSaving}>
                  {t('remoteClients.dialog.save')}
                </Button>
              </Stack>
            </Stack>
          </Box>
        </ResponsiveDialog>
      )}

      {deletingClient && (
        <ResponsiveDialog
          open={Boolean(deletingClient)}
          onClose={closeDeleteDialog}
          maxWidth="xs"
          fullWidth
        >
          <Box sx={{ p: 2.5 }}>
            <Typography variant="h6" sx={{ fontWeight: 800 }}>
              {t('remoteClients.deleteDialog.title')}
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.75 }}>
              {t('remoteClients.deleteDialog.description', { name: deletingClient.name })}
            </Typography>
            <Stack direction="row" spacing={1} justifyContent="flex-end" sx={{ mt: 2.5 }}>
              <Button onClick={closeDeleteDialog} disabled={isDeleting}>
                {t('common.buttons.cancel')}
              </Button>
              <Button
                variant="contained"
                color="error"
                onClick={() => void handleDelete()}
                disabled={isDeleting}
              >
                {t('remoteClients.deleteDialog.confirm')}
              </Button>
            </Stack>
          </Box>
        </ResponsiveDialog>
      )}
    </Box>
  )
}

export default function RemoteClients() {
  const { t } = useTranslation()
  const { hasGlobalPermission } = useAuth()
  const hasPermission = hasGlobalPermission('settings.ssh.manage')
  const hasShownPermissionToast = useRef(false)

  useEffect(() => {
    if (!hasPermission && !hasShownPermissionToast.current) {
      toast.error(t('protectedRoute.permissionDenied'), { duration: 4000 })
      hasShownPermissionToast.current = true
    }
    if (hasPermission) {
      hasShownPermissionToast.current = false
    }
  }, [hasPermission, t])

  if (!hasPermission) {
    return <Navigate to="/dashboard" replace />
  }

  return (
    <PlanGate
      feature="remote_clients"
      message={t('remoteClients.planGate.message')}
      surface="remote_clients"
      operation="view_management"
    >
      <RemoteClientsContent />
    </PlanGate>
  )
}
