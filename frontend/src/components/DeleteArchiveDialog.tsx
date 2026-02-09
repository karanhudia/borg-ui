import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Box,
  Alert,
  CircularProgress,
} from '@mui/material'
import { AlertCircle, Trash2 } from 'lucide-react'

interface DeleteArchiveDialogProps {
  open: boolean
  archiveName: string | null
  onClose: () => void
  onConfirm: (archiveName: string) => void
  deleting?: boolean
}

export default function DeleteArchiveDialog({
  open,
  archiveName,
  onClose,
  onConfirm,
  deleting = false,
}: DeleteArchiveDialogProps) {
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
            Delete Archive
          </Typography>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Alert severity="warning" sx={{ mb: 2 }}>
          This action cannot be undone!
        </Alert>
        <Typography variant="body2" gutterBottom>
          Are you sure you want to delete the archive <strong>"{archiveName}"</strong>?
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          The deletion will run in the background. You can close this dialog and continue working.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          color="error"
          onClick={() => archiveName && onConfirm(archiveName)}
          disabled={deleting}
          startIcon={
            deleting ? <CircularProgress size={16} color="inherit" /> : <Trash2 size={16} />
          }
        >
          {deleting ? 'Starting...' : 'Delete'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
