import { useTranslation } from 'react-i18next'
import { Dialog, DialogContent, DialogActions, Button, Typography } from '@mui/material'

interface CancelJobDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  jobId?: string | number
}

export default function CancelJobDialog({ open, onClose, onConfirm }: CancelJobDialogProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Typography variant="h6" gutterBottom>
          {t('dialogs.cancelJob.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('dialogs.cancelJob.message')}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        <Button onClick={onConfirm} color="error" variant="contained">
          {t('dialogs.cancelJob.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
