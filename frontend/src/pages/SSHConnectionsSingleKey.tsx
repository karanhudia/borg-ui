import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
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
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
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
  WifiOff,
  CheckCircle,
  XCircle,
  AlertTriangle,
  Plus,
} from 'lucide-react'
import { toast } from 'react-hot-toast'

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
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
  const [keyType, setKeyType] = useState('ed25519')
  const [manualDeployment, setManualDeployment] = useState(false)
  const [connectionForm, setConnectionForm] = useState({
    host: '',
    username: '',
    port: 22,
    password: '',
  })

  // Queries
  const { data: systemKeyData, isLoading: keyLoading } = useQuery(
    'system-ssh-key',
    sshKeysAPI.getSystemKey,
    { refetchInterval: 30000 }
  )

  const { data: connectionsData, isLoading: connectionsLoading } = useQuery(
    'ssh-connections',
    sshKeysAPI.getSSHConnections,
    { refetchInterval: 30000 }
  )

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
  const generateKeyMutation = useMutation(
    (data: { name: string; key_type: string; description?: string }) =>
      sshKeysAPI.generateSSHKey(data),
    {
      onSuccess: () => {
        toast.success('System SSH key generated successfully!')
        queryClient.invalidateQueries('system-ssh-key')
        setGenerateDialogOpen(false)
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || 'Failed to generate SSH key')
      },
    }
  )

  const deployKeyMutation = useMutation(
    (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.deploySSHKey(data.keyId, data.connectionData),
    {
      onSuccess: () => {
        toast.success('SSH key deployed successfully!')
        queryClient.invalidateQueries('ssh-connections')
        setDeployDialogOpen(false)
        setConnectionForm({ host: '', username: '', port: 22, password: '' })
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || 'Failed to deploy SSH key')
      },
    }
  )

  const testConnectionMutation = useMutation(
    (data: { keyId: number; connectionData: any }) =>
      sshKeysAPI.testSSHConnection(data.keyId, data.connectionData),
    {
      onSuccess: (response) => {
        if (response.data.success) {
          toast.success('Connection test successful!')
        } else {
          toast.error('Connection test failed')
        }
        queryClient.invalidateQueries('ssh-connections')
      },
      onError: (error: any) => {
        toast.error(error.response?.data?.detail || 'Connection test failed')
      },
    }
  )

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

    // If manual deployment, create connection via test endpoint (skip ssh-copy-id)
    if (manualDeployment) {
      testConnectionMutation.mutate({
        keyId: systemKey.id,
        connectionData: {
          host: connectionForm.host,
          username: connectionForm.username,
          port: connectionForm.port,
        },
      })
      setDeployDialogOpen(false)
      setConnectionForm({ host: '', username: '', port: 22, password: '' })
      setManualDeployment(false)
    } else {
      deployKeyMutation.mutate({
        keyId: systemKey.id,
        connectionData: connectionForm,
      })
    }
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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <Wifi size={18} color="#2e7d32" />
      case 'failed':
        return <WifiOff size={18} color="#d32f2f" />
      case 'testing':
        return <CircularProgress size={18} />
      default:
        return <AlertTriangle size={18} color="#ed6c02" />
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
                  <Wifi size={24} color="primary" />
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
                  <CheckCircle size={24} color="#2e7d32" />
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
                  <XCircle size={24} color="#d32f2f" />
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
                <Stack direction="row" spacing={2}>
                  <Button
                    variant="contained"
                    startIcon={<Plus size={18} />}
                    onClick={() => setDeployDialogOpen(true)}
                  >
                    Deploy to Server
                  </Button>
                  <Tooltip title="Copy public key to clipboard">
                    <Button
                      variant="outlined"
                      startIcon={<Copy size={18} />}
                      onClick={handleCopyPublicKey}
                    >
                      Copy Public Key
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
                  onClick={() => queryClient.invalidateQueries('ssh-connections')}
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
              <TableContainer>
                <Table>
                  <TableHead>
                    <TableRow>
                      <TableCell>Status</TableCell>
                      <TableCell>Host</TableCell>
                      <TableCell>Username</TableCell>
                      <TableCell>Port</TableCell>
                      <TableCell>Last Test</TableCell>
                      <TableCell align="right">Actions</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {connections.map((connection) => (
                      <TableRow key={connection.id}>
                        <TableCell>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            {getStatusIcon(connection.status)}
                            <Chip
                              label={connection.status}
                              size="small"
                              color={getStatusColor(connection.status)}
                              sx={{ height: 20, fontSize: '0.7rem' }}
                            />
                          </Stack>
                        </TableCell>
                        <TableCell>
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
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">
                            {connection.username}
                          </Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="body2">{connection.port}</Typography>
                        </TableCell>
                        <TableCell>
                          <Typography variant="caption" color="text.secondary">
                            {connection.last_test
                              ? new Date(connection.last_test).toLocaleString()
                              : 'Never'}
                          </Typography>
                        </TableCell>
                        <TableCell align="right">
                          <Tooltip title="Test connection">
                            <IconButton
                              size="small"
                              onClick={() => handleTestConnection(connection)}
                              disabled={testConnectionMutation.isLoading}
                            >
                              <RefreshCw size={16} />
                            </IconButton>
                          </Tooltip>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
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
            disabled={generateKeyMutation.isLoading}
          >
            {generateKeyMutation.isLoading ? 'Generating...' : 'Generate Key'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Deploy Key Dialog */}
      <Dialog
        open={deployDialogOpen}
        onClose={() => {
          setDeployDialogOpen(false)
          setManualDeployment(false)
        }}
        maxWidth="sm"
        fullWidth
      >
        <DialogTitle>Deploy SSH Key to Server</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            {/* Manual Deployment Option */}
            <FormControlLabel
              control={
                <Checkbox
                  checked={manualDeployment}
                  onChange={(e) => setManualDeployment(e.target.checked)}
                />
              }
              label="I deployed the SSH key manually"
            />

            {/* Show public key and instructions when manual deployment is selected */}
            {manualDeployment && (
              <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
                <Typography variant="body2" fontWeight={600} gutterBottom>
                  Manual Deployment Instructions:
                </Typography>
                <Typography variant="caption" component="div" sx={{ mb: 1 }}>
                  1. Copy the public key above (from the System SSH Key section)
                </Typography>
                <Typography variant="caption" component="div" sx={{ mb: 1 }}>
                  2. SSH into your server
                </Typography>
                <Typography variant="caption" component="div" sx={{ mb: 1 }}>
                  3. Add it to: <code style={{ background: '#e3f2fd', padding: '2px 4px', borderRadius: '2px' }}>~/.ssh/authorized_keys</code>
                </Typography>
                <Typography variant="caption" component="div">
                  4. Enter your server details below to test the connection
                </Typography>
              </Alert>
            )}

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

            {/* Only show password field if NOT manual deployment */}
            {!manualDeployment && (
              <>
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
                <Alert severity="info" sx={{ fontSize: '0.85rem' }}>
                  The password is used to deploy your public key to the server's
                  authorized_keys file. After deployment, you'll connect using the SSH
                  key.
                </Alert>
              </>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => {
            setDeployDialogOpen(false)
            setManualDeployment(false)
          }}>
            Cancel
          </Button>
          <Button
            variant="contained"
            onClick={handleDeployKey}
            disabled={
              (deployKeyMutation.isLoading || testConnectionMutation.isLoading) ||
              !connectionForm.host ||
              !connectionForm.username ||
              (!manualDeployment && !connectionForm.password)
            }
          >
            {(deployKeyMutation.isLoading || testConnectionMutation.isLoading)
              ? (manualDeployment ? 'Testing...' : 'Deploying...')
              : (manualDeployment ? 'Test Connection' : 'Deploy Key')}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}
