import React from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  CircularProgress,
  Stack,
  Box,
} from '@mui/material'
import { AlertCircle, Trash2 } from 'lucide-react'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  repository: string | null
  repository_id: number | null
  repository_ids: number[] | null
  enabled: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
  updated_at: string | null
  description: string | null
  archive_name_template: string | null
  run_repository_scripts: boolean
  pre_backup_script_id: number | null
  post_backup_script_id: number | null
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  last_prune: string | null
  last_compact: string | null
}

interface DeleteScheduleDialogProps {
  open: boolean
  job: ScheduledJob | null
  onClose: () => void
  onConfirm: () => void
  isDeleting: boolean
}

const DeleteScheduleDialog: React.FC<DeleteScheduleDialogProps> = ({
  open,
  job,
  onClose,
  onConfirm,
  isDeleting,
}) => {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <Box
            sx={{
              width: 48,
              height: 48,
              borderRadius: '50%',
              backgroundColor: 'error.lighter',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <AlertCircle size={24} color="#d32f2f" />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            Delete Scheduled Job
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Typography variant="body2">
          Are you sure you want to delete the scheduled job <strong>"{job?.name}"</strong>?
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          This action cannot be undone. The job will no longer run automatically.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color="error"
          disabled={isDeleting}
          startIcon={isDeleting ? <CircularProgress size={16} /> : <Trash2 size={16} />}
        >
          {isDeleting ? 'Deleting...' : 'Delete Job'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default DeleteScheduleDialog
