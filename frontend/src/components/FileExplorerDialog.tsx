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
  useTheme,
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
  const theme = useTheme()
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
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth PaperProps={{ sx: { height: '75vh' } }}>
      <DialogTitle sx={{ pb: 1, pt: 2 }}>
        <Box display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="h6" fontWeight={600}>{title}</Typography>
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

      <DialogContent sx={{ p: 0 }}>
        {/* Breadcrumb Navigation */}
        <Box sx={{ px: 2, py: 1, bgcolor: 'background.default', borderBottom: 1, borderColor: 'divider' }}>
          <Breadcrumbs
            separator={<ChevronRight size={12} />}
            maxItems={6}
            sx={{ '& .MuiBreadcrumbs-separator': { mx: 0.25 } }}
          >
            {getBreadcrumbs().map((crumb, index) => (
              <Link
                key={index}
                component="button"
                variant="caption"
                onClick={() => handleBreadcrumbClick(crumb.path)}
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.25,
                  textDecoration: 'none',
                  color: 'text.primary',
                  fontWeight: index === getBreadcrumbs().length - 1 ? 600 : 400,
                  '&:hover': {
                    textDecoration: 'underline',
                    color: 'primary.main'
                  },
                }}
              >
                {index === 0 && <Home size={12} />}
                {crumb.label}
              </Link>
            ))}
          </Breadcrumbs>
        </Box>

        {/* Search */}
        <Box sx={{ px: 2, py: 1 }}>
          <TextField
            fullWidth
            size="small"
            placeholder="Search..."
            value={searchTerm}
            onChange={e => setSearchTerm(e.target.value)}
            InputProps={{
              startAdornment: (
                <InputAdornment position="start">
                  <Search size={16} />
                </InputAdornment>
              ),
            }}
            sx={{
              '& .MuiOutlinedInput-root': {
                bgcolor: 'background.paper',
              },
              '& .MuiOutlinedInput-input': {
                py: 0.75,
              }
            }}
          />
        </Box>

        {/* Error Display */}
        {error && (
          <Box sx={{ px: 2, pb: 1 }}>
            <Alert severity="error" sx={{ borderRadius: 1, py: 0.5 }}>
              {error}
            </Alert>
          </Box>
        )}

        {/* Loading State */}
        {loading ? (
          <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" py={4}>
            <CircularProgress size={32} />
            <Typography variant="caption" color="text.secondary" mt={1.5}>
              Loading...
            </Typography>
          </Box>
        ) : (
          <>
            {/* File List */}
            <List
              sx={{
                flex: 1,
                overflow: 'auto',
                px: 0.5,
                py: 0,
              }}
            >
              {filteredItems.length === 0 ? (
                <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" py={4} sx={{ color: 'text.secondary' }}>
                  <Folder size={36} />
                  <Typography variant="body2" color="text.secondary" mt={1.5}>
                    No items found
                  </Typography>
                  <Typography variant="caption" color="text.disabled">
                    {searchTerm ? 'Try a different search' : 'Empty directory'}
                  </Typography>
                </Box>
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
                            size="small"
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
                        sx={{
                          py: 0.5,
                          px: 1.5,
                          '&:hover': {
                            bgcolor: 'action.hover',
                          },
                          '&.Mui-selected': {
                            bgcolor: 'primary.50',
                            '&:hover': {
                              bgcolor: 'primary.100',
                            }
                          }
                        }}
                      >
                        <ListItemIcon sx={{ minWidth: 32 }}>
                          {item.is_borg_repo ? (
                            <Archive size={18} color="#ff6b6b" />
                          ) : item.is_directory ? (
                            <Folder size={18} color={theme.palette.mode === 'dark' ? theme.palette.text.primary : '#4A90E2'} />
                          ) : (
                            <File size={18} color="#999" />
                          )}
                        </ListItemIcon>
                        <ListItemText
                          primary={
                            <Box display="flex" alignItems="center" gap={0.75}>
                              <Typography variant="body2">
                                {item.name}
                              </Typography>
                              {item.is_borg_repo && (
                                <Chip
                                  label="Borg"
                                  size="small"
                                  color="warning"
                                  sx={{ height: 16, fontSize: '0.6rem', fontWeight: 600 }}
                                />
                              )}
                              {!item.is_directory && item.size && (
                                <Typography variant="caption" color="text.disabled" sx={{ ml: 'auto' }}>
                                  {formatFileSize(item.size)}
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
              <Box sx={{ px: 2, py: 1, bgcolor: 'primary.50', borderTop: 1, borderColor: 'divider' }}>
                <Typography variant="caption" color="primary.main" fontWeight={600}>
                  {selectedPaths.length} selected
                </Typography>
              </Box>
            )}
          </>
        )}
      </DialogContent>

      <DialogActions sx={{ px: 2, py: 1.5, borderTop: 1, borderColor: 'divider' }}>
        <Button onClick={onClose} size="small" sx={{ color: 'text.secondary' }}>
          Cancel
        </Button>
        <Box sx={{ flex: 1 }} />
        {selectMode === 'directories' && (
          <Button onClick={handleSelectCurrent} variant="outlined" size="small" sx={{ mr: 1 }}>
            Use Current
          </Button>
        )}
        <Button
          onClick={handleConfirm}
          variant="contained"
          size="small"
          disabled={selectedPaths.length === 0}
        >
          Select {multiSelect && selectedPaths.length > 0 ? `(${selectedPaths.length})` : ''}
        </Button>
      </DialogActions>
    </Dialog>
  )
}
