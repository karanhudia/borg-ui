import React, { useState } from 'react'
import {
  Dialog,
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
} from '@mui/material'
import { Delete, Info } from '@mui/icons-material'

interface Repository {
  id: number
  name: string
}

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
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          <Delete color="secondary" />
          <Typography variant="h6" fontWeight={600}>
            Prune Archives
          </Typography>
        </Box>
      </DialogTitle>
      <DialogContent>
        <Alert severity="info" sx={{ mb: 3 }}>
          <Typography variant="subtitle2" fontWeight={600} gutterBottom>
            What does pruning do?
          </Typography>
          <Typography variant="body2" gutterBottom>
            Pruning automatically deletes old archives based on retention rules. This helps manage
            repository size by keeping only the backups you need.
          </Typography>
          <Typography variant="body2" fontWeight={600} color="primary.main">
            Tip: Always run "Dry Run" first to preview what will be deleted!
          </Typography>
        </Alert>

        <Typography variant="subtitle2" fontWeight={600} gutterBottom>
          Retention Policy
        </Typography>
        <Typography variant="body2" color="text.secondary" gutterBottom sx={{ mb: 2 }}>
          Specify how many backups to keep for each time period
        </Typography>

        <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 2, mb: 3 }}>
          <TextField
            label="Keep Hourly"
            type="number"
            value={pruneForm.keep_hourly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_hourly: parseInt(e.target.value) || 0 })
            }
            helperText="Last N hourly backups (0 = disabled)"
            fullWidth
          />
          <TextField
            label="Keep Daily"
            type="number"
            value={pruneForm.keep_daily}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_daily: parseInt(e.target.value) || 0 })
            }
            helperText="Last N daily backups"
            fullWidth
          />
          <TextField
            label="Keep Weekly"
            type="number"
            value={pruneForm.keep_weekly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_weekly: parseInt(e.target.value) || 0 })
            }
            helperText="Last N weekly backups"
            fullWidth
          />
          <TextField
            label="Keep Monthly"
            type="number"
            value={pruneForm.keep_monthly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_monthly: parseInt(e.target.value) || 0 })
            }
            helperText="Last N monthly backups"
            fullWidth
          />
          <TextField
            label="Keep Quarterly"
            type="number"
            value={pruneForm.keep_quarterly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_quarterly: parseInt(e.target.value) || 0 })
            }
            helperText="Last N quarterly backups (0 = disabled)"
            fullWidth
          />
          <TextField
            label="Keep Yearly"
            type="number"
            value={pruneForm.keep_yearly}
            onChange={(e) =>
              setPruneForm({ ...pruneForm, keep_yearly: parseInt(e.target.value) || 0 })
            }
            helperText="Last N yearly backups"
            fullWidth
          />
        </Box>

        <Box sx={{ bgcolor: 'background.default', p: 2, borderRadius: 1, mb: 2 }}>
          <Typography variant="body2" gutterBottom>
            <strong>Repository:</strong> {repository?.name}
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block">
            Example: With these settings, you'll keep the last 7 daily, 4 weekly, 6 monthly, and 1
            yearly backup. Older archives will be deleted.
          </Typography>
        </Box>

        {/* Prune Results Display */}
        {results && (
          <Box sx={{ mt: 2 }}>
            <Typography variant="subtitle2" fontWeight={600} gutterBottom>
              {results.dry_run ? 'Dry Run Results (Preview)' : 'Prune Results'}
            </Typography>

            {results.prune_result?.success === false ? (
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="body2" fontWeight={600} gutterBottom>
                  Operation Failed
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
                        Output:
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
                        {results.prune_result.stdout || 'No output'}
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
                        Messages:
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
                <Typography variant="body2">
                  Dry run completed successfully. Review the output above to see which archives
                  would be deleted. If everything looks correct, click "Prune Archives" to execute.
                </Typography>
              </Alert>
            )}
          </Box>
        )}

        <Alert severity="warning">
          <Typography variant="body2" fontWeight={600} gutterBottom>
            Warning: Deleted archives cannot be recovered!
          </Typography>
          <Typography variant="body2">
            After pruning, run "Compact" to actually free up disk space.
          </Typography>
        </Alert>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button onClick={handleDryRun} variant="outlined" disabled={isLoading} startIcon={<Info />}>
          Dry Run (Preview)
        </Button>
        <Button
          onClick={handleConfirmPrune}
          variant="contained"
          color="error"
          disabled={isLoading}
          startIcon={isLoading ? <Delete className="animate-spin" /> : <Delete />}
        >
          {isLoading ? 'Pruning...' : 'Prune Archives'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
