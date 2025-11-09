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
} from '@mui/material'
import { Warning, Compress, Lock } from '@mui/icons-material'

interface CompactWarningDialogProps {
  open: boolean
  repositoryName: string
  onConfirm: () => void
  onCancel: () => void
  isLoading?: boolean
}

export default function CompactWarningDialog({
  open,
  repositoryName,
  onConfirm,
  onCancel,
  isLoading = false,
}: CompactWarningDialogProps) {
  return (
    <Dialog open={open} onClose={onCancel} maxWidth="sm" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Warning color="warning" />
        Confirm Repository Compaction
      </DialogTitle>
      <DialogContent>
        <Typography variant="body1" gutterBottom>
          Compact repository: <strong>{repositoryName}</strong>
        </Typography>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Compaction removes unused segments and reclaims disk space from deleted archives.
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
                secondary="Other operations (info, archives, backup) will not be available until compaction completes"
              />
            </ListItem>
            <ListItem sx={{ py: 0.5 }}>
              <ListItemIcon sx={{ minWidth: 36 }}>
                <Compress fontSize="small" color="action" />
              </ListItemIcon>
              <ListItemText
                primary="Progress tracking"
                secondary="You can monitor progress in real-time"
              />
            </ListItem>
          </List>
        </Box>

        <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
          Tip: Run compaction after pruning old archives to free up space. Other repositories will remain accessible.
        </Typography>
      </DialogContent>
      <DialogActions>
        <Button onClick={onCancel} disabled={isLoading}>
          Cancel
        </Button>
        <Button
          onClick={onConfirm}
          variant="contained"
          color="warning"
          disabled={isLoading}
          startIcon={isLoading ? <Compress className="animate-spin" /> : <Compress />}
        >
          {isLoading ? 'Starting...' : 'Start Compacting'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
