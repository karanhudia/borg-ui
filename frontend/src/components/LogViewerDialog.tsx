import { useCallback, useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
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
  const { t } = useTranslation()
  // Determine job type for API endpoint (default to 'backup' for backward compatibility)
  const jobType = job?.type || 'backup'
  const jobId = job?.id

  // Determine display label
  const displayLabel =
    jobTypeLabel || (job?.type ? getTypeLabel(job.type, t) : t('logViewer.typeBackup'))

  // Track live status so the badge and log viewer update after the job finishes
  const [currentStatus, setCurrentStatus] = useState(job?.status || 'unknown')

  // Reset status whenever a different job is opened
  useEffect(() => {
    setCurrentStatus(job?.status || 'unknown')
  }, [job?.id, job?.status])

  // Poll the activity list every 3 s while the dialog is open and the job is still running
  useEffect(() => {
    if (!open || !jobId || currentStatus !== 'running') return
    const poll = async () => {
      try {
        const res = await fetch(
          `/api/activity/recent?job_type=${jobType}&limit=100`,
          {
            headers: {
              Authorization: `Bearer ${localStorage.getItem('access_token') || ''}`,
            },
          }
        )
        if (!res.ok) return
        const items: Array<{ id: number; type: string; status: string }> = await res.json()
        const item = items.find(
          (i) => String(i.id) === String(jobId) && i.type === jobType
        )
        if (item && item.status !== 'running') setCurrentStatus(item.status)
      } catch {
        // Ignore network errors — next poll will retry
      }
    }
    const interval = setInterval(poll, 3000)
    return () => clearInterval(interval)
  }, [open, jobId, jobType, currentStatus])

  // Memoize the fetch function to prevent re-renders from causing duplicate log fetches
  const handleFetchLogs = useCallback(
    async (offset: number) => {
      if (!jobId) return { lines: [], total_lines: 0, has_more: false }

      const response = await fetch(
        `/api/activity/${jobType}/${jobId}/logs?offset=${offset}&limit=500`,
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
    },
    [jobType, jobId]
  )

  if (!job) return null

  return (
    <Dialog open={open} onClose={onClose} maxWidth="lg" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="h6">
            {t('logViewer.title', { label: displayLabel, jobId: job.id })}
          </Typography>
          <StatusBadge status={currentStatus} />
        </Box>
      </DialogTitle>
      <DialogContent dividers>
        <TerminalLogViewer
          jobId={String(job.id)}
          status={currentStatus}
          jobType={jobType}
          showHeader={false}
          onFetchLogs={handleFetchLogs}
        />
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('dialogs.logViewer.close')}</Button>
      </DialogActions>
    </Dialog>
  )
}

// Helper to get human-readable type labels
function getTypeLabel(type: string, t: (key: string) => string): string {
  switch (type) {
    case 'backup':
      return t('logViewer.typeBackup')
    case 'restore':
      return t('logViewer.typeRestore')
    case 'check':
      return t('logViewer.typeCheck')
    case 'compact':
      return t('logViewer.typeCompact')
    case 'prune':
      return t('logViewer.typePrune')
    case 'package':
      return t('logViewer.typePackage')
    default:
      return type.charAt(0).toUpperCase() + type.slice(1)
  }
}
