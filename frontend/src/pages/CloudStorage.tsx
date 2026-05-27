import { useMemo, useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { toast } from 'react-hot-toast'
import { useTranslation } from 'react-i18next'
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Dialog,
  DialogActions,
  DialogContent,
  DialogContentText,
  DialogTitle,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Skeleton,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import {
  AlertTriangle,
  CheckCircle,
  Cloud,
  File,
  Folder,
  HardDrive,
  Plus,
  RefreshCw,
  Search,
  SquarePen,
  Trash2,
  XCircle,
} from 'lucide-react'
import { rcloneAPI } from '../services/api'
import type { RcloneRemote, RcloneStatus } from '../services/api'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import RcloneRemoteDialog from '../components/wizard/RcloneRemoteDialog'
import type { RcloneRemoteCreateInput } from '../components/wizard/RcloneRemoteDialog'
import OperationalCard from '../components/OperationalCard'

interface BrowseEntry {
  name: string
  path: string
  is_dir?: boolean
  size?: number | null
  modified?: string | null
}

interface BrowseState {
  remote: RcloneRemote
  path: string
  entries: BrowseEntry[]
}

interface CloudStorageContentProps {
  status?: RcloneStatus | null
  remotes: RcloneRemote[]
  isLoading?: boolean
  isRefreshing?: boolean
  isCreating?: boolean
  isUpdating?: boolean
  isDeleting?: boolean
  testingRemoteId?: number | null
  browseState?: BrowseState | null
  isBrowsing?: boolean
  addDialogOpen?: boolean
  editingRemote?: RcloneRemote | null
  deleteRemote?: RcloneRemote | null
  createError?: string | null
  updateError?: string | null
  loadError?: string | null
  onRefresh?: () => void
  onAddRemote?: () => void
  onCloseAddRemote?: () => void
  onCreateRemote?: (data: RcloneRemoteCreateInput) => Promise<void> | void
  onEditRemote?: (remote: RcloneRemote) => void
  onCloseEditRemote?: () => void
  onUpdateRemote?: (data: RcloneRemoteCreateInput) => Promise<void> | void
  onRequestDeleteRemote?: (remote: RcloneRemote) => void
  onCloseDeleteRemote?: () => void
  onConfirmDeleteRemote?: () => Promise<void> | void
  onTestRemote?: (remote: RcloneRemote) => void
  onBrowseRemote?: (remote: RcloneRemote) => void
  onCloseBrowse?: () => void
}

const getApiMessage = (error: unknown, fallback: string) => {
  return translateBackendKey(getApiErrorDetail(error)) || fallback
}

const formatStatus = (remote: RcloneRemote) => {
  return remote.last_test_status || 'Not tested'
}

const statusColor = (
  status?: string | null
): 'default' | 'success' | 'error' | 'warning' | 'info' => {
  switch (status) {
    case 'success':
    case 'connected':
      return 'success'
    case 'failed':
    case 'error':
      return 'error'
    case 'pending':
    case 'running':
      return 'info'
    default:
      return 'default'
  }
}

interface CloudStorageRemoteCardProps {
  remote: RcloneRemote
  testingRemoteId?: number | null
  isBrowsing?: boolean
  onTestRemote?: (remote: RcloneRemote) => void
  onBrowseRemote?: (remote: RcloneRemote) => void
  onEditRemote?: (remote: RcloneRemote) => void
  onRequestDeleteRemote?: (remote: RcloneRemote) => void
}

function CloudStorageRemoteCard({
  remote,
  testingRemoteId = null,
  isBrowsing = false,
  onTestRemote,
  onBrowseRemote,
  onEditRemote,
  onRequestDeleteRemote,
}: CloudStorageRemoteCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'
  const status = formatStatus(remote)
  const statusThemeColor = statusColor(remote.last_test_status)
  const usageCount = remote.usage_count ?? 0
  const deleteDisabled = usageCount > 0

  const iconBtnSx = {
    width: 32,
    height: 32,
    borderRadius: 1.5,
    color: 'text.secondary',
    '&:hover': {
      bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
      color: 'text.primary',
    },
    '&.Mui-disabled': { opacity: 0.28 },
  }

  const coloredIconBtnSx = (colorKey: 'primary' | 'success' | 'warning' | 'info') => {
    const color = (theme.palette[colorKey] as { main: string }).main
    return {
      ...iconBtnSx,
      color: alpha(color, isDark ? 0.65 : 0.55),
      '&:hover': {
        bgcolor: alpha(color, isDark ? 0.12 : 0.09),
        color,
      },
      '&.Mui-disabled': { opacity: 0.28 },
    }
  }

  const statItems = [
    {
      icon: <Cloud size={11} />,
      label: t('cloudStorage.remoteProviderLabel'),
      value: remote.provider,
      colorKey: 'primary' as const,
    },
    {
      icon: <CheckCircle size={11} />,
      label: t('cloudStorage.remoteStatusLabel'),
      value: status,
      colorKey: statusThemeColor === 'error' ? ('warning' as const) : ('success' as const),
    },
    {
      icon: <HardDrive size={11} />,
      label: t('cloudStorage.remoteUsageLabel'),
      value: t('cloudStorage.usageCount', { count: usageCount }),
      colorKey: 'info' as const,
    },
  ]

  return (
    <OperationalCard dataTestId={`cloud-storage-remote-${remote.name}`}>
      <Box sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: 1.5 }}>
        <Box sx={{ mb: 1.5 }}>
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              gap: 1,
              mb: 0.4,
            }}
          >
            <Box sx={{ minWidth: 0, flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.75, flexWrap: 'wrap' }}>
                <Typography variant="subtitle1" fontWeight={700} noWrap sx={{ lineHeight: 1.3 }}>
                  {remote.name}
                </Typography>
                <Chip
                  icon={<Cloud size={12} />}
                  label={status}
                  color={statusThemeColor}
                  variant="outlined"
                  size="small"
                  sx={{
                    height: 20,
                    maxWidth: { xs: 140, sm: 180 },
                    fontSize: '0.64rem',
                    fontWeight: 700,
                    '& .MuiChip-icon': { ml: 0.75 },
                    '& .MuiChip-label': {
                      px: 0.75,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                    },
                  }}
                />
              </Box>
            </Box>
            <Tooltip title={t('cloudStorage.editRemote')} arrow placement="left">
              <IconButton
                size="small"
                onClick={() => onEditRemote?.(remote)}
                aria-label={t('cloudStorage.editRemote')}
                sx={{
                  width: 28,
                  height: 28,
                  borderRadius: 1,
                  flexShrink: 0,
                  color: 'text.disabled',
                  '&:hover': {
                    color: 'text.primary',
                    bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
                  },
                }}
              >
                <SquarePen size={14} />
              </IconButton>
            </Tooltip>
          </Box>
          <Typography
            variant="body2"
            title={remote.config_path || t('cloudStorage.managedConfig')}
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.7rem',
              color: 'text.disabled',
              overflow: 'hidden',
              textOverflow: 'ellipsis',
              whiteSpace: 'nowrap',
            }}
          >
            {remote.config_path || t('cloudStorage.managedConfig')}
          </Typography>
        </Box>

        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
            borderRadius: 1.5,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 1.5,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
          }}
        >
          {statItems.map((stat, index) => {
            const statColor = (theme.palette[stat.colorKey] as { main: string }).main
            return (
              <Box
                key={stat.label}
                sx={{
                  px: 1.5,
                  py: 1.1,
                  borderRight: { sm: index === statItems.length - 1 ? 0 : '1px solid' },
                  borderBottom: { xs: index === statItems.length - 1 ? 0 : '1px solid', sm: 0 },
                  borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                }}
              >
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: 0.35 }}>
                  <Box sx={{ color: alpha(statColor, 0.7), display: 'flex' }}>{stat.icon}</Box>
                  <Typography
                    sx={{
                      fontSize: '0.58rem',
                      fontWeight: 700,
                      textTransform: 'uppercase',
                      letterSpacing: '0.07em',
                      color: alpha(statColor, 0.7),
                      lineHeight: 1,
                    }}
                  >
                    {stat.label}
                  </Typography>
                </Box>
                <Typography
                  variant="body2"
                  fontWeight={600}
                  noWrap
                  sx={{ fontVariantNumeric: 'tabular-nums', fontSize: '0.85rem' }}
                >
                  {stat.value}
                </Typography>
              </Box>
            )
          })}
        </Box>

        <Box sx={{ display: 'flex', gap: 1.75, flexWrap: 'wrap', mb: 1.5, px: 0.25 }}>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
            <Typography sx={{ fontSize: '0.68rem', color: 'text.disabled', lineHeight: 1 }}>
              {t('cloudStorage.configSourceLabel')}:
            </Typography>
            <Typography
              sx={{ fontSize: '0.68rem', fontWeight: 600, color: 'text.secondary', lineHeight: 1 }}
            >
              {remote.config_source || 'managed'}
            </Typography>
          </Box>
        </Box>

        {remote.last_error ? (
          <Box
            sx={{
              mb: 1.5,
              px: 1.25,
              py: 0.875,
              borderRadius: 1,
              bgcolor: alpha(theme.palette.error.main, isDark ? 0.12 : 0.07),
              border: '1px solid',
              borderColor: alpha(theme.palette.error.main, isDark ? 0.28 : 0.18),
            }}
          >
            <Typography variant="caption" color="error">
              {remote.last_error}
            </Typography>
          </Box>
        ) : null}

        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.5,
            pt: 1.25,
            borderTop: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.25, flex: 1 }}>
            <Tooltip title={t('cloudStorage.testConnection')} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => onTestRemote?.(remote)}
                  aria-label={t('cloudStorage.testConnection')}
                  disabled={testingRemoteId === remote.id}
                  sx={coloredIconBtnSx('success')}
                >
                  {testingRemoteId === remote.id ? (
                    <RefreshCw size={16} className="animate-spin" />
                  ) : (
                    <CheckCircle size={16} />
                  )}
                </IconButton>
              </span>
            </Tooltip>
            <Tooltip title={t('cloudStorage.browseRemote')} arrow>
              <span>
                <IconButton
                  size="small"
                  onClick={() => onBrowseRemote?.(remote)}
                  aria-label={t('cloudStorage.browseRemote')}
                  disabled={isBrowsing}
                  sx={coloredIconBtnSx('info')}
                >
                  <Search size={16} />
                </IconButton>
              </span>
            </Tooltip>
          </Box>
          <Tooltip
            title={
              deleteDisabled
                ? t('cloudStorage.deleteRemoteInUse', { count: usageCount })
                : t('cloudStorage.deleteRemote')
            }
            arrow
          >
            <span>
              <IconButton
                size="small"
                onClick={() => onRequestDeleteRemote?.(remote)}
                aria-label={t('cloudStorage.deleteRemote')}
                disabled={deleteDisabled}
                sx={{
                  ...iconBtnSx,
                  color: alpha(theme.palette.error.main, 0.6),
                  '&:hover': {
                    color: theme.palette.error.main,
                    bgcolor: alpha(theme.palette.error.main, 0.1),
                  },
                }}
              >
                <Trash2 size={16} />
              </IconButton>
            </span>
          </Tooltip>
        </Box>
      </Box>
    </OperationalCard>
  )
}

