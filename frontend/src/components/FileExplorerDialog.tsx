import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Breadcrumbs,
  Link,
  Typography,
  Box,
  CircularProgress,
  Alert,
  Chip,
  TextField,
  InputAdornment,
  Checkbox,
} from '@mui/material'
import {
  Folder,
  File,
  ChevronRight,
  Home,
  Search,
  Archive,
} from 'lucide-react'
import api from '../services/api'

interface FileSystemItem {
  name: string
  path: string
  is_directory: boolean
  size?: number
  modified?: string
  is_borg_repo: boolean
  permissions?: string
}

interface FileExplorerDialogProps {
  open: boolean
  onClose: () => void
  onSelect: (selectedPaths: string[]) => void
  title?: string
  initialPath?: string
  multiSelect?: boolean
  connectionType?: 'local' | 'ssh'
  sshConfig?: {
    ssh_key_id: number
    host: string
    username: string
    port: number
  }
  selectMode?: 'directories' | 'files' | 'both'
}

export default function FileExplorerDialog({
  open,
  onClose,
  onSelect,
  title = 'Select Directory',
  initialPath = '/',
  multiSelect = false,
  connectionType = 'local',
  sshConfig,
  selectMode = 'directories',
}: FileExplorerDialogProps) {
  const [currentPath, setCurrentPath] = useState(initialPath)
  const [items, setItems] = useState<FileSystemItem[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [selectedPaths, setSelectedPaths] = useState<string[]>([])
  const [searchTerm, setSearchTerm] = useState('')

  useEffect(() => {
    if (open) {
      loadDirectory(initialPath)
      setSelectedPaths([])
    }
  }, [open, initialPath])

  const loadDirectory = async (path: string) => {
    setLoading(true)
    setError(null)

    try {
      const params: any = {
        path,
        connection_type: connectionType,
      }

      if (connectionType === 'ssh' && sshConfig) {
        params.ssh_key_id = sshConfig.ssh_key_id
        params.host = sshConfig.host
        params.username = sshConfig.username
        params.port = sshConfig.port
      }

      const response = await api.get('/filesystem/browse', { params })
      setItems(response.data.items || [])
      setCurrentPath(response.data.current_path)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load directory')
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const handleItemClick = (item: FileSystemItem) => {
    if (item.is_directory) {
      loadDirectory(item.path)
    }
  }

  const handleItemSelect = (item: FileSystemItem) => {
    // Check if item type matches selectMode
    if (selectMode === 'directories' && !item.is_directory) return
    if (selectMode === 'files' && item.is_directory) return

    if (multiSelect) {
      setSelectedPaths(prev =>
        prev.includes(item.path)
          ? prev.filter(p => p !== item.path)
          : [...prev, item.path]
      )
    } else {
      setSelectedPaths([item.path])
    }
  }

  const handleBreadcrumbClick = (path: string) => {
    loadDirectory(path)
  }

  const handleConfirm = () => {
    onSelect(selectedPaths)
    onClose()
  }

  const handleSelectCurrent = () => {
    onSelect([currentPath])
    onClose()
  }

  const getBreadcrumbs = () => {
    const parts = currentPath.split('/').filter(Boolean)
    const breadcrumbs: { label: string; path: string }[] = [
      { label: 'Root', path: '/' },
    ]

    let accumulatedPath = ''
    parts.forEach(part => {
      accumulatedPath += `/${part}`
      breadcrumbs.push({ label: part, path: accumulatedPath })
    })

    return breadcrumbs
  }

  const formatFileSize = (bytes?: number) => {
    if (!bytes) return '-'
    const units = ['B', 'KB', 'MB', 'GB', 'TB']
    let size = bytes
    let unitIndex = 0
    while (size >= 1024 && unitIndex < units.length - 1) {
      size /= 1024
      unitIndex++
    }
    return `${size.toFixed(1)} ${units[unitIndex]}`
  }

  const filteredItems = items.filter(item =>
    item.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6">{title}</Typography>
          {connectionType === 'ssh' && sshConfig && (
            <Chip
              label={`${sshConfig.username}@${sshConfig.host}`}
              size="small"
              color="primary"
              variant="outlined"
            />
          )}
        </Box>
      </DialogTitle>

      <DialogContent dividers>
        {/* Breadcrumb Navigation */}
        <Box mb={2}>
          <Breadcrumbs separator={<ChevronRight size={16} />} maxItems={6}>
            {getBreadcrumbs().map((crumb, index) => (
              <Link
                key={index}
                component="button"
                variant="body2"
                onClick={() => handleBreadcrumbClick(crumb.path)}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' },
                }}
              >
                {index === 0 && <Home size={16} />}
                {crumb.label}
              </Link>
            ))}
          </Breadcrumbs>
        </Box>

        {/* Search */}
        <TextField
          fullWidth
          size="small"
          placeholder="Search files and folders..."
          value={searchTerm}
          onChange={e => setSearchTerm(e.target.value)}
          InputProps={{
            startAdornment: (
              <InputAdornment position="start">
                <Search size={18} />
              </InputAdornment>
            ),
          }}
          sx={{ mb: 2 }}
        />

        {/* Error Display */}
        {error && (
          <Alert severity="error" sx={{ mb: 2 }}>
            {error}
          </Alert>
        )}

        {/* Loading State */}
        {loading ? (
          <Box display="flex" justifyContent="center" py={4}>
            <CircularProgress />
          </Box>
        ) : (
          <>
            {/* File List */}
            <List sx={{ maxHeight: 400, overflow: 'auto' }}>
              {filteredItems.length === 0 ? (
                <ListItem>
                  <ListItemText
                    primary="No items found"
                    secondary={searchTerm ? 'Try a different search term' : 'This directory is empty'}
                  />
                </ListItem>
              ) : (
                filteredItems.map(item => {
                  const isSelectable =
                    (selectMode === 'directories' && item.is_directory) ||
                    (selectMode === 'files' && !item.is_directory) ||
                    selectMode === 'both'

                  const isSelected = selectedPaths.includes(item.path)

                  return (
                    <ListItem
                      key={item.path}
                      disablePadding
                      secondaryAction={
                        isSelectable && multiSelect ? (
                          <Checkbox
                            edge="end"
                            checked={isSelected}
                            onChange={() => handleItemSelect(item)}
                          />
                        ) : null
                      }
                    >
                      <ListItemButton
                        onClick={() =>
                          item.is_directory
                            ? handleItemClick(item)
                            : isSelectable && handleItemSelect(item)
                        }
                        selected={isSelected && !multiSelect}
                      >
                        <ListItemIcon>
                          {item.is_borg_repo ? (
                            <Archive size={20} color="#ff6b6b" />
                          ) : item.is_directory ? (
                            <Folder size={20} color="#4A90E2" />
                          ) : (
                            <File size={20} color="#666" />
                          )}
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={1}>
                              <Typography variant="body2">{item.name}</Typography>
                              {item.is_borg_repo && (
                                <Chip
                                  label="Borg Repo"
                                  size="small"
                                  color="warning"
                                  sx={{ height: 20, fontSize: '0.7rem' }}
                                />
                              )}
                            </Box>
                          }
                          secondary={
                            <Box display="flex" gap={2} mt={0.5}>
                              {!item.is_directory && item.size && (
                                <Typography variant="caption" color="text.secondary">
                                  {formatFileSize(item.size)}
                                </Typography>
                              )}
                              {item.modified && (
                                <Typography variant="caption" color="text.secondary">
                                  {new Date(item.modified).toLocaleDateString()}
                                </Typography>
                              )}
                              {item.permissions && (
                                <Typography variant="caption" color="text.secondary">
                                  {item.permissions}
                                </Typography>
                              )}
                            </Box>
                          }
                        />
                      </ListItemButton>
                    </ListItem>
                  )
                })
              )}
            </List>

            {/* Info Box */}
            {multiSelect && selectedPaths.length > 0 && (
              <Alert severity="info" sx={{ mt: 2 }}>
                {selectedPaths.length} item(s) selected
              </Alert>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        {selectMode === 'directories' && (
          <Button onClick={handleSelectCurrent} variant="outlined">
            Select Current Directory
          </Button>
        )}
        <Button
          onClick={handleConfirm}
          variant="contained"
          disabled={selectedPaths.length === 0}
        >
          Select {multiSelect && selectedPaths.length > 0 ? `(${selectedPaths.length})` : ''}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
