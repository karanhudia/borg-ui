import React from 'react'
import { useTranslation } from 'react-i18next'
import {
  Box,
  Card,
  CardContent,
  Chip,
  IconButton,
  LinearProgress,
  Stack,
  Tooltip,
  Typography,
  alpha,
  useTheme,
} from '@mui/material'
import { CloudDownload, CloudUpload, Eye, RefreshCw } from 'lucide-react'
import StatusBadge from './StatusBadge'
import type { Job } from '../types/jobs'

interface RunningCloudStorageJobsSectionProps {
  jobs: Job[]
  onViewLogs?: (job: Job) => void
}

const ACTIVE_STATUSES = new Set(['pending', 'running'])

const isCloudStorageJob = (job: Job) => job.type === 'rclone_sync' || job.type === 'rclone_hydrate'

const getJobLabelKey = (job: Job) => {
  if (job.type === 'rclone_hydrate') return 'cloudStorageJobs.operations.hydrate'
  if (job.triggered_by === 'initial') return 'cloudStorageJobs.operations.initialSync'
  return 'cloudStorageJobs.operations.sync'
}

const getTriggerLabelKey = (triggeredBy?: string) => {
  switch (triggeredBy) {
    case 'initial':
      return 'cloudStorageJobs.triggers.initial'
    case 'schedule':
      return 'cloudStorageJobs.triggers.schedule'
    default:
      return 'cloudStorageJobs.triggers.manual'
  }
}

const RunningCloudStorageJobsSection: React.FC<RunningCloudStorageJobsSectionProps> = ({
  jobs,
  onViewLogs,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const activeJobs = jobs.filter((job) => isCloudStorageJob(job) && ACTIVE_STATUSES.has(job.status))

  if (activeJobs.length === 0) return null

  const accent = theme.palette.info.main

  return (
    <Card
      sx={{
        mb: 3,
        border: `1px solid ${alpha(accent, 0.22)}`,
        boxShadow: 'none',
      }}
    >
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.75 }}>
          <Box sx={{ color: accent, display: 'flex' }}>
            <RefreshCw size={16} className="animate-spin" />
          </Box>
          <Typography variant="h6" fontWeight={600}>
            {t('cloudStorageJobs.title')}
          </Typography>
          <Chip
            label={activeJobs.length}
            size="small"
            sx={{
              height: 22,
              fontWeight: 700,
              bgcolor: alpha(accent, 0.1),
              border: `1px solid ${alpha(accent, 0.25)}`,
              color: accent,
            }}
          />
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
          {t('cloudStorageJobs.subtitle')}
        </Typography>

        <Stack spacing={1.5}>
          {activeJobs.map((job) => {
            const isHydrate = job.type === 'rclone_hydrate'
            const Icon = isHydrate ? CloudDownload : CloudUpload
            const progressValue = job.status === 'running' ? 55 : 10

            return (
              <Box
                key={`${job.type}-${job.id}`}
                sx={{
                  p: 1.5,
                  borderRadius: 1,
                  border: `1px solid ${theme.palette.divider}`,
                  bgcolor: alpha(theme.palette.background.default, 0.58),
                }}
              >
                <Stack
                  direction={{ xs: 'column', sm: 'row' }}
                  spacing={1.5}
                  justifyContent="space-between"
                  alignItems={{ xs: 'flex-start', sm: 'center' }}
                >
                  <Stack direction="row" spacing={1.25} alignItems="center" sx={{ minWidth: 0 }}>
                    <Box sx={{ color: accent, display: 'flex', flexShrink: 0 }}>
                      <Icon size={18} />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        <Typography variant="subtitle2" fontWeight={700} noWrap>
                          {job.repository || t('cloudStorageJobs.unknownRepository')}
                        </Typography>
                        <StatusBadge status={job.status} />
                        <Chip
                          size="small"
                          label={t(getJobLabelKey(job))}
                          variant="outlined"
                          sx={{ height: 22, fontSize: '0.72rem' }}
                        />
                      </Stack>
                      {job.repository_path && (
                        <Typography variant="caption" color="text.secondary" noWrap>
                          {job.repository_path}
                        </Typography>
                      )}
                    </Box>
                  </Stack>

                  <Stack direction="row" spacing={1} alignItems="center">
                    <Chip
                      size="small"
                      label={t(getTriggerLabelKey(job.triggered_by))}
                      variant="outlined"
                      sx={{ height: 22, fontSize: '0.72rem' }}
                    />
                    {onViewLogs && job.has_logs && (
                      <Tooltip title={t('cloudStorageJobs.actions.viewLogs')} arrow>
                        <IconButton
                          size="small"
                          aria-label={t('cloudStorageJobs.actions.viewLogs')}
                          onClick={() => onViewLogs(job)}
                        >
                          <Eye size={16} />
                        </IconButton>
                      </Tooltip>
                    )}
                  </Stack>
                </Stack>
                <LinearProgress
                  variant="determinate"
                  value={progressValue}
                  sx={{
                    mt: 1.25,
                    height: 6,
                    borderRadius: 1,
                    bgcolor: alpha(accent, 0.1),
                    '& .MuiLinearProgress-bar': {
                      borderRadius: 1,
                    },
                  }}
                />
              </Box>
            )
          })}
        </Stack>
      </CardContent>
    </Card>
  )
}

export default RunningCloudStorageJobsSection
