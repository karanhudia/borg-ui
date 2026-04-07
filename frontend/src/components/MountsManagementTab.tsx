import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Box, Typography, CircularProgress, Stack, Alert, Paper } from '@mui/material'
import { HardDrive, XCircle, Trash2, AlertCircle, FolderOpen, Copy } from 'lucide-react'
import SettingsCard from './SettingsCard'
import { mountsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import { formatDate } from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from './DataTable'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'

interface Mount {
  mount_id: string
  mount_point: string
  mount_type: string
  source: string
  created_at: string
  job_id: number | null
  repository_id: number | null
  connection_id: number | null
}

function getErrorDetail(error: unknown): string | undefined {
  if (
    typeof error === 'object' &&
    error !== null &&
    'response' in error &&
    typeof error.response === 'object' &&
    error.response !== null &&
    'data' in error.response &&
    typeof error.response.data === 'object' &&
    error.response.data !== null &&
    'detail' in error.response.data &&
    typeof error.response.data.detail === 'string'
  ) {
    return error.response.data.detail
  }

  return undefined
}

export default function MountsManagementTab() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageMounts = hasGlobalPermission('settings.mounts.manage')

  // Fetch active mounts
  const { data: mountsData, isLoading } = useQuery({
    queryKey: ['mounts'],
    queryFn: async () => {
      const response = await mountsAPI.listMounts()
      return response.data
    },
    enabled: canManageMounts,
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  // Unmount mutation
  const unmountMutation = useMutation({
    mutationFn: ({ mountId, force }: { mountId: string; force: boolean }) =>
      mountsAPI.unmountBorgArchive(mountId, force),
    onSuccess: () => {
      toast.success(t('mountsManagement.unmountedSuccessfully'))
      queryClient.invalidateQueries({ queryKey: ['mounts'] })
    },
    onError: (error: unknown) => {
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('mountsManagement.failedToUnmount')
      )
    },
  })

  const mounts: Mount[] = mountsData || []

  const handleUnmount = (mountId: string, force: boolean = false) => {
    track(EventCategory.MOUNT, force ? EventAction.DELETE : EventAction.UNMOUNT, {
      operation: force ? 'force_unmount' : 'unmount',
    })
    unmountMutation.mutate({ mountId, force })
  }

  const copyToClipboard = (text: string, label: string) => {
    navigator.clipboard.writeText(text)
    toast.success(t('mounts.copiedToClipboard', { label }))
  }

  // Define columns for DataTable
  const columns: Column<Mount>[] = [
    {
      id: 'source',
      label: t('mounts.columns.archive'),
      render: (mount) => {
        // Extract archive name and repo name from source (format: RepoName::archive-name)
        const parts = mount.source.split('::')
        const archiveName = parts.length > 1 ? parts[1] : parts[0]
        const repoName = parts.length > 1 ? parts[0] : ''

        return (
          <Box>
            <Typography variant="body2" fontWeight={600}>
              {archiveName}
            </Typography>
            {repoName && (
              <Typography
                variant="caption"
                sx={{
                  color: 'text.secondary',
                  opacity: 0.7,
                  display: 'block',
                  mt: 0.25,
                }}
              >
                {repoName}
              </Typography>
            )}
          </Box>
        )
      },
    },
    {
      id: 'mount_point',
      label: t('mounts.columns.mountLocation'),
      render: (mount) => {
        return (
          <Typography
            variant="body2"
            sx={{
              fontFamily: 'monospace',
              fontSize: '0.875rem',
              color: 'text.secondary',
            }}
          >
            {mount.mount_point}
          </Typography>
        )
      },
    },
    {
      id: 'created_at',
      label: t('mounts.columns.mounted'),
      render: (mount) => (
        <Typography variant="body2" sx={{ color: 'text.secondary' }}>
          {formatDate(mount.created_at)}
        </Typography>
      ),
    },
  ]

  // Define action buttons
  const actionButtons: ActionButton<Mount>[] = [
    {
      label: t('mounts.actions.copy'),
      icon: <Copy size={16} />,
      onClick: (mount) => {
        const containerName = 'borg-web-ui'
        const command = `docker exec -it ${containerName} bash -c "cd ${mount.mount_point} && bash"`
        copyToClipboard(command, t('mounts.actions.accessCommand'))
        track(EventCategory.MOUNT, EventAction.VIEW, { operation: 'copy_access_command' })
      },
      color: 'primary',
      tooltip: t('mounts.actions.copyAccessCommand'),
    },
    {
      label: t('mounts.actions.unmount'),
      icon: <Trash2 size={16} />,
      onClick: (mount) => handleUnmount(mount.mount_id, false),
      color: 'error',
      tooltip: t('mounts.actions.unmountArchive'),
    },
    {
      label: t('mounts.actions.forceUnmount'),
      icon: <XCircle size={16} />,
      onClick: (mount) => handleUnmount(mount.mount_id, true),
      color: 'error',
      tooltip: t('mounts.actions.forceUnmountTooltip'),
    },
  ]

  if (!canManageMounts) {
    return null
  }

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', py: 8 }}>
        <CircularProgress />
      </Box>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Stack
        direction={{ xs: 'column', sm: 'row' }}
        justifyContent="space-between"
        alignItems={{ xs: 'flex-start', sm: 'center' }}
        sx={{ mb: 3 }}
        spacing={1.5}
      >
        <Box>
          <Typography variant="h5" fontWeight={700} gutterBottom>
            {t('mountsManagement.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('mountsManagement.subtitle')}
          </Typography>
        </Box>
      </Stack>

      {/* Info Alert */}
      <Alert severity="info" sx={{ mb: 3 }} icon={<AlertCircle size={20} />}>
        <Typography variant="body2">{t('mounts.infoAlert')}</Typography>
      </Alert>

      {/* No mounts message */}
      {mounts.length === 0 ? (
        <SettingsCard>
          <Stack alignItems="center" spacing={2} sx={{ py: 4 }}>
            <FolderOpen size={48} color="#999" />
            <Typography variant="h6" color="text.secondary">
              {t('mountsManagement.empty')}
            </Typography>
            <Typography variant="body2" color="text.secondary" textAlign="center">
              {t('mounts.emptyDescription')}
            </Typography>
          </Stack>
        </SettingsCard>
      ) : (
        <>
          {/* Summary */}
          <Paper sx={{ p: 2, mb: 3, bgcolor: 'background.default' }}>
            <Stack direction="row" spacing={3} alignItems="center">
              <HardDrive size={24} />
              <Box>
                <Typography variant="body2" color="text.secondary">
                  {t('mounts.activeMounts')}
                </Typography>
                <Typography variant="h5" fontWeight={700}>
                  {mounts.length}
                </Typography>
              </Box>
            </Stack>
          </Paper>

          {/* Mounts Table */}
          <DataTable<Mount>
            columns={columns}
            data={mounts}
            actions={actionButtons}
            getRowKey={(mount) => mount.mount_id}
          />
        </>
      )}
    </Box>
  )
}
