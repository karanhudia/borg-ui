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
            <Typography variant="body2" fontWeight={600}>
              {selectedFiles.length === 0 ? 'All files in archive' : selectedFiles.length}
            </Typography>
          </SummaryRow>

          {selectedFiles.length > 0 && (
            <>
              <Divider sx={{ my: 1 }} />
              <Box sx={{ mt: 2 }}>
                <Typography variant="caption" color="text.secondary" gutterBottom>
                  Selected items:
                </Typography>
                <Box
                  sx={{
                    mt: 1,
                    p: 1,
                    bgcolor: 'background.default',
                    borderRadius: 1,
                    maxHeight: 120,
                    overflow: 'auto',
                  }}
                >
                  {selectedFiles.slice(0, 5).map((file, index) => (
                    <Typography
                      key={index}
                      variant="caption"
                      sx={{
                        display: 'block',
                        fontFamily: 'monospace',
                        color: 'text.secondary',
                        py: 0.25,
                      }}
                    >
                      {file.path}
                    </Typography>
                  ))}
                  {selectedFiles.length > 5 && (
                    <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5 }}>
                      ... and {selectedFiles.length - 5} more
                    </Typography>
                  )}
                </Box>
              </Box>
            </>
          )}

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
