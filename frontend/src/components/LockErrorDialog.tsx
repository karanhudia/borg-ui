import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Alert,
  Box,
  CircularProgress,
} from '@mui/material'
import { AlertCircle, Unlock } from 'lucide-react'
import { useState } from 'react'
import { repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface LockErrorDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  repositoryName: string
  onLockBroken?: () => void
}

export default function LockErrorDialog({
  open,
  onClose,
  repositoryId,
  repositoryName,
  onLockBroken,
}: LockErrorDialogProps) {
  const [breaking, setBreaking] = useState(false)

  const handleBreakLock = async () => {
    if (!window.confirm(
      'Are you CERTAIN no backup or operation is currently running on this repository? ' +
      'Breaking the lock while an operation is running can corrupt your repository!'
    )) {
      return
    }

    setBreaking(true)
    try {
      await repositoriesAPI.breakLock(repositoryId)
      toast.success('Lock removed successfully! You can now retry your operation.')
      onLockBroken?.()
      onClose()
    } catch (error: any) {
      toast.error(error.response?.data?.detail || 'Failed to break lock')
    } finally {
      setBreaking(false)
    }
  }

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <AlertCircle size={24} color="#f57c00" />
          <Box sx={{ display: 'flex', flexDirection: 'column' }}>
            <Typography variant="h6">Repository Locked</Typography>
            <Typography variant="body2" color="text.secondary">
              <strong>{repositoryName}</strong> is locked by another process or has a stale lock.
            </Typography>
          </Box>
        </Box>
      </DialogTitle>

      <DialogContent>
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          <Typography variant="body2">
            If no backup is currently running, this is likely a stale lock from a crashed backup.
          </Typography>
        </Alert>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          <strong>What causes this?</strong>
        </Typography>
        <Typography variant="body2" color="text.secondary" component="ul" sx={{ pl: 2, mb: 1.5, mt: 0 }}>
          <li>Previous backup was interrupted or crashed</li>
          <li>Network connection dropped during SSH backup</li>
          <li>Container was restarted during an operation</li>
          <li>Repository cache locks from stale operations</li>
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
          <strong>Before breaking the lock:</strong>
        </Typography>
        <Typography variant="body2" color="text.secondary" component="ul" sx={{ pl: 2, mt: 0, mb: 0 }}>
          <li>Make sure no backup process is currently running</li>
          <li>Check that no other client is accessing this repository</li>
          <li>This will break both repository and cache locks</li>
        </Typography>
      </DialogContent>

      <DialogActions sx={{ px: 3, pb: 2 }}>
        <Button onClick={onClose} disabled={breaking}>
          Cancel
        </Button>
        <Button
          variant="contained"
          color="warning"
          onClick={handleBreakLock}
          disabled={breaking}
          startIcon={breaking ? <CircularProgress size={16} /> : <Unlock size={16} />}
        >
          {breaking ? 'Breaking Lock...' : 'Break Lock'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
