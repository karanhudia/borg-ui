import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { dashboardAPI, repositoriesAPI } from '../services/api'
import { toast } from 'react-hot-toast'
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Stack,
  LinearProgress,
  Tooltip,
} from '@mui/material'
import {
  Activity,
  MemoryStick,
  Cpu,
  Clock,
  Eye,
  Download,
  CheckCircle,
  HardDrive,
} from 'lucide-react'
import { formatDate, formatTimeRange } from '../utils/dateUtils'
import DataTable, { Column, ActionButton } from '../components/DataTable'
import StatusBadge from '../components/StatusBadge'
import RepositoryCell from '../components/RepositoryCell'
import { TerminalLogViewer } from '../components/TerminalLogViewer'
import {
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  Button,
} from '@mui/material'

interface SystemMetrics {
  cpu_usage: number
  memory_total: number
  memory_available: number
  memory_usage: number
  disk_total: number
  disk_free: number
  disk_usage: number
}

interface BackupJob {
  id: string | number
  repository: string
  status: string
  progress?: number
  started_at?: string
  completed_at?: string
  triggered_by?: string  // 'manual' or 'schedule'
  schedule_id?: number | null
  has_logs?: boolean
  error_message?: string
}

interface DashboardStatus {
  system_metrics?: SystemMetrics
  recent_jobs?: BackupJob[]
}

