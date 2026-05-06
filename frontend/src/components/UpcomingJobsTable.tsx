import React from 'react'
import { Box, Typography, Stack, useTheme, alpha, Tooltip } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate, formatRelativeTime } from '../utils/dateUtils'
import { Repository } from '../types'

const ACCENT = '#059669'

interface UpcomingJob {
  id: number
  name: string
  repository?: string
  repository_id?: number
  repository_ids?: number[]
  next_run: string
  cron_expression: string
  timezone?: string | null
}

interface UpcomingJobsTableProps {
  upcomingJobs: UpcomingJob[]
  repositories: Repository[]
  isLoading: boolean
  onRunNow?: (jobId: number) => void
  getRepositoryName: (path: string) => string
}

const UpcomingJobsTable: React.FC<UpcomingJobsTableProps> = ({
  upcomingJobs,
  repositories,
  getRepositoryName,
}) => {
  const { t } = useTranslation()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  if (upcomingJobs.length === 0) {
    return null
  }

  const getRepoLabel = (job: UpcomingJob): string => {
    if (job.repository_ids && job.repository_ids.length > 0) {
      return t('upcomingJobs.repositories', { count: job.repository_ids.length })
    }
    if (job.repository_id) {
      return repositories.find((r) => r.id === job.repository_id)?.name || 'Unknown'
    }
    return getRepositoryName(job.repository || '')
  }

  return (
    <Box sx={{ mb: 3 }}>
      {/* Section label */}
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
        <Box
          sx={{
            width: 6,
            height: 6,
            borderRadius: '50%',
            bgcolor: ACCENT,
            boxShadow: `0 0 6px ${alpha(ACCENT, 0.7)}`,
            flexShrink: 0,
          }}
        />
        <Typography
          variant="caption"
          sx={{
            fontWeight: 700,
            fontSize: '0.68rem',
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            color: 'text.secondary',
          }}
        >
          {t('upcomingJobs.title')}
        </Typography>
      </Box>

      {/* Job rows */}
      <Stack spacing={1}>
        {upcomingJobs.slice(0, 5).map((job) => (
          <Tooltip
            key={job.id}
            title={`${formatDate(job.next_run)} - ${job.cron_expression} (${job.timezone || 'UTC'})`}
            placement="top"
            arrow
          >
            <Box
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 2,
                px: 2,
                py: 1.5,
                borderRadius: 2,
                border: '1px solid',
                borderColor: alpha(ACCENT, isDark ? 0.2 : 0.15),
                bgcolor: alpha(ACCENT, isDark ? 0.06 : 0.03),
                transition: 'border-color 0.15s, box-shadow 0.15s',
                '&:hover': {
                  borderColor: alpha(ACCENT, isDark ? 0.38 : 0.28),
                  boxShadow: `0 2px 14px ${alpha(ACCENT, 0.1)}`,
                },
              }}
            >
              {/* Left accent bar */}
              <Box
                sx={{
                  width: 3,
                  height: 32,
                  borderRadius: 4,
                  bgcolor: ACCENT,
                  flexShrink: 0,
                  boxShadow: `0 0 8px ${alpha(ACCENT, 0.5)}`,
                }}
              />

              {/* Job name + repo — single line */}
              <Box
                sx={{
                  flex: 1,
                  minWidth: 0,
                  display: 'flex',
                  alignItems: 'center',
                  gap: 1.5,
                  overflow: 'hidden',
                }}
              >
                <Typography variant="body2" fontWeight={600} noWrap sx={{ flexShrink: 0 }}>
                  {job.name}
                </Typography>
                <Typography
                  variant="body2"
                  color="text.secondary"
                  noWrap
                  sx={{ fontSize: '0.8rem', minWidth: 0 }}
                >
                  {getRepoLabel(job)}
                </Typography>
              </Box>

              {/* Countdown */}
              <Box
                sx={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 0.5,
                  px: 1.25,
                  py: 0.5,
                  borderRadius: 1.5,
                  bgcolor: alpha(ACCENT, isDark ? 0.15 : 0.1),
                  flexShrink: 0,
                }}
              >
                <Box component="span" sx={{ display: 'flex', alignItems: 'center' }}>
                  <Clock size={11} color={ACCENT} />
                </Box>
                <Typography
                  sx={{ fontSize: '0.75rem', fontWeight: 700, color: ACCENT, lineHeight: 1 }}
                >
                  {formatRelativeTime(job.next_run)}
                </Typography>
              </Box>
            </Box>
          </Tooltip>
        ))}
      </Stack>
    </Box>
  )
}

export default UpcomingJobsTable
