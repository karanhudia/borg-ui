import { Box, Chip, Stack, Tooltip, Typography } from '@mui/material'
import { useTranslation } from 'react-i18next'
import { formatDistanceToNow } from 'date-fns'
import { RotateCw } from 'lucide-react'
import { formatDateTimeFull } from '../../utils/dateUtils'
import { useT } from './tokens'
import type { UpcomingTask } from './types'

export function UpcomingBackupsPanel({ tasks }: { tasks: UpcomingTask[] }) {
  const T = useT()
  const { t } = useTranslation()
  const rows = tasks
    .filter((task) => task.type === 'backup_plan' || task.type === 'schedule')
    .slice(0, 5)

  if (rows.length === 0) return null

  const typeLabel = (type: string) => {
    if (type === 'backup_plan') return t('backup.planRun.selectLabel')
    if (type === 'schedule') return t('upcomingJobs.types.schedule')
    return type
  }

  return (
    <Box
      sx={{
        bgcolor: T.bgCard,
        border: `1px solid ${T.border}`,
        borderRadius: T.radius,
        backdropFilter: 'blur(12px)',
        transition: 'border-color 0.2s',
        p: 2.5,
        '&:hover': { borderColor: T.borderHover },
      }}
    >
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 1.75 }}>
        <RotateCw size={13} color={T.textMuted} />
        <Typography
          sx={{
            fontSize: '0.58rem',
            color: T.textMuted,
            letterSpacing: 2,
            textTransform: 'uppercase',
          }}
        >
          {t('dashboard.upcomingBackups.title')}
        </Typography>
      </Stack>

      <Stack spacing={1}>
        {rows.map((task) => {
          const repoCount = Array.isArray(task.repositories)
            ? task.repositories.length
            : task.repository
              ? 1
              : 0
          const nextRunDate = task.next_run ? new Date(task.next_run) : null
          const hasValidNextRun = nextRunDate != null && !Number.isNaN(nextRunDate.getTime())
          const nextRunLabel = hasValidNextRun
            ? formatDistanceToNow(nextRunDate, { addSuffix: true })
            : task.cron

          return (
            <Box
              key={`${task.type}-${task.id}`}
              sx={{
                border: `1px solid ${T.border}`,
                borderRadius: '8px',
                p: 1,
                bgcolor: T.bgCard,
              }}
            >
              <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={1}>
                <Box sx={{ minWidth: 0 }}>
                  <Chip
                    label={typeLabel(task.type)}
                    size="small"
                    sx={{
                      height: 18,
                      fontSize: '0.58rem',
                      bgcolor: T.blueDim,
                      color: T.blue,
                      border: `1px solid ${T.blue}25`,
                      fontFamily: T.mono,
                      mb: 0.6,
                    }}
                  />
                  <Typography
                    sx={{
                      fontSize: '0.78rem',
                      fontWeight: 700,
                      color: T.textPrimary,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {task.name ?? task.repository ?? t('upcomingJobs.types.schedule')}
                  </Typography>
                  {repoCount > 0 && (
                    <Typography sx={{ fontSize: '0.62rem', color: T.textMuted, mt: 0.25 }}>
                      {t('upcomingJobs.repositories', { count: repoCount })}
                    </Typography>
                  )}
                </Box>
                {nextRunLabel && (
                  <Tooltip
                    title={hasValidNextRun ? formatDateTimeFull(task.next_run ?? '') : task.cron}
                    placement="top"
                    arrow
                  >
                    <Typography
                      sx={{
                        fontFamily: T.mono,
                        fontSize: '0.58rem',
                        color: T.textMuted,
                        whiteSpace: 'nowrap',
                        pt: 0.2,
                      }}
                    >
                      {nextRunLabel}
                    </Typography>
                  </Tooltip>
                )}
              </Stack>
            </Box>
          )
        })}
      </Stack>
    </Box>
  )
}
