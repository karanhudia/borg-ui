import { useState, useEffect } from 'react'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Stepper,
  Step,
  StepLabel,
  Box,
  Button,
  TextField,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  Paper,
  Chip,
  InputAdornment,
  IconButton,
  Card,
  CardContent,
  CardActionArea,
} from '@mui/material'
import { FolderOpen, Server, Cloud, HardDrive, Laptop } from 'lucide-react'
import CompressionSettings from './CompressionSettings'
import CommandPreview from './CommandPreview'
import SourceDirectoriesInput from './SourceDirectoriesInput'
import ExcludePatternInput from './ExcludePatternInput'
import FileExplorerDialog from './FileExplorerDialog'
import { sshKeysAPI } from '../services/api'

interface RepositoryWizardProps {
  open: boolean
  onClose: () => void
  mode: 'create' | 'edit' | 'import'
  repository?: any
  onSubmit: (data: any) => void
}

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
  ssh_key_id: number
  default_path?: string
  mount_point?: string
  status: string
}

const RepositoryWizard = ({ open, onClose, mode, repository, onSubmit }: RepositoryWizardProps) => {
  const [activeStep, setActiveStep] = useState(0)

  // Form state
  const [name, setName] = useState('')
  const [repositoryMode, setRepositoryMode] = useState<'full' | 'observe'>('full')

  // Step 1: Repository Location
  const [repositoryLocation, setRepositoryLocation] = useState<'local' | 'ssh'>('local')
  const [path, setPath] = useState('')
  const [repositoryType, setRepositoryType] = useState<'local' | 'ssh' | 'sftp'>('local')
  const [repoSshConnectionId, setRepoSshConnectionId] = useState<number | ''>('')
  const [host, setHost] = useState('')
  const [username, setUsername] = useState('')
  const [port, setPort] = useState('22')
  const [sshKeyId, setSshKeyId] = useState<number | ''>('')

  // Step 2: Data Source
  const [dataSource, setDataSource] = useState<'local' | 'remote'>('local')
  const [sourceSshConnectionId, setSourceSshConnectionId] = useState<number | ''>('')

  // Security
  const [encryption, setEncryption] = useState('repokey')
  const [passphrase, setPassphrase] = useState('')
  const [remotePath, setRemotePath] = useState('')
  const [selectedKeyfile, setSelectedKeyfile] = useState<File | null>(null)

  // Backup Configuration
  const [compression, setCompression] = useState('lz4')
  const [sourceDirs, setSourceDirs] = useState<string[]>([])
  const [excludePatterns, setExcludePatterns] = useState<string[]>([])
  const [customFlags, setCustomFlags] = useState('')

  // Data from API
  const [sshConnections, setSshConnections] = useState<SSHConnection[]>([])

  // File explorer states
  const [showPathExplorer, setShowPathExplorer] = useState(false)
  const [showSourceExplorer, setShowSourceExplorer] = useState(false)
  const [showExcludeExplorer, setShowExcludeExplorer] = useState(false)

  // Load SSH connections
  useEffect(() => {
    if (open) {
      loadSshData()
      if (mode === 'edit' && repository) {
        populateEditData()
      } else {
        resetForm()
      }
    }
  }, [open, mode, repository])

  const loadSshData = async () => {
    try {
      const connectionsRes = await sshKeysAPI.getSSHConnections()
      const connections = connectionsRes.data?.connections || []
      setSshConnections(Array.isArray(connections) ? connections : [])
    } catch (error) {
      console.error('Failed to load SSH data:', error)
      setSshConnections([])
    }
  }

  const populateEditData = () => {
    if (!repository) return
    setName(repository.name || '')
    setRepositoryMode(repository.mode || 'full')
    setPath(repository.path || '')
    setRepositoryType(repository.repository_type || 'local')
    setRepositoryLocation(repository.repository_type === 'local' ? 'local' : 'ssh')
    setHost(repository.host || '')
    setUsername(repository.username || '')
    setPort(String(repository.port || 22))
    setSshKeyId(repository.ssh_key_id || '')
    setEncryption(repository.encryption || 'repokey')
    setPassphrase(repository.passphrase || '')
    setRemotePath(repository.remote_path || '')
    setCompression(repository.compression || 'lz4')
    setSourceDirs(repository.source_directories || [])
    setExcludePatterns(repository.exclude_patterns || [])
    setCustomFlags(repository.custom_flags || '')
  }

  const resetForm = () => {
    setActiveStep(0)
    setName('')
    setRepositoryMode('full')
    setRepositoryLocation('local')
    setPath('')
    setRepositoryType('local')
    setRepoSshConnectionId('')
    setHost('')
    setUsername('')
    setPort('22')
    setSshKeyId('')
    setDataSource('local')
    setSourceSshConnectionId('')
    setEncryption('repokey')
    setPassphrase('')
    setRemotePath('')
    setCompression('lz4')
    setSourceDirs([])
    setExcludePatterns([])
    setCustomFlags('')
    setSelectedKeyfile(null)
  }

  // Handle SSH connection selection for repository
  const handleRepoSshConnectionSelect = (connectionId: number) => {
    const connection = sshConnections.find((c) => c.id === connectionId)
    if (connection) {
      setRepoSshConnectionId(connectionId)
      setRepositoryType('ssh')
      setHost(connection.host)
      setUsername(connection.username)
      setPort(String(connection.port))
      setSshKeyId(connection.ssh_key_id)
      if (connection.default_path) {
        setPath(connection.default_path)
      }
    }
  }

  // Handle SSH connection selection for source
  const handleSourceSshConnectionSelect = (connectionId: number) => {
    const connection = sshConnections.find((c) => c.id === connectionId)
    if (connection) {
      setSourceSshConnectionId(connectionId)
      // Store connection details for later use
      // We'll need this for the API call
    }
  }

  const getSteps = () => {
    if (mode === 'import') {
      return ['Repository Location', 'Security', 'Review']
    }
    if (repositoryMode === 'observe') {
      return ['Repository Location', 'Security', 'Review']
    }
    return ['Repository Location', 'Data Source', 'Security', 'Backup Configuration', 'Review']
  }

  const steps = getSteps()

  const handleNext = () => {
    setActiveStep((prev) => prev + 1)
  }

  const handleBack = () => {
    setActiveStep((prev) => prev - 1)
  }

  const handleSubmit = () => {
    const data: any = {
      name,
      mode: repositoryMode,
      path,
      repository_type: repositoryType,
      encryption,
      passphrase,
      compression,
      source_directories: sourceDirs,
      exclude_patterns: excludePatterns,
      custom_flags: customFlags,
      remote_path: remotePath,
    }

    if (repositoryType === 'ssh') {
      data.host = host
      data.username = username
      data.port = parseInt(port) || 22
      data.ssh_key_id = sshKeyId
    }

    // Add source connection info if remote source
    if (dataSource === 'remote' && sourceSshConnectionId) {
      data.source_connection_id = sourceSshConnectionId
    }

    onSubmit(data)
  }

  const canProceed = () => {
    if (activeStep === 0) {
      if (!name.trim() || !path.trim()) return false
      if (repositoryLocation === 'ssh' && !repoSshConnectionId) return false
      return true
    }
    if (activeStep === 1 && repositoryMode === 'full' && mode !== 'import') {
      // Data source step
      if (dataSource === 'remote' && !sourceSshConnectionId) return false
      if (dataSource === 'local' && sourceDirs.length === 0) return false
      return true
    }
    if (activeStep === 2 || (activeStep === 1 && (repositoryMode === 'observe' || mode === 'import'))) {
      // Security step
      if (encryption !== 'none' && !passphrase.trim()) return false
      return true
    }
    return true
  }

  // Render step content
  const renderStepContent = () => {
    if (activeStep === 0) {
      return renderRepositoryLocation()
    }
    if (activeStep === 1) {
      if (repositoryMode === 'full' && mode !== 'import') {
        return renderDataSource()
      }
      return renderSecurity()
    }
    if (activeStep === 2) {
      if (repositoryMode === 'full' && mode !== 'import') {
        return renderSecurity()
      }
      return renderBackupConfiguration()
    }
    if (activeStep === 3) {
      if (repositoryMode === 'full' && mode !== 'import') {
        return renderBackupConfiguration()
      }
      return renderReview()
    }
    if (activeStep === 4) {
      return renderReview()
    }
    return null
  }

  const renderRepositoryLocation = () => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Name and Mode */}
      <TextField
        label="Repository Name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        fullWidth
        helperText="A friendly name to identify this repository"
      />

