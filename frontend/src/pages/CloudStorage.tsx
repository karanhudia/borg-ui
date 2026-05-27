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
  DialogContent,
  DialogTitle,
  Divider,
  IconButton,
  List,
  ListItem,
  ListItemIcon,
  ListItemText,
  Paper,
  Skeleton,
  Stack,
  Typography,
} from '@mui/material'
import {
  AlertTriangle,
  CheckCircle,
  Cloud,
  File,
  Folder,
  Plus,
  RefreshCw,
  Search,
  XCircle,
} from 'lucide-react'
import { rcloneAPI } from '../services/api'
import type { RcloneRemote, RcloneStatus } from '../services/api'
import { getApiErrorDetail } from '../utils/apiErrors'
import { translateBackendKey } from '../utils/translateBackendKey'
import RcloneRemoteDialog from '../components/wizard/RcloneRemoteDialog'
import type { RcloneRemoteCreateInput } from '../components/wizard/RcloneRemoteDialog'

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
  testingRemoteId?: number | null
  browseState?: BrowseState | null
  isBrowsing?: boolean
  addDialogOpen?: boolean
  createError?: string | null
  loadError?: string | null
  onRefresh?: () => void
  onAddRemote?: () => void
  onCloseAddRemote?: () => void
  onCreateRemote?: (data: RcloneRemoteCreateInput) => Promise<void> | void
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

export function CloudStorageContent({
  status,
  remotes,
  isLoading = false,
  isRefreshing = false,
  isCreating = false,
  testingRemoteId = null,
  browseState = null,
  isBrowsing = false,
  addDialogOpen = false,
  createError = null,
  loadError = null,
  onRefresh,
  onAddRemote,
  onCloseAddRemote,
  onCreateRemote,
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
    <Box>
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', md: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'stretch', md: 'center' },
          gap: 2,
          mb: 3,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Cloud size={32} />
          <Box>
            <Typography variant="h4">{t('cloudStorage.title')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('cloudStorage.subtitle')}
            </Typography>
          </Box>
        </Box>
        <Stack direction="row" spacing={1} sx={{ alignSelf: { xs: 'flex-start', md: 'center' } }}>
          <IconButton
            onClick={onRefresh}
            disabled={isRefreshing}
            title={t('common.buttons.refresh')}
          >
            {isRefreshing ? <CircularProgress size={20} /> : <RefreshCw size={20} />}
          </IconButton>
          <Button
            variant="contained"
            startIcon={<Plus size={16} />}
            disabled={!isAvailable || isLoading}
            onClick={onAddRemote}
          >
            {t('cloudStorage.addRemote')}
          </Button>
        </Stack>
      </Box>

      <Paper variant="outlined" sx={{ borderRadius: 1, mb: 3, overflow: 'hidden' }}>
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: { xs: '1fr', sm: 'repeat(3, 1fr)' },
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
            <Paper
              key={remote.id}
              variant="outlined"
              data-testid={`cloud-storage-remote-${remote.name}`}
              sx={{ borderRadius: 1, p: 2 }}
            >
              <Stack
                direction={{ xs: 'column', sm: 'row' }}
                spacing={1.5}
                justifyContent="space-between"
                alignItems={{ xs: 'flex-start', sm: 'center' }}
              >
                <Box sx={{ minWidth: 0 }}>
                  <Typography variant="h6" noWrap>
                    {remote.name}
                  </Typography>
                  <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap sx={{ mt: 0.75 }}>
                    <Chip size="small" label={remote.provider} />
                    <Chip
                      size="small"
                      color={statusColor(remote.last_test_status)}
                      variant="outlined"
                      label={formatStatus(remote)}
                    />
                    <Chip
                      size="small"
                      variant="outlined"
                      label={t('cloudStorage.usageCount', {
                        count: remote.usage_count ?? 0,
                      })}
                    />
                  </Stack>
                </Box>
                <Stack direction="row" spacing={1}>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={
                      testingRemoteId === remote.id ? (
                        <CircularProgress size={14} />
                      ) : (
                        <CheckCircle size={14} />
                      )
                    }
                    disabled={testingRemoteId === remote.id}
                    onClick={() => onTestRemote?.(remote)}
                  >
                    {t('cloudStorage.testConnection')}
                  </Button>
                  <Button
                    size="small"
                    variant="outlined"
                    startIcon={<Search size={14} />}
                    disabled={isBrowsing}
                    onClick={() => onBrowseRemote?.(remote)}
                  >
                    {t('cloudStorage.browseRemote')}
                  </Button>
                </Stack>
              </Stack>
              {remote.last_error ? (
                <>
                  <Divider sx={{ my: 1.5 }} />
                  <Typography variant="body2" color="error">
                    {remote.last_error}
                  </Typography>
                </>
              ) : null}
            </Paper>
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
      testingRemoteId={testingRemoteId}
      browseState={browseState}
      isBrowsing={browseRemoteMutation.isPending}
      addDialogOpen={addDialogOpen}
      createError={
        createRemoteMutation.error
          ? getApiMessage(createRemoteMutation.error, t('wizard.location.rcloneCreateFailed'))
          : null
      }
      loadError={loadError}
      onRefresh={refreshAll}
      onAddRemote={() => setAddDialogOpen(true)}
      onCloseAddRemote={() => setAddDialogOpen(false)}
      onCreateRemote={async (data) => {
        await createRemoteMutation.mutateAsync(data)
      }}
      onTestRemote={(remote) => testRemoteMutation.mutate(remote)}
      onBrowseRemote={(remote) => browseRemoteMutation.mutate(remote)}
      onCloseBrowse={() => setBrowseState(null)}
    />
  )
}
