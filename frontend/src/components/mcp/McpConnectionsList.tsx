import { useState } from 'react'
import {
  Box,
  Button,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Stack,
  Tooltip,
  Typography,
  useTheme,
} from '@mui/material'
import { Activity, Bot, Pencil, Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { McpConnection } from '../../services/api'
import { formatRelativeTime } from '../../utils/dateUtils'
import EmptyStateCard from '../EmptyStateCard'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import { tintChipSx } from '../shared/tones'

interface McpConnectionsListProps {
  connections: McpConnection[]
  showOwner: boolean
  onEdit: (connection: McpConnection) => void
  onRevoke: (connection: McpConnection) => void
  onOpenActivity: (connection: McpConnection) => void
  /** Set while MCP is turned off: editing is pointless, revoking still works. */
  editDisabled?: boolean
}

function ConnectionRow({
  connection,
  showOwner,
  editDisabled,
  onEdit,
  onAskRevoke,
  onOpenActivity,
}: {
  connection: McpConnection
  showOwner: boolean
  editDisabled?: boolean
  onEdit: () => void
  onAskRevoke: () => void
  onOpenActivity: () => void
}) {
  const { t } = useTranslation()
  const theme = useTheme()
  const lowered = connection.effective_level !== connection.access_level
  const client = connection.last_client_name
    ? [connection.last_client_name, connection.last_client_version].filter(Boolean).join(' ')
    : null

  const action = (label: string, icon: React.ReactNode, onClick: () => void, disabled = false) => (
    <Tooltip title={label}>
      <span>
        <IconButton
          aria-label={label}
          onClick={onClick}
          disabled={disabled}
          sx={{ width: 44, height: 44 }}
        >
          {icon}
        </IconButton>
      </span>
    </Tooltip>
  )

  return (
    <Box
      data-testid={`mcp-connection-${connection.id}`}
      sx={{
        display: 'flex',
        flexDirection: { xs: 'column', sm: 'row' },
        alignItems: { xs: 'stretch', sm: 'center' },
        gap: 1.5,
        px: 2.5,
        py: 1.75,
        '&:not(:last-of-type)': { borderBottom: '1px solid', borderColor: 'divider' },
      }}
    >
      <Box sx={{ flex: 1, minWidth: 0 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, flexWrap: 'wrap' }}>
          <Typography variant="body1" noWrap sx={{ fontWeight: 600 }} title={connection.name}>
            {connection.name}
          </Typography>
          <Chip
            size="small"
            label={t(`mcp.levels.${connection.access_level}.title`)}
            sx={tintChipSx(theme, 'primary')}
          />
          {lowered && (
            <Chip
              size="small"
              variant="outlined"
              label={t('mcp.list.appliesAs', {
                level: t(`mcp.levels.${connection.effective_level}.title`),
              })}
            />
          )}
        </Box>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
          {[
            client
              ? t('mcp.list.lastSeen', {
                  client,
                  when: formatRelativeTime(connection.last_used_at),
                })
              : t('mcp.list.notConnected'),
            t('mcp.list.callsToday', { count: connection.calls_today }),
            showOwner && connection.username
              ? t('mcp.list.owner', { name: connection.username })
              : null,
            connection.prefix + '…',
          ]
            .filter(Boolean)
            .join(' · ')}
        </Typography>
      </Box>
      <Stack direction="row" spacing={0.5} sx={{ alignSelf: { xs: 'flex-end', sm: 'center' } }}>
        {action(t('mcp.list.activity'), <Activity size={18} />, onOpenActivity)}
        {action(t('mcp.list.edit'), <Pencil size={18} />, onEdit, editDisabled)}
        {action(t('mcp.list.revoke'), <Trash2 size={18} />, onAskRevoke)}
      </Stack>
    </Box>
  )
}

export default function McpConnectionsList({
  connections,
  showOwner,
  onEdit,
  onRevoke,
  onOpenActivity,
  editDisabled,
}: McpConnectionsListProps) {
  const { t } = useTranslation()
  const [revoking, setRevoking] = useState<McpConnection | null>(null)

  if (connections.length === 0) {
    return (
      <EmptyStateCard
        icon={<Bot size={28} />}
        title={t('mcp.list.empty')}
        description={t('mcp.list.emptyBody')}
      />
    )
  }

  return (
    <>
      <Box
        sx={{ border: '1px solid', borderColor: 'divider', borderRadius: 2, overflow: 'hidden' }}
      >
        {connections.map((connection) => (
          <ConnectionRow
            key={connection.id}
            connection={connection}
            showOwner={showOwner}
            editDisabled={editDisabled}
            onEdit={() => onEdit(connection)}
            onAskRevoke={() => setRevoking(connection)}
            onOpenActivity={() => onOpenActivity(connection)}
          />
        ))}
      </Box>
      <ResponsiveDialog
        open={revoking !== null}
        onClose={() => setRevoking(null)}
        maxWidth="xs"
        fullWidth
        footer={
          <DialogActions sx={{ px: 3, pb: 2 }}>
            <Button onClick={() => setRevoking(null)}>{t('mcp.list.cancel')}</Button>
            <Button
              color="error"
              variant="contained"
              onClick={() => {
                if (revoking) onRevoke(revoking)
                setRevoking(null)
              }}
            >
              {t('mcp.list.revoke')}
            </Button>
          </DialogActions>
        }
      >
        <DialogTitle>{t('mcp.list.revokeTitle', { name: revoking?.name ?? '' })}</DialogTitle>
        <DialogContent>
          <Typography variant="body2">{t('mcp.list.revokeBody')}</Typography>
        </DialogContent>
      </ResponsiveDialog>
    </>
  )
}
