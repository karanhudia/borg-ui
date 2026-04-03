import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Alert,
  Box,
  CircularProgress,
} from '@mui/material'
import { AlertCircle, Unlock } from 'lucide-react'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'

interface LockErrorDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  borgVersion?: 1 | 2
  onLockBroken?: () => void
  canBreakLock?: boolean
}

export default function LockErrorDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  borgVersion: _borgVersion,
  onLockBroken,
  canBreakLock = false,
}: LockErrorDialogProps) {
  const { t } = useTranslation()
  const [breaking, setBreaking] = useState(false)

  const handleBreakLock = async () => {
    if (!window.confirm(t('dialogs.lockError.breakLockWarning'))) {
      return
    }

    setBreaking(true)
    try {
      await repositoriesAPI.breakLock(repositoryId)
      toast.success(t('dialogs.lockError.lockRemovedSuccess'))
      onLockBroken?.()
      onClose()
    } catch (
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      error: any
    ) {
      toast.error(
        translateBackendKey(error.response?.data?.detail) ||
          t('dialogs.lockError.failedToBreakLock')
      )
    } finally {
      setBreaking(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AlertCircle size={24} color="#f57c00" />
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6">{t('dialogs.lockError.title')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('dialogs.lockError.lockedDescription', { repositoryName })}
            </Typography>
          </Box>
        </Box>
      </DialogTitle>

      <DialogContent>
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          <Typography variant="body2">{t('dialogs.lockError.staleLockInfo')}</Typography>
        </Alert>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          <strong>{t('dialogs.lockError.whatCausesThis')}</strong>
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          component="ul"
          sx={{ pl: 2, mb: 1.5, mt: 0 }}
        >
          <li>{t('dialogs.lockError.causeInterrupted')}</li>
          <li>{t('dialogs.lockError.causeNetworkDrop')}</li>
          <li>{t('dialogs.lockError.causeContainerRestart')}</li>
          <li>{t('dialogs.lockError.causeCacheLocks')}</li>
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          <strong>{t('dialogs.lockError.beforeBreaking')}</strong>
        </Typography>
        <Typography
          variant="body2"
          color="text.secondary"
          component="ul"
          sx={{ pl: 2, mt: 0, mb: 0 }}
        >
          <li>{t('dialogs.lockError.beforeBreakingCheck1')}</li>
          <li>{t('dialogs.lockError.beforeBreakingCheck2')}</li>
          <li>{t('dialogs.lockError.beforeBreakingCheck3')}</li>
        </Typography>

        {!canBreakLock && (
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>{t('dialogs.lockError.adminRequired')}</strong>{' '}
              {t('dialogs.lockError.adminRequiredDetail')}
            </Typography>
          </Alert>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={breaking}>
          {t('dialogs.lockError.cancel')}
        </Button>
        <Button
          variant="contained"
          color="warning"
          onClick={handleBreakLock}
          disabled={breaking || !canBreakLock}
          startIcon={breaking ? <CircularProgress size={16} /> : <Unlock size={16} />}
          title={!canBreakLock ? 'Admin privileges required to break locks' : ''}
        >
          {breaking ? t('status.running') : t('dialogs.lockError.breakLock')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
