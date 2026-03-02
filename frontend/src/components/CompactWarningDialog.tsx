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
} from '@mui/material'
import { Warning, Compress, Lock } from '@mui/icons-material'
import { useTranslation } from 'react-i18next'

interface CompactWarningDialogProps {
  open: boolean
  repositoryName: string
  onConfirm: () => void
  onCancel: () => void
  isLoading?: boolean
}

export default function CompactWarningDialog({
  open,
  repositoryName,
  onConfirm,
  onCancel,
  isLoading = false,
}: CompactWarningDialogProps) {
  const { t } = useTranslation()
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Warning color="warning" />
        {t('dialogs.compactWarning.title')}
      </DialogTitle>
      <DialogContent>
        <Typography variant="body1" gutterBottom>
          {t('dialogs.compact.description', { repositoryName })}
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('dialogs.compact.explanation')}
        </Typography>

        <Box sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2" gutterBottom>
            {t('dialogs.compact.important')}
          </Typography>
          <List dense sx={{ py: 0 }}>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Lock fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary={t('dialogs.compact.repoWillBeLocked')}
                secondary={t('dialogs.compact.otherOperationsUnavailable')}
              />
            </ListItem>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Compress fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary={t('dialogs.compact.progressTracking')}
                secondary={t('dialogs.compact.progressTrackingDetail')}
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          {t('dialogs.compact.tip')}
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={isLoading}>
          {t('dialogs.compactWarning.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color="warning"
          disabled={isLoading}
          startIcon={isLoading ? <Compress className="animate-spin" /> : <Compress />}
        >
          {isLoading ? t('common.status.starting') : t('dialogs.compactWarning.confirm')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
