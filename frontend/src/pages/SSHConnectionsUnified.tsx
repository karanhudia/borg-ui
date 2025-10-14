import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import { toast } from 'react-hot-toast'
import {
  Box,
  Card,
  CardContent,
  Typography,
  Button,
  IconButton,
  Chip,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Alert,
  Divider,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Checkbox,
  FormControlLabel,
  Tooltip,
  Stack,
} from '@mui/material'
import {
  Key,
  Add,
  Edit,
  Delete,
  Refresh,
  PlayArrow,
  CheckCircle,
  Cancel,
  Warning,
  Rocket,
} from '@mui/icons-material'
import { sshKeysAPI } from '../services/api'

interface SSHKey {
  id: number
  name: string
  description: string | null
  key_type: string
  public_key: string
  is_active: boolean
  created_at: string
  updated_at: string | null
  connection_count: number
  active_connections: number
}

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  status: string
  last_test: string | null
  last_success: string | null
  error_message: string | null
  created_at: string
}

export default function SSHConnectionsUnified() {
  const [selectedKey, setSelectedKey] = useState<SSHKey | null>(null)
  const [showQuickSetupDialog, setShowQuickSetupDialog] = useState(false)
  const [showGenerateDialog, setShowGenerateDialog] = useState(false)
  const [showDeployDialog, setShowDeployDialog] = useState(false)
  const [showTestDialog, setShowTestDialog] = useState(false)
  const [showEditDialog, setShowEditDialog] = useState(false)
  const [showAddConnectionDialog, setShowAddConnectionDialog] = useState(false)

  const queryClient = useQueryClient()

  // Queries
  const { data: sshKeysData, isLoading: loadingKeys } = useQuery({
    queryKey: ['ssh-keys'],
    queryFn: sshKeysAPI.getSSHKeys,
  })

  const { data: connectionsData, isLoading: loadingConnections } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    refetchInterval: 30000,
  })

  // Form states
  const [quickSetupForm, setQuickSetupForm] = useState({
    name: '',
    key_type: 'ed25519',
    description: '',
    host: '',
    username: '',
    port: 22,
    password: '',
    skip_deployment: false,
  })

  const [generateForm, setGenerateForm] = useState({
    name: '',
    description: '',
    key_type: 'rsa',
  })

  const [deployForm, setDeployForm] = useState({
    host: '',
    username: '',
    port: 22,
    password: '',
  })

  const [testForm, setTestForm] = useState({
    host: '',
    username: '',
    port: 22,
  })

  const [editForm, setEditForm] = useState({
    name: '',
    description: '',
    is_active: true,
  })

  const [connectionForm, setConnectionForm] = useState({
    ssh_key_id: '',
    host: '',
    username: '',
    port: 22,
  })

  // Mutations
  const quickSetupMutation = useMutation({
    mutationFn: sshKeysAPI.quickSetup,
    onSuccess: (data: any) => {
      queryClient.invalidateQueries(['ssh-keys'])
      queryClient.invalidateQueries(['ssh-connections'])
      setShowQuickSetupDialog(false)
      if (data.success) {
        toast.success('SSH key generated and deployed successfully!')
      } else {
        toast.error(`SSH key generated but deployment failed: ${data.detail || 'Connection failed'}`)
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Quick setup failed')
    },
  })

  const generateSSHKeyMutation = useMutation({
    mutationFn: sshKeysAPI.generateSSHKey,
    onSuccess: () => {
      queryClient.invalidateQueries(['ssh-keys'])
      setShowGenerateDialog(false)
      toast.success('SSH key generated successfully!')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to generate SSH key')
    },
  })

  const deploySSHKeyMutation = useMutation({
    mutationFn: ({ keyId, data }: { keyId: number; data: any }) =>
      sshKeysAPI.deploySSHKey(keyId, data),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries(['ssh-connections'])
      setShowDeployDialog(false)
      if (data.success) {
        toast.success('SSH key deployed successfully!')
      } else {
        toast.error('SSH key deployment failed')
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to deploy SSH key')
    },
  })

  const testConnectionMutation = useMutation({
    mutationFn: ({ keyId, data }: { keyId: number; data: any }) =>
      sshKeysAPI.testSSHConnection(keyId, data),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries(['ssh-connections'])
      setShowTestDialog(false)
      setShowAddConnectionDialog(false)
      if (data.success) {
        toast.success('SSH connection successful!')
      } else {
        toast.error(`SSH connection failed: ${data.connection?.error_message || 'Unknown error'}`)
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to test SSH connection')
    },
  })

  const updateSSHKeyMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: any }) =>
      sshKeysAPI.updateSSHKey(id, data),
    onSuccess: () => {
      queryClient.invalidateQueries(['ssh-keys'])
      setShowEditDialog(false)
      toast.success('SSH key updated successfully!')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to update SSH key')
    },
  })

  const deleteSSHKeyMutation = useMutation({
    mutationFn: sshKeysAPI.deleteSSHKey,
    onSuccess: () => {
      queryClient.invalidateQueries(['ssh-keys'])
      queryClient.invalidateQueries(['ssh-connections'])
      setSelectedKey(null)
      toast.success('SSH key deleted successfully!')
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to delete SSH key')
    },
  })

  // Event handlers
  const handleQuickSetup = (e: React.FormEvent) => {
    e.preventDefault()
    quickSetupMutation.mutate(quickSetupForm)
  }

  const handleGenerateKey = (e: React.FormEvent) => {
    e.preventDefault()
    generateSSHKeyMutation.mutate(generateForm)
  }

  const handleDeployKey = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedKey) {
      deploySSHKeyMutation.mutate({ keyId: selectedKey.id, data: deployForm })
    }
  }

  const handleTestConnection = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedKey) {
      testConnectionMutation.mutate({ keyId: selectedKey.id, data: testForm })
    }
  }

  const handleAddConnection = (e: React.FormEvent) => {
    e.preventDefault()
    const keyId = parseInt(connectionForm.ssh_key_id)
    if (isNaN(keyId)) {
      toast.error('Please select a valid SSH key')
      return
    }
    testConnectionMutation.mutate({
      keyId,
      data: {
        host: connectionForm.host,
        username: connectionForm.username,
        port: connectionForm.port,
      },
    })
  }

  const handleUpdateKey = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedKey) {
      updateSSHKeyMutation.mutate({ id: selectedKey.id, data: editForm })
    }
  }

  const handleDeleteKey = (key: SSHKey) => {
    if (window.confirm(`Are you sure you want to delete SSH key "${key.name}"?`)) {
      deleteSSHKeyMutation.mutate(key.id)
    }
  }

  const handleRetryConnection = (connection: SSHConnection) => {
    testConnectionMutation.mutate({
      keyId: connection.ssh_key_id,
      data: {
        host: connection.host,
        username: connection.username,
        port: connection.port,
      },
    })
  }

  // Utility functions
  const getKeyTypeColor = (keyType: string) => {
    switch (keyType) {
      case 'rsa':
        return 'primary'
      case 'ed25519':
        return 'success'
      case 'ecdsa':
        return 'secondary'
      default:
        return 'default'
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'success'
      case 'failed':
        return 'error'
      case 'testing':
        return 'warning'
      default:
        return 'default'
    }
  }

  const formatDate = (dateString: string | null) => {
    if (!dateString) return 'Never'
    return new Date(dateString).toLocaleString()
  }

  const getTimeSince = (dateString: string | null) => {
    if (!dateString) return 'Never'
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  }

  const sshKeys = sshKeysData?.data?.ssh_keys || []
  const connections = connectionsData?.data?.connections || []
  const selectedKeyConnections = selectedKey
    ? connections.filter((c: SSHConnection) => c.ssh_key_id === selectedKey.id)
    : []

  const connectedCount = connections.filter((c: SSHConnection) => c.status === 'connected').length
  const failedCount = connections.filter((c: SSHConnection) => c.status === 'failed').length

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 3, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Box>
          <Typography variant="h4" fontWeight={600} gutterBottom>
            SSH Connections
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Manage SSH keys and their connections to remote machines
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Button
            variant="contained"
            startIcon={<Rocket />}
            onClick={() => setShowQuickSetupDialog(true)}
          >
            Quick Setup
          </Button>
          <Button
            variant="outlined"
            startIcon={<Add />}
            onClick={() => setShowGenerateDialog(true)}
          >
            Generate Key
          </Button>
        </Box>
      </Box>

      {/* Statistics Cards */}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3} sx={{ mb: 3 }}>
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Total Keys
                  </Typography>
                  <Typography variant="h3" fontWeight={700}>
                    {sshKeys.length}
                  </Typography>
                </Box>
                <Key sx={{ fontSize: 40, color: 'primary.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Box>
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Active Connections
                  </Typography>
                  <Typography variant="h3" fontWeight={700} color="success.main">
                    {connectedCount}
                  </Typography>
                </Box>
                <CheckCircle sx={{ fontSize: 40, color: 'success.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Box>
        <Box sx={{ flex: 1 }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Failed Connections
                  </Typography>
                  <Typography variant="h3" fontWeight={700} color="error.main">
                    {failedCount}
                  </Typography>
                </Box>
                <Cancel sx={{ fontSize: 40, color: 'error.main' }} />
              </Box>
            </CardContent>
          </Card>
        </Box>
      </Stack>

      {/* Failed Connections Alert */}
      {failedCount > 0 && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          <Typography variant="subtitle2" fontWeight={600}>
            Failed Connections Detected
          </Typography>
          <Typography variant="body2">
            {failedCount} connection{failedCount > 1 ? 's have' : ' has'} failed. You can retry them from the connections list below.
          </Typography>
        </Alert>
      )}

      {/* Main Content Grid */}
      <Stack direction={{ xs: 'column', md: 'row' }} spacing={3}>
        {/* SSH Keys Panel (Left 40%) */}
        <Box sx={{ flex: { xs: 1, md: '0 0 42%' } }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" fontWeight={600}>
                  SSH Keys ({sshKeys.length})
                </Typography>
                <IconButton
                  size="small"
                  onClick={() => queryClient.invalidateQueries(['ssh-keys'])}
                >
                  <Refresh />
                </IconButton>
              </Box>
              <Divider sx={{ mb: 2 }} />
              {loadingKeys ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    Loading SSH keys...
                  </Typography>
                </Box>
              ) : sshKeys.length === 0 ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Key sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    No SSH keys yet
                  </Typography>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<Rocket />}
                    onClick={() => setShowQuickSetupDialog(true)}
                    sx={{ mt: 2 }}
                  >
                    Quick Setup
                  </Button>
                </Box>
              ) : (
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
                  {sshKeys.map((key: SSHKey) => (
                    <Card
                      key={key.id}
                      variant="outlined"
                      sx={{
                        cursor: 'pointer',
                        border: selectedKey?.id === key.id ? 2 : 1,
                        borderColor: selectedKey?.id === key.id ? 'primary.main' : 'divider',
                        '&:hover': { borderColor: 'primary.main' },
                      }}
                      onClick={() => setSelectedKey(key)}
                    >
                      <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'start', mb: 1 }}>
                          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                            <Key sx={{ fontSize: 20 }} />
                            <Typography variant="subtitle2" fontWeight={600}>
                              {key.name}
                            </Typography>
                          </Box>
                          <Box sx={{ display: 'flex', gap: 0.5 }}>
                            <Chip
                              label={key.key_type.toUpperCase()}
                              size="small"
                              color={getKeyTypeColor(key.key_type) as any}
                            />
                            <Chip
                              label={key.is_active ? 'Active' : 'Inactive'}
                              size="small"
                              color={key.is_active ? 'success' : 'default'}
                            />
                          </Box>
                        </Box>
                        {key.description && (
                          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
                            {key.description}
                          </Typography>
                        )}
                        <Typography variant="caption" color="text.secondary">
                          {key.active_connections} active / {key.connection_count} total connections
                        </Typography>
                        <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
                          <Button
                            size="small"
                            startIcon={<Rocket />}
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedKey(key)
                              setShowDeployDialog(true)
                            }}
                          >
                            Deploy
                          </Button>
                          <Button
                            size="small"
                            startIcon={<PlayArrow />}
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedKey(key)
                              setShowTestDialog(true)
                            }}
                          >
                            Test
                          </Button>
                          <IconButton
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation()
                              setSelectedKey(key)
                              setEditForm({
                                name: key.name,
                                description: key.description || '',
                                is_active: key.is_active,
                              })
                              setShowEditDialog(true)
                            }}
                          >
                            <Edit fontSize="small" />
                          </IconButton>
                          <IconButton
                            size="small"
                            color="error"
                            onClick={(e) => {
                              e.stopPropagation()
                              handleDeleteKey(key)
                            }}
                          >
                            <Delete fontSize="small" />
                          </IconButton>
                        </Box>
                      </CardContent>
                    </Card>
                  ))}
                </Box>
              )}
            </CardContent>
          </Card>
        </Box>

        {/* Connections Panel (Right 60%) */}
        <Box sx={{ flex: { xs: 1, md: '0 0 58%' } }}>
          <Card>
            <CardContent>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
                <Typography variant="h6" fontWeight={600}>
                  {selectedKey ? `Connections for ${selectedKey.name}` : 'All Connections'} ({selectedKeyConnections.length || connections.length})
                </Typography>
                <Box sx={{ display: 'flex', gap: 1 }}>
                  <IconButton
                    size="small"
                    onClick={() => queryClient.invalidateQueries(['ssh-connections'])}
                  >
                    <Refresh />
                  </IconButton>
                  <Button
                    size="small"
                    variant="contained"
                    startIcon={<Add />}
                    onClick={() => setShowAddConnectionDialog(true)}
                  >
                    Add Connection
                  </Button>
                </Box>
              </Box>
              <Divider sx={{ mb: 2 }} />
              {loadingConnections ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Typography variant="body2" color="text.secondary">
                    Loading connections...
                  </Typography>
                </Box>
              ) : (selectedKeyConnections.length === 0 && selectedKey) || (connections.length === 0 && !selectedKey) ? (
                <Box sx={{ textAlign: 'center', py: 4 }}>
                  <Warning sx={{ fontSize: 48, color: 'text.disabled', mb: 2 }} />
                  <Typography variant="body2" color="text.secondary" gutterBottom>
                    {selectedKey ? `No connections for ${selectedKey.name}` : 'No connections yet'}
                  </Typography>
                  <Button
                    variant="contained"
                    size="small"
                    startIcon={<Add />}
                    onClick={() => setShowAddConnectionDialog(true)}
                    sx={{ mt: 2 }}
                  >
                    Add Connection
                  </Button>
                </Box>
              ) : (
                <TableContainer>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell>Host</TableCell>
                        <TableCell>Status</TableCell>
                        <TableCell>Last Test</TableCell>
                        <TableCell align="right">Actions</TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {(selectedKey ? selectedKeyConnections : connections).map((connection: SSHConnection) => (
                        <TableRow key={connection.id}>
                          <TableCell>
                            <Typography variant="body2" fontWeight={500}>
                              {connection.username}@{connection.host}:{connection.port}
                            </Typography>
                            {connection.error_message && (
                              <Typography variant="caption" color="error">
                                {connection.error_message}
                              </Typography>
                            )}
                          </TableCell>
                          <TableCell>
                            <Chip
                              label={connection.status}
                              size="small"
                              color={getStatusColor(connection.status) as any}
                            />
                          </TableCell>
                          <TableCell>
                            <Typography variant="caption">
                              {getTimeSince(connection.last_test)}
                            </Typography>
                          </TableCell>
                          <TableCell align="right">
                            <Tooltip title="Test Connection">
                              <IconButton
                                size="small"
                                color="success"
                                onClick={() => handleRetryConnection(connection)}
                              >
                                <PlayArrow fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            {connection.status === 'failed' && (
                              <Tooltip title="Retry">
                                <IconButton
                                  size="small"
                                  color="primary"
                                  onClick={() => handleRetryConnection(connection)}
                                >
                                  <Refresh fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </CardContent>
          </Card>
        </Box>
      </Stack>

      {/* Quick Setup Dialog */}
      <Dialog open={showQuickSetupDialog} onClose={() => setShowQuickSetupDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleQuickSetup}>
          <DialogTitle>Quick SSH Setup</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Key Name"
                value={quickSetupForm.name}
                onChange={(e) => setQuickSetupForm({ ...quickSetupForm, name: e.target.value })}
                required
                fullWidth
              />
              <FormControl fullWidth>
                <InputLabel>Key Type</InputLabel>
                <Select
                  value={quickSetupForm.key_type}
                  label="Key Type"
                  onChange={(e) => setQuickSetupForm({ ...quickSetupForm, key_type: e.target.value })}
                >
                  <MenuItem value="ed25519">Ed25519 (Recommended)</MenuItem>
                  <MenuItem value="rsa">RSA</MenuItem>
                  <MenuItem value="ecdsa">ECDSA</MenuItem>
                </Select>
              </FormControl>
              <TextField
                label="Description (optional)"
                value={quickSetupForm.description}
                onChange={(e) => setQuickSetupForm({ ...quickSetupForm, description: e.target.value })}
                fullWidth
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={quickSetupForm.skip_deployment}
                    onChange={(e) => setQuickSetupForm({ ...quickSetupForm, skip_deployment: e.target.checked })}
                  />
                }
                label="Only generate key (skip deployment)"
              />
              {!quickSetupForm.skip_deployment && (
                <>
                  <Divider />
                  <Typography variant="subtitle2" fontWeight={600}>
                    Deployment Settings
                  </Typography>
                  <TextField
                    label="Host"
                    value={quickSetupForm.host}
                    onChange={(e) => setQuickSetupForm({ ...quickSetupForm, host: e.target.value })}
                    placeholder="192.168.1.250"
                    required={!quickSetupForm.skip_deployment}
                    fullWidth
                  />
                  <TextField
                    label="Username"
                    value={quickSetupForm.username}
                    onChange={(e) => setQuickSetupForm({ ...quickSetupForm, username: e.target.value })}
                    placeholder="username"
                    required={!quickSetupForm.skip_deployment}
                    fullWidth
                  />
                  <TextField
                    label="Port"
                    type="number"
                    value={quickSetupForm.port}
                    onChange={(e) => setQuickSetupForm({ ...quickSetupForm, port: parseInt(e.target.value) })}
                    required={!quickSetupForm.skip_deployment}
                    fullWidth
                  />
                  <TextField
                    label="Password"
                    type="password"
                    value={quickSetupForm.password}
                    onChange={(e) => setQuickSetupForm({ ...quickSetupForm, password: e.target.value })}
                    placeholder="••••••••"
                    required={!quickSetupForm.skip_deployment}
                    fullWidth
                  />
                </>
              )}
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowQuickSetupDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={quickSetupMutation.isLoading}>
              {quickSetupMutation.isLoading
                ? 'Setting up...'
                : quickSetupForm.skip_deployment
                  ? 'Generate Key'
                  : 'Generate & Deploy'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Generate Key Dialog */}
      <Dialog open={showGenerateDialog} onClose={() => setShowGenerateDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleGenerateKey}>
          <DialogTitle>Generate SSH Key</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Name"
                value={generateForm.name}
                onChange={(e) => setGenerateForm({ ...generateForm, name: e.target.value })}
                required
                fullWidth
              />
              <TextField
                label="Description"
                value={generateForm.description}
                onChange={(e) => setGenerateForm({ ...generateForm, description: e.target.value })}
                fullWidth
              />
              <FormControl fullWidth>
                <InputLabel>Key Type</InputLabel>
                <Select
                  value={generateForm.key_type}
                  label="Key Type"
                  onChange={(e) => setGenerateForm({ ...generateForm, key_type: e.target.value })}
                >
                  <MenuItem value="rsa">RSA (Recommended)</MenuItem>
                  <MenuItem value="ed25519">Ed25519 (Modern)</MenuItem>
                  <MenuItem value="ecdsa">ECDSA</MenuItem>
                </Select>
              </FormControl>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowGenerateDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={generateSSHKeyMutation.isLoading}>
              {generateSSHKeyMutation.isLoading ? 'Generating...' : 'Generate'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Deploy Key Dialog */}
      <Dialog open={showDeployDialog} onClose={() => setShowDeployDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleDeployKey}>
          <DialogTitle>Deploy SSH Key: {selectedKey?.name}</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Host"
                value={deployForm.host}
                onChange={(e) => setDeployForm({ ...deployForm, host: e.target.value })}
                placeholder="192.168.1.250"
                required
                fullWidth
              />
              <TextField
                label="Username"
                value={deployForm.username}
                onChange={(e) => setDeployForm({ ...deployForm, username: e.target.value })}
                placeholder="username"
                required
                fullWidth
              />
              <TextField
                label="Port"
                type="number"
                value={deployForm.port}
                onChange={(e) => setDeployForm({ ...deployForm, port: parseInt(e.target.value) })}
                required
                fullWidth
              />
              <TextField
                label="Password"
                type="password"
                value={deployForm.password}
                onChange={(e) => setDeployForm({ ...deployForm, password: e.target.value })}
                placeholder="••••••••"
                required
                fullWidth
              />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowDeployDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={deploySSHKeyMutation.isLoading}>
              {deploySSHKeyMutation.isLoading ? 'Deploying...' : 'Deploy'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Test Connection Dialog */}
      <Dialog open={showTestDialog} onClose={() => setShowTestDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleTestConnection}>
          <DialogTitle>Test Connection: {selectedKey?.name}</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Host"
                value={testForm.host}
                onChange={(e) => setTestForm({ ...testForm, host: e.target.value })}
                placeholder="192.168.1.250"
                required
                fullWidth
              />
              <TextField
                label="Username"
                value={testForm.username}
                onChange={(e) => setTestForm({ ...testForm, username: e.target.value })}
                placeholder="username"
                required
                fullWidth
              />
              <TextField
                label="Port"
                type="number"
                value={testForm.port}
                onChange={(e) => setTestForm({ ...testForm, port: parseInt(e.target.value) })}
                required
                fullWidth
              />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowTestDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={testConnectionMutation.isLoading}>
              {testConnectionMutation.isLoading ? 'Testing...' : 'Test Connection'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Edit Key Dialog */}
      <Dialog open={showEditDialog} onClose={() => setShowEditDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleUpdateKey}>
          <DialogTitle>Edit SSH Key</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <TextField
                label="Name"
                value={editForm.name}
                onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                required
                fullWidth
              />
              <TextField
                label="Description"
                value={editForm.description}
                onChange={(e) => setEditForm({ ...editForm, description: e.target.value })}
                fullWidth
              />
              <FormControlLabel
                control={
                  <Checkbox
                    checked={editForm.is_active}
                    onChange={(e) => setEditForm({ ...editForm, is_active: e.target.checked })}
                  />
                }
                label="Active"
              />
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowEditDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={updateSSHKeyMutation.isLoading}>
              {updateSSHKeyMutation.isLoading ? 'Updating...' : 'Update'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>

      {/* Add Connection Dialog */}
      <Dialog open={showAddConnectionDialog} onClose={() => setShowAddConnectionDialog(false)} maxWidth="sm" fullWidth>
        <form onSubmit={handleAddConnection}>
          <DialogTitle>Add New Connection</DialogTitle>
          <DialogContent>
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, mt: 1 }}>
              <FormControl fullWidth required>
                <InputLabel>SSH Key</InputLabel>
                <Select
                  value={connectionForm.ssh_key_id}
                  label="SSH Key"
                  onChange={(e) => setConnectionForm({ ...connectionForm, ssh_key_id: e.target.value })}
                >
                  {sshKeys
                    .filter((k: SSHKey) => k.is_active)
                    .map((key: SSHKey) => (
                      <MenuItem key={key.id} value={key.id}>
                        {key.name} ({key.key_type})
                      </MenuItem>
                    ))}
                </Select>
              </FormControl>
              <TextField
                label="Host"
                value={connectionForm.host}
                onChange={(e) => setConnectionForm({ ...connectionForm, host: e.target.value })}
                placeholder="192.168.1.250"
                required
                fullWidth
              />
              <TextField
                label="Username"
                value={connectionForm.username}
                onChange={(e) => setConnectionForm({ ...connectionForm, username: e.target.value })}
                placeholder="username"
                required
                fullWidth
              />
              <TextField
                label="Port"
                type="number"
                value={connectionForm.port}
                onChange={(e) => setConnectionForm({ ...connectionForm, port: parseInt(e.target.value) })}
                required
                fullWidth
              />
              <Alert severity="info">
                This will test the SSH connection. Make sure the SSH key is already deployed to the remote machine.
              </Alert>
            </Box>
          </DialogContent>
          <DialogActions>
            <Button onClick={() => setShowAddConnectionDialog(false)}>Cancel</Button>
            <Button type="submit" variant="contained" disabled={testConnectionMutation.isLoading}>
              {testConnectionMutation.isLoading ? 'Testing...' : 'Add & Test Connection'}
            </Button>
          </DialogActions>
        </form>
      </Dialog>
    </Box>
  )
}
