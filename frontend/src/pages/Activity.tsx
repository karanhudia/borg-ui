import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  IconButton,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
  FormControl,
  InputLabel,
  Select,
  MenuItem,
} from '@mui/material'
import { History, RefreshCw, Info } from 'lucide-react'
import { activityAPI } from '../services/api'
import BackupJobsTable from '../components/BackupJobsTable'
import { TerminalLogViewer } from '../components/TerminalLogViewer'
import StatusBadge from '../components/StatusBadge'

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
  has_logs?: boolean
}

const Activity: React.FC = () => {
  const [selectedJob, setSelectedJob] = useState<ActivityItem | null>(null)
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
      const params: any = { limit: 50 }
      if (typeFilter !== 'all') params.job_type = typeFilter
      if (statusFilter !== 'all') params.status = statusFilter

      const response = await activityAPI.list(params)
      return response.data
    },
    refetchInterval: 3000, // Refresh every 3 seconds
  })

  const getTypeLabel = (type: string): string => {
    switch (type) {
      case 'backup':
        return 'Backup'
      case 'restore':
        return 'Restore'
      case 'check':
        return 'Repository Check'
      case 'compact':
        return 'Compact'
      case 'prune':
        return 'Prune'
      case 'package':
        return 'Package Install'
      default:
        return type
    }
  }

  const handleViewLogs = (job: ActivityItem) => {
    setSelectedJob(job)
  }

  const handleCloseLogs = () => {
    setSelectedJob(null)
  }

  const handleDownloadLogs = (job: ActivityItem) => {
    activityAPI.downloadLogs(job.type, job.id)
  }

  // Just return all activities without grouping
  const processedActivities = React.useMemo(() => {
    if (!activities) return { grouped: [], individual: [] }
    return { grouped: [], individual: activities }
  }, [activities])

  return (
    <Box>
      {/* Header */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <History size={32} />
          <Box>
            <Typography variant="h4">Activity</Typography>
            <Typography variant="body2" color="text.secondary">
              View all operations and their logs
            </Typography>
          </Box>
        </Box>
        <IconButton onClick={() => refetch()} title="Refresh">
          <RefreshCw size={20} />
        </IconButton>
      </Box>

      {/* Filters */}
      <Card sx={{ mb: 3, p: 2 }}>
        <Box sx={{ display: 'flex', gap: 2 }}>
          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Type</InputLabel>
            <Select value={typeFilter} label="Type" onChange={(e) => setTypeFilter(e.target.value)}>
              <MenuItem value="all">All Types</MenuItem>
              <MenuItem value="backup">Backup</MenuItem>
              <MenuItem value="restore">Restore</MenuItem>
              <MenuItem value="check">Check</MenuItem>
              <MenuItem value="compact">Compact</MenuItem>
              <MenuItem value="prune">Prune</MenuItem>
              <MenuItem value="package">Package</MenuItem>
            </Select>
          </FormControl>

          <FormControl size="small" sx={{ minWidth: 150 }}>
            <InputLabel>Status</InputLabel>
            <Select
              value={statusFilter}
              label="Status"
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <MenuItem value="all">All Status</MenuItem>
              <MenuItem value="completed">Completed</MenuItem>
              <MenuItem value="failed">Failed</MenuItem>
              <MenuItem value="running">Running</MenuItem>
              <MenuItem value="pending">Pending</MenuItem>
            </Select>
          </FormControl>
        </Box>
      </Card>

      {/* Activity List */}
      {isLoading ? (
        <BackupJobsTable
          jobs={[]}
          showTypeColumn={true}
          showTriggerColumn={true}
          loading={true}
          actions={{
            viewLogs: true,
            downloadLogs: true,
          }}
          onViewLogs={handleViewLogs}
          onDownloadLogs={handleDownloadLogs}
          getRowKey={(activity) => `${activity.type}-${activity.id}`}
          headerBgColor="background.default"
          enableHover={true}
        />
      ) : (
        <BackupJobsTable
          jobs={processedActivities.individual}
          showTypeColumn={true}
          showTriggerColumn={true}
          loading={false}
          actions={{
            viewLogs: true,
            downloadLogs: true,
          }}
          onViewLogs={handleViewLogs}
          onDownloadLogs={handleDownloadLogs}
          getRowKey={(activity) => `${activity.type}-${activity.id}`}
          headerBgColor="background.default"
          enableHover={true}
          emptyState={{
            icon: <Info size={48} />,
            title: 'No activity found',
            description: 'There are no operations matching your filters',
          }}
        />
      )}

      {/* Logs Dialog */}
      <Dialog open={Boolean(selectedJob)} onClose={handleCloseLogs} maxWidth="lg" fullWidth>
        <DialogTitle>
          {selectedJob && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h6">
                {getTypeLabel(selectedJob.type)} Logs - Job #{selectedJob.id}
              </Typography>
              <StatusBadge status={selectedJob.status} />
            </Box>
          )}
        </DialogTitle>
        <DialogContent dividers>
          {selectedJob && (
            <TerminalLogViewer
              jobId={`${selectedJob.type}-${selectedJob.id}`}
              status={selectedJob.status}
              jobType={selectedJob.type}
              showHeader={false}
              onFetchLogs={async (offset) => {
                const response = await activityAPI.getLogs(selectedJob.type, selectedJob.id, offset)
                return response.data
              }}
            />
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseLogs}>Close</Button>
        </DialogActions>
      </Dialog>
    </Box>
  )
}

export default Activity