export function CloudStorageContent({
  status,
  remotes,
  isLoading = false,
  isRefreshing = false,
  isCreating = false,
  isUpdating = false,
  isDeleting = false,
  testingRemoteId = null,
  browseState = null,
  isBrowsing = false,
  addDialogOpen = false,
  editingRemote = null,
  deleteRemote = null,
  createError = null,
  updateError = null,
  loadError = null,
  onRefresh,
  onAddRemote,
  onCloseAddRemote,
  onCreateRemote,
  onEditRemote,
  onCloseEditRemote,
  onUpdateRemote,
  onRequestDeleteRemote,
  onCloseDeleteRemote,
  onConfirmDeleteRemote,
  onTestRemote,
  onBrowseRemote,
  onCloseBrowse,
}: CloudStorageContentProps) {
  const { t } = useTranslation()
  const isAvailable = status?.available !== false
  const connectedCount = remotes.filter((remote) =>
    ['success', 'connected'].includes(remote.last_test_status || '')
  ).length

  return (
    <Box component="section" aria-label={t('cloudStorage.title')}>
      <Paper variant="outlined" sx={{ borderRadius: 1, mb: 2.5, overflow: 'hidden' }}>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: '1.2fr 1fr 1fr auto' },
            alignItems: 'stretch',
          }}
        >
          <Box sx={{ p: 2, borderRight: { sm: '1px solid' }, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" fontWeight={700}>
              {t('cloudStorage.rcloneAvailability')}
            </Typography>
            <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.75 }}>
              {isAvailable ? (
                <CheckCircle size={18} color="#047857" />
              ) : (
                <XCircle size={18} color="#b91c1c" />
              )}
              <Typography fontWeight={700}>
                {isAvailable
                  ? t('cloudStorage.statusAvailable')
                  : t('cloudStorage.statusUnavailable')}
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.25 }}>
              {status?.version || t('cloudStorage.versionUnknown')}
            </Typography>
          </Box>
          <Box
            sx={{
              p: 2,
              borderRight: { sm: '1px solid' },
              borderTop: { xs: '1px solid', sm: 0 },
              borderColor: 'divider',
            }}
          >
            <Typography variant="caption" color="text.secondary" fontWeight={700}>
              {t('cloudStorage.remoteCountLabel')}
            </Typography>
            <Typography variant="h5" fontWeight={700} sx={{ mt: 0.5 }}>
              {remotes.length}
            </Typography>
          </Box>
          <Box sx={{ p: 2, borderTop: { xs: '1px solid', sm: 0 }, borderColor: 'divider' }}>
            <Typography variant="caption" color="text.secondary" fontWeight={700}>
              {t('cloudStorage.connectedCountLabel')}
            </Typography>
            <Typography variant="h5" fontWeight={700} sx={{ mt: 0.5 }}>
              {connectedCount}
            </Typography>
          </Box>
          <Stack
            direction="row"
            spacing={1}
            alignItems="center"
            justifyContent={{ xs: 'flex-start', lg: 'flex-end' }}
            sx={{
              p: 2,
              borderTop: { xs: '1px solid', lg: 0 },
              borderLeft: { lg: '1px solid' },
              borderColor: 'divider',
              minWidth: { lg: 190 },
            }}
          >
            <IconButton
              onClick={onRefresh}
              disabled={isRefreshing}
              aria-label={t('common.buttons.refresh')}
              title={t('common.buttons.refresh')}
            >
              {isRefreshing ? <CircularProgress size={20} /> : <RefreshCw size={20} />}
            </IconButton>
            <Button
              variant="contained"
              startIcon={<Plus size={16} />}
              disabled={!isAvailable || isLoading}
              onClick={onAddRemote}
              sx={{ height: 36 }}
            >
              {t('cloudStorage.addRemote')}
            </Button>
          </Stack>
        </Box>
      </Paper>

      {loadError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          {loadError}
        </Alert>
      ) : null}

      {!isAvailable ? (
        <Alert severity="error" icon={<AlertTriangle size={18} />} sx={{ mb: 2 }}>
          {status?.error || t('cloudStorage.unavailableHelp')}
        </Alert>
      ) : null}

      {isLoading ? (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
          {[0, 1].map((item) => (
            <Paper key={item} variant="outlined" sx={{ borderRadius: 1, p: 2 }}>
              <Skeleton width="35%" />
              <Skeleton width="60%" />
              <Skeleton height={44} sx={{ mt: 2 }} />
            </Paper>
          ))}
        </Box>
      ) : remotes.length === 0 ? (
        <Paper
          variant="outlined"
          sx={{
            borderRadius: 1,
            p: 3,
            textAlign: 'center',
            bgcolor: 'background.paper',
          }}
        >
          <Cloud size={34} />
          <Typography variant="h6" sx={{ mt: 1 }}>
            {t('cloudStorage.emptyTitle')}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {t('cloudStorage.emptyDescription')}
          </Typography>
        </Paper>
      ) : (
        <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}>
          {remotes.map((remote) => (
            <CloudStorageRemoteCard
              key={remote.id}
              remote={remote}
              testingRemoteId={testingRemoteId}
              isBrowsing={isBrowsing}
              onTestRemote={onTestRemote}
              onBrowseRemote={onBrowseRemote}
              onEditRemote={onEditRemote}
              onRequestDeleteRemote={onRequestDeleteRemote}
            />
          ))}
        </Box>
      )}

      {onCreateRemote && onCloseAddRemote ? (
        <RcloneRemoteDialog
          open={addDialogOpen}
          isCreating={isCreating}
          error={createError}
          onClose={onCloseAddRemote}
          onCreate={onCreateRemote}
        />
      ) : null}

      {editingRemote && onUpdateRemote && onCloseEditRemote ? (
        <RcloneRemoteDialog
          open={!!editingRemote}
          mode="edit"
          initialRemote={{
            name: editingRemote.name,
            provider: editingRemote.provider,
            config_source: 'managed',
            redacted_config: editingRemote.redacted_config || { type: editingRemote.provider },
          }}
          isCreating={isUpdating}
          error={updateError}
          onClose={onCloseEditRemote}
          onCreate={onUpdateRemote}
        />
      ) : null}

      <Dialog open={!!deleteRemote} onClose={isDeleting ? undefined : onCloseDeleteRemote}>
        <DialogTitle>{t('cloudStorage.deleteTitle', { name: deleteRemote?.name })}</DialogTitle>
        <DialogContent>
          <DialogContentText>
            {t('cloudStorage.deleteDescription', { name: deleteRemote?.name })}
          </DialogContentText>
        </DialogContent>
        <DialogActions>
          <Button onClick={onCloseDeleteRemote} disabled={isDeleting}>
            {t('common.buttons.cancel')}
          </Button>
          <Button
            color="error"
            variant="contained"
            onClick={onConfirmDeleteRemote}
            disabled={isDeleting}
            startIcon={isDeleting ? <CircularProgress size={16} color="inherit" /> : null}
          >
            {t('cloudStorage.deleteRemote')}
          </Button>
        </DialogActions>
      </Dialog>

      <Dialog open={!!browseState} onClose={onCloseBrowse} maxWidth="sm" fullWidth>
        <DialogTitle>
          {t('cloudStorage.browseTitle', { name: browseState?.remote.name })}
        </DialogTitle>
        <DialogContent dividers>
          {isBrowsing ? (
            <Stack direction="row" spacing={1.5} alignItems="center">
              <CircularProgress size={18} />
              <Typography>{t('cloudStorage.browsing')}</Typography>
            </Stack>
          ) : browseState?.entries.length ? (
            <List dense>
              {browseState.entries.map((entry) => (
                <ListItem key={entry.path || entry.name} disableGutters>
                  <ListItemIcon sx={{ minWidth: 34 }}>
                    {entry.is_dir ? <Folder size={18} /> : <File size={18} />}
                  </ListItemIcon>
                  <ListItemText
                    primary={entry.name}
                    secondary={entry.is_dir ? t('cloudStorage.directory') : t('cloudStorage.file')}
                  />
                </ListItem>
              ))}
            </List>
          ) : (
            <Typography color="text.secondary">{t('cloudStorage.noEntries')}</Typography>
          )}
        </DialogContent>
      </Dialog>
    </Box>
  )
}

