import { useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  DialogActions,
  DialogContent,
  DialogTitle,
  TextField,
  Typography,
} from '@mui/material'
import { FolderX } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import type { Repository } from '../types'
import ResponsiveDialog from './shared/ResponsiveDialog'

interface PermanentDeleteRepositoryDialogProps {
  open: boolean
  repository: Repository | null
  isPending: boolean
  onClose: () => void
  onConfirm: (confirmationPhrase: string) => void
}

export default function PermanentDeleteRepositoryDialog({
  open,
  repository,
  isPending,
  onClose,
  onConfirm,
}: PermanentDeleteRepositoryDialogProps) {
  const { t } = useTranslation()
  const [confirmationPhrase, setConfirmationPhrase] = useState('')

  useEffect(() => {
    if (open) setConfirmationPhrase('')
  }, [open, repository?.id])

  if (!repository) return null

  const isConfirmed = confirmationPhrase === repository.name

  const footer = (
    <DialogActions sx={{ px: 3, py: 2 }}>
      <Button onClick={onClose} disabled={isPending}>
        {t('common.buttons.cancel')}
      </Button>
      <Button
        color="error"
        variant="contained"
        onClick={() => onConfirm(confirmationPhrase)}
        disabled={!isConfirmed || isPending}
        startIcon={isPending ? <CircularProgress color="inherit" size={16} /> : <FolderX size={16} />}
      >
        {isPending
          ? t('repositories.permanentDeleteDialog.deleting')
          : t('repositories.permanentDeleteDialog.confirm')}
      </Button>
    </DialogActions>
  )

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth footer={footer}>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1.25, pb: 1 }}>
        <FolderX size={22} />
        {t('repositories.permanentDeleteDialog.title')}
      </DialogTitle>
      <DialogContent sx={{ pt: 1 }}>
        <Alert severity="error" sx={{ mb: 2 }}>
          {t('repositories.permanentDeleteDialog.warning')}
        </Alert>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          {t('repositories.permanentDeleteDialog.message', { name: repository.name })}
        </Typography>
        <Box
          sx={{
            mb: 2,
            px: 1.5,
            py: 1,
            borderRadius: 1,
            border: '1px solid',
            borderColor: 'divider',
            bgcolor: 'action.hover',
            fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
            fontSize: '0.8rem',
            overflowWrap: 'anywhere',
          }}
        >
          {repository.path}
        </Box>
        <TextField
          autoFocus
          fullWidth
          label={t('repositories.permanentDeleteDialog.confirmationLabel')}
          value={confirmationPhrase}
          onChange={(event) => setConfirmationPhrase(event.target.value)}
          disabled={isPending}
          helperText={t('repositories.permanentDeleteDialog.confirmationHelper', {
            name: repository.name,
          })}
        />
      </DialogContent>
    </ResponsiveDialog>
  )
}
