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
  useMediaQuery,
  useTheme,
} from '@mui/material'
import { File, ChevronRight, Home, Search, Archive, HardDrive, FolderPlus } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'
import api from '../services/api'
import { sshKeysAPI } from '../services/api'

interface FileSystemItem {
  name: string
  path: string
  is_directory: boolean
  size?: number
  modified?: string
  is_borg_repo: boolean
  is_local_mount?: boolean // Local host filesystem mount
  is_mount_point?: boolean // SSH mount point
  ssh_connection?: SSHConnection
  permissions?: string
}

interface SSHConnection {
  id: number
  ssh_key_id: number
  host: string
  username: string
  port: number
  default_path?: string
  mount_point?: string
  status: string
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
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])

  // Track current browsing mode (can switch from local to ssh when clicking mount points)
  const [activeConnectionType, setActiveConnectionType] = useState(connectionType)
  const [activeSshConfig, setActiveSshConfig] = useState(sshConfig)
  const [isInsideLocalMount, setIsInsideLocalMount] = useState(false)

  // Create folder dialog
  const [showCreateFolder, setShowCreateFolder] = useState(false)
  const [newFolderName, setNewFolderName] = useState('')
  const [creatingFolder, setCreatingFolder] = useState(false)

  // Responsive dialog
  const theme = useTheme()
  const fullScreen = useMediaQuery(theme.breakpoints.down('md'))

  useEffect(() => {
    if (open) {
      // Reset to initial state when dialog opens
      setCurrentPath(initialPath)
      setActiveConnectionType(connectionType)
      setActiveSshConfig(sshConfig)
      setSelectedPaths([])
      setSearchTerm('')
      setError(null)

      // Load the initial directory
      loadDirectory(initialPath)

      // Load SSH connections to show mount points
      if (connectionType === 'local') {
        loadSSHConnections()
      }
    }
  }, [open, initialPath, connectionType, sshConfig])

  const loadSSHConnections = async () => {
    try {
      const response = await sshKeysAPI.getSSHConnections()
      const connections = response.data?.connections || []
      // Show all connected SSH connections (mount point is optional)
      setSshConnections(connections.filter((conn: SSHConnection) => conn.status === 'connected'))
    } catch (err) {
      // Silently fail - mount points are optional
      console.error('Failed to load SSH connections:', err)
      setSshConnections([])
    }
  }

  const loadDirectory = async (path: string, conn?: 'local' | 'ssh', config?: any) => {
    setLoading(true)
    setError(null)

    // Update state if new connection params provided
    if (conn !== undefined) {
      setActiveConnectionType(conn)
    }
    if (config !== undefined) {
      setActiveSshConfig(config)
    }

    const useConnectionType = conn !== undefined ? conn : activeConnectionType
    const useSshConfig = config !== undefined ? config : activeSshConfig

    try {
      const params: any = {
        path,
        connection_type: useConnectionType,
      }

      if (useConnectionType === 'ssh' && useSshConfig) {
        params.ssh_key_id = useSshConfig.ssh_key_id
        params.host = useSshConfig.host
        params.username = useSshConfig.username
        params.port = useSshConfig.port
      }

      const response = await api.get('/filesystem/browse', { params })
      setItems(response.data.items || [])
      setCurrentPath(response.data.current_path)
      setIsInsideLocalMount(response.data.is_inside_local_mount || false)
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Failed to load directory')
      setItems([])
    } finally {
      setLoading(false)
    }
  }

  const handleItemClick = (item: FileSystemItem) => {
    if (item.is_mount_point && item.ssh_connection) {
      // Switch to SSH browsing mode for this mount point
      const sshCfg = {
        ssh_key_id: item.ssh_connection.ssh_key_id,
        host: item.ssh_connection.host,
        username: item.ssh_connection.username,
        port: item.ssh_connection.port,
      }
      const startPath = item.ssh_connection.default_path || '/'
      loadDirectory(startPath, 'ssh', sshCfg)
    } else if (item.is_directory) {
      loadDirectory(item.path)
    }
  }

  const handleItemSelect = (item: FileSystemItem) => {
    // Check if item type matches selectMode
    if (selectMode === 'directories' && !item.is_directory) return
    if (selectMode === 'files' && item.is_directory) return

    if (multiSelect) {
      setSelectedPaths((prev) =>
        prev.includes(item.path) ? prev.filter((p) => p !== item.path) : [...prev, item.path]
      )
    } else {
      setSelectedPaths([item.path])
    }
  }

  const handleBreadcrumbClick = (path: string) => {
    // If clicking root while in SSH mode from mount point, go back to local
    if (path === '/' && activeConnectionType === 'ssh' && connectionType === 'local') {
      setActiveConnectionType('local')
      setActiveSshConfig(undefined)
      loadDirectory('/', 'local', undefined)
    } else {
      loadDirectory(path)
    }
  }

  const handleConfirm = () => {
    // Convert paths to SSH URL format if browsing via mount point
    const paths = selectedPaths.map((path) => {
      if (activeConnectionType === 'ssh' && activeSshConfig && connectionType === 'local') {
        // We're browsing a mount point - convert to SSH URL
        return `ssh://${activeSshConfig.username}@${activeSshConfig.host}:${activeSshConfig.port}${path}`
      }
      return path
    })
    onSelect(paths)
    onClose()
  }

  const handleSelectCurrent = () => {
    // Convert path to SSH URL format if browsing via mount point
    let path = currentPath
    if (activeConnectionType === 'ssh' && activeSshConfig && connectionType === 'local') {
      // We're browsing a mount point - convert to SSH URL
      path = `ssh://${activeSshConfig.username}@${activeSshConfig.host}:${activeSshConfig.port}${currentPath}`
    }
    onSelect([path])
    onClose()
  }

  const handleCreateFolder = async () => {
    if (!newFolderName.trim()) return

    setCreatingFolder(true)
    try {
      const params: any = {
        path: currentPath,
        folder_name: newFolderName.trim(),
        connection_type: activeConnectionType,
      }

      if (activeConnectionType === 'ssh' && activeSshConfig) {
        params.ssh_key_id = activeSshConfig.ssh_key_id
        params.host = activeSshConfig.host
        params.username = activeSshConfig.username
        params.port = activeSshConfig.port
      }

      await api.post('/filesystem/create-folder', params)

      // Refresh directory
      await loadDirectory(currentPath)

      // Close dialog and reset
      setShowCreateFolder(false)
      setNewFolderName('')
      setError(null)
    } catch (err: any) {
      console.error('Failed to create folder:', err)
      const errorMessage = err.response?.data?.detail || err.message || 'Failed to create folder'
      // Handle validation errors from FastAPI
      if (typeof errorMessage === 'object') {
        setError(JSON.stringify(errorMessage))
      } else {
        setError(errorMessage)
      }
    } finally {
      setCreatingFolder(false)
    }
  }

  const getBreadcrumbs = () => {
    const parts = currentPath.split('/').filter(Boolean)
    const breadcrumbs: { label: string; path: string }[] = [{ label: 'Root', path: '/' }]

    let accumulatedPath = ''
    parts.forEach((part) => {
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

  // Add mount points as virtual items at root level
  const getMountPointItems = (): FileSystemItem[] => {
    if (currentPath !== '/' || activeConnectionType !== 'local') return []
    return sshConnections.map((conn) => {
      // Use mount_point name if available, otherwise show full SSH URL
      const displayName =
        conn.mount_point && conn.mount_point.trim()
          ? conn.mount_point
          : `ssh://${conn.username}@${conn.host}:${conn.port}${conn.default_path || '/'}`

      return {
        name: displayName,
        path: `ssh://${conn.username}@${conn.host}:${conn.port}${conn.default_path || '/'}`,
        is_directory: true,
        is_borg_repo: false,
        is_mount_point: true,
        ssh_connection: conn,
      }
    })
  }

  const allItems = [...getMountPointItems(), ...items]
  const filteredItems = allItems.filter((item) =>
    item.name.toLowerCase().includes(searchTerm.toLowerCase())
  )

  return (
    <>
      <Dialog
        open={open}
        onClose={onClose}
        maxWidth="md"
        fullWidth
        fullScreen={fullScreen}
        PaperProps={{ sx: { height: fullScreen ? '100%' : '75vh' } }}
      >
        <DialogTitle sx={{ pb: 1, pt: 2 }}>
          <Box display="flex" alignItems="center" justifyContent="space-between">
            <Typography variant="h6" fontWeight={600}>
              {title}
            </Typography>
            {activeConnectionType === 'ssh' && activeSshConfig ? (
              <Chip
                label={`${activeSshConfig.username}@${activeSshConfig.host}`}
                size="small"
                color="primary"
                variant="outlined"
              />
            ) : isInsideLocalMount && activeConnectionType === 'local' ? (
              <Chip
                icon={<HardDrive size={14} />}
                label="Host"
                size="small"
                color="primary"
                variant="outlined"
              />
            ) : null}
          </Box>
        </DialogTitle>

        <DialogContent sx={{ p: 0 }}>
          {/* Breadcrumb Navigation */}
          <Box
            sx={{
              px: 2,
              py: 1,
              bgcolor: 'background.default',
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
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
                      color: 'primary.main',
                    },
                  }}
                >
                  {index === 0 && <Home size={12} />}
                  {crumb.label}
                </Link>
              ))}
            </Breadcrumbs>
          </Box>

          {/* Search and Create Folder */}
          <Box sx={{ px: 2, py: 1, display: 'flex', gap: 1 }}>
            <TextField
              fullWidth
              size="small"
              placeholder="Search..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
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
                },
              }}
            />
            <Button
              variant="outlined"
              size="small"
              startIcon={<FolderPlus size={16} />}
              onClick={() => setShowCreateFolder(true)}
              sx={{
                flexShrink: 0,
                whiteSpace: 'nowrap',
                height: '35px',
                minHeight: '35px',
              }}
            >
              New Folder
            </Button>
          </Box>

          {/* Error Display */}
          {error && (
            <Box sx={{ px: 2, pb: 1 }}>
              <Alert severity="error" sx={{ borderRadius: 1, py: 0.5 }}>
                {error}
              </Alert>
            </Box>
          )}

          {/* Mount Point Info */}
          {currentPath === '/' && activeConnectionType === 'local' && sshConnections.length > 0 && (
            <Box sx={{ px: 2, pb: 1 }}>
              <Alert severity="info" sx={{ borderRadius: 1, py: 0.5 }}>
                <Typography variant="caption">
                  💡 SSH connections are shown below. Configure mount points in SSH Keys page for
                  cleaner display names.
                </Typography>
              </Alert>
            </Box>
          )}

          {/* Loading State */}
          {loading ? (
            <Box
              display="flex"
              flexDirection="column"
              alignItems="center"
              justifyContent="center"
              py={4}
            >
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
                  <Box
                    display="flex"
                    flexDirection="column"
                    alignItems="center"
                    justifyContent="center"
                    py={4}
                    sx={{ color: 'text.secondary' }}
                  >
                    <FolderOpenIcon sx={{ fontSize: 36 }} />
                    <Typography variant="body2" color="text.secondary" mt={1.5}>
                      No items found
                    </Typography>
                    <Typography variant="caption" color="text.disabled">
                      {searchTerm ? 'Try a different search' : 'Empty directory'}
                    </Typography>
                  </Box>
                ) : (
                  filteredItems.map((item) => {
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
                              },
                            },
                          }}
                        >
                          <ListItemIcon sx={{ minWidth: 32 }}>
                            {item.is_mount_point ? (
                              <HardDrive size={18} color="#10b981" />
                            ) : item.is_local_mount ? (
                              <HardDrive size={18} color="#6366f1" />
                            ) : item.is_borg_repo ? (
                              <Archive size={18} color="#ff6b6b" />
                            ) : item.is_directory ? (
                              <FolderOpenIcon sx={{ fontSize: 18, color: '#2563eb' }} />
                            ) : (
                              <File size={18} color="#999" />
                            )}
                          </ListItemIcon>
                          <ListItemText
                            primary={
                              <Box display="flex" alignItems="center" gap={0.75}>
                                <Typography variant="body2">{item.name}</Typography>
                                {item.is_mount_point && (
                                  <Chip
                                    label="Remote"
                                    size="small"
                                    color="success"
                                    sx={{ height: 16, fontSize: '0.6rem', fontWeight: 600 }}
                                  />
                                )}
                                {item.is_local_mount && (
                                  <Chip
                                    label="Host"
                                    size="small"
                                    color="primary"
                                    sx={{ height: 16, fontSize: '0.6rem', fontWeight: 600 }}
                                  />
                                )}
                                {item.is_borg_repo && (
                                  <Chip
                                    label="Borg"
                                    size="small"
                                    color="warning"
                                    sx={{ height: 16, fontSize: '0.6rem', fontWeight: 600 }}
                                  />
                                )}
                                {!item.is_directory && item.size && (
                                  <Typography
                                    variant="caption"
                                    color="text.disabled"
                                    sx={{ ml: 'auto' }}
                                  >
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
                <Box
                  sx={{ px: 2, py: 1, bgcolor: 'primary.50', borderTop: 1, borderColor: 'divider' }}
                >
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

      {/* Create Folder Dialog */}
      <Dialog
        open={showCreateFolder}
        onClose={() => !creatingFolder && setShowCreateFolder(false)}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>Create New Folder</DialogTitle>
        <DialogContent>
          <TextField
            autoFocus
            fullWidth
            label="Folder Name"
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter' && newFolderName.trim()) {
                handleCreateFolder()
              }
            }}
            placeholder="Enter folder name"
            margin="dense"
            disabled={creatingFolder}
          />
          {error && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {error}
            </Alert>
          )}
        </DialogContent>

        <DialogActions>
          <Button
            onClick={() => {
              setShowCreateFolder(false)
              setNewFolderName('')
              setError(null)
            }}
            disabled={creatingFolder}
          >
            Cancel
          </Button>
          <Button
            onClick={handleCreateFolder}
            variant="contained"
            disabled={!newFolderName.trim() || creatingFolder}
          >
            {creatingFolder ? 'Creating...' : 'Create'}
          </Button>
        </DialogActions>
      </Dialog>
    </>
  )
}
