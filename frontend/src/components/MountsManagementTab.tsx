import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Box,
  Typography,
  CircularProgress,
  Stack,
  Alert,
  Paper,
  Card,
  CardContent,
} from '@mui/material'
import { HardDrive, XCircle, Trash2, AlertCircle, FolderOpen, Copy } from 'lucide-react'
import { mountsAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import { formatDate } from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from './DataTable'

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

export default function MountsManagementTab() {
  const queryClient = useQueryClient()

  // Fetch active mounts
  const { data: mountsData, isLoading } = useQuery({
    queryKey: ['mounts'],
    queryFn: async () => {
      const response = await mountsAPI.listMounts()
      return response.data
    },
    refetchInterval: 10000, // Refresh every 10 seconds
  })

  // Unmount mutation
  const unmountMutation = useMutation({
    mutationFn: ({ mountId, force }: { mountId: string; force: boolean }) =>
      mountsAPI.unmountBorgArchive(mountId, force),
    onSuccess: () => {
      toast.success('Archive unmounted successfully')
      queryClient.invalidateQueries({ queryKey: ['mounts'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to unmount path')
    },
  })

  const mounts: Mount[] = mountsData || []

  const handleUnmount = (mountId: string, force: boolean = false) => {
    unmountMutation.mutate({ mountId, force })
  }

  const copyToClipboard = (text: string, label: string = 'Mount point') => {
    navigator.clipboard.writeText(text)
    toast.success(`${label} copied to clipboard`)
  }

  // Define columns for DataTable
  const columns: Column<Mount>[] = [
    {
      id: 'source',
      label: 'Archive',
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
      label: 'Mount Location',
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
      label: 'Mounted',
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
      label: 'Copy',
      icon: <Copy size={16} />,
      onClick: (mount) => {
        const containerName = 'borg-web-ui'
        const command = `docker exec -it ${containerName} bash -c "cd ${mount.mount_point} && bash"`
        copyToClipboard(command, 'Access command')
      },
      color: 'primary',
      tooltip: 'Copy access command',
    },
    {
      label: 'Unmount',
      icon: <Trash2 size={16} />,
      onClick: (mount) => handleUnmount(mount.mount_id, false),
      color: 'error',
      tooltip: 'Unmount archive',
    },
    {
      label: 'Force Unmount',
      icon: <XCircle size={16} />,
      onClick: (mount) => handleUnmount(mount.mount_id, true),
      color: 'error',
      tooltip: 'Force unmount (use if busy)',
    },
  ]

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
      <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 3 }}>
        <Box>
          <Typography variant="h5" fontWeight={700} gutterBottom>
            Active Mounts
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage mounted Borg archives. Archives are automatically unmounted on container restart.
          </Typography>
        </Box>
      </Stack>

      {/* Info Alert */}
      <Alert severity="info" sx={{ mb: 3 }} icon={<AlertCircle size={20} />}>
        <Typography variant="body2">
          <strong>Note:</strong> Mounted archives appear as read-only filesystems in your file
          manager. Access them at the mount point path. Mounts are automatically cleaned up on
          container restart.
        </Typography>
      </Alert>

      {/* No mounts message */}
      {mounts.length === 0 ? (
        <Card>
          <CardContent>
            <Stack alignItems="center" spacing={2} sx={{ py: 4 }}>
              <FolderOpen size={48} color="#999" />
              <Typography variant="h6" color="text.secondary">
                No Active Mounts
              </Typography>
              <Typography variant="body2" color="text.secondary" textAlign="center">
                Mount archives from the Archives page to browse their contents directly in your file
                manager.
              </Typography>
            </Stack>
          </CardContent>
        </Card>
      ) : (
        <>
          {/* Summary */}
          <Paper sx={{ p: 2, mb: 3, bgcolor: 'background.default' }}>
            <Stack direction="row" spacing={3} alignItems="center">
              <HardDrive size={24} />
              <Box>
                <Typography variant="body2" color="text.secondary">
                  Active Mounts
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
