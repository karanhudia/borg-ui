import { useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogContent,
  DialogTitle,
  FormControlLabel,
  Stack,
  Switch,
  Typography,
} from '@mui/material'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Plus } from 'lucide-react'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import { useAuth } from '../hooks/useAuth'
import { mcpAPI, type McpConnection } from '../services/api'
import { useActiveBackendTarget } from '../services/remoteBackends/context'
import { translateBackendKey, type BackendDetail } from '../utils/translateBackendKey'
import PlanGate from './shared/PlanGate'
import ResponsiveDialog from './shared/ResponsiveDialog'
import McpActivityPanel from './mcp/McpActivityPanel'
import McpConnectedDialog from './mcp/McpConnectedDialog'
import McpConnectionDialog, { type McpConnectionBody } from './mcp/McpConnectionDialog'
import McpConnectionsList from './mcp/McpConnectionsList'
import { backendOrigin, mcpEndpointUrl } from './mcp/clientSnippets'

// eslint-disable-next-line @typescript-eslint/no-explicit-any
const backendMessage = (error: any) =>
  translateBackendKey(error?.response?.data?.detail as BackendDetail)

function McpConnections() {
  const { t } = useTranslation()
  const { user } = useAuth()
  const backend = useActiveBackendTarget()
  const queryClient = useQueryClient()
  const isAdmin = user?.role === 'admin'
  const [everyone, setEveryone] = useState(false)
  const [editing, setEditing] = useState<McpConnection | 'new' | null>(null)
  const [newToken, setNewToken] = useState<string | null>(null)
  const [activityFor, setActivityFor] = useState<McpConnection | null>(null)
  const all = isAdmin && everyone

  const config = useQuery({
    queryKey: ['mcp-config'],
    queryFn: () => mcpAPI.getConfig().then((r) => r.data),
  })
  const list = useQuery({
    queryKey: ['mcp-connections', all],
    queryFn: () => mcpAPI.list(all).then((r) => r.data),
  })
  const refresh = () => queryClient.invalidateQueries({ queryKey: ['mcp-connections'] })

  const revoke = useMutation({
    mutationFn: (id: number) => mcpAPI.revoke(id),
    onSuccess: () => {
      refresh()
      toast.success(t('mcp.tab.revoked'))
    },
    onError: (error) => toast.error(backendMessage(error)),
  })

  const submit = async (body: McpConnectionBody) => {
    try {
      if (editing === 'new') {
        const created = (await mcpAPI.create(body)).data
        setNewToken(created.token)
        toast.success(t('mcp.tab.created'))
      } else if (editing) {
        await mcpAPI.update(editing.id, body)
        toast.success(t('mcp.tab.updated'))
      }
      setEditing(null)
      refresh()
    } catch (error) {
      throw new Error(backendMessage(error))
    }
  }

  const failed = [config, list].find((query) => query.isError)
  if (failed) {
    return (
      <Alert
        severity="error"
        action={
          <Button color="inherit" size="small" onClick={() => failed.refetch()}>
            {t('mcp.tab.retry')}
          </Button>
        }
      >
        {t('mcp.tab.loadFailed')}
      </Alert>
    )
  }
  if (config.isLoading || list.isLoading || !config.data) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
        <CircularProgress size={28} />
      </Box>
    )
  }
  const enabled = config.data.enabled

  return (
    <Stack spacing={2.5}>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          alignItems: { xs: 'flex-start', sm: 'center' },
          justifyContent: 'space-between',
          gap: 1.5,
        }}
      >
        <Box sx={{ maxWidth: 680 }}>
          <Typography variant="h6">{t('mcp.tab.title')}</Typography>
          <Typography variant="body2" color="text.secondary">
            {t('mcp.tab.description')}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5} sx={{ alignItems: 'center', flexShrink: 0 }}>
          {isAdmin && (
            <FormControlLabel
              control={
                <Switch checked={everyone} onChange={(e) => setEveryone(e.target.checked)} />
              }
              label={t('mcp.tab.everyone')}
            />
          )}
          <Button
            variant="contained"
            startIcon={<Plus size={18} />}
            onClick={() => setEditing('new')}
            disabled={!enabled}
            sx={{ minHeight: 44 }}
          >
            {t('mcp.tab.newConnection')}
          </Button>
        </Stack>
      </Box>

      {!enabled && <Alert severity="info">{t('mcp.tab.turnedOff')}</Alert>}

      <McpConnectionsList
        connections={list.data ?? []}
        showOwner={all}
        editDisabled={!enabled}
        onEdit={(connection) => setEditing(connection)}
        onRevoke={(connection) => revoke.mutate(connection.id)}
        onOpenActivity={setActivityFor}
      />

      <McpConnectionDialog
        open={editing !== null}
        mode={editing === 'new' ? 'create' : 'edit'}
        connection={editing && editing !== 'new' ? editing : undefined}
        config={config.data}
        onClose={() => setEditing(null)}
        onSubmit={submit}
      />

      {newToken && (
        <McpConnectedDialog
          open
          token={newToken}
          endpointUrl={mcpEndpointUrl(config.data.endpoint_path, backendOrigin(backend))}
          onClose={() => setNewToken(null)}
        />
      )}

      <ResponsiveDialog
        open={activityFor !== null}
        onClose={() => setActivityFor(null)}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>{t('mcp.tab.activityFor', { name: activityFor?.name ?? '' })}</DialogTitle>
        <DialogContent>
          {activityFor && <McpActivityPanel connectionId={activityFor.id} />}
        </DialogContent>
      </ResponsiveDialog>
    </Stack>
  )
}

/** Settings > AI assistants (MCP). */
export default function McpTab() {
  const backend = useActiveBackendTarget()
  return (
    <PlanGate feature="mcp" surface="settings_mcp">
      {/* A token belongs to the backend that issued it. Remounting on a
          switch drops it and any open dialog; a create still in flight
          resolves into the unmounted copy and is ignored. */}
      <McpConnections key={backend.id} />
    </PlanGate>
  )
}
