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
  HardDrive,
  Plus,
  RefreshCw,
  Search,
  SquarePen,
  Trash2,
} from 'lucide-react'
import { rcloneAPI } from '../services/api'
import type {
  RcloneOAuthSession,
  RcloneProvider,
  RcloneRemote,
  RcloneStatus,
} from '../services/api'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import RcloneRemoteDialog from '../components/wizard/RcloneRemoteDialog'
import type { RcloneRemoteCreateInput } from '../components/wizard/RcloneRemoteDialog'
import OperationalCard from '../components/OperationalCard'
import PageHeader from '../components/PageHeader'
import ListToolbar from '../components/ListToolbar'
import StorageBrowserDialog, { type StorageBrowserItem } from '../components/StorageBrowserDialog'
import { joinBrowserPath, normalizeBrowserPath } from '../utils/storageBrowserPaths'

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
  providers?: RcloneProvider[]
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
  onStartOAuth?: (data: {
    provider: string
    config: Record<string, unknown>
  }) => Promise<RcloneOAuthSession>
  onGetOAuthSession?: (sessionId: string) => Promise<RcloneOAuthSession>
  onEditRemote?: (remote: RcloneRemote) => void
  onCloseEditRemote?: () => void
  onUpdateRemote?: (data: RcloneRemoteCreateInput) => Promise<void> | void
  onRequestDeleteRemote?: (remote: RcloneRemote) => void
  onCloseDeleteRemote?: () => void
  onConfirmDeleteRemote?: () => Promise<void> | void
  onTestRemote?: (remote: RcloneRemote) => void
  onBrowseRemote?: (remote: RcloneRemote, path?: string) => void
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
                  sx={{
                    fontVariantNumeric: 'tabular-nums',
                    fontSize: '0.85rem',
                    minWidth: 0,
                    overflowWrap: 'anywhere',
                  }}
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
  providers,
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
  onStartOAuth,
  onGetOAuthSession,
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

  const [searchQuery, setSearchQuery] = useState('')
  const [sortBy, setSortBy] = useState<string>(
    () => localStorage.getItem('cloud_storage_sort') || 'name-asc'
  )
  const [groupBy, setGroupBy] = useState<string>(
    () => localStorage.getItem('cloud_storage_group') || 'none'
  )

  const handleSortChange = (value: string) => {
    setSortBy(value)
    localStorage.setItem('cloud_storage_sort', value)
  }
  const handleGroupChange = (value: string) => {
    setGroupBy(value)
    localStorage.setItem('cloud_storage_group', value)
  }

  const statusRank: Record<string, number> = {
    connected: 0,
    success: 0,
    pending: 1,
    running: 1,
    unknown: 2,
    failed: 3,
    error: 3,
  }

  const statusGroupLabel = (status?: string | null) => {
    switch (status) {
      case 'connected':
      case 'success':
        return t('cloudStorage.groups.connected', { defaultValue: 'Connected' })
      case 'failed':
      case 'error':
        return t('cloudStorage.groups.failed', { defaultValue: 'Failed' })
      case 'pending':
      case 'running':
        return t('cloudStorage.groups.pending', { defaultValue: 'Pending' })
      default:
        return t('cloudStorage.groups.notTested', { defaultValue: 'Not tested' })
    }
  }

  const processedRemotes = useMemo(() => {
    let filtered = remotes
    const query = searchQuery.trim().toLowerCase()
    if (query) {
      filtered = filtered.filter(
        (remote) =>
          remote.name.toLowerCase().includes(query) || remote.provider.toLowerCase().includes(query)
      )
    }

    const sorted = [...filtered].sort((a, b) => {
      switch (sortBy) {
        case 'name-asc':
          return a.name.localeCompare(b.name)
        case 'name-desc':
          return b.name.localeCompare(a.name)
        case 'provider-asc':
          return a.provider.localeCompare(b.provider) || a.name.localeCompare(b.name)
        case 'status':
          return (
            (statusRank[a.last_test_status || 'unknown'] ?? 2) -
              (statusRank[b.last_test_status || 'unknown'] ?? 2) || a.name.localeCompare(b.name)
          )
        case 'usage-desc':
          return (b.usage_count ?? 0) - (a.usage_count ?? 0) || a.name.localeCompare(b.name)
        case 'usage-asc':
          return (a.usage_count ?? 0) - (b.usage_count ?? 0) || a.name.localeCompare(b.name)
        default:
          return 0
      }
    })

    if (groupBy === 'none') {
      return { groups: [{ name: null as string | null, remotes: sorted }] }
    }

    const grouped = new Map<string, RcloneRemote[]>()
    const keyFor = (remote: RcloneRemote) =>
      groupBy === 'provider' ? remote.provider : statusGroupLabel(remote.last_test_status)
    sorted.forEach((remote) => {
      const key = keyFor(remote)
      const bucket = grouped.get(key) ?? []
      bucket.push(remote)
      grouped.set(key, bucket)
    })
    const groups = Array.from(grouped.entries()).map(([name, list]) => ({ name, remotes: list }))
    return {
      groups: groups.length > 0 ? groups : [{ name: null as string | null, remotes: sorted }],
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [remotes, searchQuery, sortBy, groupBy, t])

  const totalAfterFilter = processedRemotes.groups.reduce((sum, g) => sum + g.remotes.length, 0)
  const hasUnfilteredRemotes = remotes.length > 0
  const showToolbar = isLoading || hasUnfilteredRemotes
  const browseItems = useMemo<StorageBrowserItem[] | null>(() => {
    if (!browseState) return null

    return browseState.entries.map((entry) => ({
      name: entry.name,
      path: joinBrowserPath(browseState.path, entry.path || entry.name),
      type: entry.is_dir ? 'directory' : 'file',
      size: entry.size,
      modified: entry.modified,
    }))
  }, [browseState])

  return (
    <Box component="section" aria-label={t('cloudStorage.title')}>
      <PageHeader
        title={t('cloudStorage.title')}
        subtitle={t('cloudStorage.subtitle')}
        actions={
          <>
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
              startIcon={<Plus size={18} />}
              disabled={!isAvailable || isLoading}
              onClick={onAddRemote}
              sx={{ width: { xs: '100%', md: 'auto' } }}
            >
              {t('cloudStorage.addRemote')}
            </Button>
          </>
        }
      />

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

      {showToolbar ? (
        <ListToolbar
          searchValue={searchQuery}
          onSearchChange={setSearchQuery}
          searchPlaceholder={t('cloudStorage.search', {
            defaultValue: 'Search cloud storage...',
          })}
          sortValue={sortBy}
          onSortChange={handleSortChange}
          sortOptions={[
            {
              value: 'name-asc',
              label: t('cloudStorage.sort.nameAZ', { defaultValue: 'Name A → Z' }),
            },
            {
              value: 'name-desc',
              label: t('cloudStorage.sort.nameZA', { defaultValue: 'Name Z → A' }),
            },
            {
              value: 'provider-asc',
              label: t('cloudStorage.sort.provider', { defaultValue: 'Provider' }),
            },
            {
              value: 'status',
              label: t('cloudStorage.sort.status', { defaultValue: 'Status (connected first)' }),
            },
            {
              value: 'usage-desc',
              label: t('cloudStorage.sort.usageMost', { defaultValue: 'Usage (most first)' }),
            },
            {
              value: 'usage-asc',
              label: t('cloudStorage.sort.usageLeast', { defaultValue: 'Usage (least first)' }),
            },
          ]}
          groupValue={groupBy}
          onGroupChange={handleGroupChange}
          groupOptions={[
            { value: 'none', label: t('cloudStorage.group.none', { defaultValue: 'No grouping' }) },
            {
              value: 'status',
              label: t('cloudStorage.group.status', { defaultValue: 'By status' }),
            },
            {
              value: 'provider',
              label: t('cloudStorage.group.provider', { defaultValue: 'By provider' }),
            },
          ]}
        />
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
      ) : !hasUnfilteredRemotes ? (
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
      ) : totalAfterFilter === 0 ? (
        <Paper
          variant="outlined"
          sx={{ borderRadius: 1, p: 3, textAlign: 'center', bgcolor: 'background.paper' }}
        >
          <Cloud size={34} />
          <Typography variant="h6" sx={{ mt: 1 }}>
            {t('cloudStorage.noMatch.title', { defaultValue: 'No matching remotes' })}
          </Typography>
          <Typography color="text.secondary" sx={{ mt: 0.5 }}>
            {searchQuery
              ? t('cloudStorage.noMatch.message', {
                  search: searchQuery,
                  defaultValue: `No remotes match "${searchQuery}".`,
                })
              : t('cloudStorage.noMatch.fallback', {
                  defaultValue: 'No remotes match the current filters.',
                })}
          </Typography>
          {searchQuery ? (
            <Button variant="outlined" sx={{ mt: 2 }} onClick={() => setSearchQuery('')}>
              {t('cloudStorage.noMatch.clearSearch', { defaultValue: 'Clear search' })}
            </Button>
          ) : null}
        </Paper>
      ) : (
        <Stack spacing={3}>
          {processedRemotes.groups.map((group, groupIndex) => (
            <Box key={group.name ?? `group-${groupIndex}`}>
              {group.name ? (
                <Typography
                  variant="h6"
                  sx={{
                    fontSize: '0.95rem',
                    fontWeight: 600,
                    color: 'primary.main',
                    mb: 1.5,
                  }}
                >
                  {group.name}
                  <Typography
                    component="span"
                    sx={{ ml: 1, color: 'text.disabled', fontWeight: 500 }}
                  >
                    ({group.remotes.length})
                  </Typography>
                </Typography>
              ) : null}
              <Box
                sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '1fr 1fr' }, gap: 2 }}
              >
                {group.remotes.map((remote) => (
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
            </Box>
          ))}
        </Stack>
      )}

      {onCreateRemote && onCloseAddRemote ? (
        <RcloneRemoteDialog
          open={addDialogOpen}
          isCreating={isCreating}
          error={createError}
          providers={providers}
          onClose={onCloseAddRemote}
          onCreate={onCreateRemote}
          onStartOAuth={onStartOAuth}
          onGetOAuthSession={onGetOAuthSession}
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
          providers={providers}
          onClose={onCloseEditRemote}
          onCreate={onUpdateRemote}
          onStartOAuth={onStartOAuth}
          onGetOAuthSession={onGetOAuthSession}
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

      <StorageBrowserDialog
        open={!!browseState}
        title={t('cloudStorage.browseTitle', { name: browseState?.remote.name })}
        subtitle={browseState?.remote.provider}
        currentPath={browseState?.path || ''}
        items={browseItems}
        isLoading={isBrowsing}
        rootLabel={t('archiveContents.root')}
        closeLabel={t('common.buttons.close')}
        emptyDirectoryLabel={t('cloudStorage.noEntries')}
        noInfoLabel={t('cloudStorage.noEntries')}
        maxWidth="md"
        onClose={() => onCloseBrowse?.()}
        onNavigate={(path) => {
          if (browseState) {
            onBrowseRemote?.(browseState.remote, path)
          }
        }}
      />
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

  const providersQuery = useQuery({
    queryKey: ['rclone-providers'],
    queryFn: async () => {
      const response = await rcloneAPI.getProviders()
      return response.data.providers
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
    mutationFn: async ({ remote, path }: { remote: RcloneRemote; path: string }) => {
      const normalizedPath = normalizeBrowserPath(path)
      setBrowseState({ remote, path: normalizedPath, entries: [] })
      const response = await rcloneAPI.browseRemote(remote.id, normalizedPath)
      return {
        remote,
        path: normalizeBrowserPath(response.data.path || normalizedPath),
        entries: (response.data.entries || []) as BrowseEntry[],
      }
    },
    onSuccess: ({ remote, path, entries }) => {
      const normalizedPath = normalizeBrowserPath(path)
      setBrowseState((current) => {
        if (
          !current ||
          current.remote.id !== remote.id ||
          normalizeBrowserPath(current.path) !== normalizedPath
        ) {
          return current
        }

        return { remote, path: normalizedPath, entries }
      })
    },
    onError: (error: unknown) => {
      toast.error(getApiMessage(error, t('cloudStorage.browseFailed')))
    },
  })

  const refreshAll = () => {
    queryClient.invalidateQueries({ queryKey: ['rclone-status'] })
    queryClient.invalidateQueries({ queryKey: ['rclone-remotes'] })
    queryClient.invalidateQueries({ queryKey: ['rclone-providers'] })
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
      providers={providersQuery.data}
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
      onStartOAuth={async (data) => {
        const response = await rcloneAPI.startOAuthSession(data)
        return response.data
      }}
      onGetOAuthSession={async (sessionId) => {
        const response = await rcloneAPI.getOAuthSession(sessionId)
        return response.data
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
      onBrowseRemote={(remote, path = '') => browseRemoteMutation.mutate({ remote, path })}
      onCloseBrowse={() => setBrowseState(null)}
    />
  )
}