export default function CloudStorage() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const [addDialogOpen, setAddDialogOpen] = useState(false)
  const [editingRemote, setEditingRemote] = useState<RcloneRemote | null>(null)
  const [deleteRemote, setDeleteRemote] = useState<RcloneRemote | null>(null)
  const [testingRemoteId, setTestingRemoteId] = useState<number | null>(null)
  const [browseState, setBrowseState] = useState<BrowseState | null>(null)

  const statusQuery = useQuery({
    queryKey: ['rclone-status'],
    queryFn: async () => {
      const response = await rcloneAPI.getStatus()
      return response.data
    },
  })

  const remotesQuery = useQuery({
    queryKey: ['rclone-remotes'],
    queryFn: async () => {
      const response = await rcloneAPI.listRemotes()
      return response.data.remotes
    },
  })

  const createRemoteMutation = useMutation({
    mutationFn: (data: RcloneRemoteCreateInput) => rcloneAPI.createRemote(data),
    onSuccess: () => {
      toast.success(t('cloudStorage.remoteCreateSucceeded'))
      setAddDialogOpen(false)
      queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('wizard.location.rcloneCreateFailed')))
    },
  })

  const updateRemoteMutation = useMutation({
    mutationFn: (data: RcloneRemoteCreateInput) => {
      if (!editingRemote) {
        throw new Error('No rclone remote selected for update')
      }
      return rcloneAPI.updateRemote(editingRemote.id, data)
    },
    onSuccess: () => {
      toast.success(t('cloudStorage.remoteUpdateSucceeded'))
      setEditingRemote(null)
      queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('cloudStorage.remoteUpdateFailed')))
    },
  })

  const deleteRemoteMutation = useMutation({
    mutationFn: () => {
      if (!deleteRemote) {
        throw new Error('No rclone remote selected for deletion')
      }
      return rcloneAPI.deleteRemote(deleteRemote.id)
    },
    onSuccess: () => {
      toast.success(t('cloudStorage.remoteDeleteSucceeded'))
      setDeleteRemote(null)
      queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('cloudStorage.remoteDeleteFailed')))
    },
  })

  const testRemoteMutation = useMutation({
    mutationFn: (remote: RcloneRemote) => rcloneAPI.testRemote(remote.id),
    onMutate: (remote) => {
      setTestingRemoteId(remote.id)
    },
    onSuccess: () => {
      toast.success(t('cloudStorage.remoteTestSucceeded'))
      queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('cloudStorage.remoteTestFailed')))
    },
    onSettled: () => {
      setTestingRemoteId(null)
    },
  })

  const browseRemoteMutation = useMutation({
    mutationFn: async (remote: RcloneRemote) => {
      setBrowseState({ remote, path: '', entries: [] })
      const response = await rcloneAPI.browseRemote(remote.id, '')
      return {
        remote,
        path: response.data.path || '',
        entries: (response.data.entries || []) as BrowseEntry[],
      }
    },
    onSuccess: ({ remote, path, entries }) => {
      setBrowseState({ remote, path, entries })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('cloudStorage.browseFailed')))
    },
  })

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['rclone-status'] })
    queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
  }

  const loadError = useMemo(() => {
    if (statusQuery.error) {
      return getApiMessage(statusQuery.error, t('cloudStorage.statusLoadFailed'))
    }
    if (remotesQuery.error) {
      return getApiMessage(remotesQuery.error, t('cloudStorage.remotesLoadFailed'))
    }
    return null
  }, [remotesQuery.error, statusQuery.error, t])

  return (
    <CloudStorageContent
      status={statusQuery.data}
      remotes={remotesQuery.data || []}
      isLoading={statusQuery.isLoading || remotesQuery.isLoading}
      isRefreshing={statusQuery.isFetching || remotesQuery.isFetching}
      isCreating={createRemoteMutation.isPending}
      isUpdating={updateRemoteMutation.isPending}
      isDeleting={deleteRemoteMutation.isPending}
      testingRemoteId={testingRemoteId}
      browseState={browseState}
      isBrowsing={browseRemoteMutation.isPending}
      addDialogOpen={addDialogOpen}
      editingRemote={editingRemote}
      deleteRemote={deleteRemote}
      createError={
        createRemoteMutation.error
          ? getApiMessage(createRemoteMutation.error, t('wizard.location.rcloneCreateFailed'))
          : null
      }
      updateError={
        updateRemoteMutation.error
          ? getApiMessage(updateRemoteMutation.error, t('cloudStorage.remoteUpdateFailed'))
          : null
      }
      loadError={loadError}
      onRefresh={refreshAll}
      onAddRemote={() => setAddDialogOpen(true)}
      onCloseAddRemote={() => {
        setAddDialogOpen(false)
        createRemoteMutation.reset()
      }}
      onCreateRemote={async (data) => {
        await createRemoteMutation.mutateAsync(data)
      }}
      onEditRemote={(remote) => {
        updateRemoteMutation.reset()
        setEditingRemote(remote)
      }}
      onCloseEditRemote={() => {
        setEditingRemote(null)
        updateRemoteMutation.reset()
      }}
      onUpdateRemote={async (data) => {
        await updateRemoteMutation.mutateAsync(data)
      }}
      onRequestDeleteRemote={(remote) => {
        deleteRemoteMutation.reset()
        setDeleteRemote(remote)
      }}
      onCloseDeleteRemote={() => {
        setDeleteRemote(null)
        deleteRemoteMutation.reset()
      }}
      onConfirmDeleteRemote={async () => {
        await deleteRemoteMutation.mutateAsync()
      }}
      onTestRemote={(remote) => testRemoteMutation.mutate(remote)}
      onBrowseRemote={(remote) => browseRemoteMutation.mutate(remote)}
      onCloseBrowse={() => setBrowseState(null)}
    />
  )
}
