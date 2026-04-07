import { Box, CircularProgress, Stack, Typography } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import ScheduleJobCard from './ScheduleJobCard'

interface ScheduledJob {
  id: number
  name: string
  cron_expression: string
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
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}>
          <CircularProgress />
        </Box>
      )
    }

    if (jobs.length === 0) {
      return (
        <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary' }}>
          <Clock size={40} style={{ opacity: 0.25, marginBottom: 12 }} />
          <Typography variant="body1" gutterBottom>{t('scheduledJobsTableSection.noJobsFound')}</Typography>
          <Typography variant="body2" color="text.secondary">{t('scheduledJobsTableSection.noJobsDesc')}</Typography>
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
        {t('scheduledJobsTableSection.title')}
      </Typography>
      {renderContent()}
    </Box>
  )
}

export default ScheduledJobsTable
