import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
} from '@mui/material'
import StatusBadge from './StatusBadge'
import { TerminalLogViewer } from './TerminalLogViewer'

interface JobWithLogs {
  id: string | number
  status: string
  type?: string
}

interface LogViewerDialogProps<T extends JobWithLogs> {
  job: T | null
  open: boolean
  onClose: () => void
  jobTypeLabel?: string // Optional: "Backup", "Check", "Compact", etc.
}

export default function LogViewerDialog<T extends JobWithLogs>({
  job,
  open,
  onClose,
  jobTypeLabel,
}: LogViewerDialogProps<T>) {
  if (!job) return null

  // Determine job type for API endpoint (default to 'backup' for backward compatibility)
  const jobType = job.type || 'backup'

  // Determine display label
  const displayLabel = jobTypeLabel || (job.type ? getTypeLabel(job.type) : 'Backup')

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">
            {displayLabel} Logs - Job #{job.id}
          </Typography>
          <StatusBadge status={job.status} />
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        <TerminalLogViewer
          jobId={String(job.id)}
          status={job.status}
          jobType={jobType}
          showHeader={false}
          onFetchLogs={async (offset) => {
            const response = await fetch(
              `/api/activity/${jobType}/${job.id}/logs?offset=${offset}&limit=500`,
              {
                headers: {
                  Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
                },
              }
            )
            if (!response.ok) {
              throw new Error('Failed to fetch logs')
            }
            return response.json()
          }}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}

// Helper to get human-readable type labels
function getTypeLabel(type: string): string {
  switch (type) {
    case 'backup':
      return 'Backup'
    case 'restore':
      return 'Restore'
    case 'check':
      return 'Check'
    case 'compact':
      return 'Compact'
    case 'prune':
      return 'Prune'
    case 'package':
      return 'Package'
    default:
      return type.charAt(0).toUpperCase() + type.slice(1)
  }
}
