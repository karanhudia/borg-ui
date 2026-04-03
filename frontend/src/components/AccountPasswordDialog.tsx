import {
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
  Typography,
} from '@mui/material'

interface AccountPasswordDialogProps {
  open: boolean
  mustChangePassword: boolean
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
  mustChangePassword,
  currentPassword,
  newPassword,
  confirmPassword,
  isSubmitting,
  onClose,
  onFormChange,
  onSubmit,
}: AccountPasswordDialogProps) {
  const passwordsMismatch = confirmPassword !== '' && newPassword !== confirmPassword

  return (
    <Dialog
      open={open}
      onClose={(_, reason) => onClose(reason)}
      maxWidth="sm"
      fullWidth
      disableEscapeKeyDown={mustChangePassword}
    >
      <DialogTitle>{mustChangePassword ? 'Complete account setup' : 'Change password'}</DialogTitle>
      <form
        onSubmit={(e) => {
          e.preventDefault()
          onSubmit()
        }}
      >
        <DialogContent>
          <Stack spacing={2}>
            {mustChangePassword && (
              <Typography variant="body2" color="text.secondary">
                Your password must be changed before you can navigate outside account settings.
              </Typography>
            )}
            <TextField
              label="Current password"
              type="password"
              value={currentPassword}
              onChange={(e) => onFormChange({ current_password: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="New password"
              type="password"
              value={newPassword}
              onChange={(e) => onFormChange({ new_password: e.target.value })}
              required
              fullWidth
              size="small"
            />
            <TextField
              label="Confirm password"
              type="password"
              value={confirmPassword}
              onChange={(e) => onFormChange({ confirm_password: e.target.value })}
              required
              fullWidth
              size="small"
              error={passwordsMismatch}
              helperText={passwordsMismatch ? 'Passwords do not match' : ''}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          {!mustChangePassword && <Button onClick={() => onClose('closeButton')}>Cancel</Button>}
          <Button
            type="submit"
            variant="contained"
            disabled={isSubmitting}
            startIcon={isSubmitting ? <CircularProgress size={14} /> : null}
          >
            {isSubmitting ? 'Saving' : 'Update password'}
          </Button>
        </DialogActions>
      </form>
    </Dialog>
  )
}
