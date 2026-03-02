import { useTranslation } from 'react-i18next'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Box,
  Alert,
  CircularProgress,
} from '@mui/material'
import { AlertCircle, Trash2 } from 'lucide-react'

interface DeleteArchiveDialogProps {
  open: boolean
  archiveName: string | null
  onClose: () => void
  onConfirm: (archiveName: string) => void
  deleting?: boolean
}

export default function DeleteArchiveDialog({
  open,
  archiveName,
  onClose,
  onConfirm,
  deleting = false,
}: DeleteArchiveDialogProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              backgroundColor: 'error.lighter',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <AlertCircle size={24} color="#d32f2f" />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {t('dialogs.deleteArchive.title')}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          {t('dialogs.deleteArchive.warning')}
        </Alert>
        <Typography variant="body2" gutterBottom>
          {t('dialogs.deleteArchive.subtitle')} <strong>"{archiveName}"</strong>
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('dialogs.deleteArchive.archiveName', { name: archiveName })}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        <Button
          variant="contained"
          color="error"
          onClick={() => archiveName && onConfirm(archiveName)}
          disabled={deleting}
          startIcon={
            deleting ? <CircularProgress size={16} color="inherit" /> : <Trash2 size={16} />
          }
        >
          {deleting ? t('dialogs.deleteArchive.deleting') : t('dialogs.deleteArchive.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
