import { Box, Stack, Typography, Alert } from '@mui/material'
import { RefreshCw, CheckCircle, AlertCircle, Clock } from 'lucide-react'
import { formatTimeRange, formatDurationSeconds, formatRelativeTime } from '../utils/dateUtils'

interface RestoreJob {
  id: number
  repository: string
  archive: string
  destination: string
  status: string
  started_at?: string
  completed_at?: string
  progress?: number
  error_message?: string
  progress_details?: {
    nfiles: number
    current_file: string
    progress_percent: number
    restore_speed: number
    estimated_time_remaining: number
  }
}

interface RestoreJobCardProps {
  job: RestoreJob
  showJobId?: boolean
}

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'running':
      return <RefreshCw size={18} className="animate-spin" />
    case 'completed':
      return <CheckCircle size={18} />
    case 'failed':
      return <AlertCircle size={18} />
    default:
      return <Clock size={18} />
  }
}

export default function RestoreJobCard({ job, showJobId = true }: RestoreJobCardProps) {
  // Extract a cleaner archive name (remove timestamp if present)
  const getArchiveName = (archiveName: string) => {
    // If archive name contains a timestamp pattern, extract the base name
    const timestampPattern = /-\d{4}-\d{2}-\d{2}T[\d:.]+$/
    return archiveName.replace(timestampPattern, '')
  }

  // Calculate duration for display
  const getDurationText = () => {
    if (!job.started_at || !job.completed_at) return null
    const duration = formatTimeRange(job.started_at, job.completed_at, job.status)
    // Don't show duration if it's 0 or very short
    if (duration === '0 sec' || duration === '0 min') return null
    return `Duration: ${duration}`
  }

  return (
    <Box>
      {/* Header with job info */}
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 1.5 }}>
        {job.status !== 'completed' && (
          <Box sx={{ color: 'info.main' }}>{getStatusIcon(job.status)}</Box>
        )}
        <Box sx={{ flex: 1, minWidth: 0 }}>
          {showJobId && (
            <Typography variant="body1" fontWeight={500} sx={{ mb: 0.5 }}>
              Restore Job #{job.id}
            </Typography>
          )}
          <Stack direction="row" spacing={1} alignItems="baseline" sx={{ flexWrap: 'wrap' }}>
            <Typography variant="body2" fontWeight={500}>
              {getArchiveName(job.archive)}
            </Typography>
            <Typography variant="body2" color="text.secondary">
              →
            </Typography>
            <Typography
              variant="body2"
              color="text.secondary"
              sx={{
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
                fontFamily: 'monospace',
                fontSize: '0.8rem',
              }}
            >
              {job.destination}
            </Typography>
          </Stack>
        </Box>
      </Stack>

      {/* Status info */}
      {job.status === 'running' && (
        <Box sx={{ mb: 2 }}>
          <Stack
            direction="row"
            justifyContent="space-between"
            alignItems="center"
            sx={{ mb: 1.5 }}
          >
            <Stack direction="row" spacing={1} alignItems="center">
              <Box
                sx={{
                  width: 8,
                  height: 8,
                  borderRadius: '50%',
                  bgcolor: 'info.main',
                  animation: 'pulse 2s ease-in-out infinite',
                  '@keyframes pulse': {
                    '0%, 100%': { opacity: 1 },
                    '50%': { opacity: 0.5 },
                  },
                }}
              />
              <Typography variant="body2" fontWeight={500} color="info.main">
                Restoring files...
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary">
              {formatTimeRange(job.started_at, job.completed_at, job.status)}
            </Typography>
          </Stack>
        </Box>
      )}

      {job.status === 'completed' && job.completed_at && (
        <Stack direction="row" spacing={1.5} alignItems="baseline" sx={{ flexWrap: 'wrap', gap: 1 }}>
          <Typography variant="body2" color="success.main" fontWeight={500}>
            ✓ Completed
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {formatRelativeTime(job.completed_at)}
          </Typography>
          {getDurationText() && (
            <>
              <Typography variant="body2" color="text.secondary">
                •
              </Typography>
              <Typography variant="body2" color="text.secondary">
                {getDurationText()}
              </Typography>
            </>
          )}
        </Stack>
      )}

      {job.status === 'failed' && job.error_message && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography variant="body2">{job.error_message}</Typography>
        </Alert>
      )}

      {job.status === 'running' && job.progress_details?.current_file && (
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

      {job.status === 'running' && job.progress_details && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
            gap: 2,
          }}
        >
          <Box>
            <Typography variant="body2" color="text.secondary">
              Files Restored:
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {job.progress_details.nfiles?.toLocaleString() || '0'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">
              Progress:
            </Typography>
            <Typography variant="body2" fontWeight={500} color="primary.main">
              {job.progress_details.progress_percent?.toFixed(1) || '0'}%
            </Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">
              Speed:
            </Typography>
            <Typography variant="body2" fontWeight={500} color="primary.main">
              {job.progress_details.restore_speed
                ? `${job.progress_details.restore_speed.toFixed(2)} MB/s`
                : 'N/A'}
            </Typography>
          </Box>
          {(job.progress_details.estimated_time_remaining || 0) > 0 && (
            <Box>
              <Typography variant="body2" color="text.secondary">
                ETA:
              </Typography>
              <Typography variant="body2" fontWeight={500} color="success.main">
                {formatDurationSeconds(job.progress_details.estimated_time_remaining || 0)}
              </Typography>
            </Box>
          )}
        </Box>
      )}
    </Box>
  )
}