{mode === 'import' && (
        <FormControl fullWidth>
          <InputLabel>Repository Mode</InputLabel>
          <Select
            value={repositoryMode}
            label="Repository Mode"
            onChange={(e) => setRepositoryMode(e.target.value as 'full' | 'observe')}
          >
            <MenuItem value="full">
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Full Repository
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Create backups and browse archives
                </Typography>
              </Box>
            </MenuItem>
            <MenuItem value="observe">
              <Box>
                <Typography variant="body2" fontWeight={600}>
                  Observability Only
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Browse and restore only (no backups)
                </Typography>
              </Box>
            </MenuItem>
          </Select>
        </FormControl>
      )}

      {mode === 'import' && repositoryMode === 'observe' && (
        <Alert severity="info">
          Observability-only repositories can browse and restore existing archives but cannot create
          new backups.
        </Alert>
      )}

      {/* Location Selection Cards */}
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2 }}>
          Where should backups be stored?
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: repositoryLocation === 'local' ? 2 : 1,
              borderColor: repositoryLocation === 'local' ? 'primary.main' : 'divider',
            }}
          >
            <CardActionArea onClick={() => {
              setRepositoryLocation('local')
              setRepositoryType('local')
              setRepoSshConnectionId('')
            }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Server size={24} color={repositoryLocation === 'local' ? '#1976d2' : '#666'} />
                  <Typography variant="h6">Borg UI Server</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Store backups on this server's local storage
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>

          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: repositoryLocation === 'ssh' ? 2 : 1,
              borderColor: repositoryLocation === 'ssh' ? 'primary.main' : 'divider',
            }}
          >
            <CardActionArea onClick={() => {
              setRepositoryLocation('ssh')
              setRepositoryType('ssh')
            }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <Cloud size={24} color={repositoryLocation === 'ssh' ? '#1976d2' : '#666'} />
                  <Typography variant="h6">Remote Client</Typography>
                </Box>
                <Typography variant="body2" color="text.secondary">
                  Store backups on a remote machine via SSH
                </Typography>
              </CardContent>
            </CardActionArea>
          </Card>
        </Box>
      </Box>

      {/* SSH Connection Selection */}
      {repositoryLocation === 'ssh' && (
        <>
          {(!Array.isArray(sshConnections) || sshConnections.length === 0) ? (
            <Alert severity="warning">
              No SSH connections configured. Please configure SSH connections in the SSH Keys page first.
            </Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel>Select SSH Connection</InputLabel>
              <Select
                value={repoSshConnectionId === '' ? '' : String(repoSshConnectionId)}
                label="Select SSH Connection"
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    handleRepoSshConnectionSelect(Number(value))
                  }
                }}
                sx={{
                  '& .MuiSelect-select': {
                    py: '16.5px',
                    display: 'flex',
                    alignItems: 'center',
                  }
                }}
              >
                {sshConnections.map((conn) => (
                  <MenuItem key={conn.id} value={String(conn.id)}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                      <Cloud size={16} />
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2">
                          {conn.username}@{conn.host}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Port {conn.port}
                          {conn.mount_point && ` • ${conn.mount_point}`}
                        </Typography>
                      </Box>
                      {conn.status === 'connected' && (
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: 'success.main',
                          }}
                          title="Connected"
                        />
                      )}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}
        </>
      )}

      {/* Path Input */}
      <TextField
        label="Repository Path"
        value={path}
        onChange={(e) => setPath(e.target.value)}
        placeholder={
          repositoryLocation === 'local' ? '/backups/my-repo' : '/path/on/remote/server'
        }
        required
        fullWidth
        helperText="Path where the repository will be stored"
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={() => setShowPathExplorer(true)}
                edge="end"
                size="small"
                title="Browse filesystem"
                disabled={repositoryLocation === 'ssh' && !repoSshConnectionId}
              >
                <FolderOpen fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
        }}
      />
    </Box>
  )

  const renderDataSource = () => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <Typography variant="subtitle2" gutterBottom>
        Where is the data you want to back up?
      </Typography>

      <Box sx={{ display: 'flex', gap: 2 }}>
        <Card
          variant="outlined"
          sx={{
            flex: 1,
            border: dataSource === 'local' ? 2 : 1,
            borderColor: dataSource === 'local' ? 'primary.main' : 'divider',
          }}
        >
          <CardActionArea onClick={() => setDataSource('local')}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <HardDrive size={24} color={dataSource === 'local' ? '#1976d2' : '#666'} />
                <Typography variant="h6">Borg UI Server</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Back up data from this server (local or mounted filesystems)
              </Typography>
            </CardContent>
          </CardActionArea>
        </Card>

        <Card
          variant="outlined"
          sx={{
            flex: 1,
            border: dataSource === 'remote' ? 2 : 1,
            borderColor: dataSource === 'remote' ? 'primary.main' : 'divider',
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          <CardActionArea
            onClick={() => {
              setDataSource('remote')
              // If repository is on a remote client, auto-select the same client for data source
              if (repositoryLocation === 'ssh' && repoSshConnectionId) {
                handleSourceSshConnectionSelect(repoSshConnectionId)
              }
            }}
            sx={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'stretch' }}
          >
            <CardContent sx={{ flex: 1 }}>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                <Laptop size={24} color={dataSource === 'remote' ? '#1976d2' : '#666'} />
                <Typography variant="h6">Remote Machine</Typography>
              </Box>
              <Typography variant="body2" color="text.secondary">
                Back up data from a remote machine via SSH
              </Typography>
            </CardContent>
          </CardActionArea>
        </Card>
      </Box>

      {dataSource === 'local' && (
        <SourceDirectoriesInput
          directories={sourceDirs}
          onChange={setSourceDirs}
          onBrowseClick={() => setShowSourceExplorer(true)}
        />
      )}

      {dataSource === 'remote' && (
        <>
          {/* Show warning if repo is also on a remote client */}
          {repositoryLocation === 'ssh' && repoSshConnectionId && (
            <Alert severity="info">
              <Typography variant="body2">
                <strong>Note:</strong> You can only select the same remote machine that stores the repository.
                Backing up from one remote client to another is not supported.
              </Typography>
            </Alert>
          )}

          {(!Array.isArray(sshConnections) || sshConnections.length === 0) ? (
            <Alert severity="warning">
              No SSH connections configured. Please configure SSH connections in the SSH Keys page first.
            </Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel>Select Remote Machine</InputLabel>
              <Select
                value={sourceSshConnectionId === '' ? '' : String(sourceSshConnectionId)}
                label="Select Remote Machine"
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    handleSourceSshConnectionSelect(Number(value))
                  }
                }}
                sx={{
                  '& .MuiSelect-select': {
                    py: '16.5px',
                    display: 'flex',
                    alignItems: 'center',
                  }
                }}
              >
                {sshConnections
                  .filter((conn) => {
                    // If repository is on a remote client, only show that same client
                    if (repositoryLocation === 'ssh' && repoSshConnectionId) {
                      return conn.id === repoSshConnectionId
                    }
                    return true
                  })
                  .map((conn) => (
                  <MenuItem key={conn.id} value={String(conn.id)}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, width: '100%' }}>
                      <Laptop size={16} />
                      <Box sx={{ flex: 1 }}>
                        <Typography variant="body2">
                          {conn.username}@{conn.host}
                        </Typography>
                        <Typography variant="caption" color="text.secondary">
                          Port {conn.port}
                          {conn.mount_point && ` • ${conn.mount_point}`}
                        </Typography>
                      </Box>
                      {conn.status === 'connected' && (
                        <Box
                          sx={{
                            width: 8,
                            height: 8,
                            borderRadius: '50%',
                            bgcolor: 'success.main',
                          }}
                          title="Connected"
                        />
                      )}
                    </Box>
                  </MenuItem>
                ))}
              </Select>
            </FormControl>
          )}

          <Alert severity="info">
            <Typography variant="body2">
              <strong>Note:</strong> The Borg UI server will mount the remote machine's filesystem and perform the backup.
              Data will be pulled from the remote machine to the repository.
            </Typography>
          </Alert>
        </>
      )}
    </Box>
  )

  const renderSecurity = () => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {mode === 'create' && (
        <FormControl fullWidth>
          <InputLabel>Encryption</InputLabel>
          <Select
            value={encryption}
            label="Encryption"
            onChange={(e) => setEncryption(e.target.value)}
          >
            <MenuItem value="repokey">Repokey (Recommended)</MenuItem>
            <MenuItem value="keyfile">Keyfile</MenuItem>
            <MenuItem value="none">None (Unencrypted)</MenuItem>
          </Select>
        </FormControl>
      )}

      {encryption !== 'none' && (
        <TextField
          label="Passphrase"
          type="password"
          value={passphrase}
          onChange={(e) => setPassphrase(e.target.value)}
          placeholder="Enter passphrase"
          required
          fullWidth
          helperText="Keep this safe - you cannot access backups without it!"
        />
      )}

      {mode === 'import' && (
        <Box>
          <Typography variant="subtitle2" gutterBottom>
            Borg Keyfile (Optional)
          </Typography>
          <Typography variant="caption" color="text.secondary" display="block" sx={{ mb: 1 }}>
            Upload keyfile if using keyfile/keyfile-blake2 encryption (found in ~/.config/borg/keys/)
          </Typography>
          <Button variant="outlined" component="label" fullWidth>
            {selectedKeyfile ? `Selected: ${selectedKeyfile.name}` : 'Choose Keyfile'}
            <input
              type="file"
              hidden
              accept=".key,*"
              onChange={(e) => {
                if (e.target.files && e.target.files[0]) {
                  setSelectedKeyfile(e.target.files[0])
                }
              }}
            />
          </Button>
          {selectedKeyfile && (
            <Alert severity="success" sx={{ mt: 1 }}>
              Keyfile will be uploaded after import
            </Alert>
          )}
        </Box>
      )}

      <TextField
        label="Remote Path (Optional)"
        value={remotePath}
        onChange={(e) => setRemotePath(e.target.value)}
        placeholder="/usr/local/bin/borg"
        fullWidth
        helperText="Path to borg executable on remote (if not in PATH)"
      />
    </Box>
  )

  const renderBackupConfiguration = () => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      <CompressionSettings value={compression} onChange={setCompression} />

      {dataSource === 'local' && (
        <>
          <ExcludePatternInput
            patterns={excludePatterns}
            onChange={setExcludePatterns}
            onBrowseClick={() => setShowExcludeExplorer(true)}
          />

          <TextField
            label="Custom Borg Flags (Optional)"
            value={customFlags}
            onChange={(e) => setCustomFlags(e.target.value)}
            placeholder="--one-file-system --keep-exclude-tags"
            fullWidth
            multiline
            rows={2}
            helperText="Additional borg create flags (advanced)"
          />
        </>
      )}

      {dataSource === 'remote' && (
        <Alert severity="info">
          <Typography variant="body2">
            Source directories and exclude patterns will be configured on the remote machine during
            backup execution.
          </Typography>
        </Alert>
      )}
    </Box>
  )

  const renderReview = () => (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {dataSource === 'local' && (
        <CommandPreview
          mode={mode === 'create' ? 'create' : 'import'}
          repositoryPath={path}
          repositoryType={repositoryType}
          host={host}
          username={username}
          port={parseInt(port) || 22}
          encryption={encryption}
          compression={compression}
          excludePatterns={excludePatterns}
          sourceDirs={sourceDirs}
          customFlags={customFlags}
          remotePath={remotePath}
          repositoryMode={repositoryMode}
        />
      )}

      <Paper variant="outlined" sx={{ p: 2 }}>
        <Typography variant="subtitle2" gutterBottom>
          Summary
        </Typography>
        <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body2" color="text.secondary">
              Name:
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {name}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body2" color="text.secondary">
              Mode:
            </Typography>
            <Chip label={repositoryMode === 'full' ? 'Full' : 'Observe Only'} size="small" />
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body2" color="text.secondary">
              Repository:
            </Typography>
            <Typography variant="body2" fontWeight={600}>
              {repositoryLocation === 'local' ? 'Local Storage' : 'SSH Remote'}
            </Typography>
          </Box>
          <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
            <Typography variant="body2" color="text.secondary">
              Path:
            </Typography>
            <Typography variant="body2" fontFamily="monospace" fontSize="0.875rem">
              {path}
            </Typography>
          </Box>
          {repositoryMode === 'full' && (
            <>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2" color="text.secondary">
                  Data Source:
                </Typography>
                <Typography variant="body2" fontWeight={600}>
                  {dataSource === 'local' ? 'Borg UI Server' : 'Remote Machine'}
                </Typography>
              </Box>
              <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                <Typography variant="body2" color="text.secondary">
                  Compression:
                </Typography>
                <Typography variant="body2" fontFamily="monospace">
                  {compression}
                </Typography>
              </Box>
              {dataSource === 'local' && (
                <>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">
                      Source Directories:
                    </Typography>
                    <Typography variant="body2">{sourceDirs.length} configured</Typography>
                  </Box>
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">
                      Exclude Patterns:
                    </Typography>
                    <Typography variant="body2">{excludePatterns.length} configured</Typography>
                  </Box>
                </>
              )}
            </>
          )}
        </Box>
      </Paper>

      {mode === 'create' && repositoryMode === 'full' && (
        <Alert severity="success">
          <Typography variant="body2">
            ✓ Repository will be initialized
            {dataSource === 'local' && ' and a test backup will be created'}
          </Typography>
        </Alert>
      )}

      {mode === 'import' && (
        <Alert severity="info">
          <Typography variant="body2">
            Repository will be verified before import. Ensure the passphrase is correct.
          </Typography>
        </Alert>
      )}
    </Box>
  )

  return (
    <>
      <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
        <DialogTitle>
          {mode === 'create' ? 'Create' : mode === 'edit' ? 'Edit' : 'Import'} Repository
        </DialogTitle>
        <DialogContent>
          <Box sx={{ mt: 2 }}>
            <Stepper activeStep={activeStep} sx={{ mb: 4 }}>
              {steps.map((label) => (
                <Step key={label}>
                  <StepLabel>{label}</StepLabel>
                </Step>
              ))}
            </Stepper>

            <Box sx={{ minHeight: 400 }}>{renderStepContent()}</Box>
          </Box>
        </DialogContent>
        <DialogActions sx={{ px: 3, pb: 2 }}>
          <Button onClick={onClose}>Cancel</Button>
          <Box sx={{ flex: 1 }} />
          <Button disabled={activeStep === 0} onClick={handleBack}>
            Back
          </Button>
          {activeStep < steps.length - 1 ? (
            <Button variant="contained" onClick={handleNext} disabled={!canProceed()}>
              Next
            </Button>
          ) : (
            <Button variant="contained" onClick={handleSubmit} disabled={!canProceed()}>
              {mode === 'create' ? 'Create Repository' : mode === 'edit' ? 'Save Changes' : 'Import Repository'}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* File Explorer Dialogs */}
      <FileExplorerDialog
        key={`path-explorer-${repositoryLocation}-${repoSshConnectionId}`}
        open={showPathExplorer}
        onClose={() => setShowPathExplorer(false)}
        onSelect={(paths) => {
          if (paths.length > 0) {
            setPath(paths[0])
          }
          setShowPathExplorer(false)
        }}
        title="Select Repository Path"
        initialPath={
          repositoryLocation === 'ssh' && repoSshConnectionId
            ? sshConnections.find((c) => c.id === repoSshConnectionId)?.default_path || '/'
            : '/'
        }
        multiSelect={false}
        connectionType={repositoryLocation === 'local' ? 'local' : 'ssh'}
        sshConfig={
          repositoryLocation === 'ssh' && repoSshConnectionId
            ? (() => {
                const conn = sshConnections.find((c) => c.id === repoSshConnectionId)
                return conn
                  ? {
                      ssh_key_id: conn.ssh_key_id,
                      host: conn.host,
                      username: conn.username,
                      port: conn.port,
                    }
                  : undefined
              })()
            : undefined
        }
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showSourceExplorer}
        onClose={() => setShowSourceExplorer(false)}
        onSelect={(paths) => {
          setSourceDirs([...sourceDirs, ...paths])
        }}
        title="Select Source Directories"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="directories"
      />

      <FileExplorerDialog
        open={showExcludeExplorer}
        onClose={() => setShowExcludeExplorer(false)}
        onSelect={(paths) => {
          setExcludePatterns([...excludePatterns, ...paths])
        }}
        title="Select Directories/Files to Exclude"
        initialPath="/"
        multiSelect={true}
        connectionType="local"
        selectMode="both"
      />
    </>
  )
}

export default RepositoryWizard
