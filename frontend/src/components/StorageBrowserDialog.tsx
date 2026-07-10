import type { ReactNode } from 'react'
import {
  alpha,
  Box,
  Button,
  Chip,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
} from '@mui/material'
import { Download, FileText, Folder, FolderOpen, Inbox, ShieldCheck } from 'lucide-react'
import ResponsiveDialog from './shared/ResponsiveDialog'
import { normalizeBrowserPath } from '../utils/storageBrowserPaths'

export interface StorageBrowserItem {
  name: string
  path: string
  type: 'directory' | 'file'
  size?: number | null
  modified?: string | null
  downloadPath?: string
  badgeLabel?: string
  tooltip?: string
  tone?: 'info'
}

interface StorageBrowserDialogProps {
  open: boolean
  title: string
  subtitle?: string | null
  currentPath: string
  items?: StorageBrowserItem[] | null
  isLoading?: boolean
  rootLabel: string
  closeLabel: string
  emptyDirectoryLabel: string
  noInfoLabel?: string
  emptyRootTitle?: string
  emptyRootDescription?: string
  banner?: ReactNode
  maxWidth?: 'xs' | 'sm' | 'md' | 'lg' | 'xl'
  showModifiedColumn?: boolean
  onClose: () => void
  onNavigate: (path: string) => void
  onDownloadFile?: (path: string, size?: number | null) => void
  downloadBusy?: boolean
  downloadLabel?: string
  formatSize?: (size: number) => string
  formatModified?: (modified: string) => string
}

function buildBreadcrumbs(path: string, rootLabel: string) {
  const normalized = normalizeBrowserPath(path)
  const parts = normalized ? normalized.split('/').filter(Boolean) : []
  const breadcrumbs = [{ label: rootLabel, path: '' }]

  let accumulatedPath = ''
  parts.forEach((part) => {
    accumulatedPath = accumulatedPath ? `${accumulatedPath}/${part}` : part
    breadcrumbs.push({ label: part, path: accumulatedPath })
  })

  return breadcrumbs
}

function defaultFormatSize(size: number) {
  if (size === 0) return '0 B'

  const unit = 1024
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const unitIndex = Math.min(Math.floor(Math.log(size) / Math.log(unit)), units.length - 1)
  return `${(size / Math.pow(unit, unitIndex)).toFixed(1)} ${units[unitIndex]}`
}

function StorageBrowserEmptyState({
  title,
  description,
  fallback,
}: {
  title?: string
  description?: string
  fallback: string
}) {
  return (
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
      {title ? (
        <Typography variant="h6" fontWeight={600} gutterBottom>
          {title}
        </Typography>
      ) : null}
      <Typography
        variant={title ? 'body2' : 'body1'}
        color="text.secondary"
        sx={{ maxWidth: 380, lineHeight: 1.7 }}
      >
        {description || fallback}
      </Typography>
    </Box>
  )
}

