import React from 'react'
import { Box, Typography, Alert, Paper, Chip, Divider } from '@mui/material'
import { HardDrive, Cloud, FolderOpen, FileCheck, CheckCircle } from 'lucide-react'

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

interface ArchiveFile {
  path: string
  mode: string
  user: string
  group: string
  size: number
  mtime: string
  healthy: boolean
}

export interface RestoreReviewData {
  destinationType: 'local' | 'ssh'
  destinationConnectionId: number | ''
  restoreStrategy: 'original' | 'custom'
  customPath: string
}

interface WizardStepRestoreReviewProps {
  data: RestoreReviewData
  selectedFiles: ArchiveFile[]
  sshConnections: SSHConnection[]
  archiveName: string
}

// SummaryRow component
function SummaryRow({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', py: 0.75 }}>
      <Typography variant="body2" color="text.secondary">
        {label}
      </Typography>
      <Box sx={{ textAlign: 'right' }}>{children}</Box>
    </Box>
  )
}

export default function WizardStepRestoreReview({
  data,
  selectedFiles,
  sshConnections,
  archiveName,
}: WizardStepRestoreReviewProps) {
  // Get destination connection details
  const destinationConnection =
    data.destinationType === 'ssh' && data.destinationConnectionId
      ? sshConnections.find((c) => c.id === data.destinationConnectionId)
      : null

  // Get SSH prefix for displaying paths
  const sshPrefix = destinationConnection
    ? `ssh://${destinationConnection.username}@${destinationConnection.host}:${destinationConnection.port}`
    : ''

  // Get destination path with SSH prefix if applicable
  const getDestinationPath = (originalPath: string) => {
    let path: string
    if (data.restoreStrategy === 'custom' && data.customPath) {
      // Borg recreates the full archive path structure under the custom destination.
      // Archive paths have no leading slash (e.g. "home/user/file.txt"), so the result
      // is customPath + "/" + archivePath (e.g. "/mnt/disk/home/user/file.txt").
      const archivePath = originalPath.startsWith('/') ? originalPath.slice(1) : originalPath
      path = `${data.customPath.replace(/\/$/, '')}/${archivePath}`
    } else {
      // Original location: borg extracts to cwd=/, preserving the full archive path.
      path = originalPath
    }

    // Ensure path starts with / for proper display
    if (path && !path.startsWith('/')) {
      path = '/' + path
    }

    // Add SSH prefix if restoring to SSH destination
    return sshPrefix ? `${sshPrefix}${path}` : path
  }

  // Get example paths to show
  const examplePaths = selectedFiles.length > 0 ? selectedFiles.slice(0, 3).map((f) => f.path) : []
  const hasMoreFiles = selectedFiles.length > 3

  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
      {/* Success Alert */}
      <Alert severity="success" icon={<CheckCircle size={20} />} sx={{ py: 0.5 }}>
        <Typography variant="body2" fontWeight={600}>
          {selectedFiles.length === 0
            ? `Ready to restore entire archive from ${archiveName}`
            : `Ready to restore ${selectedFiles.length} file${selectedFiles.length !== 1 ? 's' : ''} from ${archiveName}`}
        </Typography>
      </Alert>

      {/* Destination Summary */}
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        {/* Header */}
        <Box
          sx={{
            px: 2,
            py: 1.5,
            bgcolor: '#1976d220',
            borderBottom: 1,
            borderColor: 'divider',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            {data.destinationType === 'local' ? <HardDrive size={18} /> : <Cloud size={18} />}
            <Typography variant="subtitle2" fontWeight={600}>
              Restore Destination
            </Typography>
          </Box>
        </Box>

        {/* Content */}
        <Box sx={{ p: 2 }}>
          <SummaryRow label="Destination Type">
            <Chip
              label={data.destinationType === 'local' ? 'Borg UI Server' : 'Remote Machine'}
              size="small"
              color="primary"
            />
          </SummaryRow>

          {data.destinationType === 'ssh' && destinationConnection && (
            <>
              <Divider sx={{ my: 1 }} />
              <SummaryRow label="SSH Connection">
                <Typography variant="body2" fontFamily="monospace">
                  {destinationConnection.username}@{destinationConnection.host}:
                  {destinationConnection.port}
                </Typography>
              </SummaryRow>
            </>
          )}

          <Divider sx={{ my: 1 }} />
          <SummaryRow label="Restore Strategy">
            <Chip
              label={data.restoreStrategy === 'original' ? 'Original Location' : 'Custom Location'}
              size="small"
              color={data.restoreStrategy === 'original' ? 'warning' : 'default'}
            />
          </SummaryRow>

          {data.restoreStrategy === 'custom' && (
            <>
              <Divider sx={{ my: 1 }} />
              <SummaryRow label="Custom Path">
                <Typography variant="body2" fontFamily="monospace">
                  {data.customPath || '(not set)'}
                </Typography>
              </SummaryRow>
            </>
          )}
        </Box>
      </Paper>

      {/* Restore Preview */}
      {examplePaths.length > 0 && (
        <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
          {/* Header */}
          <Box
            sx={{
              px: 2,
              py: 1.5,
              bgcolor: '#ed6c0220',
              borderBottom: 1,
              borderColor: 'divider',
            }}
          >
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
              <FileCheck size={18} />
              <Typography variant="subtitle2" fontWeight={600}>
                Restore Preview
              </Typography>
            </Box>
          </Box>

          {/* Content */}
          <Box sx={{ p: 2 }}>
            <Typography
              variant="caption"
              color="text.secondary"
              gutterBottom
              sx={{ display: 'block', mb: 1 }}
            >
              Preview of where your files will be restored:
            </Typography>
            <Box
              sx={{
                p: 2,
                bgcolor: 'background.default',
                borderRadius: 1,
                maxHeight: 200,
                overflow: 'auto',
              }}
            >
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
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
                        color: '#1976d2',
                        fontWeight: 600,
                      }}
                    >
                      → {getDestinationPath(path)}
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
            </Box>
          </Box>
        </Paper>
      )}

      {/* Files Summary */}
      <Paper variant="outlined" sx={{ overflow: 'hidden' }}>
        {/* Header */}
        <Box
          sx={{
            px: 2,
            py: 1.5,
            bgcolor: '#ed6c0220',
            borderBottom: 1,
            borderColor: 'divider',
          }}
        >
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
            <FolderOpen size={18} />
            <Typography variant="subtitle2" fontWeight={600}>
              Files to Restore
            </Typography>
          </Box>
        </Box>

        {/* Content */}
        <Box sx={{ p: 2 }}>
          <SummaryRow label="Number of Items">
            <Chip
              label={
                selectedFiles.length === 0
                  ? 'All files in archive'
                  : `${selectedFiles.length} file${selectedFiles.length !== 1 ? 's' : ''}`
              }
              size="small"
              color="primary"
            />
          </SummaryRow>

          {selectedFiles.length === 0 && (
            <>
              <Divider sx={{ my: 1 }} />
              <Alert severity="info" sx={{ mt: 1 }}>
                <Typography variant="body2">
                  The entire archive will be restored with all files and directories.
                </Typography>
              </Alert>
            </>
          )}
        </Box>
      </Paper>

      {/* Ready Alert */}
      <Alert severity="success" icon={<FileCheck size={20} />}>
        <Typography variant="body2" fontWeight={600}>
          Everything looks good! Click "Restore Files" to begin the restore operation.
        </Typography>
      </Alert>
    </Box>
  )
}
