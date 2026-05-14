import React from 'react'
import { Box, Typography, Stack, useTheme, alpha, Tooltip } from '@mui/material'
import { Clock, ListChecks, CalendarClock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import { formatDate, formatRelativeTime } from '../utils/dateUtils'
import { Repository } from '../types'

const ACCENT_SCHEDULE = '#059669'
const ACCENT_PLAN = '#3b82f6'

interface UpcomingJob {
  id: number
  type?: 'schedule' | 'backup_plan'
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
  onPlanClick?: (planId: number) => void
  getRepositoryName: (path: string) => string
}

const UpcomingJobsTable: React.FC<UpcomingJobsTableProps> = ({
  upcomingJobs,
  repositories,
  onPlanClick,
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
            bgcolor: ACCENT_SCHEDULE,
            boxShadow: `0 0 6px ${alpha(ACCENT_SCHEDULE, 0.7)}`,
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
        {upcomingJobs.slice(0, 5).map((job) => {
          const isPlan = job.type === 'backup_plan'
          const accent = isPlan ? ACCENT_PLAN : ACCENT_SCHEDULE
          const isClickable = isPlan && Boolean(onPlanClick)
          const typeLabel = isPlan
            ? t('upcomingJobs.types.plan', { defaultValue: 'Plan' })
            : t('upcomingJobs.types.schedule', { defaultValue: 'Schedule' })
          const TypeIcon = isPlan ? ListChecks : CalendarClock

          const rowContent = (
            <Box
              role={isClickable ? 'button' : undefined}
              tabIndex={isClickable ? 0 : undefined}
              onClick={isClickable ? () => onPlanClick?.(job.id) : undefined}
              onKeyDown={
                isClickable
                  ? (e) => {
                      if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault()
                        onPlanClick?.(job.id)
                      }
                    }
                  : undefined
              }
              sx={{
                display: 'flex',
                alignItems: 'center',
                gap: 2,
                px: 2,
                py: 1.5,
                borderRadius: 2,
                border: '1px solid',
                borderColor: alpha(accent, isDark ? 0.2 : 0.15),
                bgcolor: alpha(accent, isDark ? 0.06 : 0.03),
                transition: 'border-color 0.15s, box-shadow 0.15s, transform 0.15s',
                cursor: isClickable ? 'pointer' : 'default',
                '&:hover': {
                  borderColor: alpha(accent, isDark ? 0.38 : 0.28),
                  boxShadow: `0 2px 14px ${alpha(accent, 0.1)}`,
                  ...(isClickable && { transform: 'translateY(-1px)' }),
                },
                '&:focus-visible': {
                  outline: '2px solid',
                  outlineColor: accent,
                  outlineOffset: 2,
                },
              }}
            >
              {/* Left accent bar */}
              <Box
                sx={{
                  width: 3,
                  height: 32,
                  borderRadius: 4,
                  bgcolor: accent,
                  flexShrink: 0,
                  boxShadow: `0 0 8px ${alpha(accent, 0.5)}`,
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

              {/* Type pill */}
              <Box
                sx={{
                  display: { xs: 'none', sm: 'flex' },
                  alignItems: 'center',
                  gap: 0.4,
                  px: 0.9,
                  py: 0.35,
                  borderRadius: 1,
                  bgcolor: alpha(accent, isDark ? 0.14 : 0.09),
                  border: '1px solid',
                  borderColor: alpha(accent, isDark ? 0.3 : 0.22),
                  flexShrink: 0,
                }}
              >
                <TypeIcon size={10} color={accent} />
                <Typography
                  sx={{
                    fontSize: '0.62rem',
                    fontWeight: 700,
                    color: accent,
                    lineHeight: 1,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  {typeLabel}
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
                  bgcolor: alpha(accent, isDark ? 0.15 : 0.1),
                  flexShrink: 0,
                }}
              >
                <Box component="span" sx={{ display: 'flex', alignItems: 'center' }}>
                  <Clock size={11} color={accent} />
                </Box>
                <Typography
                  sx={{ fontSize: '0.75rem', fontWeight: 700, color: accent, lineHeight: 1 }}
                >
                  {formatRelativeTime(job.next_run)}
                </Typography>
              </Box>
            </Box>
          )

          return (
            <Tooltip
              key={`${job.type || 'schedule'}-${job.id}`}
              title={`${formatDate(job.next_run)} - ${job.cron_expression} (${job.timezone || 'UTC'})`}
              placement="top"
              arrow
            >
              {rowContent}
            </Tooltip>
          )
        })}
      </Stack>
    </Box>
  )
}

export default UpcomingJobsTable
