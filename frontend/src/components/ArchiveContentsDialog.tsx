import React, { useState, useEffect } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Box,
  CircularProgress,
  IconButton,
  alpha,
} from '@mui/material'
import { FolderOpen, Folder, AlertCircle } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { browseAPI } from '../services/api'
import { Archive } from '../types'
import { formatDateCompact, formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface ArchiveContentsDialogProps {
  open: boolean
  archive: Archive | null
  repositoryId: number | null
  onClose: () => void
  onDownloadFile?: (archiveName: string, filePath: string) => void
}

interface FileItem {
  name: string
  path: string
  size: number
  mtime?: string
  type: string
}

export default function ArchiveContentsDialog({
  open,
  archive,
  repositoryId,
  onClose,
  onDownloadFile,
}: ArchiveContentsDialogProps) {
  const [currentPath, setCurrentPath] = useState('/')

  // Reset path when archive changes
  useEffect(() => {
    if (open && archive) {
      setCurrentPath('/')
    }
  }, [open, archive])

  // Fetch archive contents
  const { data: archiveContents, isLoading: loadingArchiveContents } = useQuery({
    queryKey: ['archive-contents', repositoryId, archive?.name, currentPath],
    queryFn: async () => {
      if (!repositoryId || !archive) {
        throw new Error('Repository or archive not selected')
      }
      const path = currentPath === '/' ? '' : currentPath.replace(/^\//, '')
      return await browseAPI.getContents(repositoryId, archive.name, path)
    },
    enabled: !!archive && !!repositoryId && open,
    staleTime: 5 * 60 * 1000,
  })

  // File browser helper functions
  const getFilesInCurrentPath = () => {
    if (!archiveContents?.data?.items) return { folders: [], files: [] }

    const items = archiveContents.data.items
    const folders: FileItem[] = []
    const files: FileItem[] = []

    items.forEach((item: any) => {
      if (item.type === 'directory') {
        folders.push({
          name: item.name,
          path: item.path,
          size: item.size,
          type: 'd',
        })
      } else {
        files.push({
          name: item.name,
          path: item.path,
          size: item.size,
          mtime: item.mtime,
          type: 'f',
        })
      }
    })

    return { folders, files }
  }

  const navigateToPath = (path: string) => {
    setCurrentPath(path)
  }

  const getBreadcrumbs = () => {
    if (currentPath === '/') return [{ label: 'Root', path: '/' }]

    const parts = currentPath.split('/').filter(Boolean)
    const breadcrumbs = [{ label: 'Root', path: '/' }]

    let accumulatedPath = ''
    parts.forEach((part) => {
      accumulatedPath += `/${part}`
      breadcrumbs.push({ label: part, path: accumulatedPath })
    })

    return breadcrumbs
  }

  const { folders, files } = getFilesInCurrentPath()

  return (
    <Dialog
      open={open}
      onClose={onClose}
      maxWidth="md"
      fullWidth
      PaperProps={{
        sx: {
          maxHeight: '80vh',
        },
      }}
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={2}>
          <FolderOpen size={24} />
          <Box>
            <Typography variant="h6" fontWeight={600}>
              Archive Contents
            </Typography>
            <Typography variant="body2" color="text.secondary">
              {archive?.name}
            </Typography>
          </Box>
        </Stack>
      </DialogTitle>
      <DialogContent
        dividers
        sx={{
          height: 600,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {loadingArchiveContents ? (
          <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', py: 8 }}>
            <CircularProgress size={48} />
            <Typography variant="body2" color="text.secondary" sx={{ mt: 2 }}>
              Loading archive contents...
            </Typography>
          </Box>
        ) : archiveContents?.data?.items ? (
          <Stack spacing={2} sx={{ height: '100%', overflow: 'hidden' }}>
            {/* Breadcrumb Navigation */}
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                flexWrap: 'wrap',
                gap: 0.5,
                flexShrink: 0,
              }}
            >
              {getBreadcrumbs().map((crumb, index) => (
                <React.Fragment key={crumb.path}>
                  {index > 0 && (
                    <Typography variant="body2" color="text.secondary">
                      /
                    </Typography>
                  )}
                  <Typography
                    variant="body2"
                    onClick={() => navigateToPath(crumb.path)}
                    sx={{
                      cursor: 'pointer',
                      color: 'primary.main',
                      textDecoration: 'underline',
                      '&:hover': {
                        color: 'primary.dark',
                      },
                    }}
                  >
                    {crumb.label}
                  </Typography>
                </React.Fragment>
              ))}
            </Box>

            {/* Files and Folders List */}
            {archiveContents?.data?.items && archiveContents.data.items.length > 0 ? (
              <Box sx={{ flex: 1, overflow: 'hidden' }}>
                <Box sx={{ height: '100%', overflowY: 'auto' }}>
                  {folders.length === 0 && files.length === 0 ? (
                    <Box sx={{ textAlign: 'center', py: 4 }}>
                      <Typography variant="body2" color="text.secondary">
                        This directory is empty
                      </Typography>
                    </Box>
                  ) : (
                    <Stack spacing={0.5}>
                      {/* Folders */}
                      {folders.map((folder, index) => (
                        <Box
                          key={`folder-${index}`}
                          onClick={() => navigateToPath(folder.path)}
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            p: 1.5,
                            borderRadius: 1,
                            cursor: 'pointer',
                            userSelect: 'none',
                            backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.1),
                            '&:hover': {
                              backgroundColor: (theme) => alpha(theme.palette.primary.main, 0.2),
                            },
                          }}
                        >
                          <Stack
                            direction="row"
                            spacing={1.5}
                            alignItems="center"
                            sx={{ color: 'text.primary', flex: 1 }}
                          >
                            <Folder size={20} />
                            <Typography variant="body2" fontWeight={500}>
                              {folder.name}
                            </Typography>
                          </Stack>
                          <Typography variant="body2" color="text.secondary" sx={{ ml: 2 }}>
                            {formatBytesUtil(folder.size)}
                          </Typography>
                        </Box>
                      ))}

                      {/* Files */}
                      {files.map((file, index) => (
                        <Box
                          key={`file-${index}`}
                          sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            p: 1.5,
                            borderRadius: 1,
                            userSelect: 'none',
                            backgroundColor: 'action.hover',
                            '&:hover': {
                              backgroundColor: 'action.selected',
                            },
                          }}
                        >
                          <Stack
                            direction="row"
                            spacing={1.5}
                            alignItems="center"
                            sx={{ flex: 1, minWidth: 0, color: 'text.primary' }}
                          >
                            <FolderOpen size={20} />
                            <Typography
                              variant="body2"
                              sx={{
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {file.name}
                            </Typography>
                          </Stack>
                          <Stack direction="row" spacing={2} alignItems="center">
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{
                                minWidth: 165,
                                textAlign: 'right',
                                fontFamily: 'monospace',
                                fontSize: '0.8rem',
                                whiteSpace: 'nowrap',
                              }}
                            >
                              {file.mtime ? formatDateCompact(file.mtime) : '-'}
                            </Typography>
                            <Typography
                              variant="body2"
                              color="text.secondary"
                              sx={{ width: 80, textAlign: 'right' }}
                            >
                              {file.size ? formatBytesUtil(file.size) : '0 B'}
                            </Typography>
                            {onDownloadFile && (
                              <IconButton
                                size="small"
                                sx={{ color: 'text.secondary' }}
                                onClick={() => {
                                  if (archive) {
                                    onDownloadFile(archive.name, file.path)
                                  }
                                }}
                                title="Download file"
                              >
                                <svg
                                  width="16"
                                  height="16"
                                  viewBox="0 0 24 24"
                                  fill="none"
                                  stroke="currentColor"
                                  strokeWidth="2"
                                >
                                  <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                                  <polyline points="7 10 12 15 17 10" />
                                  <line x1="12" y1="15" x2="12" y2="3" />
                                </svg>
                              </IconButton>
                            )}
                          </Stack>
                        </Box>
                      ))}
                    </Stack>
                  )}
                </Box>
              </Box>
            ) : (
              <Box sx={{ textAlign: 'center', py: 8, color: 'text.secondary' }}>
                <AlertCircle size={48} style={{ display: 'block', margin: '0 auto 16px auto' }} />
                <Typography variant="h6" color="text.secondary" gutterBottom>
                  This archive is empty
                </Typography>
                <Typography variant="body2" color="text.secondary">
                  No files were backed up in this archive. This may happen if the source directory
                  was empty or inaccessible during the backup.
                </Typography>
              </Box>
            )}
          </Stack>
        ) : (
          <Box sx={{ textAlign: 'center', py: 8, color: 'text.secondary' }}>
            <AlertCircle size={48} style={{ display: 'block', margin: '0 auto 16px auto' }} />
            <Typography variant="body1" color="text.secondary">
              No archive information available
            </Typography>
          </Box>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Close</Button>
      </DialogActions>
    </Dialog>
  )
}