export default function StorageBrowserDialog({
  open,
  title,
  subtitle,
  currentPath,
  items,
  isLoading = false,
  rootLabel,
  closeLabel,
  emptyDirectoryLabel,
  noInfoLabel,
  emptyRootTitle,
  emptyRootDescription,
  banner,
  maxWidth = 'md',
  showModifiedColumn = false,
  onClose,
  onNavigate,
  onDownloadFile,
  downloadBusy = false,
  downloadLabel,
  formatSize = defaultFormatSize,
  formatModified,
}: StorageBrowserDialogProps) {
  const normalizedPath = normalizeBrowserPath(currentPath)
  const breadcrumbs = buildBreadcrumbs(normalizedPath, rootLabel)
  const folders = (items || []).filter((item) => item.type === 'directory')
  const files = (items || []).filter((item) => item.type === 'file')
  const hasItems = folders.length > 0 || files.length > 0
  const hasModifiedColumn =
    showModifiedColumn || files.some((file) => Boolean(file.modified || formatModified))

  const renderSize = (size?: number | null) => {
    if (typeof size !== 'number' || !Number.isFinite(size) || size < 0) {
      return null
    }
    return formatSize(size)
  }

  return (
    <ResponsiveDialog
      open={open}
      onClose={onClose}
      maxWidth={maxWidth}
      fullWidth
      PaperProps={{
        sx: {
          maxHeight: '80vh',
        },
      }}
      footer={
        <DialogActions sx={{ display: { xs: 'none', md: 'flex' } }}>
          <Button onClick={onClose}>{closeLabel}</Button>
        </DialogActions>
      }
    >
      <DialogTitle>
        <Stack direction="row" alignItems="center" spacing={2}>
          <FolderOpen size={24} />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="h6" fontWeight={600}>
              {title}
            </Typography>
            {subtitle ? (
              <Typography variant="body2" color="text.secondary" noWrap>
                {subtitle}
              </Typography>
            ) : null}
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
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              flexWrap: 'wrap',
              gap: 0.5,
              flexShrink: 0,
            }}
          >
            {breadcrumbs.map((crumb, index) => (
              <Box key={crumb.path || 'root'} sx={{ display: 'flex', alignItems: 'center' }}>
                {index > 0 ? (
                  <Typography variant="body2" color="text.secondary" sx={{ mx: 0.5 }}>
                    /
                  </Typography>
                ) : null}
                <Button
                  size="small"
                  variant="text"
                  onClick={() => onNavigate(crumb.path)}
                  disabled={crumb.path === normalizedPath}
                  sx={{
                    minWidth: 0,
                    px: 0.5,
                    textTransform: 'none',
                    fontWeight: crumb.path === normalizedPath ? 700 : 500,
                  }}
                >
                  {crumb.label}
                </Button>
              </Box>
            ))}
          </Box>

          {banner}

          <Box sx={{ flex: 1, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
            {isLoading ? (
              <Stack spacing={0.5}>
                {[
                  { width: '55%', isFolder: true },
                  { width: '40%', isFolder: true },
                  { width: '70%', isFolder: true },
                  { width: '62%', isFolder: false },
                  { width: '48%', isFolder: false },
                  { width: '75%', isFolder: false },
                  { width: '33%', isFolder: false },
                ].map((row, index) => (
                  <Box
                    key={index}
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
            ) : items ? (
              hasItems ? (
                <Box sx={{ flex: 1, overflow: 'hidden' }}>
                  <Box sx={{ height: '100%', overflowY: 'auto' }}>
                    <Stack spacing={0.5}>
                      {folders.map((folder) => {
                        const highlighted = folder.tone === 'info'
                        return (
                          <Tooltip
                            key={folder.path || folder.name}
                            title={folder.tooltip || ''}
                            arrow
                            disableHoverListener={!folder.tooltip}
                          >
                            <Box
                              component="button"
                              type="button"
                              onClick={() => onNavigate(normalizeBrowserPath(folder.path))}
                              sx={{
                                width: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 1.5,
                                p: 1.5,
                                borderRadius: 1,
                                cursor: 'pointer',
                                userSelect: 'none',
                                textAlign: 'left',
                                font: 'inherit',
                                color: 'text.primary',
                                border: '1px solid',
                                borderColor: (theme) =>
                                  highlighted
                                    ? alpha(theme.palette.info.main, 0.35)
                                    : 'transparent',
                                backgroundColor: (theme) =>
                                  highlighted
                                    ? alpha(theme.palette.info.main, 0.08)
                                    : alpha(theme.palette.primary.main, 0.1),
                                '&:hover': {
                                  backgroundColor: (theme) =>
                                    highlighted
                                      ? alpha(theme.palette.info.main, 0.14)
                                      : alpha(theme.palette.primary.main, 0.2),
                                },
                                '&:focus-visible': {
                                  outline: '2px solid',
                                  outlineColor: 'primary.main',
                                  outlineOffset: 2,
                                },
                              }}
                            >
                              <Stack
                                direction="row"
                                spacing={1.5}
                                alignItems="center"
                                sx={{ minWidth: 0, flex: 1 }}
                              >
                                {highlighted ? <ShieldCheck size={20} /> : <Folder size={20} />}
                                <Typography variant="body2" fontWeight={500} noWrap>
                                  {folder.name}
                                </Typography>
                                {folder.badgeLabel ? (
                                  <Chip
                                    label={folder.badgeLabel}
                                    size="small"
                                    color={folder.tone || 'default'}
                                    variant="outlined"
                                    sx={{ height: 22, flexShrink: 0 }}
                                  />
                                ) : null}
                              </Stack>
                              {renderSize(folder.size) ? (
                                <Typography variant="body2" color="text.secondary" sx={{ ml: 2 }}>
                                  {renderSize(folder.size)}
                                </Typography>
                              ) : null}
                            </Box>
                          </Tooltip>
                        )
                      })}

                      {files.map((file) => {
                        const highlighted = file.tone === 'info'
                        return (
                          <Tooltip
                            key={file.path || file.name}
                            title={file.tooltip || ''}
                            arrow
                            disableHoverListener={!file.tooltip}
                          >
                            <Box
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'space-between',
                                gap: 1.5,
                                p: 1.5,
                                borderRadius: 1,
                                userSelect: 'none',
                                border: '1px solid',
                                borderColor: (theme) =>
                                  highlighted
                                    ? alpha(theme.palette.info.main, 0.35)
                                    : 'transparent',
                                backgroundColor: (theme) =>
                                  highlighted
                                    ? alpha(theme.palette.info.main, 0.06)
                                    : theme.palette.action.hover,
                                '&:hover': {
                                  backgroundColor: (theme) =>
                                    highlighted
                                      ? alpha(theme.palette.info.main, 0.12)
                                      : theme.palette.action.selected,
                                },
                              }}
                            >
                              <Stack
                                direction="row"
                                spacing={1.5}
                                alignItems="center"
                                sx={{ flex: 1, minWidth: 0, color: 'text.primary' }}
                              >
                                {highlighted ? <ShieldCheck size={20} /> : <FileText size={20} />}
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
                                {file.badgeLabel ? (
                                  <Chip
                                    label={file.badgeLabel}
                                    size="small"
                                    color={file.tone || 'default'}
                                    variant="outlined"
                                    sx={{ height: 22, flexShrink: 0 }}
                                  />
                                ) : null}
                              </Stack>
                              <Stack direction="row" spacing={2} alignItems="center">
                                {hasModifiedColumn ? (
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
                                    {file.modified && formatModified
                                      ? formatModified(file.modified)
                                      : '-'}
                                  </Typography>
                                ) : null}
                                {renderSize(file.size) ? (
                                  <Typography
                                    variant="body2"
                                    color="text.secondary"
                                    sx={{ width: 80, textAlign: 'right' }}
                                  >
                                    {renderSize(file.size)}
                                  </Typography>
                                ) : null}
                                {onDownloadFile ? (
                                  <IconButton
                                    size="small"
                                    sx={{ color: 'text.secondary' }}
                                    disabled={downloadBusy}
                                    onClick={() =>
                                      onDownloadFile(file.downloadPath || file.path, file.size)
                                    }
                                    title={downloadLabel}
                                    aria-label={downloadLabel}
                                  >
                                    <Download size={16} />
                                  </IconButton>
                                ) : null}
                              </Stack>
                            </Box>
                          </Tooltip>
                        )
                      })}
                    </Stack>
                  </Box>
                </Box>
              ) : normalizedPath ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    {emptyDirectoryLabel}
                  </Typography>
                </Box>
              ) : (
                <StorageBrowserEmptyState
                  title={emptyRootTitle}
                  description={emptyRootDescription}
                  fallback={emptyDirectoryLabel}
                />
              )
            ) : (
              <StorageBrowserEmptyState fallback={noInfoLabel || emptyDirectoryLabel} />
            )}
          </Box>
        </Stack>
      </DialogContent>
    </ResponsiveDialog>
  )
}
