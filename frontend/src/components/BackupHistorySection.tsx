import React from 'react'
import {
  Card,
  CardContent,
  Typography,
  Stack,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material'
import { Clock } from 'lucide-react'
import BackupJobsTable from './BackupJobsTable'

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

interface BackupJob {
  id: string
  repository: string
  status: 'running' | 'completed' | 'failed' | 'cancelled' | 'completed_with_warnings'
  started_at: string
  completed_at?: string
  error_message?: string
  has_logs?: boolean
  maintenance_status?: string | null
  scheduled_job_id?: number | null
  progress_details?: {
    original_size: number
    compressed_size: number
    deduplicated_size: number
    nfiles: number
    current_file: string
    progress_percent: number
    backup_speed: number
    total_expected_size: number
    estimated_time_remaining: number
  }
}

interface BackupHistorySectionProps {
  backupJobs: BackupJob[]
  scheduledJobs: ScheduledJob[]
  repositories: Repository[]
  isLoading: boolean
  isAdmin: boolean
  filterSchedule: number | 'all'
  filterRepository: string | 'all'
  filterStatus: string | 'all'
  onFilterScheduleChange: (value: number | 'all') => void
  onFilterRepositoryChange: (value: string | 'all') => void
  onFilterStatusChange: (value: string | 'all') => void
}

const BackupHistorySection: React.FC<BackupHistorySectionProps> = ({
  backupJobs,
  scheduledJobs,
  repositories,
  isLoading,
  isAdmin,
  filterSchedule,
  filterRepository,
  filterStatus,
  onFilterScheduleChange,
  onFilterRepositoryChange,
  onFilterStatusChange,
}) => {
  // Apply filters
  const filteredBackupJobs = backupJobs.filter((job: BackupJob) => {
    if (filterSchedule !== 'all' && job.scheduled_job_id !== filterSchedule) return false
    if (filterRepository !== 'all' && job.repository !== filterRepository) return false
    if (filterStatus !== 'all') {
      if (filterStatus === 'completed' && job.status !== 'completed') return false
      if (filterStatus === 'failed' && job.status !== 'failed') return false
      if (filterStatus === 'warning' && job.status !== 'completed_with_warnings') return false
    }
    return true
  })

  const hasFilters =
    filterSchedule !== 'all' || filterRepository !== 'all' || filterStatus !== 'all'

  return (
    <Card sx={{ mt: 3 }}>
      <CardContent>
        <Typography variant="h6" fontWeight={600} gutterBottom>
          Backup History
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Showing {filteredBackupJobs.length} of {backupJobs.length} backup jobs
          {hasFilters && ' (filtered)'}
        </Typography>

        {/* Filters */}
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} sx={{ mb: 3 }}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Schedule</InputLabel>
            <Select
              value={filterSchedule}
              label="Schedule"
              onChange={(e) => onFilterScheduleChange(e.target.value as number | 'all')}
            >
              <MenuItem value="all">All Schedules</MenuItem>
              {scheduledJobs.map((job: ScheduledJob) => (
                <MenuItem key={job.id} value={job.id}>
                  {job.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>Repository</InputLabel>
            <Select
              value={filterRepository}
              label="Repository"
              onChange={(e) => onFilterRepositoryChange(e.target.value)}
            >
              <MenuItem value="all">All Repositories</MenuItem>
              {repositories.map((repo: Repository) => (
                <MenuItem key={repo.id} value={repo.path}>
                  {repo.name}
                </MenuItem>
              ))}
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Status</InputLabel>
            <Select
              value={filterStatus}
              label="Status"
              onChange={(e) => onFilterStatusChange(e.target.value)}
            >
              <MenuItem value="all">All Status</MenuItem>
              <MenuItem value="completed">Completed</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
              <MenuItem value="warning">Warning</MenuItem>
            </Select>
          </FormControl>
        </Stack>

        <BackupJobsTable
          jobs={filteredBackupJobs}
          repositories={repositories || []}
          loading={isLoading}
          actions={{
            viewLogs: true,
            cancel: true,
            downloadLogs: true,
            errorInfo: true,
            delete: true,
          }}
          isAdmin={isAdmin}
          getRowKey={(job) => String(job.id)}
          headerBgColor="background.default"
          enableHover={true}
          tableId="schedule"
          emptyState={{
            icon: <Clock size={48} />,
            title: 'No backup jobs found',
          }}
        />
      </CardContent>
    </Card>
  )
}

export default BackupHistorySection
