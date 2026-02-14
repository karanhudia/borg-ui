import {
  Box,
  TextField,
  FormControl,
  FormControlLabel,
  Radio,
  RadioGroup,
  Typography,
  Alert,
  Paper,
  InputAdornment,
  IconButton,
} from '@mui/material'
import { FolderOpen, FileCheck } from 'lucide-react'
import FolderOpenIcon from '@mui/icons-material/FolderOpen'

interface ArchiveFile {
  path: string
  mode: string
  user: string
  group: string
  size: number
  mtime: string
  healthy: boolean
}

export interface RestorePathStepData {
  restoreStrategy: 'original' | 'custom'
  customPath: string
}

interface SSHConnection {
  id: number
  host: string
  username: string
  port: number
}

interface WizardStepRestorePathProps {
  data: RestorePathStepData
  selectedFiles: ArchiveFile[]
  destinationType: 'local' | 'ssh'
  destinationConnectionId: number | ''
  sshConnections?: SSHConnection[]
  onChange: (data: Partial<RestorePathStepData>) => void
  onBrowsePath: () => void
}

export default function WizardStepRestorePath({
  data,
  selectedFiles,
  destinationType,
  destinationConnectionId,
  sshConnections = [],
  onChange,
  onBrowsePath,
}: WizardStepRestorePathProps) {
  // Get example paths to show
  const examplePaths = selectedFiles.slice(0, 3).map((f) => f.path)
  const hasMoreFiles = selectedFiles.length > 3

  // Get SSH connection details
  const sshConnection =
    destinationType === 'ssh' && destinationConnectionId
      ? sshConnections.find((c) => c.id === destinationConnectionId)
      : null

  // Get SSH prefix for displaying paths
  const sshPrefix = sshConnection
    ? `ssh://${sshConnection.username}@${sshConnection.host}:${sshConnection.port}`
    : ''

  // Get destination path with SSH prefix if applicable
  const getCustomDestinationPath = (originalPath: string) => {
    let path: string
    if (data.restoreStrategy === 'custom' && data.customPath) {
      // Extract filename from original path
      const filename = originalPath.split('/').pop() || ''
      path = `${data.customPath.replace(/\/$/, '')}/${filename}`
    } else {
      path = originalPath
    }

    // Add SSH prefix if restoring to SSH destination
    return sshPrefix ? `${sshPrefix}${path}` : path
  }

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {/* Header */}
      <Box>
        <Typography variant="h6" gutterBottom sx={{ fontWeight: 600 }}>
          Choose restore location
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Restore files to their original paths or select a custom destination
        </Typography>
      </Box>

      {/* Restore Strategy Selection */}
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
              borderColor: data.restoreStrategy === 'original' ? '#ed6c02' : 'divider',
              bgcolor:
                data.restoreStrategy === 'original'
                  ? (theme) => (theme.palette.mode === 'dark' ? '#ed6c0220' : '#ed6c020d')
                  : 'background.paper',
              transition: 'all 0.2s',
              cursor: 'pointer',
              '&:hover': {
                borderColor: data.restoreStrategy === 'original' ? '#ed6c02' : 'text.primary',
              },
            }}
            onClick={() => onChange({ restoreStrategy: 'original' })}
          >
            <FormControlLabel
              value="original"
              control={<Radio sx={{ color: '#ed6c02', '&.Mui-checked': { color: '#ed6c02' } }} />}
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
              borderColor: data.restoreStrategy === 'custom' ? '#ed6c02' : 'divider',
              bgcolor:
                data.restoreStrategy === 'custom'
                  ? (theme) => (theme.palette.mode === 'dark' ? '#ed6c0220' : '#ed6c020d')
                  : 'background.paper',
              transition: 'all 0.2s',
              cursor: 'pointer',
              '&:hover': {
                borderColor: data.restoreStrategy === 'custom' ? '#ed6c02' : 'text.primary',
              },
            }}
            onClick={() => onChange({ restoreStrategy: 'custom' })}
          >
            <FormControlLabel
              value="custom"
              control={<Radio sx={{ color: '#ed6c02', '&.Mui-checked': { color: '#ed6c02' } }} />}
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

      {/* Custom Path Input */}
      {data.restoreStrategy === 'custom' && (
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
                    disabled={destinationType === 'ssh' && !destinationConnectionId}
                  >
                    <FolderOpenIcon fontSize="small" />
                  </IconButton>
                </InputAdornment>
              ),
            }}
          />
        </>
      )}

      {/* Preview of destination paths */}
      {selectedFiles.length > 0 && (
        <Box>
          <Typography variant="subtitle2" gutterBottom sx={{ fontWeight: 600, mb: 1 }}>
            Preview
          </Typography>
          <Paper
            variant="outlined"
            sx={{
              p: 2,
              bgcolor: 'background.default',
              maxHeight: 200,
              overflow: 'auto',
            }}
          >
            <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1 }}>
              {examplePaths.map((path, index) => (
                <Box key={index} sx={{ display: 'flex', flexDirection: 'column', gap: 0.5 }}>
                  <Typography
                    variant="body2"
                    color="text.secondary"
                    sx={{ fontSize: '0.75rem', fontFamily: 'monospace' }}
                  >
                    Original: {path}
                  </Typography>
                  <Typography
                    variant="body2"
                    sx={{
                      fontSize: '0.8125rem',
                      fontFamily: 'monospace',
                      color: '#ed6c02',
                      fontWeight: 600,
                    }}
                  >
                    → {getCustomDestinationPath(path)}
                  </Typography>
                </Box>
              ))}
              {hasMoreFiles && (
                <Typography variant="caption" color="text.secondary" sx={{ mt: 1 }}>
                  ... and {selectedFiles.length - 3} more file
                  {selectedFiles.length - 3 !== 1 ? 's' : ''}
                </Typography>
              )}
            </Box>
          </Paper>
        </Box>
      )}

      {destinationType === 'ssh' && !destinationConnectionId && (
        <Alert severity="error">
          <Typography variant="body2">
            Please select an SSH connection in the previous step.
          </Typography>
        </Alert>
      )}
    </Box>
  )
}
