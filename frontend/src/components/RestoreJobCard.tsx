import { Box, Typography, Alert, Chip, useTheme, alpha, type Theme } from '@mui/material'
import { RefreshCw, CheckCircle, AlertCircle, Clock, AlertTriangle } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatTimeRange, formatDurationSeconds, formatRelativeTime } from '../utils/dateUtils'
import { translateBackendKey } from '../utils/translateBackendKey'

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

const ICON_SIZE = 14

const getStatusIcon = (status: string) => {
  switch (status) {
    case 'running':
      return <RefreshCw size={ICON_SIZE} className="animate-spin" />
    case 'completed':
      return <CheckCircle size={ICON_SIZE} />
    case 'completed_with_warnings':
      return <AlertTriangle size={ICON_SIZE} />
    case 'failed':
      return <AlertCircle size={ICON_SIZE} />
    default:
      return <Clock size={ICON_SIZE} />
  }
}

const getStatusColor = (status: string, theme: Theme): string => {
  switch (status) {
    case 'running':
      return theme.palette.info.main
    case 'completed':
      return theme.palette.success.main
    case 'completed_with_warnings':
      return theme.palette.warning.main
    case 'failed':
      return theme.palette.error.main
    default:
      return theme.palette.text.secondary
  }
}

const getStatusLabel = (status: string, t: (key: string) => string): string => {
  switch (status) {
    case 'completed':
      return t('restoreJobCard.completed')
    case 'completed_with_warnings':
      return t('restoreJobCard.completedWithWarnings')
    case 'failed':
      return t('status.failed')
    case 'running':
      return t('restoreJobCard.restoringFiles')
    default:
      return t('status.pending')
  }
}

export default function RestoreJobCard({ job, showJobId = true }: RestoreJobCardProps) {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const getArchiveName = (archiveName: string) => {
    const timestampPattern = /-\d{4}-\d{2}-\d{2}T[\d:.]+$/
    return archiveName.replace(timestampPattern, '')
  }

  const getDurationText = () => {
    if (!job.started_at || !job.completed_at) return null
    const duration = formatTimeRange(job.started_at, job.completed_at, job.status)
    if (duration === '0 sec' || duration === '0 min') return null
    return duration
  }

  const statusColor = getStatusColor(job.status, theme)

  return (
    <Box>
      {showJobId && (
        <Typography variant="body2" fontWeight={500} sx={{ mb: 1 }}>
          {t('restoreJobCard.title')} #{job.id}
        </Typography>
      )}

      {/* Single-line layout: archive → destination + status chip + time */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'center',
          gap: 1.5,
          flexWrap: 'wrap',
          rowGap: 0.75,
        }}
      >
        {/* Archive → Destination */}
        <Box
          sx={{
            display: 'flex',
            alignItems: 'center',
            gap: 0.75,
            minWidth: 0,
            flex: '1 1 auto',
          }}
        >
          <Typography
            variant="body2"
            fontWeight={600}
            noWrap
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.78rem',
            }}
          >
            {getArchiveName(job.archive)}
          </Typography>
          <Box component="span" sx={{ color: 'text.disabled', fontSize: '0.72rem', flexShrink: 0 }}>
            →
          </Box>
          <Typography
            variant="body2"
            color="text.secondary"
            noWrap
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              fontSize: '0.72rem',
              minWidth: 0,
            }}
          >
            {job.destination}
          </Typography>
        </Box>

        {/* Status chip */}
        <Chip
          icon={
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
              }}
            >
              {getStatusIcon(job.status)}
            </Box>
          }
          label={getStatusLabel(job.status, t)}
          size="small"
          sx={{
            height: 22,
            fontSize: '0.68rem',
            fontWeight: 600,
            letterSpacing: '0.02em',
            bgcolor: alpha(statusColor, isDark ? 0.12 : 0.08),
            color: statusColor,
            border: '1px solid',
            borderColor: alpha(statusColor, isDark ? 0.25 : 0.18),
            '& .MuiChip-icon': { ml: 0.5, mr: -0.25, color: 'inherit' },
            '& .MuiChip-label': { px: 0.75 },
          }}
        />

        {/* Time + duration */}
        {job.completed_at && (
          <Box
            sx={{
              display: 'flex',
              alignItems: 'center',
              gap: 0.75,
              flexShrink: 0,
            }}
          >
            <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
              {formatRelativeTime(job.completed_at)}
            </Typography>
            {getDurationText() && (
              <>
                <Box
                  component="span"
                  sx={{
                    width: 3,
                    height: 3,
                    borderRadius: '50%',
                    bgcolor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.18),
                    flexShrink: 0,
                  }}
                />
                <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.72rem' }}>
                  {getDurationText()}
                </Typography>
              </>
            )}
          </Box>
        )}
      </Box>

      {/* Running: elapsed time */}
      {job.status === 'running' && job.started_at && !job.completed_at && (
        <Typography variant="body2" color="text.secondary" sx={{ fontSize: '0.72rem', mt: 0.5 }}>
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      )}

      {/* Error alert */}
      {job.status === 'failed' && job.error_message && (
        <Alert severity="error" sx={{ mt: 1.5 }}>
          <Typography variant="body2" sx={{ whiteSpace: 'pre-wrap' }}>
            {job.error_message
              .split('\n')
              .map((line) => translateBackendKey(line))
              .join('\n')}
          </Typography>
        </Alert>
      )}

      {/* Running: current file */}
      {job.status === 'running' && job.progress_details?.current_file && (
        <Alert severity="info" sx={{ mt: 1.5, py: 0.5 }}>
          <Typography variant="caption" fontWeight={500}>
            {t('restoreJobCard.currentFile')}
          </Typography>
          <Typography
            variant="caption"
            sx={{
              fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
              display: 'block',
              mt: 0.5,
              wordBreak: 'break-all',
            }}
          >
            {job.progress_details.current_file}
          </Typography>
        </Alert>
      )}

      {/* Running: progress stats */}
      {job.status === 'running' && job.progress_details && (
        <Box
          sx={{
            display: 'grid',
            gridTemplateColumns: 'repeat(auto-fit, minmax(140px, 1fr))',
            gap: 2,
            mt: 1.5,
          }}
        >
          <Box>
            <Typography variant="body2" color="text.secondary">
              {t('restoreJobCard.filesRestored')}
            </Typography>
            <Typography variant="body2" fontWeight={500}>
              {job.progress_details.nfiles?.toLocaleString() || '0'}
            </Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">
              {t('restoreJobCard.progress')}
            </Typography>
            <Typography variant="body2" fontWeight={500} color="primary.main">
              {job.progress_details.progress_percent?.toFixed(1) || '0'}%
            </Typography>
          </Box>
          <Box>
            <Typography variant="body2" color="text.secondary">
              {t('restoreJobCard.speed')}
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
                {t('restoreJobCard.eta')}
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