export default function Dashboard() {
  const [selectedJob, setSelectedJob] = React.useState<BackupJob | null>(null)

  // Poll data every 30 seconds for fresh data
  const { data: status, isLoading } = useQuery<{ data: DashboardStatus }>({
    queryKey: ['dashboard-status'],
    queryFn: dashboardAPI.getStatus,
    refetchInterval: 30000,
  })

  // Get repositories for name mapping
  const { data: repositoriesData } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  })

  if (isLoading) {
    return (
      <Box
        sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}
      >
        <CircularProgress size={60} />
      </Box>
    )
  }

  const metrics = status?.data?.system_metrics

  const formatBytes = (bytes: number): string => {
    return (bytes / 1024 / 1024 / 1024).toFixed(1)
  }

  // Action handlers for Dashboard jobs
  const handleViewLogs = (job: BackupJob) => {
    setSelectedJob(job)
  }

  const handleCloseLogs = () => {
    setSelectedJob(null)
  }

  const handleDownloadLogs = (job: BackupJob) => {
    // Use activity API for downloading logs
    const token = localStorage.getItem('token')
    if (!token) {
      toast.error('Authentication required')
      return
    }

    const url = `/api/activity/backup/${job.id}/logs/download?token=${token}`
    const a = document.createElement('a')
    a.href = url
    a.download = `backup-${job.id}-logs.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    toast.success('Downloading logs...')
  }

  // Define actions for Dashboard jobs (with conditional show/disable based on job state)
  const jobActions: ActionButton<BackupJob>[] = [
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
      show: (job) => job.has_logs === true,
    },
  ]

  // Define columns for Recent Jobs table (ordered: Job ID → Repository → Status → Started → Duration)
  const jobColumns: Column<BackupJob>[] = [
    {
      id: 'id',
      label: 'Job ID',
      align: 'left',
      render: (job) => (
        <Typography variant="body2" fontWeight={600} color="primary">
          #{job.id}
        </Typography>
      ),
    },
    {
      id: 'repository',
      label: 'Repository',
      align: 'left',
      minWidth: '250px',
      render: (job) => {
        const repos = repositoriesData?.data?.repositories || []
        const repo = repos.find((r: any) => r.path === job.repository)
        return (
          <RepositoryCell
            repositoryName={repo?.name || job.repository}
            repositoryPath={job.repository}
          />
        )
      },
    },
    {
      id: 'status',
      label: 'Status',
      align: 'left',
      render: (job) => (
        <Tooltip
          title={job.triggered_by === 'schedule' ? `Triggered by: Schedule (ID: ${job.schedule_id})` : 'Triggered by: Manual'}
          placement="top"
          arrow
        >
          <span>
            <StatusBadge status={job.status} />
          </span>
        </Tooltip>
      ),
    },
    {
      id: 'started_at',
      label: 'Started',
      align: 'left',
      render: (job) => (
        <Typography variant="body2" color="text.secondary">
          {job.started_at ? formatDate(job.started_at) : 'N/A'}
        </Typography>
      ),
    },
    {
      id: 'duration',
      label: 'Duration',
      align: 'left',
      render: (job) => (
        <Typography variant="body2" color="text.secondary">
          {formatTimeRange(job.started_at, job.completed_at, job.status)}
        </Typography>
      ),
    },
  ]

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Dashboard
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Overview of your backup system status and performance
        </Typography>
      </Box>

      {/* Status Cards */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 3,
          mb: 4,
          '& > *': { mb: { xs: 2, sm: 0 } },
        }}
      >
        {/* Borg Status Card */}
        <Card>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="flex-start">
              <Box
                sx={{
                  backgroundColor: 'primary.light',
                  borderRadius: 2,
                  p: 1.5,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  alignSelf: 'center',
                }}
              >
                <Activity size={28} color="white" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary" noWrap>
                  Borg Status
                </Typography>
                <Box
                  sx={{
                    mt: 0.5,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: 0.75,
                    backgroundColor: 'success.main',
                    color: 'white',
                    px: 1.5,
                    py: 0.5,
                    borderRadius: 1,
                  }}
                >
                  <CheckCircle size={16} />
                  <Typography variant="h6" fontWeight={600} component="span">
                    Running
                  </Typography>
                </Box>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* CPU Usage Card */}
        {metrics && (
          <Card>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="flex-start">
                <Box
                  sx={{
                    backgroundColor: 'info.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    alignSelf: 'center',
                  }}
                >
                  <Cpu size={28} color="white" />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    CPU Usage
                  </Typography>
                  <Typography variant="h6" fontWeight={600} sx={{ mt: 0.5 }}>
                    {metrics.cpu_usage.toFixed(1)}%
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(metrics.cpu_usage, 100)}
                    sx={{ mt: 1, height: 6, borderRadius: 1 }}
                    color={
                      metrics.cpu_usage > 80 ? 'error' : metrics.cpu_usage > 60 ? 'warning' : 'info'
                    }
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        )}

        {/* Memory Card */}
        {metrics && (
          <Card>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="flex-start">
                <Box
                  sx={{
                    backgroundColor: 'success.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    alignSelf: 'center',
                  }}
                >
                  <MemoryStick size={28} color="white" />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    Memory
                  </Typography>
                  <Typography variant="h6" fontWeight={600} sx={{ mt: 0.5, fontSize: '1rem' }}>
                    {formatBytes(metrics.memory_total - metrics.memory_available)} GB /{' '}
                    {formatBytes(metrics.memory_total)} GB
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(metrics.memory_usage, 100)}
                    sx={{ mt: 1, height: 6, borderRadius: 1 }}
                    color={
                      metrics.memory_usage > 80
                        ? 'error'
                        : metrics.memory_usage > 60
                          ? 'warning'
                          : 'success'
                    }
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        )}

        {/* Disk Space Card */}
        {metrics && (
          <Card>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="flex-start">
                <Box
                  sx={{
                    backgroundColor: 'warning.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    alignSelf: 'center',
                  }}
                >
                  <HardDrive size={28} color="white" />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    Disk Space
                  </Typography>
                  <Typography variant="h6" fontWeight={600} sx={{ mt: 0.5, fontSize: '1rem' }}>
                    {formatBytes(metrics.disk_total - metrics.disk_free)} GB /{' '}
                    {formatBytes(metrics.disk_total)} GB
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(metrics.disk_usage, 100)}
                    sx={{ mt: 1, height: 6, borderRadius: 1 }}
                    color={
                      metrics.disk_usage > 80
                        ? 'error'
                        : metrics.disk_usage > 60
                          ? 'warning'
                          : 'warning'
                    }
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        )}
      </Box>

      {/* Recent Backup Jobs */}
      {status?.data?.recent_jobs && (
        <Card>
          <CardContent>
            <Stack
              direction="row"
              spacing={1.5}
              alignItems="center"
              sx={{ mb: 1, color: 'text.secondary' }}
            >
              <Clock size={20} />
              <Typography variant="h6" fontWeight={600}>
                Recent Backup Jobs
              </Typography>
            </Stack>
            <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
              Latest backup operations across all repositories
            </Typography>

            <DataTable<BackupJob>
              data={status.data.recent_jobs}
              columns={jobColumns}
              actions={jobActions}
              getRowKey={(job) => String(job.id)}
              headerBgColor="background.default"
              enableHover={true}
              enablePointer={false}
              emptyState={{
                icon: (
                  <Box sx={{ color: 'text.disabled' }}>
                    <Clock size={48} />
                  </Box>
                ),
                title: 'No Backup Jobs Yet',
                description:
                  'Your recent backup jobs will appear here once you start running backups',
              }}
            />
          </CardContent>
        </Card>
      )}

      {/* Logs Dialog */}
      <Dialog open={Boolean(selectedJob)} onClose={handleCloseLogs} maxWidth="lg" fullWidth>
        <DialogTitle>
          {selectedJob && (
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <Typography variant="h6">
                Backup Logs - Job #{selectedJob.id}
              </Typography>
              <StatusBadge status={selectedJob.status} />
            </Box>
          )}
        </DialogTitle>
        <DialogContent dividers>
          {selectedJob && (
            <TerminalLogViewer
              jobId={String(selectedJob.id)}
              status={selectedJob.status}
              jobType="backup"
              showHeader={false}
              onFetchLogs={async (offset) => {
                const response = await fetch(
                  `/api/activity/backup/${selectedJob.id}/logs?offset=${offset}&limit=500`,
                  {
                    headers: {
                      Authorization: `Bearer ${localStorage.getItem('token') || ''}`,
                    },
                  }
                )
                if (!response.ok) {
                  throw new Error('Failed to fetch logs')
                }
                return response.json()
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
