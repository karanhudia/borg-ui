import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import {
  Box,
  Card,
  Typography,
  Chip,
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
  Tooltip,
} from '@mui/material'
import {
  History,
  RefreshCw,
  Eye,
  Info,
  Download,
} from 'lucide-react'
import { activityAPI } from '../services/api'
import { formatDate } from '../utils/dateUtils'
import { TerminalLogViewer } from '../components/TerminalLogViewer'
import DataTable, { Column, ActionButton } from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import RepositoryCell from '../components/RepositoryCell'

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
  repository_path: string | null  // Full repository path
  triggered_by?: string  // 'manual' or 'schedule'
  schedule_id?: number | null
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
  })

  const getTypeLabel = (type: string) => {
    switch (type) {
      case 'backup':
        return 'Backup'
      case 'restore':
        return 'Restore'
      case 'check':
        return 'Repository Check'
      case 'compact':
        return 'Compact'
      case 'package':
        return 'Package Install'
      default:
        return type
    }
  }

  const getTypeColor = (
    type: string
  ): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
    switch (type) {
      case 'backup':
        return 'primary'
      case 'restore':
        return 'secondary'
      case 'check':
        return 'info'
      case 'compact':
        return 'warning'
      case 'package':
        return 'success'
      default:
        return 'default'
    }
  }

  const getDuration = (started: string | null, completed: string | null) => {
    if (!started) return '-'
    const start = new Date(started).getTime()
    const end = completed ? new Date(completed).getTime() : Date.now()
    const duration = Math.floor((end - start) / 1000)

    if (duration < 60) return `${duration}s`
    if (duration < 3600) return `${Math.floor(duration / 60)}m ${duration % 60}s`
    return `${Math.floor(duration / 3600)}h ${Math.floor((duration % 3600) / 60)}m`
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

  // Define columns for DataTable (ordered: Job ID -> Repository -> Type -> Status -> Started -> Duration)
  const columns: Column<ActivityItem>[] = [
    {
      id: 'id',
      label: 'Job ID',
      align: 'left',
      render: (activity) => (
        <Typography variant="body2" fontWeight={600} color="primary">
          #{activity.id}
        </Typography>
      ),
    },
    {
      id: 'repository',
      label: 'Repository/Target',
      align: 'left',
      minWidth: '250px',
      render: (activity) => {
        // For repository jobs (backup, restore, check, compact)
        if (activity.type === 'backup' || activity.type === 'restore' || activity.type === 'check' || activity.type === 'compact') {
          // Use repository_path if available, otherwise use repository name as fallback
          if (activity.repository_path) {
            return (
              <RepositoryCell
                repositoryName={activity.repository || activity.repository_path}
                repositoryPath={activity.repository_path}
                withIcon={false}
              />
            )
          } else if (activity.repository) {
            // If repo was deleted but we still have the name, show it
            return (
              <Typography variant="body2" color="text.secondary">
                {activity.repository}
              </Typography>
            )
          }
        }

        // Fallback for non-repository jobs (package, etc.) or when nothing available
        const displayName = activity.archive_name || activity.package_name || '-'
        return <Typography variant="body2">{displayName}</Typography>
      },
    },
    {
      id: 'type',
      label: 'Type',
      align: 'left',
      render: (activity) => (
        <Chip
          label={getTypeLabel(activity.type)}
          color={getTypeColor(activity.type)}
          size="small"
        />
      ),
    },
    {
      id: 'status',
      label: 'Status',
      align: 'left',
      render: (activity) => (
        <Tooltip
          title={activity.triggered_by === 'schedule' ? `Triggered by: Schedule (ID: ${activity.schedule_id})` : 'Triggered by: Manual'}
          placement="top"
          arrow
        >
          <span>
            <StatusBadge status={activity.status} />
          </span>
        </Tooltip>
      ),
    },
    {
      id: 'started_at',
      label: 'Started',
      align: 'left',
      render: (activity) => (
        <Typography variant="body2" color="text.secondary">
          {activity.started_at ? formatDate(activity.started_at) : '-'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      align: 'left',
      render: (activity) => (
        <Typography variant="body2" color="text.secondary">
          {getDuration(activity.started_at, activity.completed_at)}
        </Typography>
      ),
    },
  ]

  // Define actions for DataTable (with conditional show/disable based on row state)
  const actions: ActionButton<ActivityItem>[] = [
    {
      icon: <Eye size={18} />,
      label: 'View Logs',
      onClick: handleViewLogs,
      color: 'primary',
      tooltip: 'View Logs',
    },
    {
      icon: <Download size={18} />,
      label: 'Download Logs',
      onClick: handleDownloadLogs,
      color: 'info',
      tooltip: 'Download Logs',
      show: (item) => item.has_logs === true,
    },
  ]

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

      {/* Activity List using DataTable */}
      <DataTable
        data={activities || []}
        columns={columns}
        actions={actions}
        getRowKey={(activity) => `${activity.type}-${activity.id}`}
        loading={isLoading}
        headerBgColor="background.default"
        enableHover={true}
        emptyState={{
          icon: <Info size={48} />,
          title: 'No activity found',
          description: 'There are no operations matching your filters',
        }}
      />

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
