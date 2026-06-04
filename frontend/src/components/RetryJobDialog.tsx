import { Box, Button, DialogActions, DialogContent, Typography } from '@mui/material'
import { RotateCcw } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from './shared/ResponsiveDialog'

interface RetryJobDialogProps {
  open: boolean
  title: string
  confirmLabel: string
  onClose: () => void
  onConfirm: () => void
}

export default function RetryJobDialog({
  open,
  title,
  confirmLabel,
  onClose,
  onConfirm,
}: RetryJobDialogProps) {
  const { t } = useTranslation()

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Box sx={{ color: 'info.main', lineHeight: 0 }}>
            <RotateCcw size={24} />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {title}
          </Typography>
        </Box>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} variant="outlined">
          {t('common.buttons.cancel')}
        </Button>
        <Button
          onClick={onConfirm}
          color="info"
          variant="contained"
          startIcon={<RotateCcw size={18} />}
        >
          {confirmLabel}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
