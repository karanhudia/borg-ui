import {
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from './shared/ResponsiveDialog'

interface AccountPasswordDialogProps {
  open: boolean
  currentPassword: string
  newPassword: string
  confirmPassword: string
  isSubmitting: boolean
  onClose: (reason?: 'backdropClick' | 'escapeKeyDown' | 'closeButton') => void
  onFormChange: (
    updates: Partial<{
      current_password: string
      new_password: string
      confirm_password: string
    }>
  ) => void
  onSubmit: () => void
}

export default function AccountPasswordDialog({
  open,
  currentPassword,
  newPassword,
  confirmPassword,
  isSubmitting,
  onClose,
  onFormChange,
  onSubmit,
}: AccountPasswordDialogProps) {
  const { t } = useTranslation()
  const passwordsMismatch = confirmPassword !== '' && newPassword !== confirmPassword

  return (
    <ResponsiveDialog open={open} onClose={(_, reason) => onClose(reason)} maxWidth="sm" fullWidth>
      <DialogTitle>{t('accountPassword.title')}</DialogTitle>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <DialogContent>
          <Stack spacing={2}>
            <TextField
              label={t('accountPassword.current')}
              type="password"
              value={currentPassword}
              onChange={(e) => onFormChange({ current_password: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label={t('accountPassword.new')}
              type="password"
              value={newPassword}
              onChange={(e) => onFormChange({ new_password: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label={t('accountPassword.confirm')}
              type="password"
              value={confirmPassword}
              onChange={(e) => onFormChange({ confirm_password: e.target.value })}
              required
              fullWidth
              size="small"
              error={passwordsMismatch}
              helperText={passwordsMismatch ? t('accountPassword.mismatch') : ''}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => onClose('closeButton')}>{t('common.buttons.cancel')}</Button>
          <Button
            type="submit"
            variant="contained"
            disabled={isSubmitting}
            startIcon={isSubmitting ? <CircularProgress size={14} /> : null}
          >
            {isSubmitting ? t('accountPassword.saving') : t('accountPassword.update')}
          </Button>
        </DialogActions>
      </form>
    </ResponsiveDialog>
  )
}
