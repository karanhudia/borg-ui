import React, { useState } from 'react'
import { useTranslation } from 'react-i18next'
import { useQuery } from '@tanstack/react-query'
import { Box, IconButton, Typography } from '@mui/material'
import { History, Info, RefreshCw } from 'lucide-react'
import { activityAPI, repositoriesAPI } from '../services/api'
import { useAnalytics } from '../hooks/useAnalytics'
import { useAuth } from '../hooks/useAuth'
import { useLockBreakPermissions } from '../hooks/useLockBreakPermissions'
import BackupJobsTable from '../components/BackupJobsTable'
import LogViewerDialog from '../components/LogViewerDialog'
import RunningCloudStorageJobsSection from '../components/RunningCloudStorageJobsSection'
import { ActivityFilters } from './activity/ActivityFilters'

export interface ActivityItem {
  id: number
  type: string
  status: string
  started_at: string | null
  completed_at: string | null
  error_message: string | null
  repository: string | null
  repository_id?: number | null
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

interface ActivityContentProps {
  activities?: ActivityItem[]
  isLoading: boolean
  typeFilter: string
  statusFilter: string
  onTypeFilterChange: (value: string) => void
  onStatusFilterChange: (value: string) => void
  onRefresh: () => void
  canManageActivityJobs: boolean
  canBreakLockForActivity: (job: ActivityItem) => boolean
  lockBreakingEnabled: boolean
}

export function ActivityContent({
  activities,
  isLoading,
  typeFilter,
  statusFilter,
  onTypeFilterChange,
  onStatusFilterChange,
  onRefresh,
  canManageActivityJobs,
  canBreakLockForActivity,
  lockBreakingEnabled,
}: ActivityContentProps) {
  const { t } = useTranslation()
  const [logJob, setLogJob] = useState<ActivityItem | null>(null)

  const processedActivities = React.useMemo(() => {
    if (!activities) return { grouped: [], individual: [] }
    return { grouped: [], individual: activities }
  }, [activities])
  const activeCloudStorageJobs = React.useMemo(
    () =>
      ((activities || []) as ActivityItem[]).filter(
        (activity: ActivityItem) =>
          (activity.type === 'rclone_sync' || activity.type === 'rclone_hydrate') &&
          (activity.status === 'pending' || activity.status === 'running')
      ),
    [activities]
  )

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
          onClick={onRefresh}
          title="Refresh"
          sx={{ alignSelf: { xs: 'flex-end', sm: 'auto' } }}
        >
          <RefreshCw size={20} />
        </IconButton>
      </Box>

      <ActivityFilters
        typeFilter={typeFilter}
        statusFilter={statusFilter}
        onTypeFilterChange={onTypeFilterChange}
        onStatusFilterChange={onStatusFilterChange}
      />

      <RunningCloudStorageJobsSection
        jobs={activeCloudStorageJobs}
        onViewLogs={(job) => setLogJob(job as ActivityItem)}
      />

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
          canBreakLocks={canBreakLockForActivity}
          lockBreakingEnabled={lockBreakingEnabled}
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
          canBreakLocks={canBreakLockForActivity}
          lockBreakingEnabled={lockBreakingEnabled}
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
      <LogViewerDialog job={logJob} open={Boolean(logJob)} onClose={() => setLogJob(null)} />
    </Box>
  )
}

const Activity: React.FC = () => {
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

  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })
  const repositories = React.useMemo(
    () => repositoriesData?.data?.repositories ?? [],
    [repositoriesData?.data?.repositories]
  )
  const { canBreakLock: canBreakLockForActivity, lockBreakingEnabled } = useLockBreakPermissions({
    repositories,
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

  return (
    <ActivityContent
      activities={activities}
      isLoading={isLoading}
      typeFilter={typeFilter}
      statusFilter={statusFilter}
      onTypeFilterChange={handleTypeFilterChange}
      onStatusFilterChange={handleStatusFilterChange}
      onRefresh={() => refetch()}
      canManageActivityJobs={canManageActivityJobs}
      canBreakLockForActivity={canBreakLockForActivity}
      lockBreakingEnabled={lockBreakingEnabled}
    />
  )
}

export default Activity
