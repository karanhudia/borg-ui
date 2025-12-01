import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Box,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  TextField,
} from '@mui/material'
import { Warning, CheckCircle, Lock } from '@mui/icons-material'
import { useState } from 'react'

interface CheckWarningDialogProps {
  open: boolean
  repositoryName: string
  onConfirm: (maxDuration: number) => void
  onCancel: () => void
  isLoading?: boolean
}

export default function CheckWarningDialog({
  open,
  repositoryName,
  onConfirm,
  onCancel,
  isLoading = false,
}: CheckWarningDialogProps) {
  const [maxDuration, setMaxDuration] = useState<number>(3600)
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Warning color="warning" />
        Confirm Repository Check
      </DialogTitle>
      <DialogContent>
        <Typography variant="body1" gutterBottom>
          Check the integrity of repository: <strong>{repositoryName}</strong>
        </Typography>

        <Box sx={{ mt: 1.5 }}>
          <Typography variant="subtitle2" gutterBottom>
            Important:
          </Typography>
          <List dense sx={{ py: 0 }}>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Lock fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary="Repository will be locked"
                secondary="Other operations (info, archives, backup) will not be available until check completes"
              />
            </ListItem>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <CheckCircle fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary="Progress tracking"
                secondary="You can monitor progress in real-time. Note: Check operations cannot be cancelled once started."
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Other repositories will remain accessible during this operation.
        </Typography>

        <Box sx={{ mt: 2 }}>
          <TextField
            label="Max Duration (seconds)"
            type="number"
            value={maxDuration}
            onChange={(e) => {
              const value = parseInt(e.target.value)
              setMaxDuration(isNaN(value) ? 3600 : value)
            }}
            fullWidth
            helperText="Maximum time for the check operation. Default: 3600 seconds (1 hour). Set to 0 for unlimited."
            InputProps={{
              inputProps: { min: 0 },
            }}
          />
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button
          onClick={() => onConfirm(maxDuration)}
          variant="contained"
          color="warning"
          disabled={isLoading}
          startIcon={isLoading ? <CheckCircle className="animate-spin" /> : <CheckCircle />}
        >
          {isLoading ? 'Starting...' : 'Start Check'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
