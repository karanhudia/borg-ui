import {
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
  Tooltip,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { Warning, CheckCircle, Lock, InfoOutlined } from '@mui/icons-material'
import { useState } from 'react'
import { useTranslation } from 'react-i18next'

export interface CheckWarningConfirmOptions {
  maxDuration: number
  checkExtraFlags: string
}

interface CheckWarningDialogProps {
  open: boolean
  repositoryName: string
  borgVersion?: number
  onConfirm: (options: CheckWarningConfirmOptions) => void
  onCancel: () => void
  isLoading?: boolean
  initialMaxDuration?: number
  initialCheckExtraFlags?: string
}

export default function CheckWarningDialog({
  open,
  repositoryName,
  borgVersion,
  onConfirm,
  onCancel,
  isLoading = false,
  initialMaxDuration = 3600,
  initialCheckExtraFlags = '',
}: CheckWarningDialogProps) {
  const { t } = useTranslation()
  const [maxDuration, setMaxDuration] = useState<number>(initialMaxDuration)
  const [checkExtraFlags, setCheckExtraFlags] = useState(initialCheckExtraFlags)
  const isBorg2 = borgVersion === 2
  return (
    <ResponsiveDialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
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

        <Box sx={{ mt: 2 }}>
          <TextField
            label={t('dialogs.checkWarning.extraFlagsLabel')}
            value={checkExtraFlags}
            onChange={(e) => setCheckExtraFlags(e.target.value)}
            fullWidth
            placeholder="--repair --verify-data"
            helperText={t('dialogs.checkWarning.extraFlagsHelper')}
            inputProps={{ spellCheck: false }}
          />
        </Box>

        {isBorg2 && (
          <Box
            sx={{
              mt: 1,
              display: 'flex',
              alignItems: 'center',
              gap: 0.5,
              color: 'warning.light',
            }}
          >
            <Typography
              variant="body2"
              sx={{
                lineHeight: 1.4,
                color: 'inherit',
                fontWeight: 500,
              }}
            >
              {t('dialogs.checkWarning.borg2InlineNotice')}
            </Typography>
            <Tooltip
              arrow
              placement="top"
              title={
                <Box sx={{ py: 0.25 }}>
                  <Typography variant="body2" sx={{ fontWeight: 600 }}>
                    {t('dialogs.checkWarning.borg2TooltipTitle')}
                  </Typography>
                  <Typography variant="caption" sx={{ display: 'block', mt: 0.5 }}>
                    {t('dialogs.checkWarning.borg2PartialCheckNotice')}
                  </Typography>
                </Box>
              }
            >
              <Box
                component="button"
                type="button"
                aria-label={t('dialogs.checkWarning.borg2TooltipTitle')}
                sx={{
                  appearance: 'none',
                  border: 0,
                  background: 'transparent',
                  color: 'inherit',
                  p: 0,
                  m: 0,
                  lineHeight: 0,
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  cursor: 'pointer',
                }}
              >
                <InfoOutlined sx={{ fontSize: 18 }} />
              </Box>
            </Tooltip>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={isLoading}>
          {t('dialogs.checkWarning.cancel')}
        </Button>
        <Button
          onClick={() => onConfirm({ maxDuration, checkExtraFlags })}
          variant="contained"
          color="warning"
          disabled={isLoading}
          startIcon={isLoading ? <CircularProgress size={16} color="inherit" /> : <CheckCircle />}
        >
          {isLoading ? t('status.running') : t('dialogs.checkWarning.confirm')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
