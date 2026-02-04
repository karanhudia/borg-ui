import React from 'react'
import {
  Card,
  CardContent,
  Typography,
  Stack,
  Chip,
  Paper,
  Box,
  Alert,
  IconButton,
  Tooltip,
} from '@mui/material'
import { RefreshCw, X } from 'lucide-react'
import { BackupJob } from '../types'
import { formatBytes as formatBytesUtil } from '../utils/dateUtils'

interface RunningBackupsSectionProps {
  runningBackupJobs: BackupJob[]
  getRepositoryName: (path: string) => string
  formatRelativeTime: (dateString: string | null | undefined) => string
  formatDurationSeconds: (seconds: number) => string
  getMaintenanceStatusLabel: (status: string) => string | null
  getMaintenanceStatusColor: (status: string) => 'info' | 'warning' | 'success' | 'error'
  onCancelBackup: (jobId: string | number) => void
  isCancelling: boolean
}

const RunningBackupsSection: React.FC<RunningBackupsSectionProps> = ({
  runningBackupJobs,
  getRepositoryName,
  formatRelativeTime,
  formatDurationSeconds,
  getMaintenanceStatusLabel,
  getMaintenanceStatusColor,
  onCancelBackup,
  isCancelling,
}) => {
  if (runningBackupJobs.length === 0) {
    return null
  }

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 2 }}>
          <RefreshCw size={20} color="#1976d2" className="animate-spin" />
          <Typography variant="h6" fontWeight={600}>
            Running Scheduled Backups
          </Typography>
          <Chip
            label={`${runningBackupJobs.length} active`}
            size="small"
            color="primary"
            sx={{ ml: 1 }}
          />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Real-time progress for scheduled backup jobs
        </Typography>

        <Stack spacing={2}>
          {runningBackupJobs.map((job: BackupJob) => (
            <Paper
              key={job.id}
              elevation={0}
              sx={{
                p: 2,
                border: 1,
                borderColor: 'primary.main',
                borderRadius: 2,
                backgroundColor: 'primary.lighter',
              }}
            >
              {/* Job Header */}
              <Stack
                direction="row"
                justifyContent="space-between"
                alignItems="center"
                sx={{ mb: 2 }}
              >
                <Stack direction="row" spacing={2} alignItems="center">
                  <Chip
                    icon={<RefreshCw size={14} className="animate-spin" />}
                    label="Running"
                    color="primary"
                    size="small"
                  />
                  <Typography variant="body2" fontWeight={600}>
                    Job #{job.id} - {getRepositoryName(job.repository)}
                  </Typography>
                </Stack>
                <Stack direction="row" spacing={1} alignItems="center">
                  <Typography variant="caption" color="text.secondary">
                    Started: {formatRelativeTime(job.started_at)}
                  </Typography>
                  <Tooltip title="Cancel Backup" arrow>
                    <IconButton
                      size="small"
                      color="error"
                      onClick={() => {
                        if (
                          window.confirm(`Are you sure you want to cancel backup job #${job.id}?`)
                        ) {
                          onCancelBackup(job.id)
                        }
                      }}
                      disabled={isCancelling}
                      sx={{ ml: 1 }}
                    >
                      <X size={16} />
                    </IconButton>
                  </Tooltip>
                </Stack>
              </Stack>

              {/* Current File Being Processed */}
              {job.progress_details?.current_file && (
                <Alert severity="info" sx={{ mb: 2, py: 0.5 }}>
                  <Typography variant="caption" fontWeight={500}>
                    Current File:
                  </Typography>
                  <Typography
                    variant="caption"
                    sx={{
                      fontFamily: 'monospace',
                      display: 'block',
                      mt: 0.5,
                      wordBreak: 'break-all',
                    }}
                  >
                    {job.progress_details.current_file}
                  </Typography>
                </Alert>
              )}

              {/* Maintenance Status */}
              {job.maintenance_status && getMaintenanceStatusLabel(job.maintenance_status) && (
                <Alert
                  severity={getMaintenanceStatusColor(job.maintenance_status)}
                  sx={{ mb: 2, py: 0.5 }}
                  icon={
                    job.maintenance_status.includes('running') ? (
                      <RefreshCw size={16} className="animate-spin" />
                    ) : undefined
                  }
                >
                  <Typography variant="caption" fontWeight={500}>
                    {getMaintenanceStatusLabel(job.maintenance_status)}
                  </Typography>
                </Alert>
              )}

              {/* Job Details Grid */}
              <Box
                sx={{
                  display: 'grid',
                  gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
                  gap: 2,
                  width: '100%',
                }}
              >
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Files Processed:
                  </Typography>
                  <Typography variant="body2" fontWeight={500}>
                    {job.progress_details?.nfiles?.toLocaleString() || '0'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Original Size:
                  </Typography>
                  <Typography variant="body2" fontWeight={500}>
                    {job.progress_details?.original_size
                      ? formatBytesUtil(job.progress_details.original_size)
                      : 'N/A'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Compressed:
                  </Typography>
                  <Typography variant="body2" fontWeight={500}>
                    {job.progress_details?.compressed_size !== undefined &&
                    job.progress_details?.compressed_size !== null
                      ? formatBytesUtil(job.progress_details.compressed_size)
                      : 'N/A'}
                  </Typography>
                </Box>
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Deduplicated:
                  </Typography>
                  <Typography variant="body2" fontWeight={500} color="success.main">
                    {job.progress_details?.deduplicated_size !== undefined &&
                    job.progress_details?.deduplicated_size !== null
                      ? formatBytesUtil(job.progress_details.deduplicated_size)
                      : 'N/A'}
                  </Typography>
                </Box>
                {job.progress_details?.total_expected_size &&
                  job.progress_details.total_expected_size > 0 && (
                    <Box>
                      <Typography variant="body2" color="text.secondary">
                        Total Source Size:
                      </Typography>
                      <Typography variant="body2" fontWeight={500} color="info.main">
                        {formatBytesUtil(job.progress_details.total_expected_size)}
                      </Typography>
                    </Box>
                  )}
                <Box>
                  <Typography variant="body2" color="text.secondary">
                    Speed:
                  </Typography>
                  <Typography variant="body2" fontWeight={500} color="primary.main">
                    {job.progress_details?.backup_speed
                      ? `${job.progress_details.backup_speed.toFixed(2)} MB/s`
                      : 'N/A'}
                  </Typography>
                </Box>
                {(job.progress_details?.estimated_time_remaining ?? 0) > 0 && (
                  <Box>
                    <Typography variant="body2" color="text.secondary">
                      ETA:
                    </Typography>
                    <Typography variant="body2" fontWeight={500} color="success.main">
                      {formatDurationSeconds(job.progress_details?.estimated_time_remaining ?? 0)}
                    </Typography>
                  </Box>
                )}
              </Box>
            </Paper>
          ))}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default RunningBackupsSection
