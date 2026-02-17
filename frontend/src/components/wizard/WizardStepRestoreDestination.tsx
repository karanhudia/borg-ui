import {
  Box,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  Card,
  CardContent,
  CardActionArea,
  alpha,
  TextField,
  FormControlLabel,
  Radio,
  RadioGroup,
  Paper,
  InputAdornment,
  IconButton,
} from '@mui/material'
import { Server, Cloud, FileCheck, FolderOpen } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'

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

export interface RestoreDestinationStepData {
  destinationType: 'local' | 'ssh'
  destinationConnectionId: number | ''
  restoreStrategy: 'original' | 'custom'
  customPath: string
}

interface WizardStepRestoreDestinationProps {
  data: RestoreDestinationStepData
  sshConnections: SSHConnection[]
  repositoryType: string
  onChange: (data: Partial<RestoreDestinationStepData>) => void
  onBrowsePath: () => void
}

export default function WizardStepRestoreDestination({
  data,
  sshConnections,
  repositoryType,
  onChange,
  onBrowsePath,
}: WizardStepRestoreDestinationProps) {
  const isSSHRepository = repositoryType === 'ssh'

  const handleLocationChange = (location: 'local' | 'ssh') => {
    // Prevent SSH-to-SSH restore
    if (isSSHRepository && location === 'ssh') {
      return
    }

    onChange({
      destinationType: location,
      destinationConnectionId: '',
    })
  }

  // Get selected SSH connection for preview
  const selectedSshConnection =
    data.destinationType === 'ssh' && data.destinationConnectionId
      ? sshConnections.find((c) => c.id === data.destinationConnectionId)
      : null

  // Build SSH URL preview
  const getSshUrlPreview = () => {
    if (!selectedSshConnection || !data.customPath) return ''
    const path = data.customPath.startsWith('/') ? data.customPath : `/${data.customPath}`
    return `ssh://${selectedSshConnection.username}@${selectedSshConnection.host}:${selectedSshConnection.port}${path}`
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Header */}
      <Box>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          Where should files be restored?
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Select the destination and location for your restored files
        </Typography>
      </Box>

      {/* Destination Selection Cards */}
      <Box sx={{ display: 'flex', gap: 2 }}>
        <Card
          variant="outlined"
          sx={{
            flex: 1,
            border: data.destinationType === 'local' ? 2 : 1,
            borderColor: data.destinationType === 'local' ? '#1976d2' : 'divider',
            boxShadow:
              data.destinationType === 'local' ? `0 4px 12px ${alpha('#1976d2', 0.2)}` : 'none',
            bgcolor:
              data.destinationType === 'local'
                ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                : 'background.paper',
            transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
            transform: data.destinationType === 'local' ? 'translateY(-2px)' : 'none',
            '&:hover': {
              transform: 'translateY(-2px)',
              boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
              borderColor: data.destinationType === 'local' ? '#1976d2' : 'text.primary',
            },
          }}
        >
          <CardActionArea onClick={() => handleLocationChange('local')} sx={{ p: 1 }}>
            <CardContent>
              <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    width: 48,
                    height: 48,
                    borderRadius: 3,
                    bgcolor: data.destinationType === 'local' ? '#1976d2' : 'action.hover',
                    color: data.destinationType === 'local' ? 'white' : 'text.secondary',
                    transition: 'all 0.3s ease',
                    boxShadow:
                      data.destinationType === 'local'
                        ? `0 4px 12px ${alpha('#1976d2', 0.4)}`
                        : 'none',
                  }}
                >
                  <Server size={28} />
                </Box>
                <Box>
                  <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                    Borg UI Server
                  </Typography>
                  <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.8125rem' }}>
                    Restore to this server's local storage
                  </Typography>
                </Box>
              </Box>
            </CardContent>
          </CardActionArea>
        </Card>

        {!isSSHRepository && (
          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: data.destinationType === 'ssh' ? 2 : 1,
              borderColor: data.destinationType === 'ssh' ? '#1976d2' : 'divider',
              boxShadow:
                data.destinationType === 'ssh' ? `0 4px 12px ${alpha('#1976d2', 0.2)}` : 'none',
              bgcolor:
                data.destinationType === 'ssh'
                  ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                  : 'background.paper',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: data.destinationType === 'ssh' ? 'translateY(-2px)' : 'none',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                borderColor: data.destinationType === 'ssh' ? '#1976d2' : 'text.primary',
              },
            }}
          >
            <CardActionArea onClick={() => handleLocationChange('ssh')} sx={{ p: 1 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 1 }}>
                  <Box
                    sx={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      width: 48,
                      height: 48,
                      borderRadius: 3,
                      bgcolor: data.destinationType === 'ssh' ? '#1976d2' : 'action.hover',
                      color: data.destinationType === 'ssh' ? 'white' : 'text.secondary',
                      transition: 'all 0.3s ease',
                      boxShadow:
                        data.destinationType === 'ssh'
                          ? `0 4px 12px ${alpha('#1976d2', 0.4)}`
                          : 'none',
                    }}
                  >
                    <Cloud size={28} />
                  </Box>
                  <Box>
                    <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                      Remote Machine
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ fontSize: '0.8125rem' }}
                    >
                      Restore to a remote machine via SSH
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>
        )}
      </Box>

      {/* SSH Repository Info Alert */}
      {isSSHRepository && (
        <Alert severity="info">
          SSH-to-SSH restore is not supported. Only local destinations are available for SSH
          repositories.
        </Alert>
      )}

      {/* Local Destination: Original vs Custom Location */}
      {data.destinationType === 'local' && (
        <FormControl>
          <RadioGroup
            value={data.restoreStrategy}
            onChange={(e) => onChange({ restoreStrategy: e.target.value as 'original' | 'custom' })}
          >
            <Paper
              variant="outlined"
              sx={{
                p: 2,
                mb: 2,
                border: data.restoreStrategy === 'original' ? 2 : 1,
                borderColor: data.restoreStrategy === 'original' ? '#1976d2' : 'divider',
                bgcolor:
                  data.restoreStrategy === 'original'
                    ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                    : 'background.paper',
                transition: 'all 0.2s',
                cursor: 'pointer',
                '&:hover': {
                  borderColor: data.restoreStrategy === 'original' ? '#1976d2' : 'text.primary',
                },
              }}
              onClick={() => onChange({ restoreStrategy: 'original' })}
            >
              <FormControlLabel
                value="original"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <FileCheck size={18} />
                    <Box>
                      <Typography variant="body1" fontWeight={600}>
                        Restore to Original Location
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Recreate full directory structure from root (/)
                      </Typography>
                    </Box>
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>

            <Paper
              variant="outlined"
              sx={{
                p: 2,
                border: data.restoreStrategy === 'custom' ? 2 : 1,
                borderColor: data.restoreStrategy === 'custom' ? '#1976d2' : 'divider',
                bgcolor:
                  data.restoreStrategy === 'custom'
                    ? (theme) => alpha('#1976d2', theme.palette.mode === 'dark' ? 0.12 : 0.08)
                    : 'background.paper',
                transition: 'all 0.2s',
                cursor: 'pointer',
                '&:hover': {
                  borderColor: data.restoreStrategy === 'custom' ? '#1976d2' : 'text.primary',
                },
              }}
              onClick={() => onChange({ restoreStrategy: 'custom' })}
            >
              <FormControlLabel
                value="custom"
                control={<Radio />}
                label={
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                    <FolderOpen size={18} />
                    <Box>
                      <Typography variant="body1" fontWeight={600}>
                        Restore to Custom Location
                      </Typography>
                      <Typography variant="body2" color="text.secondary">
                        Choose where to restore files
                      </Typography>
                    </Box>
                  </Box>
                }
                sx={{ m: 0, width: '100%' }}
              />
            </Paper>
          </RadioGroup>
        </FormControl>
      )}

      {/* Custom Path Input (for Local destination with Custom strategy) */}
      {data.destinationType === 'local' && data.restoreStrategy === 'custom' && (
        <>
          <TextField
            label="Custom Destination Path"
            value={data.customPath}
            onChange={(e) => onChange({ customPath: e.target.value })}
            placeholder="/Users/yourusername/restored"
            required
            fullWidth
            helperText="Choose a writable directory where files will be restored"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={onBrowsePath}
                    edge="end"
                    size="small"
                    title="Browse filesystem"
                  >
                    <FolderOpenIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          {data.customPath && (
            <Alert severity="info" icon={<Server size={18} />} sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                Files will be restored to:
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: 'monospace', fontWeight: 600, color: '#1976d2', mt: 0.5 }}
              >
                {data.customPath}
              </Typography>
            </Alert>
          )}
        </>
      )}

      {/* SSH Connection Selection */}
      {data.destinationType === 'ssh' && (
        <>
          {!Array.isArray(sshConnections) || sshConnections.length === 0 ? (
            <Alert severity="warning">
              No SSH connections configured. Please configure SSH connections in the SSH Keys page
              first.
            </Alert>
          ) : (
            <FormControl fullWidth>
              <InputLabel>Select SSH Connection</InputLabel>
              <Select
                value={
                  data.destinationConnectionId === '' ? '' : String(data.destinationConnectionId)
                }
                label="Select SSH Connection"
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    onChange({ destinationConnectionId: Number(value) })
                  }
                }}
                sx={{
                  '& .MuiSelect-select': {
                    py: '16.5px',
                    display: 'flex',
                    alignItems: 'center',
                  },
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

      {/* Path Input for SSH destination */}
      {data.destinationType === 'ssh' && data.destinationConnectionId && (
        <>
          <TextField
            label="Destination Path"
            value={data.customPath}
            onChange={(e) => onChange({ customPath: e.target.value })}
            placeholder="/mnt/backup/restored"
            required
            fullWidth
            helperText="Choose a writable directory on the remote machine"
            InputProps={{
              endAdornment: (
                <InputAdornment position="end">
                  <IconButton
                    onClick={onBrowsePath}
                    edge="end"
                    size="small"
                    title="Browse remote filesystem"
                  >
                    <FolderOpenIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
          {data.customPath && (
            <Alert severity="info" icon={<Cloud size={18} />} sx={{ mt: 1 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                Files will be restored to:
              </Typography>
              <Typography
                variant="body2"
                sx={{ fontFamily: 'monospace', fontWeight: 600, color: '#1976d2', mt: 0.5 }}
              >
                {getSshUrlPreview()}
              </Typography>
            </Alert>
          )}
        </>
      )}
    </Box>
  )
}
