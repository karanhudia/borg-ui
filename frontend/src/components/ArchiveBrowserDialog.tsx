import React, { useState, useEffect } from 'react'
import { Link as RouterLink } from 'react-router-dom'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Box,
  Typography,
  List,
  ListItem,
  ListItemButton,
  ListItemIcon,
  ListItemText,
  Breadcrumbs,
  Link,
  CircularProgress,
  Alert,
  AlertTitle,
  Chip,
  Stack,
  IconButton,
  Tooltip,
} from '@mui/material'
import { Folder, File, ChevronRight, Home, CheckSquare, Square, MinusSquare } from 'lucide-react'
import { restoreAPI } from '../services/api'
import { toast } from 'react-hot-toast'

interface ArchiveItem {
  name: string
  type: 'file' | 'directory'
  path: string
  size?: number
}

interface ArchiveBrowserDialogProps {
  open: boolean
  onClose: () => void
  repositoryId: number
  archiveName: string
  onSelect: (paths: string[]) => void
  initialSelectedPaths?: string[]
}

const ArchiveBrowserDialog: React.FC<ArchiveBrowserDialogProps> = ({
  open,
  onClose,
  repositoryId,
  archiveName,
  onSelect,
  initialSelectedPaths = [],
}) => {
  const [currentPath, setCurrentPath] = useState<string>('')
  const [items, setItems] = useState<ArchiveItem[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const [isSizeLimitError, setIsSizeLimitError] = useState<boolean>(false)
  const [selectedPaths, setSelectedPaths] = useState<Set<string>>(new Set(initialSelectedPaths))

  // Fetch archive contents for current path
  useEffect(() => {
    if (!open) return

    const fetchContents = async () => {
      setLoading(true)
      setError(null)
      setIsSizeLimitError(false)

      try {
        const response = await restoreAPI.getArchiveContents(repositoryId, archiveName, currentPath)
        setItems(response.data.items || [])
      } catch (err: any) {
        const errorMsg = err.response?.data?.detail || 'Failed to load archive contents'
        const statusCode = err.response?.status
        setError(errorMsg)
        setIsSizeLimitError(statusCode === 413)
        toast.error(errorMsg)
      } finally {
        setLoading(false)
      }
    }

    fetchContents()
  }, [open, repositoryId, archiveName, currentPath])

  // Parse breadcrumb path
  const pathParts = currentPath ? currentPath.split('/').filter(Boolean) : []

  // Handle item click (navigate into folder or toggle file selection)
  const handleItemClick = (item: ArchiveItem) => {
    if (item.type === 'directory') {
      setCurrentPath(item.path)
    } else {
      toggleSelection(item.path)
    }
  }

  // Toggle path selection
  const toggleSelection = (path: string) => {
    const newSelected = new Set(selectedPaths)
    if (newSelected.has(path)) {
      newSelected.delete(path)
    } else {
      newSelected.add(path)
    }
    setSelectedPaths(newSelected)
  }

  // Check if path or any parent is selected
  const isSelected = (path: string): boolean => {
    if (selectedPaths.has(path)) return true

    // Check if any parent directory is selected
    const parts = path.split('/')
    for (let i = 1; i < parts.length; i++) {
      const parentPath = parts.slice(0, i).join('/')
      if (selectedPaths.has(parentPath)) return true
    }

    return false
  }

  // Check if path has some children selected (for indeterminate checkbox)
  const hasPartialSelection = (dirPath: string): boolean => {
    if (selectedPaths.has(dirPath)) return false // Fully selected, not partial

    // Check if any selected path starts with this directory
    for (const selected of selectedPaths) {
      if (selected.startsWith(dirPath + '/')) {
        return true
      }
    }
    return false
  }

  // Navigate to specific path
  const navigateToPath = (index: number) => {
    if (index === -1) {
      setCurrentPath('')
    } else {
      const newPath = pathParts.slice(0, index + 1).join('/')
      setCurrentPath(newPath)
    }
  }

  // Select all visible items
  const selectAllVisible = () => {
    const newSelected = new Set(selectedPaths)
    items.forEach((item) => {
      newSelected.add(item.path)
    })
    setSelectedPaths(newSelected)
  }

  // Clear all selections
  const clearSelection = () => {
    setSelectedPaths(new Set())
  }

  // Handle confirm
  const handleConfirm = () => {
    const pathsArray = Array.from(selectedPaths)
    onSelect(pathsArray)
    onClose()
  }

  // Format file size
  const formatBytes = (bytes?: number): string => {
    if (bytes === undefined || bytes === null) return ''
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    if (bytes === 0) return '0 B'
    const i = Math.floor(Math.log(bytes) / Math.log(1024))
    return Math.round((bytes / Math.pow(1024, i)) * 100) / 100 + ' ' + sizes[i]
  }

  // Get checkbox icon based on selection state
  const getCheckboxIcon = (item: ArchiveItem) => {
    if (item.type === 'directory') {
      const selected = isSelected(item.path)
      const partial = hasPartialSelection(item.path)
      if (selected) return <CheckSquare size={20} />
      if (partial) return <MinusSquare size={20} />
      return <Square size={20} />
    }
    return isSelected(item.path) ? <CheckSquare size={20} /> : <Square size={20} />
  }

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          bgcolor: 'background.paper',
        },
      }}
    >
      <DialogTitle>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Browse Archive
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {archiveName}
            </Typography>
          </Box>
          <Stack direction="row" spacing={1}>
            <Chip
              label={`${selectedPaths.size} selected`}
              color={selectedPaths.size > 0 ? 'primary' : 'default'}
              size="small"
            />
          </Stack>
        </Stack>
      </DialogTitle>

      <DialogContent
        dividers
        sx={{
          height: 500,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {/* Breadcrumbs */}
        <Box sx={{ mb: 2, flexShrink: 0 }}>
          <Breadcrumbs separator={<ChevronRight size={16} />}>
            <Link
              component="button"
              variant="body2"
              onClick={() => navigateToPath(-1)}
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 0.5,
                cursor: 'pointer',
                textDecoration: 'none',
                '&:hover': { textDecoration: 'underline' },
              }}
            >
              <Home size={16} />
              Root
            </Link>
            {pathParts.map((part, index) => (
              <Link
                key={index}
                component="button"
                variant="body2"
                onClick={() => navigateToPath(index)}
                sx={{
                  cursor: 'pointer',
                  textDecoration: 'none',
                  '&:hover': { textDecoration: 'underline' },
                }}
              >
                {part}
              </Link>
            ))}
          </Breadcrumbs>
        </Box>

        {/* Action buttons */}
        <Stack direction="row" spacing={1} sx={{ mb: 2, flexShrink: 0 }}>
          <Button size="small" variant="outlined" onClick={selectAllVisible} disabled={loading}>
            Select All Visible
          </Button>
          <Button
            size="small"
            variant="outlined"
            onClick={clearSelection}
            disabled={selectedPaths.size === 0 || loading}
          >
            Clear Selection
          </Button>
        </Stack>

        {/* Info alert */}
        <Alert severity="info" sx={{ mb: 2, flexShrink: 0 }}>
          <Typography variant="body2">
            Select specific files or folders to restore. Click folders to browse, click checkboxes
            to select. If no selection is made, the entire archive will be restored.
          </Typography>
        </Alert>

        {/* Items list - takes remaining space */}
        <Box sx={{ flexGrow: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
          {loading ? (
            <Box
              sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', flexGrow: 1 }}
            >
              <CircularProgress />
            </Box>
          ) : error ? (
            <Alert severity="error">
              {isSizeLimitError ? (
                <>
                  <AlertTitle>Archive Too Large</AlertTitle>
                  This archive contains too many files to browse safely in the UI.
                  <Box sx={{ mt: 1 }}>
                    You can increase the limit in{' '}
                    <Link component={RouterLink} to="/settings/system" onClick={onClose}>
                      Settings &gt; System
                    </Link>
                    , or use command-line tools like <code>borg mount</code> for very large
                    archives.
                  </Box>
                </>
              ) : (
                error
              )}
            </Alert>
          ) : items.length === 0 ? (
            <Alert severity="info">This directory is empty</Alert>
          ) : (
            <List sx={{ flexGrow: 1, overflow: 'auto' }}>
              {items.map((item) => (
                <ListItem key={item.path} disablePadding>
                  <ListItemButton
                    onClick={() => handleItemClick(item)}
                    sx={{
                      '&:hover': {
                        bgcolor: 'action.hover',
                      },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      <Tooltip title={isSelected(item.path) ? 'Selected' : 'Not selected'}>
                        <IconButton
                          size="small"
                          onClick={(e) => {
                            e.stopPropagation()
                            toggleSelection(item.path)
                          }}
                          sx={{ p: 0 }}
                        >
                          {getCheckboxIcon(item)}
                        </IconButton>
                      </Tooltip>
                    </ListItemIcon>
                    <ListItemIcon sx={{ minWidth: 40 }}>
                      {item.type === 'directory' ? (
                        <Folder size={20} color="#1976d2" />
                      ) : (
                        <File size={20} color="#666" />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={
                        <Typography
                          variant="body2"
                          fontWeight={item.type === 'directory' ? 500 : 400}
                        >
                          {item.name}
                        </Typography>
                      }
                      secondary={formatBytes(item.size)}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          )}
        </Box>
      </DialogContent>

      <DialogActions>
        <Button onClick={onClose}>Cancel</Button>
        <Button variant="contained" color="primary" onClick={handleConfirm}>
          {selectedPaths.size > 0
            ? `Continue with ${selectedPaths.size} selected`
            : 'Continue (Restore All)'}
        </Button>
      </DialogActions>
    </Dialog>
  )
}

export default ArchiveBrowserDialog
