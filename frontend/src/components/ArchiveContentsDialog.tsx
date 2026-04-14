import React, { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import {
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  Typography,
  Stack,
  Box,
  Skeleton,
  IconButton,
  alpha,
} from '@mui/material'
import ResponsiveDialog from './ResponsiveDialog'
import { FolderOpen, Folder, FileText, Inbox } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { BorgApiClient, type Repository } from '../services/borgApi/client'
import { Archive } from '../types'
import { formatDateCompact, formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface ArchiveContentsDialogProps {
  open: boolean
  archive: Archive | null
  repository: Repository | null
  onClose: () => void
  onDownloadFile?: (archiveName: string, filePath: string) => void
}

interface FileItem {
  name: string
  path: string
  size?: number | null
  mtime?: string
  type: string
}

interface RawFileItem {
  name: string
  path: string
  size?: number | null
  type: string
  mtime?: string
}

function normalizeArchivePath(path: string) {
  if (!path || path === '/') {
    return '/'
  }
  return `/${path.replace(/^\/+/, '').replace(/\/+$/, '')}`
}

export default function ArchiveContentsDialog({
  open,
  archive,
  repository,
  onClose,
  onDownloadFile,
}: ArchiveContentsDialogProps) {
  const { t } = useTranslation()
  const [currentPath, setCurrentPath] = useState('/')

  // Reset path when archive changes
  useEffect(() => {
    if (open && archive) {
      setCurrentPath('/')
    }
  }, [open, archive])

  // Fetch archive contents
  const { data: archiveContents, isFetching } = useQuery({
    queryKey: ['archive-contents', repository?.id, archive?.name, currentPath],
    queryFn: async () => {
      if (!repository || !archive) {
        throw new Error('Repository or archive not selected')
      }
      const path = currentPath === '/' ? '' : currentPath.slice(1)
      return new BorgApiClient(repository).getArchiveContents(archive.id, archive.name, path)
    },
    enabled: !!archive && !!repository && open,
    staleTime: 5 * 60 * 1000,
  })

  // File browser helper functions
  const getFilesInCurrentPath = () => {
    if (!archiveContents?.data?.items) return { folders: [], files: [] }

    const items = archiveContents.data.items
    const folders: FileItem[] = []
    const files: FileItem[] = []

    items.forEach((item: RawFileItem) => {
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
    setCurrentPath(normalizeArchivePath(path))
  }

  const getBreadcrumbs = () => {
    if (currentPath === '/') return [{ label: t('archiveContents.root'), path: '/' }]

    const parts = currentPath.split('/').filter(Boolean)
    const breadcrumbs = [{ label: t('archiveContents.root'), path: '/' }]

    let accumulatedPath = ''
    parts.forEach((part) => {
      accumulatedPath += `/${part}`
      breadcrumbs.push({ label: part, path: accumulatedPath })
    })

    return breadcrumbs
  }

  const { folders, files } = getFilesInCurrentPath()

  return (
    <ResponsiveDialog
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
              {t('archiveContents.title')}
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
        <Stack spacing={2} sx={{ height: '100%', overflow: 'hidden' }}>
          {/* Breadcrumb Navigation — always visible, updates immediately on navigation */}
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
                    '&:hover': { color: 'primary.dark' },
                  }}
                >
                  {crumb.label}
                </Typography>
              </React.Fragment>
            ))}
          </Box>

          {/* Content area — skeleton while loading, list or empty state when ready */}
          <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {isFetching ? (
              <Stack spacing={0.5}>
                {[
                  { width: '55%', isFolder: true },
                  { width: '40%', isFolder: true },
                  { width: '70%', isFolder: true },
                  { width: '62%', isFolder: false },
                  { width: '48%', isFolder: false },
                  { width: '75%', isFolder: false },
                  { width: '33%', isFolder: false },
                ].map((row, i) => (
                  <Box
                    key={i}
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: 1.5,
                      p: 1.5,
                      borderRadius: 1,
                      bgcolor: (theme) =>
                        row.isFolder ? alpha(theme.palette.primary.main, 0.05) : 'action.hover',
                    }}
                  >
                    <Skeleton variant="rounded" width={20} height={20} sx={{ flexShrink: 0 }} />
                    <Skeleton variant="text" sx={{ flex: 1, maxWidth: row.width }} />
                    <Skeleton variant="text" width={52} />
                  </Box>
                ))}
              </Stack>
            ) : archiveContents?.data?.items ? (
              archiveContents.data.items.length > 0 ? (
                <Box sx={{ flex: 1, overflow: 'hidden' }}>
                  <Box sx={{ height: '100%', overflowY: 'auto' }}>
                    {folders.length === 0 && files.length === 0 ? (
                      <Box sx={{ textAlign: 'center', py: 4 }}>
                        <Typography variant="body2" color="text.secondary">
                          {t('archiveContents.emptyDirectory')}
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
                            {folder.size !== null && folder.size !== undefined ? (
                              <Typography variant="body2" color="text.secondary" sx={{ ml: 2 }}>
                                {formatBytesUtil(folder.size)}
                              </Typography>
                            ) : null}
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
                              <FileText size={20} />
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
                                  title={t('archiveContents.downloadFile')}
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
                <Box
                  sx={{
                    flex: 1,
                    display: 'flex',
                    flexDirection: 'column',
                    alignItems: 'center',
                    justifyContent: 'center',
                    textAlign: 'center',
                    py: 4,
                    px: 3,
                  }}
                >
                  <Box
                    sx={{
                      width: 72,
                      height: 72,
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      bgcolor: (theme) => alpha(theme.palette.text.secondary, 0.08),
                      mb: 2.5,
                    }}
                  >
                    <Inbox size={32} style={{ opacity: 0.5 }} />
                  </Box>
                  <Typography variant="h6" fontWeight={600} gutterBottom>
                    {t('archiveContents.emptyArchive')}
                  </Typography>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ maxWidth: 380, lineHeight: 1.7 }}
                  >
                    {t('archiveContents.emptyArchiveDesc')}
                  </Typography>
                </Box>
              )
            ) : (
              <Box
                sx={{
                  flex: 1,
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  textAlign: 'center',
                  py: 4,
                  px: 3,
                }}
              >
                <Box
                  sx={{
                    width: 72,
                    height: 72,
                    borderRadius: '50%',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    bgcolor: (theme) => alpha(theme.palette.text.secondary, 0.08),
                    mb: 2.5,
                  }}
                >
                  <Inbox size={32} style={{ opacity: 0.5 }} />
                </Box>
                <Typography variant="body1" color="text.secondary">
                  {t('archiveContents.noInfo')}
                </Typography>
              </Box>
            )}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions sx={{ display: { xs: 'none', md: 'flex' } }}>
        <Button onClick={onClose}>{t('common.buttons.close')}</Button>
      </DialogActions>
    </ResponsiveDialog>
  )
}
