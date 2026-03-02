import { Dialog, DialogContent, DialogActions, Button, Typography, Alert, Box } from '@mui/material'
import { AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'

interface DeleteJobDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  jobId?: string | number
  jobType?: string
}

export default function DeleteJobDialog({
  open,
  onClose,
  onConfirm,
  jobId,
  jobType = 'job',
}: DeleteJobDialogProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
          <Box sx={{ color: 'error.main' }}>
            <AlertTriangle size={24} />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {jobType === 'backup' ? t('dialogs.deleteJob.titleBackup') : t('dialogs.deleteJob.titleJob')}
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Are you sure you want to permanently delete this {jobType} job entry
          {jobId && ` ${t('dialogs.deleteJob.jobId', { id: jobId })}`}?
        </Typography>

        <Alert severity="warning" sx={{ mb: 0 }}>
          <Typography variant="body2" fontWeight={500} gutterBottom>
            {t('dialogs.deleteJob.warnings.undone')}
          </Typography>
          <Typography variant="body2">
            • {t('dialogs.deleteJob.warnings.historyRemoved')}
            <br />
            • {t('dialogs.deleteJob.warnings.logsDeleted')}
            <br />• {t('dialogs.deleteJob.warnings.cannotRecover')}
          </Typography>
        </Alert>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} variant="outlined">
          {t('common.buttons.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          color="error"
          variant="contained"
          startIcon={<AlertTriangle size={18} />}
        >
          {t('dialogs.deleteJob.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
