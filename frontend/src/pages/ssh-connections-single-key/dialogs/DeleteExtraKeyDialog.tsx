import {
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Typography,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../../../components/shared/ResponsiveDialog'
import type { SSHConnection, SSHKeySummary } from '../types'

interface DeleteExtraKeyDialogProps {
  /** The key to delete; the dialog is closed while this is null. */
  sshKey: SSHKeySummary | null
  /** Connections that currently use the key. Deleting is blocked while any exist. */
  connectionsUsingKey: SSHConnection[]
  pending?: boolean
  onClose: () => void
  onDelete: () => void
}

export function DeleteExtraKeyDialog({
  sshKey,
  connectionsUsingKey,
  pending = false,
  onClose,
  onDelete,
}: DeleteExtraKeyDialogProps) {
  const { t } = useTranslation()
  const inUse = connectionsUsingKey.length > 0

  return (
    <ResponsiveDialog
      open={sshKey !== null}
      onClose={pending ? undefined : () => onClose()}
      maxWidth="xs"
      fullWidth
      footer={
        <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
          <Button onClick={onClose} disabled={pending}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={onDelete}
            disabled={pending || inUse}
            startIcon={pending ? <CircularProgress size={16} color="inherit" /> : undefined}
          >
            {pending
              ? t('sshConnections.extraKeys.deleteDialog.deleting')
              : t('sshConnections.extraKeys.deleteDialog.delete')}
          </Button>
        </DialogActions>
      }
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle>{t('sshConnections.extraKeys.deleteDialog.title')}</DialogTitle>
      <DialogContent>
        <Typography variant="body2" sx={{ mb: inUse ? 2 : 0 }}>
          {t('sshConnections.extraKeys.deleteDialog.confirm', { name: sshKey?.name ?? '' })}
        </Typography>
        {inUse && (
          <Alert severity="warning">
            <Typography variant="body2">
              {t('sshConnections.extraKeys.deleteDialog.inUse')}
            </Typography>
            <Box component="ul" sx={{ m: 0, mt: 0.5, pl: 2.5 }}>
              {connectionsUsingKey.map((connection) => (
                <Typography
                  key={connection.id}
                  component="li"
                  variant="body2"
                  sx={{ fontFamily: 'monospace' }}
                >
                  {connection.username}@{connection.host}:{connection.port}
                </Typography>
              ))}
            </Box>
          </Alert>
        )}
      </DialogContent>
    </ResponsiveDialog>
  )
}
