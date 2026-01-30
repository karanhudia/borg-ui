import { useState, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sshKeysAPI } from '../services/api'
import {
  Box,
  Card,
  CardContent,
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
  CircularProgress,
  Alert,
  Tooltip,
  InputAdornment,
  Checkbox,
  FormControlLabel,
} from '@mui/material'
import {
  Key,
  Copy,
  RefreshCw,
  Wifi,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Plus,
  Trash2,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import RemoteMachineCard from '../components/RemoteMachineCard'
import { useMatomo } from '../hooks/useMatomo'

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
  default_path?: string
  mount_point?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  storage?: StorageInfo | null
  created_at: string
}

export default function SSHConnectionsSingleKey() {
  const queryClient = useQueryClient()
  const { track, EventCategory, EventAction } = useMatomo()

  // State
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
    default_path: '',
    mount_point: '',
  })

  // Queries
  const { data: systemKeyData, isLoading: keyLoading } = useQuery({
    queryKey: ['system-ssh-key'],
    queryFn: sshKeysAPI.getSystemKey,
    refetchInterval: 30000,
  })

  const { data: connectionsData, isLoading: connectionsLoading } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
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
      toast.success('System SSH key generated successfully!')
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setGenerateDialogOpen(false)
      track(EventCategory.SSH, EventAction.CREATE, 'key')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to generate SSH key:', error)
      toast.error(error.response?.data?.detail || 'Failed to generate SSH key')
    },
  })

  const importKeyMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: (data: any) => sshKeysAPI.importSSHKey(data),
    onSuccess: () => {
      toast.success('System SSH key imported successfully!')
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      setImportDialogOpen(false)
      setImportForm({
        name: 'System SSH Key',
        private_key_path: '',
        public_key_path: '',
        description: 'Imported system SSH key for all remote connections',
      })
      track(EventCategory.SSH, EventAction.UPLOAD, 'key')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to import SSH key:', error)
      toast.error(error.response?.data?.detail || 'Failed to import SSH key')
    },
  })

  const deployKeyMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.deploySSHKey(data.keyId, data.connectionData),
    onSuccess: () => {
      toast.success('SSH key deployed successfully!')
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeployDialogOpen(false)
      setConnectionForm({
        host: '',
        username: '',
        port: 22,
        password: '',
        use_sftp_mode: true,
        default_path: '',
        mount_point: '',
      })
      track(EventCategory.SSH, EventAction.CREATE, 'connection')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to deploy SSH key:', error)
      toast.error(error.response?.data?.detail || 'Failed to deploy SSH key')
    },
  })

  const testConnectionMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.testSSHConnection(data.keyId, data.connectionData),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success('Connection test successful!')
        track(EventCategory.SSH, EventAction.CREATE, 'connection')
      } else {
        toast.error('Connection test failed')
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to test connection:', error)
      toast.error(error.response?.data?.detail || 'Connection test failed')
    },
  })

  const updateConnectionMutation = useMutation({
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    mutationFn: (data: { connectionId: number; connectionData: any }) =>
      sshKeysAPI.updateSSHConnection(data.connectionId, data.connectionData),
    onSuccess: async (_response, variables) => {
      toast.success('Connection updated successfully! Testing connection...')
      setEditConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.EDIT, 'connection')

      // Automatically test the connection after update
      try {
        await sshKeysAPI.testExistingConnection(variables.connectionId)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
      } catch (error: any) {
        // Test failure is already shown in the connection status
        console.error('Failed to test connection:', error)
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to update connection:', error)
      toast.error(error.response?.data?.detail || 'Failed to update connection')
    },
  })

  const deleteConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.deleteSSHConnection(connectionId),
    onSuccess: () => {
      toast.success('Connection deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteConnectionDialogOpen(false)
      setSelectedConnection(null)
      track(EventCategory.SSH, EventAction.DELETE, 'connection')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to delete connection:', error)
      toast.error(error.response?.data?.detail || 'Failed to delete connection')
    },
  })

  const refreshStorageMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.refreshConnectionStorage(connectionId),
    onSuccess: () => {
      toast.success('Storage information refreshed!')
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.VIEW, 'storage')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to refresh storage:', error)
      toast.error(error.response?.data?.detail || 'Failed to refresh storage')
    },
  })

  const testExistingConnectionMutation = useMutation({
    mutationFn: (connectionId: number) => sshKeysAPI.testExistingConnection(connectionId),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success('Connection test successful!')
      } else {
        toast.error(response.data.error || 'Connection test failed')
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      track(EventCategory.SSH, EventAction.TEST, 'connection')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to test connection:', error)
      toast.error(error.response?.data?.detail || 'Failed to test connection')
    },
  })

  const deleteKeyMutation = useMutation({
    mutationFn: (keyId: number) => sshKeysAPI.deleteSSHKey(keyId),
    onSuccess: () => {
      toast.success('System SSH key deleted successfully!')
      queryClient.invalidateQueries({ queryKey: ['system-ssh-key'] })
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeleteKeyDialogOpen(false)
      track(EventCategory.SSH, EventAction.DELETE, 'key')
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to delete SSH key:', error)
      toast.error(error.response?.data?.detail || 'Failed to delete SSH key')
    },
  })

  const redeployKeyMutation = useMutation({
    mutationFn: ({ connectionId, password }: { connectionId: number; password: string }) =>
      sshKeysAPI.redeployKeyToConnection(connectionId, password),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success('SSH key deployed successfully!')
        queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
        setRedeployKeyDialogOpen(false)
        setRedeployPassword('')
        track(EventCategory.SSH, EventAction.START, 'deploy')
      } else {
        toast.error(response.data.error || 'Failed to deploy SSH key')
      }
    },
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    onError: (error: any) => {
      console.error('Failed to redeploy SSH key:', error)
      toast.error(error.response?.data?.detail || 'Failed to deploy SSH key')
    },
  })

  // Auto-refresh storage for connections without storage info
  useEffect(() => {
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
      toast.success('Public key copied to clipboard!')
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
      default_path: connection.default_path || '',
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
      <Box
        sx={{
          display: 'flex',
          justifyContent: 'center',
          alignItems: 'center',
          minHeight: '400px',
        }}
      >
        <CircularProgress size={60} />
      </Box>
    )
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Remote Machines
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Manage remote machines with storage monitoring and logical mount points
        </Typography>
      </Box>

      {/* Info Alert */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2" fontWeight={500}>
          Single-Key System
        </Typography>
        <Typography variant="caption">
          This system uses one SSH key for all remote connections. Generate the system key once,
          then deploy it to as many remote servers as needed.
        </Typography>
      </Alert>

      {/* Statistics Cards */}
      {keyExists && (
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
          <Card sx={{ flex: 1 }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2}>
                <Box
                  sx={{
                    bgcolor: 'primary.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                  }}
                >
                  <Wifi size={24} color="#ffffff" strokeWidth={1.5} />
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Total Connections
                  </Typography>
                  <Typography variant="h6" fontWeight={600}>
                    {stats.totalConnections}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          <Card sx={{ flex: 1 }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2}>
                <Box
                  sx={{
                    bgcolor: 'success.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                  }}
                >
                  <CheckCircle size={24} color="#ffffff" strokeWidth={1.5} />
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Active
                  </Typography>
                  <Typography variant="h6" fontWeight={600}>
                    {stats.activeConnections}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>

          <Card sx={{ flex: 1 }}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={2}>
                <Box
                  sx={{
                    bgcolor: 'error.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                  }}
                >
                  <XCircle size={24} color="#ffffff" strokeWidth={1.5} />
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Failed
                  </Typography>
                  <Typography variant="h6" fontWeight={600}>
                    {stats.failedConnections}
                  </Typography>
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      )}

      {/* System SSH Key Card */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={2} sx={{ mb: 2 }}>
            <Key size={24} />
            <Typography variant="h6" fontWeight={600} sx={{ flex: 1 }}>
              System SSH Key
            </Typography>
            {keyExists && (
              <Chip label="Active" color="success" size="small" icon={<CheckCircle size={14} />} />
            )}
          </Stack>

          {!keyExists ? (
            // No key exists - show generation UI
            <Box>
              <Alert severity="warning" sx={{ mb: 2 }}>
                No system SSH key found. Generate a new one or import an existing one to start
                connecting to remote servers.
              </Alert>
              <Stack direction="row" spacing={2}>
                <Button
                  variant="contained"
                  startIcon={<Plus size={18} />}
                  onClick={() => setGenerateDialogOpen(true)}
                >
                  Generate System SSH Key
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<Key size={18} />}
                  onClick={() => setImportDialogOpen(true)}
                >
                  Import Existing Key
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
                    Key Type
                  </Typography>
                  <Typography variant="body2" fontWeight={500}>
                    {systemKey?.key_type?.toUpperCase() || 'Unknown'}
                  </Typography>
                </Box>

                {/* Fingerprint */}
                {systemKey?.fingerprint && (
                  <Box>
                    <Typography variant="caption" color="text.secondary">
                      Fingerprint
                    </Typography>
                    <Typography
                      variant="body2"
                      fontWeight={500}
                      sx={{
                        fontFamily: 'monospace',
                        fontSize: '0.85rem',
                        wordBreak: 'break-all',
                      }}
                    >
                      {systemKey.fingerprint}
                    </Typography>
                  </Box>
                )}

                {/* Public Key */}
                <Box>
                  <Stack
                    direction="row"
                    alignItems="center"
                    justifyContent="space-between"
                    sx={{ mb: 0.5 }}
                  >
                    <Typography variant="caption" color="text.secondary">
                      Public Key
                    </Typography>
                    <Tooltip title="Copy to clipboard">
                      <IconButton size="small" onClick={handleCopyPublicKey} sx={{ ml: 1 }}>
                        <Copy size={16} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                  <Box
                    sx={{
                      bgcolor: 'background.default',
                      p: 1.5,
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
                      }}
                    >
                      {systemKey?.public_key || 'N/A'}
                    </Typography>
                  </Box>
                </Box>

                {/* Action Buttons */}
                <Stack direction="row" spacing={2} flexWrap="wrap">
                  <Tooltip title="Automatically deploy SSH key using password authentication">
                    <Button
                      variant="contained"
                      startIcon={<Plus size={18} />}
                      onClick={() => setDeployDialogOpen(true)}
                    >
                      Deploy to Server
                    </Button>
                  </Tooltip>
                  <Tooltip title="Add a connection for a manually deployed SSH key">
                    <Button
                      variant="outlined"
                      startIcon={<Wifi size={18} />}
                      onClick={() => setTestConnectionDialogOpen(true)}
                    >
                      Add Manual Connection
                    </Button>
                  </Tooltip>
                  <Tooltip title="Copy public key to clipboard">
                    <Button
                      variant="outlined"
                      startIcon={<Copy size={18} />}
                      onClick={handleCopyPublicKey}
                    >
                      Copy Key
                    </Button>
                  </Tooltip>
                  <Tooltip title="Delete system SSH key (connections will be preserved)">
                    <Button
                      variant="outlined"
                      color="error"
                      startIcon={<Trash2 size={18} />}
                      onClick={() => setDeleteKeyDialogOpen(true)}
                    >
                      Delete Key
                    </Button>
                  </Tooltip>
                </Stack>
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Connections Table */}
      <Card>
        <CardContent>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>
              Remote Connections
            </Typography>
            <Tooltip title="Refresh connections">
              <IconButton
                size="small"
                onClick={() => queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })}
              >
                <RefreshCw size={18} />
              </IconButton>
            </Tooltip>
          </Stack>

          {!keyExists && connections.length > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              No SSH key configured. Generate or import a key to test these connections.
            </Alert>
          )}

          {connections.length === 0 ? (
            <Alert severity="info">
              {keyExists
                ? 'No connections yet. Deploy your SSH key to a remote server to get started.'
                : 'No connections yet. Generate or import an SSH key first, then deploy it to remote servers.'}
            </Alert>
          ) : (
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: {
                  xs: '1fr',
                  sm: 'repeat(2, 1fr)',
                  md: 'repeat(3, 1fr)',
                },
                gap: 3,
              }}
            >
              {connections.map((connection) => (
                <RemoteMachineCard
                  key={connection.id}
                  machine={connection}
                  onEdit={handleEditConnection}
                  onDelete={handleDeleteConnection}
                  onRefreshStorage={(machine) => refreshStorageMutation.mutate(machine.id)}
                  onTestConnection={handleTestConnection}
                  onDeployKey={handleDeployKeyToConnection}
                />
              ))}
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Generate Key Dialog */}
      <Dialog
        open={generateDialogOpen}
        onClose={() => setGenerateDialogOpen(false)}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Generate System SSH Key</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              This will generate a new SSH key pair for your system. You can only have one system
              key at a time.
            </Alert>

            <FormControl fullWidth>
              <InputLabel>Key Type</InputLabel>
              <Select value={keyType} label="Key Type" onChange={(e) => setKeyType(e.target.value)}>
                <MenuItem value="ed25519">ED25519 (Recommended)</MenuItem>
                <MenuItem value="rsa">RSA</MenuItem>
                <MenuItem value="ecdsa">ECDSA</MenuItem>
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
            {generateKeyMutation.isPending ? 'Generating...' : 'Generate Key'}
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
        <DialogTitle>Import Existing SSH Key</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info">
              Import an existing SSH key from your filesystem (e.g., mounted volume). The key will
              be read from the specified paths and stored in the database.
            </Alert>

            <TextField
              label="Key Name"
              fullWidth
              value={importForm.name}
              onChange={(e) => setImportForm({ ...importForm, name: e.target.value })}
              placeholder="System SSH Key"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label="Private Key Path"
              fullWidth
              required
              value={importForm.private_key_path}
              onChange={(e) => setImportForm({ ...importForm, private_key_path: e.target.value })}
              placeholder="/home/borg/.ssh/id_ed25519 or /root/.ssh/id_rsa"
              helperText="Absolute path to the private key file"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label="Public Key Path (Optional)"
              fullWidth
              value={importForm.public_key_path}
              onChange={(e) => setImportForm({ ...importForm, public_key_path: e.target.value })}
              placeholder="Leave empty to auto-detect (adds .pub to private key path)"
              helperText="If not provided, will try {private_key_path}.pub"
              InputLabelProps={{ shrink: true }}
            />

            <TextField
              label="Description"
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
            {importKeyMutation.isPending ? 'Importing...' : 'Import Key'}
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
        <DialogTitle>Deploy SSH Key to Server</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Host"
              fullWidth
              value={connectionForm.host}
              onChange={(e) => setConnectionForm({ ...connectionForm, host: e.target.value })}
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Username"
              fullWidth
              value={connectionForm.username}
              onChange={(e) => setConnectionForm({ ...connectionForm, username: e.target.value })}
              placeholder="root"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Port"
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
              label="Password"
              type="password"
              fullWidth
              value={connectionForm.password}
              onChange={(e) => setConnectionForm({ ...connectionForm, password: e.target.value })}
              placeholder="Server password (for initial deployment)"
              InputLabelProps={{ shrink: true }}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Password is only used once to deploy the key">
                      <AlertTriangle size={18} />
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
                  <Typography variant="body2">Use SFTP mode for key deployment</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Required by Hetzner Storage Box. Disable for Synology NAS or older SSH servers.
                  </Typography>
                </Box>
              }
            />
            <TextField
              label="Default Path (Optional)"
              fullWidth
              value={connectionForm.default_path}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, default_path: e.target.value })
              }
              placeholder="/home"
              helperText="Starting directory for SSH file browsing (e.g., /home for Hetzner Storage Box)"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Mount Point (Optional)"
              fullWidth
              value={connectionForm.mount_point}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, mount_point: e.target.value })
              }
              placeholder="hetzner or homeserver"
              helperText="Friendly name for this remote machine (e.g., hetzner, backup-server)"
              InputLabelProps={{ shrink: true }}
            />
            <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
              The password is used to deploy your public key to the server's authorized_keys file.
              After deployment, you'll connect using the SSH key.
            </Alert>
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
            {deployKeyMutation.isPending ? 'Deploying...' : 'Deploy Key'}
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
        <DialogTitle>Add Manual Connection</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Before adding this connection:
              </Typography>
              <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
                1. Copy the public key from above
              </Typography>
              <Typography variant="caption" component="div" sx={{ mb: 0.5 }}>
                2. SSH into your server
              </Typography>
              <Typography variant="caption" component="div">
                3. Add it to{' '}
                <code style={{ background: '#e3f2fd', padding: '2px 4px', borderRadius: '2px' }}>
                  ~/.ssh/authorized_keys
                </code>
              </Typography>
            </Alert>

            <TextField
              label="Host"
              fullWidth
              value={testConnectionForm.host}
              onChange={(e) =>
                setTestConnectionForm({ ...testConnectionForm, host: e.target.value })
              }
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Username"
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
              label="Port"
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
            {testConnectionMutation.isPending ? 'Testing...' : 'Test & Add Connection'}
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
        <DialogTitle>Edit SSH Connection</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              label="Host"
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
              label="Username"
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
              label="Port"
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
                  <Typography variant="body2">Use SFTP mode for key deployment</Typography>
                  <Typography variant="caption" color="text.secondary">
                    Required by Hetzner Storage Box. Disable for Synology NAS or older SSH servers.
                  </Typography>
                </Box>
              }
            />
            <TextField
              label="Default Path (Optional)"
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
            <TextField
              label="Mount Point (Optional)"
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
            {updateConnectionMutation.isPending ? 'Updating...' : 'Update Connection'}
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
        <DialogTitle>Delete SSH Connection</DialogTitle>
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
            {deleteConnectionMutation.isPending ? 'Deleting...' : 'Delete'}
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
        <DialogTitle>Delete System SSH Key</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Alert severity="warning" sx={{ mb: 1 }}>
              <Typography variant="body2" fontWeight={600} gutterBottom>
                Are you sure you want to delete this SSH key?
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
                Remove the SSH key from database and filesystem
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
                Connection records will be preserved. Generate or import a new key, then deploy it
                to restore access.
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
