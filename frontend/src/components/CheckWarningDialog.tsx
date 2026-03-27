import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  TextField,
  CircularProgress,
} from '@mui/material'
import { Warning, CheckCircle, Lock } from '@mui/icons-material'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

interface CheckWarningDialogProps {
  open: boolean
  repositoryName: string
  onConfirm: (maxDuration: number) => void
  onCancel: () => void
  isLoading?: boolean
}

export default function CheckWarningDialog({
  open,
  repositoryName,
  onConfirm,
  onCancel,
  isLoading = false,
}: CheckWarningDialogProps) {
  const { t } = useTranslation()
  const [maxDuration, setMaxDuration] = useState<number>(3600)
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Warning color="warning" />
        {t('dialogs.checkWarning.title')}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body1" gutterBottom>
          {t('dialogs.checkWarning.description', { repositoryName })}
        </Typography>

        <Box sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2" gutterBottom>
            {t('dialogs.checkWarning.important')}
          </Typography>
          <List dense sx={{ py: 0 }}>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Lock fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary={t('dialogs.checkWarning.repoWillBeLocked')}
                secondary={t('dialogs.checkWarning.otherOperationsUnavailable')}
              />
            </ListItem>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <CheckCircle fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary={t('dialogs.checkWarning.progressTracking')}
                secondary={t('dialogs.checkWarning.progressTrackingDetail')}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('dialogs.checkWarning.otherReposAccessible')}
        </Typography>

        <Box sx={{ mt: 2 }}>
          <TextField
            label={t('dialogs.checkWarning.maxDurationLabel')}
            type="number"
            value={maxDuration}
            onChange={(e) => {
              const value = parseInt(e.target.value)
              setMaxDuration(isNaN(value) ? 3600 : value)
            }}
            fullWidth
            helperText={t('dialogs.checkWarning.maxDurationHelper')}
            InputProps={{
              inputProps: { min: 0 },
            }}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={isLoading}>
          {t('dialogs.checkWarning.cancel')}
        </Button>
        <Button
          onClick={() => onConfirm(maxDuration)}
          variant="contained"
          color="warning"
          disabled={isLoading}
          startIcon={isLoading ? <CircularProgress size={16} color="inherit" /> : <CheckCircle />}
        >
          {isLoading ? t('status.running') : t('dialogs.checkWarning.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
