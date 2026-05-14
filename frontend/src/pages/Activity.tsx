import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Box, IconButton, MenuItem, Select, Typography } from '@mui/material'
import { History, Info, RefreshCw } from 'lucide-react'
import { activityAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import BackupJobsTable from '../components/BackupJobsTable'

interface ActivityItem {
  id: number
  type: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  repository: string | null
  log_file_path: string | null
  archive_name: string | null
  package_name: string | null
  repository_path: string | null // Full repository path
  triggered_by?: string // 'manual' or 'schedule'
  schedule_id?: number | null
  schedule_name?: string | null // Schedule name if triggered by schedule
  backup_plan_id?: number | null
  backup_plan_run_id?: number | null
  backup_plan_name?: string | null
  has_logs?: boolean
}

const Activity: React.FC = () => {
  const { t } = useTranslation()
  const { track, EventCategory, EventAction } = useAnalytics()
  const { hasGlobalPermission } = useAuth()
  const canManageActivityJobs = hasGlobalPermission('repositories.manage_all')
  const [typeFilter, setTypeFilter] = useState<string>('all')
  const [statusFilter, setStatusFilter] = useState<string>('all')

  // Fetch activity data
  const {
    data: activities,
    isLoading,
    refetch,
  } = useQuery({
    queryKey: ['activity', typeFilter, statusFilter],
    queryFn: async () => {
      const params: Record<string, unknown> = { limit: 200 }
      if (typeFilter !== 'all') params.job_type = typeFilter
      if (statusFilter !== 'all') params.status = statusFilter

      const response = await activityAPI.list(params)
      return response.data
    },
    refetchInterval: 3000, // Refresh every 3 seconds
  })

  const handleTypeFilterChange = (value: string) => {
    setTypeFilter(value)
    track(EventCategory.NAVIGATION, EventAction.FILTER, {
      filter_kind: 'type',
      filter_value: value,
    })
  }

  const handleStatusFilterChange = (value: string) => {
    setStatusFilter(value)
    track(EventCategory.NAVIGATION, EventAction.FILTER, {
      filter_kind: 'status',
      filter_value: value,
    })
  }

  // Just return all activities without grouping
  const processedActivities = React.useMemo(() => {
    if (!activities) return { grouped: [], individual: [] }
    return { grouped: [], individual: activities }
  }, [activities])

  return (
    <Box>
      {/* Header */}
      <Box
        sx={{
          display: 'flex',
          flexDirection: { xs: 'column', sm: 'row' },
          justifyContent: 'space-between',
          alignItems: { xs: 'flex-start', sm: 'center' },
          gap: 2,
          mb: 3,
        }}
      >
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <History size={32} />
          <Box>
            <Typography variant="h4">{t('activity.title')}</Typography>
            <Typography variant="body2" color="text.secondary">
              {t('activity.subtitle')}
            </Typography>
          </Box>
        </Box>
        <IconButton
          onClick={() => refetch()}
          title="Refresh"
          sx={{ alignSelf: { xs: 'flex-end', sm: 'auto' } }}
        >
          <RefreshCw size={20} />
        </IconButton>
      </Box>

      {/* Filters */}
      <Box sx={{ mb: 3, display: 'flex', flexWrap: 'wrap', gap: 1.5, alignItems: 'center' }}>
        <Select
          size="small"
          value={typeFilter}
          onChange={(e) => handleTypeFilterChange(e.target.value)}
          sx={{ minWidth: 160, fontSize: '0.8rem', fontWeight: 600, borderRadius: 1.5 }}
        >
          <MenuItem value="all">{t('activity.filters.allTypes')}</MenuItem>
          <MenuItem value="backup">{t('activity.filters.types.backup')}</MenuItem>
          <MenuItem value="restore">{t('activity.filters.types.restore')}</MenuItem>
          <MenuItem value="restore_check">{t('activity.filters.types.restoreCheck')}</MenuItem>
          <MenuItem value="check">{t('activity.filters.types.check')}</MenuItem>
          <MenuItem value="compact">{t('activity.filters.types.compact')}</MenuItem>
          <MenuItem value="prune">{t('activity.filters.types.prune')}</MenuItem>
          <MenuItem value="package">{t('activity.filters.types.package')}</MenuItem>
          <MenuItem value="script_execution">
            {t('activity.filters.types.scriptExecution')}
          </MenuItem>
        </Select>

        <Select
          size="small"
          value={statusFilter}
          onChange={(e) => handleStatusFilterChange(e.target.value)}
          sx={{ minWidth: 140, fontSize: '0.8rem', fontWeight: 600, borderRadius: 1.5 }}
        >
          <MenuItem value="all">{t('activity.filters.allStatus')}</MenuItem>
          <MenuItem value="completed">{t('activity.filters.statuses.completed')}</MenuItem>
          <MenuItem value="needs_backup">{t('activity.filters.statuses.needsBackup')}</MenuItem>
          <MenuItem value="failed">{t('activity.filters.statuses.failed')}</MenuItem>
          <MenuItem value="running">{t('activity.filters.statuses.running')}</MenuItem>
          <MenuItem value="pending">{t('activity.filters.statuses.pending')}</MenuItem>
        </Select>
      </Box>

      {/* Activity List */}
      {isLoading ? (
        <BackupJobsTable<ActivityItem>
          jobs={[]}
          showTypeColumn={true}
          showTriggerColumn={true}
          loading={true}
          actions={{
            viewLogs: true,
            downloadLogs: true,
            errorInfo: true,
            breakLock: true,
            delete: true,
          }}
          canBreakLocks={canManageActivityJobs}
          canDeleteJobs={canManageActivityJobs}
          getRowKey={(activity) => `${activity.type}-${activity.id}`}
          headerBgColor="background.default"
          enableHover={true}
          tableId="activity"
        />
      ) : (
        <BackupJobsTable<ActivityItem>
          jobs={processedActivities.individual}
          showTypeColumn={true}
          showTriggerColumn={true}
          loading={false}
          actions={{
            viewLogs: true,
            downloadLogs: true,
            errorInfo: true,
            breakLock: true,
            delete: true,
          }}
          canBreakLocks={canManageActivityJobs}
          canDeleteJobs={canManageActivityJobs}
          getRowKey={(activity) => `${activity.type}-${activity.id}`}
          headerBgColor="background.default"
          enableHover={true}
          tableId="activity"
          emptyState={{
            icon: <Info size={48} />,
            title: t('activity.empty.title'),
            description: t('activity.empty.message'),
          }}
        />
      )}
    </Box>
  )
}

export default Activity
