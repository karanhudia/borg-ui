import {
  Box,
  Button,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  Typography,
  useTheme,
} from '@mui/material'
import { History } from 'lucide-react'
import type { TFunction } from 'i18next'

import ResponsiveDialog from '../../../components/ResponsiveDialog'
import { type BackupPlanRunLogJob } from '../../../components/BackupPlanRunsPanel'
import type { BackupPlan, BackupPlanRun } from '../../../types'
import { PlanRunsHistoryTable } from './PlanRunsHistoryTable'

interface BackupPlanHistoryDialogProps {
  plan: BackupPlan | null
  runs: BackupPlanRun[]
  cancellingRunId: number | null
  onClose: () => void
  onViewLogs: (job: BackupPlanRunLogJob) => void
  onCancel: (runId: number) => void
  t: TFunction
}

export function BackupPlanHistoryDialog({
  plan,
  runs,
  cancellingRunId,
  onClose,
  onViewLogs,
  onCancel,
  t,
}: BackupPlanHistoryDialogProps) {
  const theme = useTheme()

  return (
    <ResponsiveDialog
      open={Boolean(plan)}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      footer={
        <DialogActions>
          <Button onClick={onClose}>{t('common.buttons.close', { defaultValue: 'Close' })}</Button>
        </DialogActions>
      }
    >
      <DialogTitle sx={{ pb: 1 }}>
        <Stack direction="row" spacing={1} alignItems="center">
          <Box sx={{ color: theme.palette.info.main, display: 'flex', alignItems: 'center' }}>
            <History size={18} />
          </Box>
          <Typography variant="h6" component="span" sx={{ fontWeight: 700 }}>
            {plan?.name}
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent sx={{ p: 0 }}>
        <PlanRunsHistoryTable
          runs={runs}
          cancelling={cancellingRunId}
          onViewLogs={onViewLogs}
          onCancel={onCancel}
          t={t}
        />
      </DialogContent>
    </ResponsiveDialog>
  )
}
