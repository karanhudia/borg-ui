import { useQuery } from '@tanstack/react-query'
import { dashboardAPI } from '../services/api'
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Stack,
  LinearProgress,
  Chip,
  Tooltip,
} from '@mui/material'
import {
  Activity,
  HardDrive,
  MemoryStick,
  Cpu,
  Clock,
  CheckCircle,
  RefreshCw,
  AlertCircle,
  XCircle,
} from 'lucide-react'
import { formatDate, formatTimeRange } from '../utils/dateUtils'
import DataTable, { Column } from '../components/DataTable'

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
}

interface DashboardStatus {
  system_metrics?: SystemMetrics
  recent_jobs?: BackupJob[]
}

export default function Dashboard() {
  // Poll data every 30 seconds for fresh data
  const { data: status, isLoading } = useQuery<{ data: DashboardStatus }>({
    queryKey: ['dashboard-status'],
    queryFn: dashboardAPI.getStatus,
    refetchInterval: 30000
  })

  if (isLoading) {
    return (
      <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '400px' }}>
        <CircularProgress size={60} />
      </Box>
    )
  }

  const metrics = status?.data?.system_metrics

  const formatBytes = (bytes: number): string => {
    return (bytes / 1024 / 1024 / 1024).toFixed(1)
  }

  const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'info' | 'default' => {
    switch (status.toLowerCase()) {
      case 'completed':
      case 'success':
        return 'success'
      case 'failed':
      case 'error':
        return 'error'
      case 'running':
      case 'in_progress':
        return 'info'
      case 'cancelled':
        return 'default'
      default:
        return 'warning'
    }
  }

  const getStatusIcon = (status: string) => {
    switch (status.toLowerCase()) {
      case 'running':
      case 'in_progress':
        return <RefreshCw size={18} className="animate-spin" />
      case 'completed':
      case 'success':
        return <CheckCircle size={18} />
      case 'failed':
      case 'error':
        return <AlertCircle size={18} />
      case 'cancelled':
        return <XCircle size={18} />
      default:
        return <Clock size={18} />
    }
  }

  const getRepositoryName = (path: string): string => {
    if (!path) return 'Unknown'
    const parts = path.split('/')
    return parts[parts.length - 1] || parts[parts.length - 2] || path
  }

  // Define columns for Recent Jobs table
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
      render: (job) => (
        <Tooltip title={job.repository} placement="top" arrow>
          <Stack direction="row" spacing={1} alignItems="center">
            <HardDrive size={16} color="rgba(0,0,0,0.4)" />
            <Box>
              <Typography variant="body2" fontWeight={500}>
                {getRepositoryName(job.repository)}
              </Typography>
              <Typography
                variant="caption"
                color="text.secondary"
                sx={{
                  fontFamily: 'monospace',
                  fontSize: '0.7rem',
                  maxWidth: 250,
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                  display: 'block'
                }}
              >
                {job.repository}
              </Typography>
            </Box>
          </Stack>
        </Tooltip>
      ),
    },
    {
      id: 'status',
      label: 'Status',
      align: 'left',
      render: (job) => (
        <Chip
          icon={getStatusIcon(job.status)}
          label={job.status.charAt(0).toUpperCase() + job.status.slice(1)}
          color={getStatusColor(job.status)}
          size="small"
          sx={{ fontWeight: 500 }}
        />
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
    {
      id: 'progress',
      label: 'Progress',
      align: 'left',
      render: (job) => (
        job.status === 'running' ? (
          <Stack direction="row" spacing={1} alignItems="center">
            <Box
              sx={{
                width: 6,
                height: 6,
                borderRadius: '50%',
                bgcolor: 'info.main',
                animation: 'pulse 2s ease-in-out infinite',
                '@keyframes pulse': {
                  '0%, 100%': { opacity: 1 },
                  '50%': { opacity: 0.5 },
                },
              }}
            />
            <Typography variant="body2" color="info.main">
              {(job.progress || 0) === 0
                ? 'Initializing...'
                : (job.progress || 0) >= 100
                ? 'Finalizing...'
                : 'Processing...'}
            </Typography>
          </Stack>
        ) : (
          <Typography variant="body2" color="text.secondary">
            {job.status === 'completed' ? 'Completed' : job.status === 'failed' ? 'Failed' : 'Cancelled'}
          </Typography>
        )
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
      <Box sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' }, gap: 3, mb: 4, '& > *': { mb: { xs: 2, sm: 0 } } }}>
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
                    color={metrics.cpu_usage > 80 ? 'error' : metrics.cpu_usage > 60 ? 'warning' : 'info'}
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
                    {formatBytes(metrics.memory_total - metrics.memory_available)} GB / {formatBytes(metrics.memory_total)} GB
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(metrics.memory_usage, 100)}
                    sx={{ mt: 1, height: 6, borderRadius: 1 }}
                    color={metrics.memory_usage > 80 ? 'error' : metrics.memory_usage > 60 ? 'warning' : 'success'}
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
                    {formatBytes(metrics.disk_total - metrics.disk_free)} GB / {formatBytes(metrics.disk_total)} GB
                  </Typography>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(metrics.disk_usage, 100)}
                    sx={{ mt: 1, height: 6, borderRadius: 1 }}
                    color={metrics.disk_usage > 80 ? 'error' : metrics.disk_usage > 60 ? 'warning' : 'warning'}
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
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 1 }}>
              <Clock size={20} color="rgba(0,0,0,0.6)" />
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
              getRowKey={(job) => String(job.id)}
              headerBgColor="grey.50"
              enableHover={true}
              enablePointer={false}
              emptyState={{
                icon: <Clock size={48} color="rgba(0,0,0,0.3)" />,
                title: 'No Backup Jobs Yet',
                description: 'Your recent backup jobs will appear here once you start running backups',
              }}
            />
          </CardContent>
        </Card>
      )}
    </Box>
  )
}
