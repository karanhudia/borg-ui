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
  TextField,
} from '@mui/material'
import { HardDrive } from 'lucide-react'
import { Archive } from '../types'

interface MountArchiveDialogProps {
  open: boolean
  archive: Archive | null
  mountPoint: string
  onMountPointChange: (value: string) => void
  onClose: () => void
  onConfirm: () => void
  mounting?: boolean
}

export default function MountArchiveDialog({
  open,
  archive,
  mountPoint,
  onMountPointChange,
  onClose,
  onConfirm,
  mounting = false,
}: MountArchiveDialogProps) {
  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>
        <Stack direction="row" spacing={2} alignItems="center">
          <HardDrive size={24} />
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Mount Archive
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {archive?.name}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent>
        <Stack spacing={3} sx={{ mt: 1 }}>
          <Alert severity="info">
            The archive will be mounted as a read-only filesystem inside the container. You'll
            receive a command to access it via terminal.
          </Alert>
          <TextField
            label="Mount Name"
            value={mountPoint}
            onChange={(e) => onMountPointChange(e.target.value)}
            placeholder="my-backup-2024"
            helperText={`Will be mounted at: /data/mounts/${mountPoint || '<name>'}`}
            fullWidth
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button
          variant="contained"
          color="primary"
          onClick={onConfirm}
          disabled={mounting}
          startIcon={<HardDrive size={18} />}
        >
          {mounting ? 'Mounting...' : 'Mount'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
