import { useCallback, useEffect, useState } from 'react'
import {
  Alert,
  Box,
  Button,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Typography,
} from '@mui/material'
import { Folder, FolderOpen } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { rcloneAPI } from '../../services/api'

interface RcloneEntry {
  name: string
  path: string
  is_dir?: boolean
}

interface RcloneRemoteFolderPickerDialogProps {
  open: boolean
  remoteId: number | null
  initialPath?: string
  onClose: () => void
  onSelect: (path: string) => void
}

const parentPath = (path: string) => {
  const parts = path.split('/').filter(Boolean)
  parts.pop()
  return parts.join('/')
}

export default function RcloneRemoteFolderPickerDialog({
  open,
  remoteId,
  initialPath = '',
  onClose,
  onSelect,
}: RcloneRemoteFolderPickerDialogProps) {
  const { t } = useTranslation()
  const [currentPath, setCurrentPath] = useState(initialPath)
  const [entries, setEntries] = useState<RcloneEntry[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const loadPath = useCallback(
    async (path: string) => {
      if (!remoteId) return
      setLoading(true)
      setError(null)
      try {
        const response = await rcloneAPI.browseRemote(remoteId, path)
        setCurrentPath(response.data.path || path || '')
        setEntries((response.data.entries || []).filter((entry: RcloneEntry) => entry.is_dir))
      } catch {
        setError(t('wizard.cloudMirror.browseFailed'))
        setEntries([])
      } finally {
        setLoading(false)
      }
    },
    [remoteId, t]
  )

  useEffect(() => {
    if (open && remoteId) {
      loadPath(initialPath || '')
    }
  }, [initialPath, loadPath, open, remoteId])

  return (
    <Dialog open={open} onClose={onClose} maxWidth="sm" fullWidth transitionDuration={0}>
      <DialogTitle>{t('wizard.cloudMirror.browseTitle')}</DialogTitle>
      <DialogContent dividers>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
          <Typography variant="body2" color="text.secondary">
            {currentPath || t('wizard.cloudMirror.remoteRoot')}
          </Typography>

          {error && <Alert severity="error">{error}</Alert>}

          {loading ? (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 2 }}>
              <CircularProgress size={18} />
              <Typography variant="body2">{t('wizard.cloudMirror.browsing')}</Typography>
            </Box>
          ) : (
            <List dense>
              {currentPath && (
                <ListItem disableGutters>
                  <ListItemButton onClick={() => loadPath(parentPath(currentPath))}>
                    <ListItemIcon sx={{ minWidth: 34 }}>
                      <FolderOpen size={18} />
                    </ListItemIcon>
                    <ListItemText primary=".." />
                  </ListItemButton>
                </ListItem>
              )}
              {entries.map((entry) => (
                <ListItem key={entry.path || entry.name} disableGutters>
                  <ListItemButton onClick={() => loadPath(entry.path || entry.name)}>
                    <ListItemIcon sx={{ minWidth: 34 }}>
                      <Folder size={18} />
                    </ListItemIcon>
                    <ListItemText primary={entry.name} secondary={entry.path} />
                  </ListItemButton>
                </ListItem>
              ))}
              {!entries.length && (
                <Typography variant="body2" color="text.secondary">
                  {t('wizard.cloudMirror.noRemoteFolders')}
                </Typography>
              )}
            </List>
          )}
        </Box>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>{t('common.buttons.cancel')}</Button>
        <Button
          variant="contained"
          onClick={() => onSelect(currentPath)}
          disabled={!remoteId || loading}
        >
          {t('wizard.cloudMirror.useFolder')}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
