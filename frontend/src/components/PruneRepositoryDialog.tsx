import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Box,
  Typography,
  Button,
  TextField,
  Alert,
  Card,
  CardContent,
  CircularProgress,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { Delete, Info } from '@mui/icons-material'
import { Repository } from '../types'

interface PruneForm {
  keep_hourly: number
  keep_daily: number
  keep_weekly: number
  keep_monthly: number
  keep_quarterly: number
  keep_yearly: number
}

interface PruneResults {
  dry_run: boolean
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  prune_result?: any
}

interface PruneRepositoryDialogProps {
  open: boolean
  repository: Repository | null
  onClose: () => void
  onDryRun: (form: PruneForm) => Promise<void>
  onConfirmPrune: (form: PruneForm) => Promise<void>
  isLoading: boolean
  results: PruneResults | null
}

const defaultPruneForm: PruneForm = {
  keep_hourly: 0,
  keep_daily: 7,
  keep_weekly: 4,
  keep_monthly: 6,
  keep_quarterly: 0,
  keep_yearly: 1,
}

export default function PruneRepositoryDialog({
  open,
  repository,
  onClose,
  onDryRun,
  onConfirmPrune,
  isLoading,
  results,
}: PruneRepositoryDialogProps) {
  const { t } = useTranslation()
  const [pruneForm, setPruneForm] = useState<PruneForm>(defaultPruneForm)

  // Reset form when dialog opens
  React.useEffect(() => {
    if (open) {
      setPruneForm(defaultPruneForm)
    }
  }, [open])

  const handleDryRun = () => {
    onDryRun(pruneForm)
  }

  const handleConfirmPrune = () => {
    onConfirmPrune(pruneForm)
  }

  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Delete color="secondary" />
          <Typography variant="h6" fontWeight={600}>
            {t('dialogs.pruneRepository.title')}
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            {t('dialogs.prune.whatDoesPruningDo')}
          </Typography>
          <Typography variant="body2" gutterBottom>
            {t('dialogs.prune.explanation')}
          </Typography>
          <Typography variant="body2" fontWeight={600} color="primary.main">
            {t('dialogs.prune.dryRunTip')}
          </Typography>
        </Alert>

        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          {t('dialogs.prune.retentionPolicy')}
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
          {t('dialogs.prune.retentionDescription')}
        </Typography>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)' },
            gap: 2,
            mb: 3,
          }}
        >
          <TextField
            label={t('dialogs.prune.keepHourly')}
            type="number"
            value={pruneForm.keep_hourly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_hourly: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepHourlyHelper')}
            fullWidth
          />
          <TextField
            label={t('dialogs.prune.keepDaily')}
            type="number"
            value={pruneForm.keep_daily}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_daily: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepDailyHelper')}
            fullWidth
          />
          <TextField
            label={t('dialogs.prune.keepWeekly')}
            type="number"
            value={pruneForm.keep_weekly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_weekly: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepWeeklyHelper')}
            fullWidth
          />
          <TextField
            label={t('dialogs.prune.keepMonthly')}
            type="number"
            value={pruneForm.keep_monthly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_monthly: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepMonthlyHelper')}
            fullWidth
          />
          <TextField
            label={t('dialogs.prune.keepQuarterly')}
            type="number"
            value={pruneForm.keep_quarterly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_quarterly: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepQuarterlyHelper')}
            fullWidth
          />
          <TextField
            label={t('dialogs.prune.keepYearly')}
            type="number"
            value={pruneForm.keep_yearly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_yearly: parseInt(e.target.value) || 0 })
            }
            helperText={t('dialogs.prune.keepYearlyHelper')}
            fullWidth
          />
        </Box>

        <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1, mb: 2 }}>
          <Typography variant="body2" gutterBottom>
            <strong>{t('dialogs.prune.repositoryLabel')}</strong> {repository?.name}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            {t('dialogs.prune.exampleExplanation')}
          </Typography>
        </Box>

        {/* Prune Results Display */}
        {results && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              {results.dry_run
                ? t('dialogs.prune.dryRunResultsTitle')
                : t('dialogs.prune.pruneResultsTitle')}
            </Typography>

            {results.prune_result?.success === false ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="body2" fontWeight={600} gutterBottom>
                  {t('dialogs.prune.operationFailed')}
                </Typography>
                {results.prune_result?.stderr && (
                  <Box
                    component="pre"
                    sx={{
                      mt: 1,
                      p: 1.5,
                      bgcolor: 'action.hover',
                      borderRadius: 1,
                      fontSize: '0.75rem',
                      overflow: 'auto',
                      maxHeight: 200,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {results.prune_result.stderr}
                  </Box>
                )}
              </Alert>
            ) : (
              <Card variant="outlined" sx={{ mb: 2 }}>
                <CardContent>
                  {results.prune_result?.stdout && (
                    <Box>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        display="block"
                        gutterBottom
                      >
                        {t('dialogs.prune.outputLabel')}
                      </Typography>
                      <Box
                        component="pre"
                        sx={{
                          p: 1.5,
                          bgcolor: 'background.default',
                          borderRadius: 1,
                          fontSize: '0.75rem',
                          overflow: 'auto',
                          maxHeight: 300,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'monospace',
                        }}
                      >
                        {results.prune_result.stdout || t('dialogs.prune.noOutput')}
                      </Box>
                    </Box>
                  )}
                  {results.prune_result?.stderr && (
                    <Box sx={{ mt: 2 }}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        display="block"
                        gutterBottom
                      >
                        {t('dialogs.prune.messagesLabel')}
                      </Typography>
                      <Box
                        component="pre"
                        sx={{
                          p: 1.5,
                          bgcolor: 'warning.lighter',
                          borderRadius: 1,
                          fontSize: '0.75rem',
                          overflow: 'auto',
                          maxHeight: 200,
                          whiteSpace: 'pre-wrap',
                          wordBreak: 'break-word',
                          fontFamily: 'monospace',
                        }}
                      >
                        {results.prune_result.stderr}
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            )}

            {results.dry_run && results.prune_result?.success !== false && (
              <Alert severity="success" sx={{ mb: 2 }}>
                <Typography variant="body2">{t('dialogs.prune.dryRunSuccess')}</Typography>
              </Alert>
            )}
          </Box>
        )}

        <Alert severity="warning">
          <Typography variant="body2" fontWeight={600} gutterBottom>
            {t('dialogs.prune.warningTitle')}
          </Typography>
          <Typography variant="body2">{t('dialogs.prune.warningCompact')}</Typography>
        </Alert>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('dialogs.pruneRepository.cancel')}</Button>
        <Button onClick={handleDryRun} variant="outlined" disabled={isLoading} startIcon={<Info />}>
          {t('dialogs.prune.dryRunButton')}
        </Button>
        <Button
          onClick={handleConfirmPrune}
          variant="contained"
          color="error"
          disabled={isLoading}
          startIcon={isLoading ? <CircularProgress size={16} color="inherit" /> : <Delete />}
        >
          {isLoading ? t('status.running') : t('dialogs.pruneRepository.confirm')}
        </Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
