import { useState, useEffect } from 'react'
import {
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
  Chip,
  IconButton,
  Tooltip,
  alpha,
} from '@mui/material'
import { Folder, File, ChevronRight, Home, CheckSquare, Square, MinusSquare } from 'lucide-react'
import { BorgApiClient, type Repository } from '../../services/borgApi/client'
import type { Archive } from '../../types'
import { useTranslation } from 'react-i18next'
import { translateBackendKey } from '../../utils/translateBackendKey'
import type { RestorePathMetadata } from '../../utils/restorePaths'

interface ArchiveItem {
  name: string
  type: 'file' | 'directory'
  path: string
  size?: number
}

export interface RestoreFilesStepData {
  selectedPaths: string[]
  selectedItems?: RestorePathMetadata[]
}

interface WizardStepRestoreFilesProps {
  repository: Repository
  archive: Pick<Archive, 'id' | 'name'>
  data: RestoreFilesStepData
  onChange: (data: Partial<RestoreFilesStepData>) => void
}

export default function WizardStepRestoreFiles({
  repository,
  archive,
  data,
  onChange,
}: WizardStepRestoreFilesProps) {
  const { t } = useTranslation()
  const [currentPath, setCurrentPath] = useState<string>('')
  const [items, setItems] = useState<ArchiveItem[]>([])
  const [loading, setLoading] = useState<boolean>(false)
  const [error, setError] = useState<string | null>(null)
  const selectedPaths = new Set(data.selectedPaths || [])
  const selectedItems = data.selectedItems || []

  // Fetch archive contents for current path
  useEffect(() => {
    const fetchContents = async () => {
      setLoading(true)
      setError(null)

      try {
        const response = await new BorgApiClient(repository).getArchiveContents(
          archive.id,
          archive.name,
          currentPath
        )
        setItems(response.data.items || [])
      } catch (err: unknown) {
        const error = err as { response?: { data?: { detail?: string } } }
        const errorMsg =
          translateBackendKey(error.response?.data?.detail) ||
          t('wizard.restoreFiles.failedToLoadContents')
        setError(errorMsg)
      } finally {
        setLoading(false)
      }
    }

    fetchContents()
  }, [repository, archive, currentPath, t])

  // Parse breadcrumb path
  const pathParts = currentPath ? currentPath.split('/').filter(Boolean) : []

  // Handle item click
  const handleItemClick = (item: ArchiveItem) => {
    if (item.type === 'directory') {
      setCurrentPath(item.path)
    } else {
      toggleSelection(item)
    }
  }

  // Toggle path selection
  const toggleSelection = (item: ArchiveItem) => {
    const path = item.path
    const newPaths = new Set(selectedPaths)
    let newItems = selectedItems.filter((selectedItem) => selectedItem.path !== path)

    if (newPaths.has(path)) {
      newPaths.delete(path)
    } else {
      newPaths.add(path)
      newItems = [...newItems, { path, type: item.type }]
    }

    onChange({ selectedPaths: Array.from(newPaths), selectedItems: newItems })
  }

  // Navigate to path
  const navigateToPath = (targetPath: string) => {
    setCurrentPath(targetPath)
  }

  // Format file size
  const formatSize = (bytes?: number): string => {
    if (!bytes) return '0 B'
    const k = 1024
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
    const i = Math.floor(Math.log(bytes) / Math.log(k))
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`
  }

  // Check if path or any parent is selected
  const isSelected = (path: string): boolean => {
    return selectedPaths.has(path)
  }

  // Check if any children are selected
  const hasSelectedChildren = (dirPath: string): boolean => {
    return Array.from(selectedPaths).some((p) => p.startsWith(dirPath + '/'))
  }

  // Get selection icon for directory
  const getDirectoryIcon = (item: ArchiveItem) => {
    if (isSelected(item.path)) {
      return <CheckSquare size={20} color="#1976d2" />
    } else if (hasSelectedChildren(item.path)) {
      return <MinusSquare size={20} color="#1976d2" />
    } else {
      return <Square size={20} />
    }
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* Header */}
      <Box sx={{ mb: 2 }}>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          {t('wizard.restoreFiles.title')}
        </Typography>
        <Typography variant="body2" color="text.secondary">
          {t('wizard.restoreFiles.subtitle')}
        </Typography>
      </Box>

      {/* Breadcrumbs - Fixed height to prevent layout shift */}
      <Box
        sx={{
          minHeight: 32,
          display: 'flex',
          alignItems: 'center',
          mb: 2,
        }}
      >
        <Breadcrumbs
          separator={<ChevronRight size={16} />}
          sx={{
            flexWrap: 'nowrap',
            '& .MuiBreadcrumbs-ol': {
              display: 'flex',
            },
            '& .MuiBreadcrumbs-li': {
              display: 'flex',
            },
          }}
        >
          <Link
            component="button"
            variant="body2"
            onClick={() => navigateToPath('')}
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
            {t('wizard.restoreFiles.root')}
          </Link>
          {pathParts.map((part, index) => {
            const pathUpToHere = pathParts.slice(0, index + 1).join('/')
            const isLast = index === pathParts.length - 1
            return (
              <Link
                key={pathUpToHere}
                component="button"
                variant="body2"
                onClick={() => !isLast && navigateToPath(pathUpToHere)}
                sx={{
                  cursor: isLast ? 'default' : 'pointer',
                  textDecoration: 'none',
                  fontWeight: isLast ? 600 : 400,
                  '&:hover': { textDecoration: isLast ? 'none' : 'underline' },
                  whiteSpace: 'nowrap',
                }}
              >
                {part}
              </Link>
            )
          })}
        </Breadcrumbs>
      </Box>

      {/* File list with selection info header */}
      <Box
        sx={{
          flex: 1,
          display: 'flex',
          flexDirection: 'column',
          border: '1px solid',
          borderColor: 'divider',
          borderRadius: 1,
          bgcolor: 'background.paper',
          overflow: 'hidden',
        }}
      >
        {/* Fixed selection header inside the box */}
        <Box
          sx={{
            px: 2,
            py: 1,
            borderBottom: '1px solid',
            borderColor: 'divider',
            bgcolor: (theme) => alpha(theme.palette.primary.main, 0.05),
            display: 'flex',
            alignItems: 'center',
            gap: 1,
            height: 40,
            minHeight: 40,
            maxHeight: 40,
          }}
        >
          <CheckSquare size={16} />
          <Typography variant="body2" sx={{ fontWeight: 500 }}>
            {selectedPaths.size > 0
              ? t('wizard.restoreFiles.itemsSelected', { count: selectedPaths.size })
              : t('wizard.restoreFiles.noItemsSelected')}
          </Typography>
          {selectedPaths.size > 0 && (
            <Chip
              label={t('wizard.restoreFiles.clearAll')}
              size="small"
              onClick={() => onChange({ selectedPaths: [], selectedItems: [] })}
              sx={{ ml: 'auto', cursor: 'pointer', height: 24 }}
            />
          )}
        </Box>

        {/* Scrollable file list */}
        <Box sx={{ flex: 1, overflow: 'auto' }}>
          {loading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', p: 4 }}>
              <CircularProgress size={32} />
            </Box>
          )}

          {error && (
            <Box sx={{ p: 2 }}>
              <Alert severity="error">{error}</Alert>
            </Box>
          )}

          {!loading && !error && items.length === 0 && (
            <Box sx={{ p: 4, textAlign: 'center' }}>
              <Typography variant="body2" color="text.secondary">
                {t('wizard.restoreFiles.noItemsFound')}
              </Typography>
            </Box>
          )}

          {!loading && !error && items.length > 0 && (
            <List dense disablePadding>
              {items.map((item) => (
                <ListItem
                  key={item.path}
                  disablePadding
                  secondaryAction={
                    item.type === 'directory' ? (
                      <Tooltip title={t('wizard.restoreFiles.selectDirTooltip')}>
                        <IconButton edge="end" size="small" onClick={() => toggleSelection(item)}>
                          {getDirectoryIcon(item)}
                        </IconButton>
                      </Tooltip>
                    ) : null
                  }
                >
                  <ListItemButton
                    onClick={() => handleItemClick(item)}
                    sx={{
                      '&:hover': {
                        bgcolor: (theme) => alpha(theme.palette.primary.main, 0.08),
                      },
                    }}
                  >
                    <ListItemIcon sx={{ minWidth: 36 }}>
                      {item.type === 'directory' ? (
                        <Folder size={20} />
                      ) : isSelected(item.path) ? (
                        <CheckSquare size={20} color="#1976d2" />
                      ) : (
                        <File size={20} />
                      )}
                    </ListItemIcon>
                    <ListItemText
                      primary={item.name}
                      secondary={item.size ? formatSize(item.size) : undefined}
                      primaryTypographyProps={{
                        sx: { fontSize: '0.875rem', fontWeight: isSelected(item.path) ? 600 : 400 },
                      }}
                      secondaryTypographyProps={{ sx: { fontSize: '0.75rem' } }}
                    />
                  </ListItemButton>
                </ListItem>
              ))}
            </List>
          )}
        </Box>
      </Box>

      {/* Help text */}
      <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
        {t('wizard.restoreFiles.helpText')}
      </Typography>
    </Box>
  )
}
