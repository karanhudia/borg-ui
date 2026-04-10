import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Box,
  Button,
  Card,
  CardContent,
  LinearProgress,
  Stack,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import {
  Activity,
  Archive,
  Clock,
  Database,
  Eye,
  FileText,
  HardDrive,
  RefreshCw,
  Square,
  Zap,
} from 'lucide-react'
import { BackupJob } from '../types'
import {
  formatBytes as formatBytesUtil,
  formatDurationSeconds,
  formatTimeRange,
} from '../utils/dateUtils'

// Emerald green — matches the "Backup Now" button in RepositoryCard for visual continuity
const ACCENT_BACKUP = '#059669'

interface RunningBackupsSectionProps {
  runningBackupJobs: BackupJob[]
  onCancelBackup: (jobId: string | number) => void
  isCancelling: boolean
  onViewLogs?: (job: BackupJob) => void
}

const STAT_ICONS = [
  <FileText size={11} />,
  <HardDrive size={11} />,
  <Archive size={11} />,
  <Zap size={11} />,
  <Database size={11} />,
  <Activity size={11} />,
  <Clock size={11} />,
]

const RunningBackupsSection: React.FC<RunningBackupsSectionProps> = ({
  runningBackupJobs,
  onCancelBackup,
  isCancelling,
  onViewLogs,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const statColors = [
    ACCENT_BACKUP,
    theme.palette.primary.main,
    theme.palette.secondary.main,
    theme.palette.success.main,
    theme.palette.warning.main,
    theme.palette.primary.main,
    theme.palette.success.main,
  ]

  const getVisibleStats = (job: BackupJob) =>
    [
      {
        key: 'filesProcessed',
        label: t('backup.runningJobs.progress.filesProcessed'),
        value:
          job.progress_details?.nfiles?.toLocaleString() ||
          job.processed_files?.toLocaleString() ||
          '0',
      },
      {
        key: 'originalSize',
        label: t('backup.runningJobs.progress.originalSize'),
        value: job.progress_details?.original_size
          ? formatBytesUtil(job.progress_details.original_size)
          : job.processed_size || 'Unknown',
      },
      {
        key: 'compressed',
        label: t('backup.runningJobs.progress.compressed'),
        value:
          job.progress_details?.compressed_size !== undefined
            ? formatBytesUtil(job.progress_details.compressed_size)
            : null,
      },
      {
        key: 'deduplicated',
        label: t('backup.runningJobs.progress.deduplicated'),
        value:
          job.progress_details?.deduplicated_size !== undefined
            ? formatBytesUtil(job.progress_details.deduplicated_size)
            : null,
        valueColor: 'success.main',
      },
      {
        key: 'totalSourceSize',
        label: t('backup.runningJobs.progress.totalSourceSize'),
        value:
          job.progress_details?.total_expected_size && job.progress_details.total_expected_size > 0
            ? formatBytesUtil(job.progress_details.total_expected_size)
            : 'Unknown',
        valueColor: 'success.main',
      },
      {
        key: 'speed',
        label: t('backup.runningJobs.progress.speed'),
        value:
          job.status === 'running' && job.progress_details?.backup_speed
            ? `${job.progress_details.backup_speed.toFixed(2)} MB/s`
            : 'N/A',
        valueColor: 'primary.main',
      },
      {
        key: 'eta',
        label: t('backup.runningJobs.progress.eta'),
        value:
          (job.progress_details?.estimated_time_remaining || 0) > 0
            ? formatDurationSeconds(job.progress_details?.estimated_time_remaining || 0)
            : 'N/A',
        valueColor: 'success.main',
      },
    ].filter((stat) => stat.value !== null)

  if (runningBackupJobs.length === 0) return null

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        {/* Section Header */}
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
          <Box sx={{ color: ACCENT_BACKUP, display: 'flex' }}>
            <RefreshCw size={16} className="animate-spin" />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {t('backup.runningJobs.title')}
          </Typography>
          <Box
            sx={{
              px: 0.8,
              py: 0.15,
              borderRadius: '10px',
              bgcolor: alpha(ACCENT_BACKUP, 0.1),
              border: `1px solid ${alpha(ACCENT_BACKUP, 0.22)}`,
            }}
          >
            <Typography
              sx={{ fontSize: '0.7rem', fontWeight: 700, color: ACCENT_BACKUP, lineHeight: 1.5 }}
            >
              {runningBackupJobs.length}
            </Typography>
          </Box>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          {t('backup.runningJobs.subtitle')}
        </Typography>

        <Stack spacing={2}>
          {runningBackupJobs.map((job: BackupJob) => {
            const visibleStats = getVisibleStats(job)
            const progress = job.progress || 0
            const stageLabel =
              progress === 0
                ? t('backup.runningJobs.progress.initializing')
                : progress >= 100
                  ? t('backup.runningJobs.progress.finalizing')
                  : t('backup.runningJobs.progress.processing')

            return (
              <Box
                key={job.id}
                sx={{
                  position: 'relative',
                  borderRadius: 2,
                  bgcolor: isDark ? alpha(ACCENT_BACKUP, 0.07) : alpha(ACCENT_BACKUP, 0.05),
                  overflow: 'hidden',
                  boxShadow: isDark
                    ? `inset 0 0 0 1px ${alpha('#fff', 0.05)}`
                    : `inset 0 0 0 1px ${alpha('#000', 0.04)}`,
                }}
              >
                {/* Ambient glow blob */}
                <Box
                  sx={{
                    position: 'absolute',
                    top: -60,
                    right: -40,
                    width: 200,
                    height: 140,
                    borderRadius: '50%',
                    bgcolor: alpha(ACCENT_BACKUP, isDark ? 0.1 : 0.05),
                    filter: 'blur(55px)',
                    pointerEvents: 'none',
                    animation: 'blobPulseJob 3s ease-in-out infinite',
                    '@keyframes blobPulseJob': {
                      '0%, 100%': { opacity: 1 },
                      '50%': { opacity: 0.25 },
                    },
                  }}
                />

                <Box sx={{ px: { xs: 1.75, sm: 2.25 }, pt: 2, pb: 2 }}>
                  {/* Header */}
                  <Box
                    sx={{
                      display: 'flex',
                      justifyContent: 'space-between',
                      alignItems: 'flex-start',
                      gap: 2,
                      mb: 2,
                      flexWrap: { xs: 'wrap', sm: 'nowrap' },
                    }}
                  >
                    {/* Left: Job identity */}
                    <Box sx={{ minWidth: 0, flex: 1 }}>
                      <Stack
                        direction="row"
                        spacing={0.75}
                        alignItems="center"
                        sx={{ mb: 0.5, flexWrap: 'wrap', gap: 0.5 }}
                      >
                        {/* Live pulse dot */}
                        <Box
                          sx={{
                            width: 7,
                            height: 7,
                            borderRadius: '50%',
                            bgcolor: ACCENT_BACKUP,
                            flexShrink: 0,
                            animation: 'liveDot 2s ease-in-out infinite',
                            '@keyframes liveDot': {
                              '0%, 100%': { opacity: 1, transform: 'scale(1)' },
                              '50%': { opacity: 0.45, transform: 'scale(0.82)' },
                            },
                          }}
                        />
                        <Typography variant="body1" fontWeight={700} sx={{ lineHeight: 1.3 }}>
                          {t('backup.runningJobs.jobTitle', { id: job.id })}
                        </Typography>
                        {/* Stage badge */}
                        <Box
                          sx={{
                            px: 0.8,
                            py: 0.2,
                            borderRadius: 0.75,
                            bgcolor: alpha(ACCENT_BACKUP, 0.1),
                            border: `1px solid ${alpha(ACCENT_BACKUP, 0.2)}`,
                          }}
                        >
                          <Typography
                            sx={{
                              fontSize: '0.62rem',
                              fontWeight: 700,
                              color: ACCENT_BACKUP,
                              lineHeight: 1,
                              textTransform: 'uppercase',
                              letterSpacing: '0.05em',
                            }}
                          >
                            {stageLabel}
                          </Typography>
                        </Box>
                        {/* Maintenance status badge */}
                        {job.maintenance_status && (
                          <Box
                            sx={{
                              px: 0.8,
                              py: 0.2,
                              borderRadius: 0.75,
                              bgcolor: alpha(theme.palette.info.main, 0.1),
                              border: `1px solid ${alpha(theme.palette.info.main, 0.2)}`,
                            }}
                          >
                            <Typography
                              sx={{
                                fontSize: '0.62rem',
                                fontWeight: 700,
                                color: 'info.main',
                                lineHeight: 1,
                                textTransform: 'uppercase',
                                letterSpacing: '0.05em',
                              }}
                            >
                              {job.maintenance_status}
                            </Typography>
                          </Box>
                        )}
                      </Stack>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                          fontSize: '0.69rem',
                          color: 'text.disabled',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        {job.repository}
                      </Typography>
                    </Box>

                    {/* Right: Actions */}
                    <Stack direction="row" spacing={0.75} alignItems="center" flexShrink={0}>
                      <Typography
                        variant="caption"
                        color="text.secondary"
                        sx={{ display: { xs: 'none', sm: 'block' }, mr: 0.5 }}
                      >
                        {formatTimeRange(job.started_at, job.completed_at, job.status)}
                      </Typography>
                      {onViewLogs && (
                        <Button
                          variant="outlined"
                          size="small"
                          startIcon={<Eye size={13} />}
                          onClick={() => onViewLogs(job)}
                          sx={{
                            height: 28,
                            fontSize: '0.75rem',
                            px: 1.25,
                            borderColor: alpha(ACCENT_BACKUP, 0.28),
                            color: ACCENT_BACKUP,
                            '&:hover': {
                              bgcolor: alpha(ACCENT_BACKUP, 0.07),
                              borderColor: alpha(ACCENT_BACKUP, 0.5),
                            },
                          }}
                        >
                          {t('backup.runningJobs.viewLogs')}
                        </Button>
                      )}
                      <Button
                        variant="outlined"
                        size="small"
                        startIcon={<Square size={13} />}
                        color="error"
                        onClick={() => {
                          if (
                            window.confirm(`Are you sure you want to cancel backup job #${job.id}?`)
                          ) {
                            onCancelBackup(job.id)
                          }
                        }}
                        disabled={isCancelling}
                        sx={{ height: 28, fontSize: '0.75rem', px: 1.25 }}
                      >
                        {t('backup.runningJobs.cancel')}
                      </Button>
                    </Stack>
                  </Box>

                  {/* Progress bar — only when total source size is known */}
                  {(() => {
                    const processed = job.progress_details?.original_size ?? 0
                    const total = job.progress_details?.total_expected_size ?? 0
                    if (processed <= 0 || total <= 0) return null
                    const pct = Math.min(100, (processed / total) * 100)
                    return (
                      <Box sx={{ mb: 1.5 }}>
                        <Stack
                          direction="row"
                          justifyContent="space-between"
                          alignItems="center"
                          sx={{ mb: 0.5 }}
                        >
                          <Typography
                            sx={{
                              fontSize: '0.68rem',
                              fontWeight: 600,
                              color: ACCENT_BACKUP,
                              letterSpacing: '0.02em',
                            }}
                          >
                            {pct.toFixed(1)}%
                          </Typography>
                          <Typography sx={{ fontSize: '0.65rem', color: 'text.disabled' }}>
                            {t('backup.runningJobs.progress.totalSourceSize')}
                          </Typography>
                        </Stack>
                        <LinearProgress
                          variant="determinate"
                          value={pct}
                          sx={{
                            height: 4,
                            borderRadius: 2,
                            bgcolor: isDark ? alpha('#fff', 0.07) : alpha('#000', 0.07),
                            '& .MuiLinearProgress-bar': {
                              borderRadius: 2,
                              bgcolor: ACCENT_BACKUP,
                            },
                          }}
                        />
                      </Box>
                    )
                  })()}

                  {/* Stats Band */}
                  {visibleStats.length > 0 && (
                    <Box
                      sx={{
                        display: 'grid',
                        gridTemplateColumns: {
                          xs: 'repeat(2, 1fr)',
                          sm: 'repeat(3, 1fr)',
                          md: 'repeat(4, 1fr)',
                          lg: `repeat(${visibleStats.length}, 1fr)`,
                        },
                        borderRadius: 1.5,
                        overflow: 'hidden',
                        mb: job.progress_details?.current_file ? 1.5 : 0,
                        bgcolor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                        gap: '1px',
                      }}
                    >
                      {visibleStats.map((stat, i) => {
                        const statColor = statColors[i] ?? ACCENT_BACKUP
                        const isLast = i === visibleStats.length - 1
                        const total = visibleStats.length
                        const getSpan = (cols: number) => {
                          const r = total % cols
                          return r === 0 ? 'auto' : `span ${cols - r + 1}`
                        }
                        return (
                          <Box
                            key={stat.key}
                            sx={{
                              px: 1.5,
                              py: 1.1,
                              bgcolor: isDark ? alpha(ACCENT_BACKUP, 0.04) : 'background.paper',
                              ...(isLast && {
                                gridColumn: {
                                  xs: getSpan(2),
                                  sm: getSpan(3),
                                  md: getSpan(4),
                                  lg: 'auto',
                                },
                              }),
                            }}
                          >
                            <Box
                              sx={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: 0.5,
                                mb: 0.35,
                              }}
                            >
                              <Box
                                sx={{
                                  color: alpha(statColor, 0.7),
                                  display: 'flex',
                                  alignItems: 'center',
                                }}
                              >
                                {STAT_ICONS[i]}
                              </Box>
                              <Typography
                                sx={{
                                  fontSize: '0.58rem',
                                  fontWeight: 700,
                                  textTransform: 'uppercase',
                                  letterSpacing: '0.07em',
                                  color: alpha(statColor, 0.7),
                                  lineHeight: 1,
                                }}
                              >
                                {stat.label}
                              </Typography>
                            </Box>
                            <Typography
                              variant="body2"
                              fontWeight={600}
                              noWrap
                              sx={{
                                fontVariantNumeric: 'tabular-nums',
                                fontSize: '0.85rem',
                                color: stat.valueColor || 'text.primary',
                              }}
                            >
                              {stat.value}
                            </Typography>
                          </Box>
                        )
                      })}
                    </Box>
                  )}

                  {/* Current File Terminal Box */}
                  {job.progress_details?.current_file && (
                    <Box
                      sx={{
                        px: 1.5,
                        py: 0.875,
                        borderRadius: 1,
                        bgcolor: isDark ? alpha('#000', 0.3) : alpha('#000', 0.03),
                        border: '1px solid',
                        borderColor: isDark ? alpha('#fff', 0.06) : alpha('#000', 0.07),
                        display: 'flex',
                        alignItems: 'center',
                        gap: 1,
                        overflow: 'hidden',
                      }}
                    >
                      <Box
                        sx={{
                          color: alpha(ACCENT_BACKUP, 0.65),
                          display: 'flex',
                          flexShrink: 0,
                        }}
                      >
                        <FileText size={13} />
                      </Box>
                      <Typography
                        sx={{
                          fontFamily: '"JetBrains Mono","Fira Code",ui-monospace,monospace',
                          fontSize: '0.72rem',
                          color: 'text.secondary',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          whiteSpace: 'nowrap',
                          flex: 1,
                          minWidth: 0,
                        }}
                      >
                        {job.progress_details.current_file}
                      </Typography>
                    </Box>
                  )}
                </Box>
              </Box>
            )
          })}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default RunningBackupsSection
