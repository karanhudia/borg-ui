import {
  Box,
  TextField,
  FormControl,
  FormControlLabel,
  Checkbox,
  InputLabel,
  Select,
  MenuItem,
  Typography,
  Alert,
  Card,
  CardContent,
  CardActionArea,
  InputAdornment,
  IconButton,
  alpha,
} from '@mui/material'
import { Server, Cloud } from 'lucide-react'
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

export interface LocationStepData {
  name: string
  repositoryMode: 'full' | 'observe'
  repositoryLocation: 'local' | 'ssh'
  path: string
  repoSshConnectionId: number | ''
  bypassLock: boolean
}

interface WizardStepLocationProps {
  mode: 'create' | 'edit' | 'import'
  data: LocationStepData
  sshConnections: SSHConnection[]
  dataSource?: 'local' | 'remote' // Data source from step 2
  sourceSshConnectionId?: number | '' // Source SSH connection ID
  onChange: (data: Partial<LocationStepData>) => void
  onBrowsePath: () => void
}

export default function WizardStepLocation({
  mode,
  data,
  sshConnections,
  dataSource,
  sourceSshConnectionId,
  onChange,
  onBrowsePath,
}: WizardStepLocationProps) {
  // Disable SSH repository location if data source is remote (prevent remote-to-remote)
  // Only enforce this in edit mode when we know the data source
  const isRemoteLocationDisabled =
    mode === 'edit' && dataSource === 'remote' && !!sourceSshConnectionId

  const handleLocationChange = (location: 'local' | 'ssh') => {
    if (location === 'ssh' && isRemoteLocationDisabled) {
      return // Don't allow switching to SSH if data source is remote
    }
    onChange({
      repositoryLocation: location,
      repoSshConnectionId: '',
    })
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Name Input */}
      <TextField
        label="Repository Name"
        value={data.name}
        onChange={(e) => onChange({ name: e.target.value })}
        required
        fullWidth
        helperText="A friendly name to identify this repository"
      />

      {/* Repository Mode for Import */}
      {mode === 'import' && (
        <FormControl fullWidth>
          <InputLabel>Repository Mode</InputLabel>
          <Select
            value={data.repositoryMode}
            label="Repository Mode"
            onChange={(e) => onChange({ repositoryMode: e.target.value as 'full' | 'observe' })}
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

      {mode === 'import' && data.repositoryMode === 'observe' && (
        <Alert severity="info">
          Observability-only repositories can browse and restore existing archives but cannot create
          new backups.
        </Alert>
      )}

      {/* Read-only storage access option for observe mode */}
      {data.repositoryMode === 'observe' && (
        <FormControlLabel
          control={
            <Checkbox
              checked={data.bypassLock}
              onChange={(e) => onChange({ bypassLock: e.target.checked })}
            />
          }
          label={
            <Box>
              <Typography variant="body2">Read-only storage access</Typography>
              <Typography variant="caption" color="text.secondary">
                Enable if the storage is read-only or locked by another process (adds --bypass-lock)
              </Typography>
            </Box>
          }
        />
      )}

      {/* Location Selection Cards */}
      <Box>
        <Typography variant="subtitle2" gutterBottom sx={{ mb: 2, fontWeight: 600 }}>
          Where should backups be stored?
        </Typography>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: data.repositoryLocation === 'local' ? 2 : 1,
              borderColor: data.repositoryLocation === 'local' ? 'primary.main' : 'divider',
              boxShadow:
                data.repositoryLocation === 'local'
                  ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                  : 'none',
              bgcolor:
                data.repositoryLocation === 'local'
                  ? (theme) => alpha(theme.palette.primary.main, 0.08)
                  : 'background.paper',
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: data.repositoryLocation === 'local' ? 'translateY(-2px)' : 'none',
              '&:hover': {
                transform: 'translateY(-2px)',
                boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                borderColor: data.repositoryLocation === 'local' ? 'primary.main' : 'text.primary',
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
                      bgcolor:
                        data.repositoryLocation === 'local' ? 'primary.main' : 'action.hover',
                      color: data.repositoryLocation === 'local' ? 'white' : 'text.secondary',
                      transition: 'all 0.3s ease',
                      boxShadow:
                        data.repositoryLocation === 'local'
                          ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                          : 'none',
                    }}
                  >
                    <Server size={28} />
                  </Box>
                  <Box>
                    <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                      Borg UI Server
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ fontSize: '0.8125rem' }}
                    >
                      Store backups on this server's local storage
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>

          <Card
            variant="outlined"
            sx={{
              flex: 1,
              border: data.repositoryLocation === 'ssh' ? 2 : 1,
              borderColor: data.repositoryLocation === 'ssh' ? 'primary.main' : 'divider',
              boxShadow:
                data.repositoryLocation === 'ssh'
                  ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.2)}`
                  : 'none',
              bgcolor:
                data.repositoryLocation === 'ssh'
                  ? (theme) => alpha(theme.palette.primary.main, 0.08)
                  : 'background.paper',
              opacity: isRemoteLocationDisabled ? 0.5 : 1,
              transition: 'all 0.3s cubic-bezier(0.4, 0, 0.2, 1)',
              transform: data.repositoryLocation === 'ssh' ? 'translateY(-2px)' : 'none',
              '&:hover': !isRemoteLocationDisabled
                ? {
                    transform: 'translateY(-2px)',
                    boxShadow: (theme) => `0 4px 12px ${alpha(theme.palette.text.primary, 0.08)}`,
                    borderColor:
                      data.repositoryLocation === 'ssh' ? 'primary.main' : 'text.primary',
                  }
                : {},
            }}
          >
            <CardActionArea
              onClick={() => handleLocationChange('ssh')}
              disabled={isRemoteLocationDisabled}
              sx={{ p: 1 }}
            >
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
                      bgcolor: data.repositoryLocation === 'ssh' ? 'primary.main' : 'action.hover',
                      color: data.repositoryLocation === 'ssh' ? 'white' : 'text.secondary',
                      transition: 'all 0.3s ease',
                      boxShadow:
                        data.repositoryLocation === 'ssh'
                          ? (theme) => `0 4px 12px ${alpha(theme.palette.primary.main, 0.4)}`
                          : 'none',
                    }}
                  >
                    <Cloud size={28} />
                  </Box>
                  <Box>
                    <Typography variant="h6" sx={{ fontSize: '1rem', fontWeight: 600 }}>
                      Remote Client
                    </Typography>
                    <Typography
                      variant="body2"
                      color="text.secondary"
                      sx={{ fontSize: '0.8125rem' }}
                    >
                      Store backups on a remote machine via SSH
                    </Typography>
                  </Box>
                </Box>
              </CardContent>
            </CardActionArea>
          </Card>
        </Box>

        {/* Warning when remote location is disabled due to remote data source */}
        {isRemoteLocationDisabled && (
          <Alert severity="info" sx={{ mt: 2 }}>
            <Typography variant="body2">
              <strong>Why is "Remote Client" disabled?</strong> This repository is configured to
              back up data from a remote machine. Remote-to-remote backups (backing up from one
              remote machine to another) are not supported. Please keep the repository on the Borg
              UI Server.
            </Typography>
          </Alert>
        )}
      </Box>

      {/* SSH Connection Selection */}
      {data.repositoryLocation === 'ssh' && (
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
                value={data.repoSshConnectionId === '' ? '' : String(data.repoSshConnectionId)}
                label="Select SSH Connection"
                onChange={(e) => {
                  const value = e.target.value
                  if (value) {
                    onChange({ repoSshConnectionId: Number(value) })
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

      {/* Path Input */}
      <TextField
        label="Repository Path"
        value={data.path}
        onChange={(e) => onChange({ path: e.target.value })}
        placeholder={
          data.repositoryLocation === 'local' ? '/backups/my-repo' : '/path/on/remote/server'
        }
        required
        fullWidth
        helperText="Path where the repository will be stored"
        InputProps={{
          endAdornment: (
            <InputAdornment position="end">
              <IconButton
                onClick={onBrowsePath}
                edge="end"
                size="small"
                title="Browse filesystem"
                disabled={data.repositoryLocation === 'ssh' && !data.repoSshConnectionId}
              >
                <FolderOpenIcon fontSize="small" />
              </IconButton>
            </InputAdornment>
          ),
        }}
      />
    </Box>
  )
}
