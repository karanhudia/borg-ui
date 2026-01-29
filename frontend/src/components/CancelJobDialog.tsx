import { Dialog, DialogContent, DialogActions, Button, Typography } from '@mui/material'

interface CancelJobDialogProps {
  open: boolean
  onClose: () => void
  onConfirm: () => void | Promise<void>
  jobId?: string | number
}

export default function CancelJobDialog({ open, onClose, onConfirm }: CancelJobDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogContent sx={{ pt: 3 }}>
        <Typography variant="h6" gutterBottom>
          Cancel Job?
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Are you sure you want to cancel this job? This action cannot be undone.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>No, Keep Running</Button>
        <Button onClick={onConfirm} color="error" variant="contained">
          Yes, Cancel Job
        </Button>
      </DialogActions>
    </Dialog>
  )
}
