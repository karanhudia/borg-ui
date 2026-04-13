import { useState, useEffect } from 'react'
import { Navigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sshKeysAPI } from '../services/api'
import {
  Box,
  Typography,
  Button,
  Stack,
  Chip,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Skeleton,
  Alert,
  Tooltip,
  InputAdornment,
  Checkbox,
  FormControlLabel,
  useTheme,
  alpha,
} from '@mui/material'
import {
  Key,
  Copy,
  RefreshCw,
  Wifi,
  CheckCircle,
  XCircle,
  Plus,
  Trash2,
  Info,
  Eye,
  EyeOff,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { translateBackendKey } from '../utils/translateBackendKey'
import RemoteMachineCard from '../components/RemoteMachineCard'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'

interface StorageInfo {
  total: number
  total_formatted: string
  used: number
  used_formatted: string
  available: number
  available_formatted: string
  percent_used: number
  last_check?: string | null
}

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path?: string
  ssh_path_prefix?: string
  mount_point?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  created_at: string
}

interface ImportKeyPayload extends Record<string, unknown> {
  name: string
  private_key_path: string
  public_key_path: string
  description: string
}

interface DeployConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
  password: string
  use_sftp_mode: boolean
  default_path: string
  ssh_path_prefix: string
  mount_point: string
}

interface TestConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
}

interface UpdateConnectionPayload extends Record<string, unknown> {
  host: string
  username: string
  port: number
  use_sftp_mode: boolean
  use_sudo: boolean
  default_path: string
  ssh_path_prefix: string
  mount_point: string
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

export default function SSHConnectionsSingleKey() {
  const { t } = useTranslation()
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageSsh = hasGlobalPermission('settings.ssh.manage')
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  // State
  const [keyVisible, setKeyVisible] = useState(false)
  const [fingerprintVisible, setFingerprintVisible] = useState(false)
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false)
  const [importDialogOpen, setImportDialogOpen] = useState(false)
  const [deployDialogOpen, setDeployDialogOpen] = useState(false)
  const [testConnectionDialogOpen, setTestConnectionDialogOpen] = useState(false)
  const [editConnectionDialogOpen, setEditConnectionDialogOpen] = useState(false)
  const [deleteConnectionDialogOpen, setDeleteConnectionDialogOpen] = useState(false)
  const [deleteKeyDialogOpen, setDeleteKeyDialogOpen] = useState(false)
  const [redeployKeyDialogOpen, setRedeployKeyDialogOpen] = useState(false)
  const [selectedConnection, setSelectedConnection] = useState<SSHConnection | null>(null)
  const [keyType, setKeyType] = useState('ed25519')
  const [redeployPassword, setRedeployPassword] = useState('')
  const [importForm, setImportForm] = useState({
    name: 'System SSH Key',
    private_key_path: '',
    public_key_path: '',
    description: 'Imported system SSH key for all remote connections',
  })
  const [connectionForm, setConnectionForm] = useState({
    host: '',
    username: '',
    port: 22,
    password: '',
    use_sftp_mode: true,
    default_path: '',
    ssh_path_prefix: '',
    mount_point: '',
  })
  const [testConnectionForm, setTestConnectionForm] = useState({
    host: '',
    username: '',
    port: 22,
  })
  const [editConnectionForm, setEditConnectionForm] = useState({
    host: '',
    username: '',
    port: 22,
    use_sftp_mode: true,
    use_sudo: false,
    default_path: '',
    ssh_path_prefix: '',
    mount_point: '',
  })

  // Queries
  const { data: systemKeyData, isLoading: keyLoading } = useQuery({
    queryKey: ['system-ssh-key'],
    queryFn: sshKeysAPI.getSystemKey,
    enabled: canManageSsh,
    refetchInterval: 30000,
  })

