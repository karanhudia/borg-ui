import { useTranslation } from 'react-i18next'
import { translateBackendKey } from '../utils/translateBackendKey'
import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Alert,
  Typography,
  Box,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
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
  const { t } = useTranslation()
  return (
    <ResponsiveDialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        {job && (
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
            <Typography variant="h6">
              {t('dialogs.errorDetails.title')} - Job #{job.id}
            </Typography>
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
              {job.error_message
                .split('\n')
                .map((line) => translateBackendKey(line))
                .join('\n')}
            </Typography>
          </Alert>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} sx={{ display: { xs: 'none', md: 'inline-flex' } }}>
          {t('dialogs.errorDetails.close')}
        </Button>
        {job && onViewLogs && (
          <Button
            onClick={() => {
              onClose()
              onViewLogs(job)
            }}
            variant="contained"
          >
            {t('dialogs.errorDetails.viewFullLogs')}
          </Button>
        )}
      </DialogActions>
    </ResponsiveDialog>
  )
}
