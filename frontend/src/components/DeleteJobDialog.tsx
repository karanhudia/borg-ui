import { Dialog, DialogContent, DialogActions, Button, Typography, Alert, Box } from '@mui/material'
import { AlertTriangle } from 'lucide-react'

interface DeleteJobDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  jobId?: string | number
  jobType?: string
}

export default function DeleteJobDialog({
  open,
  onClose,
  onConfirm,
  jobId,
  jobType = 'job',
}: DeleteJobDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
          <Box sx={{ color: 'error.main' }}>
            <AlertTriangle size={24} />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            Delete {jobType === 'backup' ? 'Backup' : 'Job'} Entry?
          </Typography>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Are you sure you want to permanently delete this {jobType} job entry
          {jobId && ` (ID: ${jobId})`}?
        </Typography>

        <Alert severity="warning" sx={{ mb: 0 }}>
          <Typography variant="body2" fontWeight={500} gutterBottom>
            This action cannot be undone
          </Typography>
          <Typography variant="body2">
            • Job history will be permanently removed
            <br />
            • Associated log files will be deleted
            <br />• This information cannot be recovered
          </Typography>
        </Alert>
      </DialogContent>
      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} variant="outlined">
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          color="error"
          variant="contained"
          startIcon={<AlertTriangle size={18} />}
        >
          Delete Permanently
        </Button>
      </DialogActions>
    </Dialog>
  )
}