  const { data: connectionsData, isLoading: connectionsLoading } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    enabled: canManageSsh,
    refetchInterval: 30000,
  })

  const systemKey = systemKeyData?.data?.ssh_key
  const keyExists = systemKeyData?.data?.exists
  const connections: SSHConnection[] = connectionsData?.data?.connections || []

  // Statistics
  const stats = {
    totalConnections: connections.length,
    activeConnections: connections.filter((c) => c.status === 'connected').length,
    failedConnections: connections.filter((c) => c.status === 'failed').length,
  }

  // Mutations
  const generateKeyMutation = useMutation({
    mutationFn: (data: { name: string; key_type: string; description?: string }) =>
      sshKeysAPI.generateSSHKey(data),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyGenerated'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setGenerateDialogOpen(false)
      track(EventCategory.SSH, EventAction.CREATE, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to generate SSH key:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('sshConnections.toasts.keyGenerateFailed')
      )
    },
  })

  const importKeyMutation = useMutation({
    mutationFn: (data: ImportKeyPayload) => sshKeysAPI.importSSHKey(data),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyImported'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setImportDialogOpen(false)
      setImportForm({
        name: 'System SSH Key',
        private_key_path: '',
        public_key_path: '',
        description: 'Imported system SSH key for all remote connections',
      })
      track(EventCategory.SSH, EventAction.UPLOAD, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to import SSH key:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('sshConnections.toasts.keyImportFailed')
      )
    },
  })

  const deployKeyMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: DeployConnectionPayload }) =>
      sshKeysAPI.deploySSHKey(data.keyId, data.connectionData),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyDeployed'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeployDialogOpen(false)
      setConnectionForm({
        host: '',
        username: '',
        port: 22,
        password: '',
        use_sftp_mode: true,
        default_path: '',
        ssh_path_prefix: '',
        mount_point: '',
      })
      track(EventCategory.SSH, EventAction.CREATE, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to deploy SSH key:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('sshConnections.toasts.keyDeployFailed')
      )
    },
  })

  const testConnectionMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: TestConnectionPayload }) =>
      sshKeysAPI.testSSHConnection(data.keyId, data.connectionData),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.connectionTestSuccess'))
        track(EventCategory.SSH, EventAction.TEST, { resource: 'connection' })
      } else {
        toast.error(t('sshConnections.toasts.connectionTestFailed'))
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
    },
    onError: (error: unknown) => {
      console.error('Failed to test connection:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) ||
          t('sshConnections.toasts.connectionTestFailed')
      )
    },
  })

  const updateConnectionMutation = useMutation({
    mutationFn: (data: { connectionId: number; connectionData: UpdateConnectionPayload }) =>
      sshKeysAPI.updateSSHConnection(data.connectionId, data.connectionData),
    onSuccess: async (_response, variables) => {
      toast.success(t('sshConnections.toasts.connectionUpdated'))
      setEditConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.EDIT, { resource: 'connection' })

      // Automatically test the connection after update
      try {
        await sshKeysAPI.testExistingConnection(variables.connectionId)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      } catch (error: unknown) {
        // Test failure is already shown in the connection status
        console.error('Failed to test connection:', error)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      }
    },
    onError: (error: unknown) => {
      console.error('Failed to update connection:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) ||
          t('sshConnections.toasts.connectionUpdateFailed')
      )
    },
  })

  const deleteConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.deleteSSHConnection(connectionId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.connectionDeleted'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.DELETE, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to delete connection:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) ||
          t('sshConnections.toasts.connectionDeleteFailed')
      )
    },
  })

  const refreshStorageMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.refreshConnectionStorage(connectionId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.storageRefreshed'))
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.VIEW, { resource: 'storage' })
    },
    onError: (error: unknown) => {
      console.error('Failed to refresh storage:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) ||
          t('sshConnections.toasts.storageRefreshFailed')
      )
    },
  })

  const testExistingConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.testExistingConnection(connectionId),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.connectionTestSuccess'))
      } else {
        toast.error(
          translateBackendKey(response.data.error) ||
            t('sshConnections.toasts.connectionTestFailed')
        )
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.TEST, { resource: 'connection' })
    },
    onError: (error: unknown) => {
      console.error('Failed to test connection:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) ||
          t('sshConnections.toasts.connectionTestFailed')
      )
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: number) => sshKeysAPI.deleteSSHKey(keyId),
    onSuccess: () => {
      toast.success(t('sshConnections.toasts.keyDeleted'))
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteKeyDialogOpen(false)
      track(EventCategory.SSH, EventAction.DELETE, { resource: 'key' })
    },
    onError: (error: unknown) => {
      console.error('Failed to delete SSH key:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('sshConnections.toasts.keyDeleteFailed')
      )
    },
  })

  const redeployKeyMutation = useMutation({
    mutationFn: ({ connectionId, password }: { connectionId: number; password: string }) =>
      sshKeysAPI.redeployKeyToConnection(connectionId, password),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success(t('sshConnections.toasts.keyDeployed'))
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        setRedeployKeyDialogOpen(false)
        setRedeployPassword('')
        track(EventCategory.SSH, EventAction.START, {
          resource: 'connection',
          operation: 'deploy_key',
        })
      } else {
        toast.error(
          translateBackendKey(response.data.error) || t('sshConnections.toasts.keyDeployFailed')
        )
      }
    },
    onError: (error: unknown) => {
      console.error('Failed to redeploy SSH key:', error)
      toast.error(
        translateBackendKey(getErrorDetail(error)) || t('sshConnections.toasts.keyDeployFailed')
      )
    },
  })

  // Auto-refresh storage for connections without storage info
  useEffect(() => {
    if (!canManageSsh) {
      return
    }
    if (connections && connections.length > 0) {
      const connectionsWithoutStorage = connections.filter((conn) => !conn.storage)

      if (connectionsWithoutStorage.length > 0) {
        // Refresh storage for each connection without storage (silently)
        connectionsWithoutStorage.forEach((conn) => {
          sshKeysAPI.refreshConnectionStorage(conn.id).catch(() => {
            // Silently fail - will show "No storage info" in card
          })
        })

        // Invalidate query after delay to show updated data
        setTimeout(() => {
          queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        }, 2000)
      }
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [connections?.length])

  if (!canManageSsh) {
    return <Navigate to="/dashboard" replace />
  }

  // Handlers
  const handleGenerateKey = () => {
    generateKeyMutation.mutate({
      name: 'System SSH Key',
      key_type: keyType,
      description: 'System SSH key for all remote connections',
    })
  }

  const handleImportKey = () => {
    importKeyMutation.mutate(importForm)
  }

  const handleCopyPublicKey = () => {
    if (systemKey?.public_key) {
      navigator.clipboard.writeText(systemKey.public_key)
      toast.success(t('sshConnections.toasts.publicKeyCopied'))
    }
  }

  const handleDeployKey = () => {
    if (!systemKey) return
    deployKeyMutation.mutate({
      keyId: systemKey.id,
      connectionData: connectionForm,
    })
  }

  const handleTestManualConnection = () => {
    if (!systemKey) return
    testConnectionMutation.mutate({
      keyId: systemKey.id,
      connectionData: testConnectionForm,
    })
    setTestConnectionDialogOpen(false)
    setTestConnectionForm({ host: '', username: '', port: 22 })
  }

  const handleEditConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setEditConnectionForm({
      host: connection.host,
      username: connection.username,
      port: connection.port,
      use_sftp_mode: connection.use_sftp_mode,
      use_sudo: connection.use_sudo,
      default_path: connection.default_path || '',
      ssh_path_prefix: connection.ssh_path_prefix || '',
      mount_point: connection.mount_point || '',
    })
    setEditConnectionDialogOpen(true)
  }

  const handleUpdateConnection = () => {
    if (!selectedConnection) return
    updateConnectionMutation.mutate({
      connectionId: selectedConnection.id,
      connectionData: editConnectionForm,
    })
  }

  const handleDeleteConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setDeleteConnectionDialogOpen(true)
  }

  const confirmDeleteConnection = () => {
    if (!selectedConnection) return
    deleteConnectionMutation.mutate(selectedConnection.id)
  }

  const handleTestConnection = (connection: SSHConnection) => {
    testExistingConnectionMutation.mutate(connection.id)
  }

  const handleDeployKeyToConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setRedeployKeyDialogOpen(true)
  }

  const handleConfirmRedeployKey = () => {
    if (!selectedConnection || !redeployPassword) return
    redeployKeyMutation.mutate({
      connectionId: selectedConnection.id,
      password: redeployPassword,
    })
  }

  const handleDeleteKey = () => {
    if (!systemKey) return
    deleteKeyMutation.mutate(systemKey.id)
  }

  if (keyLoading || connectionsLoading) {
    return (
      <Box>
        {/* Header skeleton */}
        <Box sx={{ mb: 4 }}>
          <Skeleton
            variant="text"
            width={200}
            height={36}
            sx={{ transform: 'none', borderRadius: 0.5, mb: 0.75 }}
          />
          <Skeleton
            variant="text"
            width={320}
            height={16}
            sx={{ transform: 'none', borderRadius: 0.5 }}
          />
        </Box>

        {/* Stats band skeleton */}
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            borderRadius: 2,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 3,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
          }}
        >
          {[0, 1, 2].map((i) => (
            <Box
              key={i}
              sx={{
                px: { xs: 1.25, sm: 2 },
                py: { xs: 1.5, sm: 1.75 },
                borderRight: i < 2 ? '1px solid' : 0,
                borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              }}
            >
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: { xs: 0.75, sm: 0.5 } }}
              >
                <Skeleton variant="rounded" width={13} height={13} sx={{ borderRadius: 0.5 }} />
                <Skeleton
                  variant="text"
                  width={80}
                  height={12}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
              <Skeleton
                variant="text"
                width={32}
                sx={{ transform: 'none', borderRadius: 0.5, height: { xs: 28, sm: 24 } }}
              />
            </Box>
          ))}
        </Box>

        {/* System SSH Key card skeleton */}
        <Box
          sx={{
            borderRadius: 2,
            bgcolor: 'background.paper',
            overflow: 'hidden',
            mb: 3,
            boxShadow: isDark
              ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
              : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
          }}
        >
          <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: { xs: 2, sm: 2.5 }, pb: { xs: 2, sm: 2.5 } }}>
            <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
              <Skeleton
                variant="rounded"
                width={34}
                height={34}
                sx={{ borderRadius: 1.5, flexShrink: 0 }}
              />
              <Skeleton
                variant="text"
                width={140}
                height={24}
                sx={{ transform: 'none', borderRadius: 0.5, flex: 1 }}
              />
              <Skeleton variant="rounded" width={64} height={22} sx={{ borderRadius: 3 }} />
            </Stack>
            <Stack spacing={2}>
              <Box>
                <Skeleton
                  variant="text"
                  width={48}
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width={80}
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
              <Box>
                <Skeleton
                  variant="text"
                  width={80}
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
                <Skeleton
                  variant="text"
                  width="60%"
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5 }}
                />
              </Box>
              <Box>
                <Skeleton
                  variant="text"
                  width={70}
                  height={20}
                  sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
                />
                <Skeleton variant="rounded" width="100%" height={55} sx={{ borderRadius: 1 }} />
              </Box>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2}>
                <Skeleton variant="rounded" width={160} height={36} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" width={140} height={36} sx={{ borderRadius: 1 }} />
                <Skeleton variant="rounded" width={120} height={36} sx={{ borderRadius: 1 }} />
              </Stack>
            </Stack>
          </Box>
        </Box>

        {/* Remote Connections section skeleton */}
        <Box>
          {/* Section header */}
          <Box
            sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 2 }}
          >
            <Box>
              <Skeleton
                variant="text"
                width={160}
                height={24}
                sx={{ transform: 'none', borderRadius: 0.5, mb: 0.4 }}
              />
              <Skeleton
                variant="text"
                width={120}
                height={14}
                sx={{ transform: 'none', borderRadius: 0.5 }}
              />
            </Box>
            <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
          </Box>

          {/* Connection cards — flex wrap matching real RemoteMachineCard layout */}
          <Box sx={{ display: 'flex', flexWrap: 'wrap', gap: { xs: 2, sm: 2.5 } }}>
            {[0, 1, 2].map((i) => (
              <Box
                key={i}
                sx={{
                  flex: {
                    xs: '0 0 100%',
                    sm: '0 0 calc(50% - 10px)',
                    md: '0 0 calc(33.333% - 14px)',
                  },
                  minWidth: 0,
                  display: 'flex',
                }}
              >
                <Box
                  sx={{
                    width: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    borderRadius: 2,
                    bgcolor: 'background.paper',
                    boxShadow: isDark
                      ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
                      : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
                    opacity: Math.max(0.4, 1 - i * 0.2),
                  }}
                >
                  <Box
                    sx={{
                      flex: 1,
                      display: 'flex',
                      flexDirection: 'column',
                      px: { xs: 1.75, sm: 2 },
                      pt: { xs: 1.75, sm: 2 },
                      pb: { xs: 1.5, sm: 1.75 },
                    }}
                  >
                    {/* Header: status + name + connection string */}
                    <Box sx={{ mb: 1.5 }}>
                      <Box
                        sx={{
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'space-between',
                          mb: 0.5,
                        }}
                      >
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                          <Skeleton variant="circular" width={13} height={13} />
                          <Skeleton
                            variant="text"
                            width={60}
                            height={12}
                            sx={{ transform: 'none', borderRadius: 0.5 }}
                          />
                        </Box>
                        <Skeleton
                          variant="text"
                          width={70}
                          height={10}
                          sx={{ transform: 'none', borderRadius: 0.5 }}
                        />
                      </Box>
                      <Skeleton
                        variant="text"
                        width={[160, 130, 150][i]}
                        height={22}
                        sx={{ transform: 'none', borderRadius: 0.5, mb: 0.25 }}
                      />
                      <Skeleton
                        variant="text"
                        width={[180, 200, 170][i]}
                        height={14}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Box>

                    {/* Storage stats band: 2-col + progress bar */}
                    <Box
                      sx={{
                        borderRadius: 1.5,
                        border: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                        overflow: 'hidden',
                        mb: 1.5,
                      }}
                    >
                      <Box sx={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)' }}>
                        {[0, 1].map((j) => (
                          <Box
                            key={j}
                            sx={{
                              px: { xs: 1.25, sm: 1.5 },
                              py: { xs: 1.25, sm: 1 },
                              borderRight: j === 0 ? '1px solid' : 0,
                              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                            }}
                          >
                            <Skeleton
                              variant="text"
                              width={30}
                              height={10}
                              sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
                            />
                            <Skeleton
                              variant="text"
                              width={50}
                              height={18}
                              sx={{ transform: 'none', borderRadius: 0.5 }}
                            />
                          </Box>
                        ))}
                      </Box>
                      <Box
                        sx={{
                          px: { xs: 1.25, sm: 1.5 },
                          pb: 1,
                          pt: 0.75,
                          borderTop: '1px solid',
                          borderColor: isDark ? alpha('#fff', 0.05) : alpha('#000', 0.06),
                        }}
                      >
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                          <Skeleton
                            variant="text"
                            width={50}
                            height={10}
                            sx={{ transform: 'none', borderRadius: 0.5 }}
                          />
                          <Skeleton
                            variant="text"
                            width={60}
                            height={10}
                            sx={{ transform: 'none', borderRadius: 0.5 }}
                          />
                        </Box>
                        <Skeleton
                          variant="rounded"
                          width="100%"
                          height={5}
                          sx={{ borderRadius: 1 }}
                        />
                      </Box>
                    </Box>

                    {/* Action bar */}
                    <Box
                      sx={{
                        mt: 'auto',
                        display: 'flex',
                        alignItems: 'center',
                        gap: { xs: 0.75, sm: 0.5 },
                        pt: { xs: 1.5, sm: 1.25 },
                        borderTop: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                      }}
                    >
                      {[0, 1, 2, 3, 4].map((j) => (
                        <Skeleton
                          key={j}
                          variant="rounded"
                          width={34}
                          height={34}
                          sx={{ borderRadius: 1.5 }}
                        />
                      ))}
                    </Box>
                  </Box>
                </Box>
              </Box>
            ))}
          </Box>
        </Box>
      </Box>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <Typography variant="h4" fontWeight={600}>
            {t('sshConnections.title')}
          </Typography>
          <Tooltip
            title={
              <Box>
                <Typography variant="body2" fontWeight={600} sx={{ mb: 0.5 }}>
                  {t('sshConnections.singleKeySystem.title')}
                </Typography>
                <Typography variant="body2">
                  {t('sshConnections.singleKeySystem.description')}
                </Typography>
              </Box>
            }
            arrow
          >
            <Info
              size={16}
              style={{ color: 'inherit', opacity: 0.45, cursor: 'help', flexShrink: 0 }}
            />
          </Tooltip>
        </Box>
        <Typography variant="body2" color="text.secondary">
          {t('sshConnections.subtitle')}
        </Typography>
      </Box>

      {/* Statistics Band */}
      {keyExists && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(3, 1fr)',
            borderRadius: 2,
            border: '1px solid',
            borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
            overflow: 'hidden',
            mb: 3,
            bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
            boxShadow: isDark
              ? `0 0 0 1px ${alpha('#fff', 0.04)}, 0 2px 8px ${alpha('#000', 0.2)}`
              : `0 0 0 1px ${alpha('#000', 0.06)}, 0 2px 6px ${alpha('#000', 0.05)}`,
          }}
        >
          {[
            {
              label: t('sshConnections.stats.totalConnections'),
              value: stats.totalConnections,
              icon: <Wifi size={13} />,
              color: theme.palette.primary.main,
            },
            {
              label: t('sshConnections.stats.active'),
              value: stats.activeConnections,
              icon: <CheckCircle size={13} />,
              color: theme.palette.success.main,
            },
            {
              label: t('sshConnections.stats.failed'),
              value: stats.failedConnections,
              icon: <XCircle size={13} />,
              color: theme.palette.error.main,
            },
          ].map((stat, i) => (
            <Box
              key={stat.label}
              sx={{
                px: { xs: 1.25, sm: 2 },
                py: { xs: 1.5, sm: 1.75 },
                borderRight: i < 2 ? '1px solid' : 0,
                borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              }}
            >
              <Box
                sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mb: { xs: 0.75, sm: 0.5 } }}
              >
                <Box
                  sx={{
                    color: alpha(stat.color, 0.75),
                    display: 'flex',
                    alignItems: 'center',
                    flexShrink: 0,
                  }}
                >
                  {stat.icon}
                </Box>
                <Typography
                  sx={{
                    fontSize: { xs: '0.58rem', sm: '0.6rem' },
                    fontWeight: 700,
                    textTransform: 'uppercase',
                    letterSpacing: '0.04em',
                    color: alpha(stat.color, 0.75),
                    lineHeight: 1.2,
                    whiteSpace: 'nowrap',
                  }}
                >
                  {stat.label}
                </Typography>
              </Box>
              <Typography
                sx={{
                  fontSize: { xs: '1.75rem', sm: '1.5rem' },
                  fontWeight: 700,
                  lineHeight: 1,
                  fontVariantNumeric: 'tabular-nums',
                }}
              >
                {stat.value}
              </Typography>
            </Box>
          ))}
        </Box>
      )}

      {/* System SSH Key Card */}
      <Box
        sx={{
          borderRadius: 2,
          bgcolor: 'background.paper',
          overflow: 'hidden',
          mb: 3,
          boxShadow: isDark
            ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
            : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
        }}
      >
        <Box sx={{ px: { xs: 2, sm: 2.5 }, pt: { xs: 2, sm: 2.5 }, pb: { xs: 2, sm: 2.5 } }}>
          <Stack direction="row" alignItems="center" spacing={1.5} sx={{ mb: 2 }}>
            <Box
              sx={{
                width: 34,
                height: 34,
                borderRadius: 1.5,
                bgcolor: isDark
                  ? alpha(theme.palette.primary.main, 0.15)
                  : alpha(theme.palette.primary.main, 0.1),
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: theme.palette.primary.main,
                flexShrink: 0,
              }}
            >
              <Key size={18} />
            </Box>
            <Typography variant="h6" fontWeight={600} sx={{ flex: 1 }}>
              {t('sshConnections.systemKey.title')}
            </Typography>
            {keyExists && (
              <Chip label="Active" color="success" size="small" icon={<CheckCircle size={14} />} />
            )}
          </Stack>

          {!keyExists ? (
            // No key exists - show generation UI
            <Box>
              <Alert severity="warning" sx={{ mb: 2 }}>
                {t('sshConnections.systemKey.noKey')}
              </Alert>
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  startIcon={<Plus size={18} />}
                  onClick={() => setGenerateDialogOpen(true)}
                >
                  {t('sshConnections.systemKey.generate')}
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Key size={18} />}
                  onClick={() => setImportDialogOpen(true)}
                >
                  {t('sshConnections.systemKey.import')}
                </Button>
              </Stack>
            </Box>
          ) : (
            // Key exists - show key details
            <Box>
              <Stack spacing={2}>
                {/* Key Type */}
                <Box>
                  <Typography variant="caption" color="text.secondary">
                    {t('sshConnections.systemKey.type')}
                  </Typography>
                  <Typography variant="body2" fontWeight={500}>
                    {systemKey?.key_type?.toUpperCase() || 'Unknown'}
                  </Typography>
                </Box>

                {/* Fingerprint */}
                {systemKey?.fingerprint && (
                  <Box>
                    <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.25 }}>
                      <Typography variant="caption" color="text.secondary">
                        {t('sshConnections.systemKey.fingerprint')}
                      </Typography>
                      <Tooltip
                        title={fingerprintVisible ? 'Hide fingerprint' : 'Reveal fingerprint'}
                      >
                        <IconButton
                          size="small"
                          onClick={() => setFingerprintVisible((v) => !v)}
                          sx={{ p: 0.25 }}
                        >
                          {fingerprintVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                        </IconButton>
                      </Tooltip>
                    </Stack>
                    <Typography
                      variant="body2"
                      fontWeight={500}
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.85rem',
                        wordBreak: 'break-all',
                        filter: fingerprintVisible ? 'none' : 'blur(4px)',
                        userSelect: fingerprintVisible ? 'auto' : 'none',
                        transition: 'filter 0.2s ease',
                      }}
                    >
                      {systemKey.fingerprint}
                    </Typography>
                  </Box>
                )}

                {/* Public Key */}
                <Box>
                  <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mb: 0.5 }}>
                    <Typography variant="caption" color="text.secondary">
                      {t('sshConnections.systemKey.publicKey')}
                    </Typography>
                    <Tooltip title={keyVisible ? 'Hide key' : 'Reveal key'}>
                      <IconButton
                        size="small"
                        onClick={() => setKeyVisible((v) => !v)}
                        sx={{ p: 0.25 }}
                      >
                        {keyVisible ? <EyeOff size={13} /> : <Eye size={13} />}
                      </IconButton>
                    </Tooltip>
                  </Stack>
                  <Box
                    sx={{
                      position: 'relative',
                      bgcolor: 'background.default',
                      p: 1.5,
                      pr: 5,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'divider',
                    }}
                  >
                    <Typography
                      variant="body2"
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.75rem',
                        wordBreak: 'break-all',
                        maxHeight: '100px',
                        overflow: 'auto',
                        filter: keyVisible ? 'none' : 'blur(4px)',
                        userSelect: keyVisible ? 'auto' : 'none',
                        transition: 'filter 0.2s ease',
                      }}
                    >
                      {systemKey?.public_key || 'N/A'}
                    </Typography>
                    <Box sx={{ position: 'absolute', top: 6, right: 6 }}>
                      <Tooltip title="Copy to clipboard">
                        <IconButton size="small" onClick={handleCopyPublicKey}>
                          <Copy size={15} />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  </Box>
                </Box>

                {/* Action Buttons */}
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} flexWrap="wrap">
                  <Tooltip title="Automatically deploy SSH key using password authentication">
                    <Button
                      variant="contained"
                      startIcon={<Plus size={18} />}
                      onClick={() => setDeployDialogOpen(true)}
                      fullWidth={false}
                      sx={{ width: { xs: '100%', sm: 'auto' } }}
                    >
                      {t('sshConnections.systemKey.actions.deploy')}
                    </Button>
                  </Tooltip>
                  <Tooltip title="Add a connection for a manually deployed SSH key">
                    <Button
                      variant="outlined"
                      startIcon={<Wifi size={18} />}
                      onClick={() => setTestConnectionDialogOpen(true)}
                      sx={{ width: { xs: '100%', sm: 'auto' } }}
                    >
                      {t('sshConnections.systemKey.actions.addManual')}
                    </Button>
                  </Tooltip>
                  <Tooltip title="Delete system SSH key (connections will be preserved)">
                    <Button
                      variant="outlined"
                      color="error"
                      startIcon={<Trash2 size={18} />}
                      onClick={() => setDeleteKeyDialogOpen(true)}
                      sx={{ width: { xs: '100%', sm: 'auto' } }}
                    >
                      {t('sshConnections.systemKey.actions.delete')}
                    </Button>
                  </Tooltip>
                </Stack>
              </Stack>
            </Box>
          )}
        </Box>
      </Box>

      {/* Remote Connections */}
      <Box>
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            mb: 2,
          }}
        >
          <Box>
            <Typography variant="h6" fontWeight={700} sx={{ lineHeight: 1.3 }}>
              Remote Connections
            </Typography>
            {connections.length > 0 && (
              <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8rem' }}>
                {connections.length} machine{connections.length !== 1 ? 's' : ''} configured
              </Typography>
            )}
          </Box>
          <Tooltip title="Refresh connections" arrow>
            <IconButton
              size="small"
              onClick={() => queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })}
              sx={{
                width: 32,
                height: 32,
                borderRadius: 1.5,
                color: 'text.secondary',
                '&:hover': {
                  bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.06),
                  color: 'text.primary',
                },
              }}
            >
              <RefreshCw size={16} />
            </IconButton>
          </Tooltip>
        </Box>

        {!keyExists && connections.length > 0 && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            No SSH key configured. Generate or import a key to test these connections.
          </Alert>
        )}

        {connections.length === 0 ? (
          <Box
            sx={{
              borderRadius: 2,
              border: '1px solid',
              borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
              bgcolor: isDark ? alpha('#fff', 0.025) : alpha('#000', 0.018),
              px: 3,
              py: 4,
              textAlign: 'center',
            }}
          >
            <Box
              sx={{
                width: 44,
                height: 44,
                borderRadius: 2,
                bgcolor: isDark
                  ? alpha(theme.palette.primary.main, 0.12)
                  : alpha(theme.palette.primary.main, 0.08),
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: theme.palette.primary.main,
                mx: 'auto',
                mb: 1.5,
              }}
            >
              <Wifi size={22} />
            </Box>
            <Typography variant="body1" fontWeight={600} sx={{ mb: 0.5 }}>
              No remote machines yet
            </Typography>
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.82rem' }}>
              {keyExists
                ? 'Deploy your SSH key to a remote server to get started.'
                : 'Generate or import an SSH key first, then deploy it to remote servers.'}
            </Typography>
          </Box>
        ) : (
          <Box
            sx={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: { xs: 2, sm: 2.5 },
            }}
          >
            {connections.map((connection) => (
              <Box
                key={connection.id}
                sx={{
                  flex: {
                    xs: '0 0 100%',
                    sm: '0 0 calc(50% - 10px)',
                    md: '0 0 calc(33.333% - 14px)',
                  },
                  minWidth: 0,
                  display: 'flex',
                }}
              >
                <RemoteMachineCard
                  machine={connection}
                  onEdit={handleEditConnection}
                  onDelete={handleDeleteConnection}
                  onRefreshStorage={(machine) => refreshStorageMutation.mutate(machine.id)}
                  onTestConnection={handleTestConnection}
                  onDeployKey={handleDeployKeyToConnection}
                  canManageConnections={canManageSsh}
                />
              </Box>
            ))}
          </Box>
        )}
      </Box>

      {/* Generate Key Dialog */}
      <Dialog
        open={generateDialogOpen}
        onClose={() => setGenerateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.generateDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              This will generate a new SSH key pair for your system. You can only have one system
              key at a time.
            </Alert>

            <FormControl fullWidth>
              <InputLabel>{t('sshConnections.generateDialog.keyType')}</InputLabel>
              <Select
                value={keyType}
                label={t('sshConnections.generateDialog.keyType')}
                onChange={(e) => setKeyType(e.target.value)}
              >
                <MenuItem value="ed25519">{t('sshConnections.generateDialog.ed25519')}</MenuItem>
                <MenuItem value="rsa">{t('sshConnections.generateDialog.rsa')}</MenuItem>
                <MenuItem value="ecdsa">{t('sshConnections.generateDialog.ecdsa')}</MenuItem>
              </Select>
            </FormControl>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setGenerateDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleGenerateKey}
            disabled={generateKeyMutation.isPending}
          >
            {generateKeyMutation.isPending
              ? t('sshConnections.generateDialog.generating')
              : t('sshConnections.generateDialog.generate')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Import Key Dialog */}
      <Dialog
        open={importDialogOpen}
        onClose={() => setImportDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.importDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              Import an existing SSH key from your filesystem (e.g., mounted volume). The key will
              be read from the specified paths and stored in the database.
            </Alert>

            <TextField
              label={t('sshConnections.importDialog.keyName')}
              fullWidth
              value={importForm.name}
              onChange={(e) => setImportForm({ ...importForm, name: e.target.value })}
              placeholder="System SSH Key"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label={t('sshConnections.importDialog.privateKeyPath')}
              fullWidth
              required
              value={importForm.private_key_path}
              onChange={(e) => setImportForm({ ...importForm, private_key_path: e.target.value })}
              placeholder="/home/borg/.ssh/id_ed25519 or /root/.ssh/id_rsa"
              helperText="Absolute path to the private key file"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label={t('sshConnections.importDialog.publicKeyPath')}
              fullWidth
              value={importForm.public_key_path}
              onChange={(e) => setImportForm({ ...importForm, public_key_path: e.target.value })}
              placeholder="Leave empty to auto-detect (adds .pub to private key path)"
              helperText="If not provided, will try {private_key_path}.pub"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label={t('sshConnections.importDialog.description')}
              fullWidth
              value={importForm.description}
              onChange={(e) => setImportForm({ ...importForm, description: e.target.value })}
              placeholder="Imported system SSH key"
              InputLabelProps={{ shrink: true }}
              multiline
              rows={2}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setImportDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleImportKey}
            disabled={importKeyMutation.isPending || !importForm.private_key_path}
          >
            {importKeyMutation.isPending
              ? t('sshConnections.importDialog.importing')
              : t('sshConnections.importDialog.import')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Deploy Key Dialog */}
      <Dialog
        open={deployDialogOpen}
        onClose={() => setDeployDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.deployDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('sshConnections.deployDialog.host')}
              fullWidth
              value={connectionForm.host}
              onChange={(e) => setConnectionForm({ ...connectionForm, host: e.target.value })}
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.username')}
              fullWidth
              value={connectionForm.username}
              onChange={(e) => setConnectionForm({ ...connectionForm, username: e.target.value })}
              placeholder="root"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.port')}
              type="number"
              fullWidth
              value={connectionForm.port}
              onChange={(e) =>
                setConnectionForm({
                  ...connectionForm,
                  port: parseInt(e.target.value),
                })
              }
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.password')}
              type="password"
              fullWidth
              value={connectionForm.password}
              onChange={(e) => setConnectionForm({ ...connectionForm, password: e.target.value })}
              placeholder="Server password (for initial deployment)"
              InputLabelProps={{ shrink: true }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip
                      title="The password is used to deploy your public key to the server's authorized_keys file. After deployment, you'll connect using the SSH key."
                      arrow
                    >
                      <Box
                        component="span"
                        sx={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          color: 'text.secondary',
                          cursor: 'help',
                        }}
                      >
                        <Info size={18} />
                      </Box>
                    </Tooltip>
                  </InputAdornment>
                ),
              }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={connectionForm.use_sftp_mode}
                  onChange={(e) =>
                    setConnectionForm({ ...connectionForm, use_sftp_mode: e.target.checked })
                  }
                />
              }
              label={
                <Box>
                  <Typography variant="body2">
                    {t('sshConnections.deployDialog.sftpMode')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Required by Hetzner Storage Box. Disable for Synology NAS or older SSH servers.
                  </Typography>
                </Box>
              }
            />
            <TextField
              label={t('sshConnections.deployDialog.defaultPath')}
              fullWidth
              value={connectionForm.default_path}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, default_path: e.target.value })
              }
              placeholder="/home"
              helperText="Starting directory for SSH file browsing (e.g., /home for Hetzner Storage Box)"
              InputLabelProps={{ shrink: true }}
            />
            {/* Temporarily disabled - feature not fully working yet
            <TextField
              label="SSH Path Prefix (Optional)"
              fullWidth
              value={connectionForm.ssh_path_prefix}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, ssh_path_prefix: e.target.value })
              }
              placeholder="/volume1"
              helperText="Path prefix for SSH commands (e.g., /volume1 for Synology). SFTP browsing uses paths as-is, SSH prepends this prefix."
              InputLabelProps={{ shrink: true }}
            />
            */}
            <TextField
              label={t('sshConnections.deployDialog.mountPoint')}
              fullWidth
              value={connectionForm.mount_point}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, mount_point: e.target.value })
              }
              placeholder="hetzner or homeserver"
              helperText="Friendly name for this remote machine (e.g., hetzner, backup-server)"
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeployDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleDeployKey}
            disabled={
              deployKeyMutation.isPending ||
              !connectionForm.host ||
              !connectionForm.username ||
              !connectionForm.password
            }
          >
            {deployKeyMutation.isPending
              ? t('sshConnections.deployDialog.deploying')
              : t('sshConnections.deployDialog.deploy')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Test Manual Connection Dialog */}
      <Dialog
        open={testConnectionDialogOpen}
        onClose={() => setTestConnectionDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.manualConnectionDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                {t('sshConnections.manualConnectionDialog.instructions.title')}
              </Typography>
              <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
                1. {t('sshConnections.manualConnectionDialog.instructions.step1')}
              </Typography>
              <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
                2. {t('sshConnections.manualConnectionDialog.instructions.step2')}
              </Typography>
              <Typography variant="caption" component="div">
                3. {t('sshConnections.manualConnectionDialog.instructions.step3')}
              </Typography>
            </Alert>

            <TextField
              label={t('sshConnections.deployDialog.host')}
              fullWidth
              value={testConnectionForm.host}
              onChange={(e) =>
                setTestConnectionForm({ ...testConnectionForm, host: e.target.value })
              }
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.username')}
              fullWidth
              value={testConnectionForm.username}
              onChange={(e) =>
                setTestConnectionForm({
                  ...testConnectionForm,
                  username: e.target.value,
                })
              }
              placeholder="root"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.port')}
              type="number"
              fullWidth
              value={testConnectionForm.port}
              onChange={(e) =>
                setTestConnectionForm({
                  ...testConnectionForm,
                  port: parseInt(e.target.value),
                })
              }
              InputLabelProps={{ shrink: true }}
            />

            <Alert severity="success" sx={{ fontSize: '0.85rem' }}>
              This will test the connection and add it to your connections list if successful.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTestConnectionDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            onClick={handleTestManualConnection}
            disabled={
              testConnectionMutation.isPending ||
              !testConnectionForm.host ||
              !testConnectionForm.username
            }
          >
            {testConnectionMutation.isPending
              ? 'Testing...'
              : t('sshConnections.manualConnectionDialog.submit')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Edit Connection Dialog */}
      <Dialog
        open={editConnectionDialogOpen}
        onClose={() => {
          setEditConnectionDialogOpen(false)
          setSelectedConnection(null)
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.editConnectionDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label={t('sshConnections.deployDialog.host')}
              fullWidth
              value={editConnectionForm.host}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  host: e.target.value,
                })
              }
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.username')}
              fullWidth
              value={editConnectionForm.username}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  username: e.target.value,
                })
              }
              placeholder="root"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label={t('sshConnections.deployDialog.port')}
              type="number"
              fullWidth
              value={editConnectionForm.port}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  port: parseInt(e.target.value),
                })
              }
              InputLabelProps={{ shrink: true }}
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={editConnectionForm.use_sftp_mode}
                  onChange={(e) =>
                    setEditConnectionForm({
                      ...editConnectionForm,
                      use_sftp_mode: e.target.checked,
                    })
                  }
                />
              }
              label={
                <Box>
                  <Typography variant="body2">
                    {t('sshConnections.deployDialog.sftpMode')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    Required by Hetzner Storage Box. Disable for Synology NAS or older SSH servers.
                  </Typography>
                </Box>
              }
            />
            <FormControlLabel
              control={
                <Checkbox
                  checked={editConnectionForm.use_sudo}
                  onChange={(e) =>
                    setEditConnectionForm({
                      ...editConnectionForm,
                      use_sudo: e.target.checked,
                    })
                  }
                />
              }
              label={
                <Box>
                  <Typography variant="body2">
                    {t('sshConnections.deployDialog.useSudo')}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">
                    {t('sshConnections.deployDialog.useSudoHint')}
                  </Typography>
                </Box>
              }
            />
            <TextField
              label={t('sshConnections.deployDialog.defaultPath')}
              fullWidth
              value={editConnectionForm.default_path}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  default_path: e.target.value,
                })
              }
              placeholder="/home"
              helperText="Starting directory for SSH file browsing (e.g., /home for Hetzner Storage Box)"
              InputLabelProps={{ shrink: true }}
            />
            {/* Temporarily disabled - feature not fully working yet
            <TextField
              label="SSH Path Prefix (Optional)"
              fullWidth
              value={editConnectionForm.ssh_path_prefix}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  ssh_path_prefix: e.target.value,
                })
              }
              placeholder="/volume1"
              helperText="Path prefix for SSH commands (e.g., /volume1 for Synology). SFTP browsing uses paths as-is, SSH prepends this prefix."
              InputLabelProps={{ shrink: true }}
            />
            */}
            <TextField
              label={t('sshConnections.deployDialog.mountPoint')}
              fullWidth
              value={editConnectionForm.mount_point}
              onChange={(e) =>
                setEditConnectionForm({
                  ...editConnectionForm,
                  mount_point: e.target.value,
                })
              }
              placeholder="hetzner or homeserver"
              helperText="Friendly name for this remote machine (e.g., hetzner, backup-server)"
              InputLabelProps={{ shrink: true }}
            />
            <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
              Update the connection details. You may want to test the connection after updating.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setEditConnectionDialogOpen(false)
              setSelectedConnection(null)
            }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleUpdateConnection}
            disabled={
              updateConnectionMutation.isPending ||
              !editConnectionForm.host ||
              !editConnectionForm.username
            }
          >
            {updateConnectionMutation.isPending
              ? 'Updating...'
              : t('sshConnections.editConnectionDialog.submit')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete Connection Dialog */}
      <Dialog
        open={deleteConnectionDialogOpen}
        onClose={() => {
          setDeleteConnectionDialogOpen(false)
          setSelectedConnection(null)
        }}
        maxWidth="xs"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.deleteConnectionDialog.title')}</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            Are you sure you want to delete this connection?
          </Alert>
          {selectedConnection && (
            <Stack spacing={1}>
              <Typography variant="body2">
                <strong>Host:</strong> {selectedConnection.host}
              </Typography>
              <Typography variant="body2">
                <strong>Username:</strong> {selectedConnection.username}
              </Typography>
              <Typography variant="body2">
                <strong>Port:</strong> {selectedConnection.port}
              </Typography>
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setDeleteConnectionDialogOpen(false)
              setSelectedConnection(null)
            }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            color="error"
            onClick={confirmDeleteConnection}
            disabled={deleteConnectionMutation.isPending}
          >
            {deleteConnectionMutation.isPending
              ? t('sshConnections.deleteConnectionDialog.deleting')
              : t('sshConnections.deleteConnectionDialog.delete')}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Redeploy Key Dialog */}
      <Dialog
        open={redeployKeyDialogOpen}
        onClose={() => {
          setRedeployKeyDialogOpen(false)
          setSelectedConnection(null)
          setRedeployPassword('')
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Deploy SSH Key to Connection</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              This will deploy your current system SSH key to this connection. You'll need to
              provide the password to authenticate.
            </Alert>
            {selectedConnection && (
              <Box sx={{ p: 2, bgcolor: 'action.hover', borderRadius: 1 }}>
                <Typography variant="body2">
                  <strong>Host:</strong> {selectedConnection.host}
                </Typography>
                <Typography variant="body2">
                  <strong>Username:</strong> {selectedConnection.username}
                </Typography>
                <Typography variant="body2">
                  <strong>Port:</strong> {selectedConnection.port}
                </Typography>
              </Box>
            )}
            <TextField
              label="Password"
              type="password"
              fullWidth
              value={redeployPassword}
              onChange={(e) => setRedeployPassword(e.target.value)}
              placeholder="Enter SSH password"
              helperText="Password is used to deploy the public key to authorized_keys"
              InputLabelProps={{ shrink: true }}
            />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button
            onClick={() => {
              setRedeployKeyDialogOpen(false)
              setSelectedConnection(null)
              setRedeployPassword('')
            }}
          >
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleConfirmRedeployKey}
            disabled={redeployKeyMutation.isPending || !redeployPassword}
          >
            {redeployKeyMutation.isPending ? 'Deploying...' : 'Deploy Key'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Delete SSH Key Dialog */}
      <Dialog
        open={deleteKeyDialogOpen}
        onClose={() => setDeleteKeyDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>{t('sshConnections.deleteKeyDialog.title')}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="warning" sx={{ mb: 1 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                {t('sshConnections.deleteKeyDialog.confirm')}
              </Typography>
            </Alert>

            {systemKey && (
              <Box
                sx={{
                  p: 2,
                  bgcolor: 'background.default',
                  borderRadius: 1,
                  border: '1px solid',
                  borderColor: 'divider',
                }}
              >
                <Stack spacing={1}>
                  <Typography variant="body2">
                    <strong>Key Name:</strong> {systemKey.name}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Key Type:</strong> {systemKey.key_type?.toUpperCase()}
                  </Typography>
                  <Typography variant="body2">
                    <strong>Active Connections:</strong> {connections.length}
                  </Typography>
                  {systemKey.fingerprint && (
                    <Typography
                      variant="body2"
                      sx={{ fontFamily: 'monospace', fontSize: '0.75rem', wordBreak: 'break-all' }}
                    >
                      <strong>Fingerprint:</strong> {systemKey.fingerprint}
                    </Typography>
                  )}
                </Stack>
              </Box>
            )}

            <Typography variant="body2" color="text.secondary" sx={{ mb: 1 }}>
              This action will:
            </Typography>
            <Box component="ul" sx={{ m: 0, pl: 3 }}>
              <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                {t('sshConnections.deleteKeyDialog.warning1')}
              </Typography>
              <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                Mark {connections.length} connection(s) as failed
              </Typography>
              <Typography component="li" variant="body2" sx={{ mb: 0.5 }}>
                Clear SSH key from any repositories using it
              </Typography>
            </Box>

            <Alert severity="info" sx={{ mt: 2 }}>
              <Typography variant="body2">
                {t('sshConnections.deleteKeyDialog.warning2')}
              </Typography>
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDeleteKeyDialogOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            color="error"
            onClick={handleDeleteKey}
            disabled={deleteKeyMutation.isPending}
          >
            {deleteKeyMutation.isPending ? 'Deleting...' : 'Delete SSH Key'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
