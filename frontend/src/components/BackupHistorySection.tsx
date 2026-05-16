import React from 'react'
import { Box, Typography, Select, MenuItem, Button, alpha, useTheme } from '@mui/material'
import { Clock } from 'lucide-react'
import { useTranslation } from 'react-i18next'
import BackupJobsTable from './BackupJobsTable'
import RepoSelect from './RepoSelect'
import { useAnalytics } from '../hooks/useAnalytics'

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

import { BackupPlan, Repository } from '../types'

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
  backup_plan_id?: number | null
  archive_name?: string | null
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
  backupPlans: BackupPlan[]
  repositories: Repository[]
  isLoading: boolean
  canBreakLocks?: boolean
  canDeleteJobs?: boolean
  filterSchedule: number | 'all'
  filterRepository: string | 'all'
  filterStatus: string | 'all'
  filterPlan: number | 'all'
  onFilterScheduleChange: (value: number | 'all') => void
  onFilterRepositoryChange: (value: string | 'all') => void
  onFilterStatusChange: (value: string | 'all') => void
  onFilterPlanChange: (value: number | 'all') => void
}

const BackupHistorySection: React.FC<BackupHistorySectionProps> = ({
  backupJobs,
  scheduledJobs,
  backupPlans,
  repositories,
  isLoading,
  canBreakLocks = false,
  canDeleteJobs = false,
  filterSchedule,
  filterRepository,
  filterStatus,
  filterPlan,
  onFilterScheduleChange,
  onFilterRepositoryChange,
  onFilterStatusChange,
  onFilterPlanChange,
}) => {
  const { trackNavigation, EventAction } = useAnalytics()
  const theme = useTheme()
  const isDark = theme.palette.mode === 'dark'

  const filteredBackupJobs = backupJobs.filter((job: BackupJob) => {
    if (filterPlan !== 'all' && job.backup_plan_id !== filterPlan) return false
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
    filterPlan !== 'all' ||
    filterSchedule !== 'all' ||
    filterRepository !== 'all' ||
    filterStatus !== 'all'

  const { t } = useTranslation()

  const filterSelectSx = {
    fontSize: '0.8rem',
    fontWeight: 600,
    borderRadius: 1.5,
    '& .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.1) : alpha('#000', 0.12),
    },
    '&:hover .MuiOutlinedInput-notchedOutline': {
      borderColor: isDark ? alpha('#fff', 0.2) : alpha('#000', 0.25),
    },
  } as const

  return (
    <Box sx={{ mt: 3 }}>
      {/* Section header */}
      <Box
        sx={{
          display: 'flex',
          alignItems: 'flex-start',
          justifyContent: 'space-between',
          mb: 2,
          gap: 1,
        }}
      >
        <Box>
          <Typography variant="h6" fontWeight={600}>
            {t('backupHistory.title')}
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {hasFilters
              ? t('backupHistory.showingFiltered', {
                  filtered: filteredBackupJobs.length,
                  total: backupJobs.length,
                })
              : t('backupHistory.showing', {
                  filtered: filteredBackupJobs.length,
                  total: backupJobs.length,
                })}
          </Typography>
        </Box>

        {hasFilters && (
          <Button
            size="small"
            variant="text"
            onClick={() => {
              onFilterPlanChange('all')
              onFilterScheduleChange('all')
              onFilterRepositoryChange('all')
              onFilterStatusChange('all')
              trackNavigation(EventAction.FILTER, {
                section: 'backup_history',
                filter_kind: 'reset',
              })
            }}
            sx={{ px: 1, minWidth: 'auto', fontWeight: 700, borderRadius: 2, flexShrink: 0 }}
          >
            {t('common.clearFilters', { defaultValue: 'Clear filters' })}
          </Button>
        )}
      </Box>

      {/* Flat filter row */}
      <Box sx={{ mb: 2.5, display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
        <Select
          size="small"
          value={filterPlan}
          displayEmpty
          onChange={(e) => {
            const value = e.target.value as number | 'all'
            onFilterPlanChange(value)
            trackNavigation(EventAction.FILTER, {
              section: 'backup_history',
              filter_kind: 'plan',
              filter_value: value,
            })
          }}
          sx={{
            flex: 1,
            minWidth: { xs: '100%', sm: 160 },
            ...filterSelectSx,
          }}
        >
          <MenuItem value="all">
            {t('backupHistory.allPlans', { defaultValue: 'All Backup Plans' })}
          </MenuItem>
          {backupPlans.map((plan) => (
            <MenuItem key={plan.id} value={plan.id}>
              {plan.name}
            </MenuItem>
          ))}
        </Select>

        <Select
          size="small"
          value={filterSchedule}
          displayEmpty
          onChange={(e) => {
            const value = e.target.value as number | 'all'
            onFilterScheduleChange(value)
            trackNavigation(EventAction.FILTER, {
              section: 'backup_history',
              filter_kind: 'schedule',
              filter_value: value,
            })
          }}
          sx={{
            flex: 1,
            minWidth: { xs: '100%', sm: 150 },
            ...filterSelectSx,
          }}
        >
          <MenuItem value="all">{t('backupHistory.allSchedules')}</MenuItem>
          {scheduledJobs.map((job: ScheduledJob) => (
            <MenuItem key={job.id} value={job.id}>
              {job.name}
            </MenuItem>
          ))}
        </Select>

        <RepoSelect
          repositories={repositories}
          value={filterRepository}
          onChange={(v) => {
            onFilterRepositoryChange(v as string)
            trackNavigation(EventAction.FILTER, {
              section: 'backup_history',
              filter_kind: 'repository',
              filter_value: v as string,
            })
          }}
          valueKey="path"
          size="small"
          hidePath
          label=""
          placeholderLabel={t('backupHistory.allRepositories')}
          fallbackDisplayValue={t('backupHistory.allRepositories')}
          prefixItems={<MenuItem value="all">{t('backupHistory.allRepositories')}</MenuItem>}
          sx={{
            flex: 2,
            minWidth: { xs: '100%', sm: 200 },
            ...filterSelectSx,
          }}
        />

        <Select
          size="small"
          value={filterStatus}
          displayEmpty
          onChange={(e) => {
            const value = e.target.value
            onFilterStatusChange(value)
            trackNavigation(EventAction.FILTER, {
              section: 'backup_history',
              filter_kind: 'status',
              filter_value: value,
            })
          }}
          sx={{
            flex: 1,
            minWidth: { xs: '100%', sm: 140 },
            ...filterSelectSx,
          }}
        >
          <MenuItem value="all">{t('backupHistory.allStatus')}</MenuItem>
          <MenuItem value="completed">{t('backupHistory.completed')}</MenuItem>
          <MenuItem value="failed">{t('backupHistory.failed')}</MenuItem>
          <MenuItem value="warning">{t('backupHistory.warning')}</MenuItem>
        </Select>
      </Box>

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
        canBreakLocks={canBreakLocks}
        canDeleteJobs={canDeleteJobs}
        getRowKey={(job) => String(job.id)}
        headerBgColor="background.default"
        enableHover={true}
        tableId="schedule"
        emptyState={{
          icon: <Clock size={48} />,
          title: t('backupHistory.noJobsFound'),
        }}
      />
    </Box>
  )
}

export default BackupHistorySection
