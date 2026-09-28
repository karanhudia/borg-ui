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
import { Trash2 } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../shared/ResponsiveDialog'

interface SshKeyDeleteDialogProps {
  open: boolean
  keyName: string
  /** Repositories whose cloud sync signs in with this key. */
  repositoryCount: number
  isDeleting?: boolean
  error?: string | null
  disablePortal?: boolean
  onClose: () => void
  onConfirm: () => void
}

export default function SshKeyDeleteDialog({
  open,
  keyName,
  repositoryCount,
  isDeleting = false,
  error = null,
  disablePortal,
  onClose,
  onConfirm,
}: SshKeyDeleteDialogProps) {
  const { t } = useTranslation()

  return (
    <ResponsiveDialog
      open={open}
      onClose={isDeleting ? undefined : () => onClose()}
      maxWidth="xs"
      fullWidth
      disablePortal={disablePortal}
      footer={
        <DialogActions sx={{ px: 3, py: 2, gap: 1 }}>
          <Button onClick={onClose} disabled={isDeleting}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={onConfirm}
            disabled={isDeleting}
            startIcon={
              isDeleting ? <CircularProgress size={16} color="inherit" /> : <Trash2 size={16} />
            }
          >
            {t('wizard.cloudMirror.sshKeyDeleteConfirm')}
          </Button>
        </DialogActions>
      }
      PaperProps={{ sx: { borderRadius: 3 } }}
    >
      <DialogTitle>{t('wizard.cloudMirror.sshKeyDeleteTitle', { name: keyName })}</DialogTitle>
      <DialogContent>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Typography variant="body2">
            {repositoryCount > 0
              ? t('wizard.cloudMirror.sshKeyDeleteInUse', { count: repositoryCount })
              : t('wizard.cloudMirror.sshKeyDeleteUnused')}
          </Typography>
        </Box>
      </DialogContent>
    </ResponsiveDialog>
  )
}
