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
} from '@mui/material'
import {
  History,
  RefreshCw,
  Eye,
  CheckCircle,
  XCircle,
  Clock,
  PlayCircle,
  Info,
} from 'lucide-react'
import { activityAPI } from '../services/api'
import { formatDate } from '../utils/dateUtils'
import { TerminalLogViewer } from '../components/TerminalLogViewer'
import DataTable, { Column, ActionButton } from '../components/DataTable'

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

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'completed':
        return <CheckCircle size={18} />
      case 'failed':
        return <XCircle size={18} />
      case 'running':
        return <PlayCircle size={18} />
      default:
        return <Clock size={18} />
    }
  }

  const getStatusColor = (
    status: string
  ): 'default' | 'primary' | 'secondary' | 'error' | 'info' | 'success' | 'warning' => {
    switch (status) {
      case 'completed':
        return 'success'
      case 'failed':
        return 'error'
      case 'running':
        return 'info'
      default:
        return 'default'
    }
  }

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

  // Define columns for DataTable
  const columns: Column<ActivityItem>[] = [
    {
      id: 'type',
      label: 'Type',
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
      render: (activity) => (
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          {getStatusIcon(activity.status)}
          <Chip
            label={activity.status}
            color={getStatusColor(activity.status)}
            size="small"
            variant="outlined"
          />
        </Box>
      ),
    },
    {
      id: 'repository',
      label: 'Repository/Target',
      render: (activity) => (
        <Typography variant="body2">
          {activity.repository || activity.package_name || activity.archive_name || '-'}
        </Typography>
      ),
    },
    {
      id: 'started_at',
      label: 'Started',
      render: (activity) => (
        <Typography variant="body2">
          {activity.started_at ? formatDate(activity.started_at) : '-'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      render: (activity) => (
        <Typography variant="body2">
          {getDuration(activity.started_at, activity.completed_at)}
        </Typography>
      ),
    },
  ]

  // Define actions for DataTable
  const actions: ActionButton<ActivityItem>[] = [
    {
      icon: <Eye size={18} />,
      label: 'View Logs',
      onClick: handleViewLogs,
      color: 'primary',
      tooltip: 'View Logs',
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
              <Chip
                label={selectedJob.status}
                color={getStatusColor(selectedJob.status)}
                size="small"
              />
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
