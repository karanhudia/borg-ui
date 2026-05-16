import { Box, Skeleton, Stack, Typography, alpha } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ScheduleJobCard from './ScheduleJobCard'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
  timezone?: string | null
  repository: string | null
  repository_id: number | null
  repository_ids: number[] | null
  enabled: boolean
  last_run: string | null
  next_run: string | null
  created_at: string
  updated_at: string | null
  description: string | null
  archive_name_template: string | null
  run_repository_scripts: boolean
  pre_backup_script_id: number | null
  post_backup_script_id: number | null
  run_prune_after: boolean
  run_compact_after: boolean
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  last_prune: string | null
  last_compact: string | null
}

interface Repository {
  id: number
  name: string
  path: string
}

interface ScheduledJobsTableProps {
  jobs: ScheduledJob[]
  repositories: Repository[]
  isLoading: boolean
  title?: string
  description?: string
  canManageJob: (job: ScheduledJob) => boolean
  onEdit: (job: ScheduledJob) => void
  onDelete: (job: ScheduledJob) => void
  onDuplicate: (job: ScheduledJob) => void
  onRunNow: (job: ScheduledJob) => void
  onToggle: (job: ScheduledJob) => void
  isRunNowPending?: boolean
  isDuplicatePending?: boolean
}

const ScheduledJobsTable = ({
  jobs,
  repositories,
  isLoading,
  title,
  description,
  canManageJob,
  onEdit,
  onDelete,
  onDuplicate,
  onRunNow,
  onToggle,
  isRunNowPending,
  isDuplicatePending,
}: ScheduledJobsTableProps) => {
  const { t } = useTranslation()

  const renderContent = () => {
    if (isLoading) {
      return (
        <Stack spacing={2}>
          {[0, 1, 2].map((i) => (
            <Box
              key={i}
              sx={{
                borderRadius: 2,
                bgcolor: 'background.paper',
                overflow: 'hidden',
                boxShadow: (theme) =>
                  theme.palette.mode === 'dark'
                    ? `0 0 0 1px ${alpha('#fff', 0.08)}, 0 4px 16px ${alpha('#000', 0.25)}`
                    : `0 0 0 1px ${alpha('#000', 0.08)}, 0 2px 8px ${alpha('#000', 0.07)}`,
                opacity: Math.max(0.4, 1 - i * 0.2),
              }}
            >
              <Box
                sx={{ px: { xs: 1.75, sm: 2 }, pt: { xs: 1.75, sm: 2 }, pb: { xs: 1.5, sm: 1.75 } }}
              >
                {/* Title row + badge (Switch toggle) */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'flex-start',
                    justifyContent: 'space-between',
                    gap: 1,
                    mb: 1.5,
                  }}
                >
                  <Box sx={{ flex: 1 }}>
                    <Skeleton
                      variant="text"
                      width={[150, 190, 130][i]}
                      height={28}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>
                  {/* Switch + enabled text badge */}
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5, flexShrink: 0 }}>
                    <Skeleton variant="rounded" width={34} height={20} sx={{ borderRadius: 10 }} />
                    <Skeleton
                      variant="text"
                      width={48}
                      height={14}
                      sx={{ transform: 'none', borderRadius: 0.5 }}
                    />
                  </Box>
                </Box>

                {/* Stats grid — 4 columns */}
                <Box
                  sx={{
                    display: 'grid',
                    gridTemplateColumns: { xs: 'repeat(2, 1fr)', sm: 'repeat(4, 1fr)' },
                    borderRadius: 1.5,
                    border: '1px solid',
                    borderColor: 'divider',
                    overflow: 'hidden',
                    mb: 1.5,
                  }}
                >
                  {[0, 1, 2, 3].map((j) => (
                    <Box
                      key={j}
                      sx={{
                        px: 1.5,
                        py: 1.1,
                        borderRight: j < 3 ? '1px solid' : 0,
                        borderColor: 'divider',
                      }}
                    >
                      <Skeleton
                        variant="text"
                        width={38}
                        height={10}
                        sx={{ transform: 'none', borderRadius: 0.5, mb: 0.5 }}
                      />
                      <Skeleton
                        variant="text"
                        width={[58, 48, 54, 44][j]}
                        height={16}
                        sx={{ transform: 'none', borderRadius: 0.5 }}
                      />
                    </Box>
                  ))}
                </Box>

                {/* Actions row — 3 icon buttons + Run Now primary button */}
                <Box
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 0.5,
                    pt: 1.25,
                    borderTop: '1px solid',
                    borderColor: 'divider',
                  }}
                >
                  <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
                  <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
                  <Skeleton variant="rounded" width={32} height={32} sx={{ borderRadius: 1.5 }} />
                  <Skeleton
                    variant="rounded"
                    width={88}
                    height={30}
                    sx={{ borderRadius: 1, ml: 'auto' }}
                  />
                </Box>
              </Box>
            </Box>
          ))}
        </Stack>
      )
    }

    if (jobs.length === 0) {
      return (
        <Box
          sx={{
            py: 6,
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            color: 'text.secondary',
          }}
        >
          <Clock size={40} style={{ opacity: 0.25, marginBottom: 12 }} />
          <Typography variant="body1" gutterBottom>
            {t('scheduledJobsTableSection.noJobsFound')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {t('scheduledJobsTableSection.noJobsDesc')}
          </Typography>
        </Box>
      )
    }

    return (
      <Stack spacing={2}>
        {jobs.map((job) => (
          <ScheduleJobCard
            key={job.id}
            job={job}
            repositories={repositories}
            canManage={canManageJob(job)}
            onEdit={() => onEdit(job)}
            onDelete={() => onDelete(job)}
            onDuplicate={() => onDuplicate(job)}
            onRunNow={() => onRunNow(job)}
            onToggle={() => onToggle(job)}
            isRunNowPending={isRunNowPending}
            isDuplicatePending={isDuplicatePending}
          />
        ))}
      </Stack>
    )
  }

  return (
    <Box>
      <Typography variant="h6" fontWeight={600} sx={{ mb: 2 }}>
        {title || t('scheduledJobsTableSection.title')}
      </Typography>
      {description && (
        <Typography variant="body2" color="text.secondary" sx={{ mt: -1, mb: 2 }}>
          {description}
        </Typography>
      )}
      {renderContent()}
    </Box>
  )
}

export default ScheduledJobsTable
