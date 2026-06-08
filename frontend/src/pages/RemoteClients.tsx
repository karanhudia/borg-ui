import { useEffect, useRef, useState } from 'react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { Navigate } from 'react-router-dom'
import { Alert, Box, Button, Paper, Stack, TextField, Typography } from '@mui/material'
import { alpha, useTheme } from '@mui/material/styles'
import { Plus, Server } from 'lucide-react'
import ResponsiveDialog from '../components/shared/ResponsiveDialog'
import PlanGate from '../components/shared/PlanGate'
import TabContentLayout from '../components/shared/TabContentLayout'
import EmptyStateCard from '../components/EmptyStateCard'
import LocalServerCard from '../components/LocalServerCard'
import PageHeader from '../components/PageHeader'
import RemoteClientCard from '../components/RemoteClientCard'
import { useAuth } from '../hooks/useAuth'
import { useAnalytics } from '../hooks/useAnalytics'
import { usePlan } from '../hooks/usePlan'
import { useRemoteBackends } from '../services/remoteBackends/context'
import { LOCAL_BACKEND_ID } from '../services/remoteBackends/storage'
import type { BackendTarget, RemoteBackendClient } from '../services/remoteBackends/types'

interface ClientFormState {
  name: string
  backendUrl: string
}

const emptyForm: ClientFormState = { name: '', backendUrl: '' }

function RemoteClientsHeader({ onAddClient }: { onAddClient?: () => void }) {
  const { t } = useTranslation()

  return (
    <PageHeader
      title={t('remoteClients.title')}
      subtitle={t('remoteClients.description')}
      actions={
        onAddClient ? (
          <Button variant="contained" startIcon={<Plus size={18} />} onClick={onAddClient}>
            {t('remoteClients.addButton')}
          </Button>
        ) : undefined
      }
    />
  )
}

function RemoteClientsBody({
  activeTarget,
  clients,
  checkingId,
  onSwitchLocal,
  onCheck,
  onUse,
  onEdit,
  onDelete,
}: {
  activeTarget: BackendTarget
  clients: RemoteBackendClient[]
  checkingId?: string | null
  onSwitchLocal: () => void
  onCheck: (client: RemoteBackendClient) => void
  onUse: (client: RemoteBackendClient) => void
  onEdit: (client: RemoteBackendClient) => void
  onDelete: (client: RemoteBackendClient) => void
}) {
  const { t } = useTranslation()
  const muiTheme = useTheme()

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2.5 }}>
      <LocalServerCard active={activeTarget.kind === 'local'} onUse={onSwitchLocal} />

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
              onCheck={onCheck}
              onUse={onUse}
              onEdit={onEdit}
              onDelete={onDelete}
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
    </Box>
  )
}

function RemoteClientsPreviewBody({
  activeTarget,
  clients,
}: {
  activeTarget: BackendTarget
  clients: RemoteBackendClient[]
}) {
  return (
    <RemoteClientsBody
      activeTarget={activeTarget}
      clients={clients}
      checkingId={null}
      onSwitchLocal={() => {}}
      onCheck={() => {}}
      onUse={() => {}}
      onEdit={() => {}}
      onDelete={() => {}}
    />
  )
}

export function RemoteClientsContent() {
  const { t } = useTranslation()
  const {
    activeTarget,
    clients,
    createClient,
    updateClient,
    deleteClient,
    switchTarget,
    checkClient,
  } = useRemoteBackends()
  const { trackRemoteClient, EventAction } = useAnalytics()
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
        const updated = await updateClient(editingClient.id, form)
        toast.success(t('remoteClients.toasts.updated'))
        trackRemoteClient(EventAction.EDIT, updated, { surface: 'remote_clients' })
      } else {
        const created = await createClient(form)
        toast.success(t('remoteClients.toasts.added'))
        trackRemoteClient(EventAction.CREATE, created, { surface: 'remote_clients' })
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
      trackRemoteClient(EventAction.TEST, updated, {
        surface: 'remote_clients',
        status: updated.health.status,
        compatibility: updated.health.compatibility,
      })
    } catch (error) {
      const message = error instanceof Error ? error.message : t('common.errors.unexpectedError')
      toast.error(t('remoteClients.toasts.checkFailed', { name: client.name, error: message }))
    } finally {
      setCheckingId(null)
    }
  }

  const handleSwitchTarget = (
    targetId: string,
    name: string,
    targetKind: 'local' | 'remote',
    client?: RemoteBackendClient
  ) => {
    try {
      switchTarget(targetId)
      toast.success(t('remoteClients.toasts.using', { name }))
      trackRemoteClient(EventAction.SWITCH, client, {
        surface: 'remote_clients',
        target_kind: targetKind,
      })
    } catch (error) {
      toast.error(
        error instanceof Error ? error.message : t('remoteClients.errors.remoteUnavailable')
      )
    }
  }

  const handleSwitch = (client: RemoteBackendClient) => {
    handleSwitchTarget(client.id, client.name, 'remote', client)
  }

  const handleSwitchLocal = () => {
    handleSwitchTarget(LOCAL_BACKEND_ID, t('remoteClients.localBackend.title'), 'local')
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
      trackRemoteClient(EventAction.DELETE, deletingClient, { surface: 'remote_clients' })
      setDeletingClient(null)
    } catch (error) {
      toast.error(error instanceof Error ? error.message : t('common.errors.unexpectedError'))
    } finally {
      deleteInFlightRef.current = false
      setIsDeleting(false)
    }
  }

  return (
    <TabContentLayout header={<RemoteClientsHeader onAddClient={openCreateDialog} />} spacing={0}>
      <RemoteClientsBody
        activeTarget={activeTarget}
        clients={clients}
        checkingId={checkingId}
        onSwitchLocal={handleSwitchLocal}
        onCheck={(client) => void handleCheck(client)}
        onUse={handleSwitch}
        onEdit={openEditDialog}
        onDelete={setDeletingClient}
      />

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
    </TabContentLayout>
  )
}

export function RemoteClientsPreview({
  activeTarget,
  clients,
}: {
  activeTarget: BackendTarget
  clients: RemoteBackendClient[]
}) {
  return (
    <TabContentLayout header={<RemoteClientsHeader />} spacing={0}>
      <RemoteClientsPreviewBody activeTarget={activeTarget} clients={clients} />
    </TabContentLayout>
  )
}

export function RemoteClientsPlanGate() {
  const { t } = useTranslation()
  const { can, isLoading } = usePlan()
  const { activeTarget, clients } = useRemoteBackends()

  if (!isLoading && can('remote_clients')) {
    return <RemoteClientsContent />
  }

  return (
    <PlanGate
      feature="remote_clients"
      message={t('remoteClients.planGate.message')}
      surface="remote_clients"
      operation="view_management"
      preview={<RemoteClientsPreview activeTarget={activeTarget} clients={clients} />}
    >
      <Box />
    </PlanGate>
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

  return <RemoteClientsPlanGate />
}
