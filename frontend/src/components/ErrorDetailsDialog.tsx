import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Alert,
  Typography,
  Box,
} from '@mui/material'
import StatusBadge from './StatusBadge'

interface JobWithError {
  id: string | number
  status: string
  error_message?: string | null
}

interface ErrorDetailsDialogProps<T extends JobWithError> {
  job: T | null
  open: boolean
  onClose: () => void
  onViewLogs?: (job: T) => void
}

export default function ErrorDetailsDialog<T extends JobWithError>({
  job,
  open,
  onClose,
  onViewLogs,
}: ErrorDetailsDialogProps<T>) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {job && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6">Error Details - Job #{job.id}</Typography>
            <StatusBadge status={job.status} />
          </Box>
        )}
      </DialogTitle>
      <DialogContent>
        {job && job.error_message && (
          <Alert severity="error" sx={{ mt: 1 }}>
            <Typography
              variant="body2"
              component="pre"
              sx={{ whiteSpace: 'pre-wrap', fontFamily: 'monospace' }}
            >
              {job.error_message}
            </Typography>
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
        {job && onViewLogs && (
          <Button
            onClick={() => {
              onClose()
              onViewLogs(job)
            }}
            variant="contained"
          >
            View Full Logs
          </Button>
        )}
      </DialogActions>
    </Dialog>
  )
}
