import { useState } from 'react'
import { Alert, Box, Typography, Button, Stack, DialogContent, DialogActions } from '@mui/material'
import { useTranslation } from 'react-i18next'
import ResponsiveDialog from '../shared/ResponsiveDialog'
import RichSelect from '../shared/RichSelect'
import CategoryToken from '../CategoryToken'
import { archivesAPI } from '../../services/api'
import type { OperationItem, RebuildStage } from '../../types/operations'

interface RepositoryTrackDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  operations: OperationItem[]
}

const REBUILD_STAGES: RebuildStage[] = ['stats', 'archives', 'history']

export default function RepositoryTrackDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  operations,
}: RepositoryTrackDialogProps) {
  const { t } = useTranslation()
  const [stage, setStage] = useState<RebuildStage>('stats')
  const [submitting, setSubmitting] = useState(false)
  const [failed, setFailed] = useState(false)

  const handleRebuild = async () => {
    setSubmitting(true)
    setFailed(false)
    try {
      await archivesAPI.rebuild(repositoryId, stage)
      onClose()
    } catch {
      // A rebuild can be refused (repository permissions, or the
      // `archive_history` plan gate), and closing on failure would read as
      // success. Keep the dialog open and say so.
      setFailed(true)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Typography variant="h6" gutterBottom>
          {repositoryName}
        </Typography>
        <Stack spacing={1.5} sx={{ py: 1 }}>
          {operations.map((op) => (
            <Box key={op.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <CategoryToken category={op.category} />
              <Typography variant="body2">{t(`operations.kind.${op.kind}`)}</Typography>
              <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
                {t(`operations.status.${op.status}`)}
              </Typography>
            </Box>
          ))}
        </Stack>
        {failed && (
          <Alert severity="error" sx={{ mt: 1 }}>
            {t('operations.background.rebuildFailed')}
          </Alert>
        )}
        <Box sx={{ display: 'flex', alignItems: 'flex-end', gap: 1, pt: 1 }}>
          <RichSelect
            value={stage}
            onChange={(value) => setStage(value as RebuildStage)}
            label={t('operations.background.rebuildFrom')}
            options={REBUILD_STAGES.map((s) => ({
              value: s,
              primary: t(`operations.background.rebuildStage.${s}`),
            }))}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        <Button variant="outlined" disabled={submitting} onClick={handleRebuild}>
          {t('operations.background.rebuildFrom')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
