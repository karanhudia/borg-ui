import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { sshKeysAPI } from '../services/api'
import { formatDate } from '../utils/dateUtils'
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
} from '@mui/material'
import {
  Key,
  Copy,
  RefreshCw,
  Wifi,
  WifiOff,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Plus,
  Edit,
  Trash2,
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import DataTable from '../components/DataTable'

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  default_path?: string
  status: string
  last_test?: string
  last_success?: string
  error_message?: string
  created_at: string
}

export default function SSHConnectionsSingleKey() {
  const queryClient = useQueryClient()

  // State
  const [generateDialogOpen, setGenerateDialogOpen] = useState(false)
  const [deployDialogOpen, setDeployDialogOpen] = useState(false)
  const [testConnectionDialogOpen, setTestConnectionDialogOpen] = useState(false)
  const [editConnectionDialogOpen, setEditConnectionDialogOpen] = useState(false)
  const [deleteConnectionDialogOpen, setDeleteConnectionDialogOpen] = useState(false)
  const [selectedConnection, setSelectedConnection] = useState<SSHConnection | null>(null)
  const [keyType, setKeyType] = useState('ed25519')
  const [connectionForm, setConnectionForm] = useState({
    host: '',
    username: '',
    port: 22,
    password: '',
    default_path: '',
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
    default_path: '',
  })

  // Queries
  const { data: systemKeyData, isLoading: keyLoading } = useQuery({
    queryKey: ['system-ssh-key'],
    queryFn: sshKeysAPI.getSystemKey,
    refetchInterval: 30000
  })

  const { data: connectionsData, isLoading: connectionsLoading } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    refetchInterval: 30000
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
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to generate SSH key')
    },
  })

  const deployKeyMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.deploySSHKey(data.keyId, data.connectionData),
    onSuccess: () => {
      toast.success('SSH key deployed successfully!')
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setDeployDialogOpen(false)
      setConnectionForm({ host: '', username: '', port: 22, password: '' })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to deploy SSH key')
    },
  })

  const testConnectionMutation = useMutation({
    mutationFn: (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.testSSHConnection(data.keyId, data.connectionData),
    onSuccess: (response) => {
      if (response.data.success) {
        toast.success('Connection test successful!')
      } else {
        toast.error('Connection test failed')
      }
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Connection test failed')
    },
  })

  const updateConnectionMutation = useMutation({
    mutationFn: (data: { connectionId: number; connectionData: any }) =>
      sshKeysAPI.updateSSHConnection(data.connectionId, data.connectionData),
    onSuccess: () => {
      toast.success('Connection updated successfully!')
      queryClient.invalidateQueries({ queryKey: ['ssh-connections'] })
      setEditConnectionDialogOpen(false)
      setSelectedConnection(null)
    },
    onError: (error: any) => {
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
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete connection')
    },
  })

  // Handlers
  const handleGenerateKey = () => {
    generateKeyMutation.mutate({
      name: 'System SSH Key',
      key_type: keyType,
      description: 'System SSH key for all remote connections',
    })
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

  const handleTestConnection = (connection: SSHConnection) => {
    if (!systemKey) return
    testConnectionMutation.mutate({
      keyId: systemKey.id,
      connectionData: {
        host: connection.host,
        username: connection.username,
        port: connection.port,
      },
    })
  }

  const handleEditConnection = (connection: SSHConnection) => {
    setSelectedConnection(connection)
    setEditConnectionForm({
      host: connection.host,
      username: connection.username,
      port: connection.port,
      default_path: connection.default_path || '',
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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <Wifi size={18} color="#ffffff" strokeWidth={1.5} />
      case 'failed':
        return <WifiOff size={18} color="#ffffff" strokeWidth={1.5} />
      case 'testing':
        return <CircularProgress size={18} />
      default:
        return <AlertTriangle size={18} color="#ffffff" strokeWidth={1.5} />
    }
  }

  const getStatusColor = (
    status: string
  ): 'success' | 'error' | 'warning' | 'info' => {
    switch (status) {
      case 'connected':
        return 'success'
      case 'failed':
        return 'error'
      case 'testing':
        return 'info'
      default:
        return 'warning'
    }
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
          SSH Connections
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Manage your system SSH key and remote server connections
        </Typography>
      </Box>

      {/* Info Alert */}
      <Alert severity="info" sx={{ mb: 3 }}>
        <Typography variant="body2" fontWeight={500}>
          Single-Key System
        </Typography>
        <Typography variant="caption">
          This system uses one SSH key for all remote connections. Generate the
          system key once, then deploy it to as many remote servers as needed.
        </Typography>
      </Alert>

      {/* Statistics Cards */}
      {keyExists && (
        <Stack
          direction={{ xs: 'column', sm: 'row' }}
          spacing={2}
          sx={{ mb: 3 }}
        >
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
              <Chip
                label="Active"
                color="success"
                size="small"
                icon={<CheckCircle size={14} />}
              />
            )}
          </Stack>

          {!keyExists ? (
            // No key exists - show generation UI
            <Box>
              <Alert severity="warning" sx={{ mb: 2 }}>
                No system SSH key found. Generate one to start connecting to
                remote servers.
              </Alert>
              <Button
                variant="contained"
                startIcon={<Plus size={18} />}
                onClick={() => setGenerateDialogOpen(true)}
              >
                Generate System SSH Key
              </Button>
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
                      <IconButton
                        size="small"
                        onClick={handleCopyPublicKey}
                        sx={{ ml: 1 }}
                      >
                        <Copy size={16} />
                      </IconButton>
                    </Tooltip>
                  </Stack>
                  <Box
                    sx={{
                      bgcolor: 'grey.100',
                      p: 1.5,
                      borderRadius: 1,
                      border: '1px solid',
                      borderColor: 'grey.300',
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
                </Stack>
              </Stack>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Connections Table */}
      {keyExists && (
        <Card>
          <CardContent>
            <Stack
              direction="row"
              alignItems="center"
              justifyContent="space-between"
              sx={{ mb: 2 }}
            >
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

            {connections.length === 0 ? (
              <Alert severity="info">
                No connections yet. Deploy your SSH key to a remote server to get
                started.
              </Alert>
            ) : (
              <DataTable<SSHConnection>
                data={connections}
                columns={[
                  {
                    id: 'status',
                    label: 'Status',
                    render: (connection) => (
                      <Stack direction="row" alignItems="center" spacing={1}>
                        {getStatusIcon(connection.status)}
                        <Chip
                          label={connection.status}
                          size="small"
                          color={getStatusColor(connection.status)}
                          sx={{ height: 20, fontSize: '0.7rem' }}
                        />
                      </Stack>
                    ),
                  },
                  {
                    id: 'host',
                    label: 'Host',
                    render: (connection) => (
                      <Box>
                        <Typography variant="body2" fontWeight={500}>
                          {connection.host}
                        </Typography>
                        {connection.error_message && (
                          <Typography
                            variant="caption"
                            color="error"
                            sx={{ display: 'block', mt: 0.5 }}
                          >
                            {connection.error_message.substring(0, 50)}...
                          </Typography>
                        )}
                      </Box>
                    ),
                  },
                  {
                    id: 'username',
                    label: 'Username',
                    render: (connection) => (
                      <Typography variant="body2">{connection.username}</Typography>
                    ),
                  },
                  {
                    id: 'port',
                    label: 'Port',
                    render: (connection) => (
                      <Typography variant="body2">{connection.port}</Typography>
                    ),
                  },
                  {
                    id: 'last_test',
                    label: 'Last Test',
                    render: (connection) => (
                      <Typography variant="caption" color="text.secondary">
                        {formatDate(connection.last_test)}
                      </Typography>
                    ),
                  },
                ]}
                actions={[
                  {
                    icon: <Edit size={16} />,
                    label: 'Edit connection',
                    onClick: handleEditConnection,
                    color: 'primary',
                    tooltip: 'Edit connection',
                  },
                  {
                    icon: <RefreshCw size={16} />,
                    label: 'Test connection',
                    onClick: handleTestConnection,
                    tooltip: 'Test connection',
                    disabled: () => testConnectionMutation.isPending,
                  },
                  {
                    icon: <Trash2 size={16} />,
                    label: 'Delete connection',
                    onClick: handleDeleteConnection,
                    color: 'error',
                    tooltip: 'Delete connection',
                  },
                ]}
                getRowKey={(connection) => connection.id}
                variant="outlined"
                enableHover={true}
              />
            )}
          </CardContent>
        </Card>
      )}

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
              This will generate a new SSH key pair for your system. You can only
              have one system key at a time.
            </Alert>

            <FormControl fullWidth>
              <InputLabel>Key Type</InputLabel>
              <Select
                value={keyType}
                label="Key Type"
                onChange={(e) => setKeyType(e.target.value)}
              >
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
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, host: e.target.value })
              }
              placeholder="192.168.1.100 or example.com"
              InputLabelProps={{ shrink: true }}
            />
            <TextField
              label="Username"
              fullWidth
              value={connectionForm.username}
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, username: e.target.value })
              }
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
              onChange={(e) =>
                setConnectionForm({ ...connectionForm, password: e.target.value })
              }
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
            <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
              The password is used to deploy your public key to the server's
              authorized_keys file. After deployment, you'll connect using the SSH
              key.
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
                3. Add it to <code style={{ background: '#e3f2fd', padding: '2px 4px', borderRadius: '2px' }}>~/.ssh/authorized_keys</code>
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
              This will test the connection and add it to your connections list if
              successful.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setTestConnectionDialogOpen(false)}>
            Cancel
          </Button>
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
    </Box>
  )
}
