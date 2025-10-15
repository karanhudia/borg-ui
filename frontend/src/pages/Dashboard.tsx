import { useQuery } from 'react-query'
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
} from '@mui/material'
import {
  Activity,
  HardDrive,
  MemoryStick,
  Cpu,
  Clock,
  CheckCircle,
} from 'lucide-react'

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
}

interface DashboardStatus {
  system_metrics?: SystemMetrics
  recent_jobs?: BackupJob[]
}

export default function Dashboard() {
  // Poll data every 30 seconds for fresh data
  const { data: status, isLoading } = useQuery<{ data: DashboardStatus }>(
    'dashboard-status',
    dashboardAPI.getStatus,
    { refetchInterval: 30000 }
  )

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

  const getStatusColor = (status: string): 'success' | 'error' | 'warning' | 'info' => {
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
      default:
        return 'warning'
    }
  }

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
      <Stack direction={{ xs: 'column', sm: 'row' }} spacing={3} sx={{ mb: 4 }} flexWrap="wrap">
        {/* Borgmatic Status Card */}
        <Box sx={{ flex: { xs: '1 1 100%', sm: '1 1 calc(50% - 12px)', lg: '1 1 calc(25% - 12px)' }, minWidth: 240 }}>
          <Card>
            <CardContent>
              <Stack direction="row" spacing={2} alignItems="center">
                <Box
                  sx={{
                    backgroundColor: 'primary.light',
                    borderRadius: 2,
                    p: 1.5,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                  }}
                >
                  <Activity size={28} color="primary" />
                </Box>
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" color="text.secondary" noWrap>
                    Borgmatic Status
                  </Typography>
                  <Typography variant="h6" fontWeight={600} sx={{ mt: 0.5 }}>
                    Running
                  </Typography>
                  <Chip
                    label="Active"
                    size="small"
                    color="success"
                    icon={<CheckCircle size={14} />}
                    sx={{ mt: 1, height: 24 }}
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Box>

        {/* CPU Usage Card */}
        {metrics && (
          <Box sx={{ flex: { xs: '1 1 100%', sm: '1 1 calc(50% - 12px)', lg: '1 1 calc(25% - 12px)' }, minWidth: 240 }}>
            <Card>
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Box
                    sx={{
                      backgroundColor: 'info.light',
                      borderRadius: 2,
                      p: 1.5,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Cpu size={28} color="#0288d1" />
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
          </Box>
        )}

        {/* Memory Card */}
        {metrics && (
          <Box sx={{ flex: { xs: '1 1 100%', sm: '1 1 calc(50% - 12px)', lg: '1 1 calc(25% - 12px)' }, minWidth: 240 }}>
            <Card>
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Box
                    sx={{
                      backgroundColor: 'success.light',
                      borderRadius: 2,
                      p: 1.5,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <MemoryStick size={28} color="#2e7d32" />
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
          </Box>
        )}

        {/* Disk Space Card */}
        {metrics && (
          <Box sx={{ flex: { xs: '1 1 100%', sm: '1 1 calc(50% - 12px)', lg: '1 1 calc(25% - 12px)' }, minWidth: 240 }}>
            <Card>
              <CardContent>
                <Stack direction="row" spacing={2} alignItems="center">
                  <Box
                    sx={{
                      backgroundColor: 'warning.light',
                      borderRadius: 2,
                      p: 1.5,
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <HardDrive size={28} color="#ed6c02" />
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
          </Box>
        )}
      </Stack>

      {/* Recent Backup Jobs */}
      {status?.data?.recent_jobs && status.data.recent_jobs.length > 0 && (
        <Card>
          <CardContent>
            <Typography variant="h6" fontWeight={600} gutterBottom>
              Recent Backup Jobs
            </Typography>
            <Stack spacing={2} sx={{ mt: 3 }}>
              {status.data.recent_jobs.map((job: BackupJob) => (
                <Box
                  key={job.id}
                  sx={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    py: 2,
                    borderBottom: 1,
                    borderColor: 'divider',
                    '&:last-child': { borderBottom: 0 },
                  }}
                >
                  <Stack direction="row" spacing={2} alignItems="center" sx={{ flex: 1 }}>
                    <Box
                      sx={{
                        backgroundColor: 'grey.100',
                        borderRadius: 1.5,
                        p: 1,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                      }}
                    >
                      <Clock size={20} />
                    </Box>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body1" fontWeight={500} noWrap>
                        {job.repository}
                      </Typography>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }}>
                        <Chip
                          label={job.status}
                          size="small"
                          color={getStatusColor(job.status)}
                          sx={{ height: 20, fontSize: '0.75rem' }}
                        />
                        {job.progress !== undefined && (
                          <Typography variant="caption" color="text.secondary">
                            {job.progress}%
                          </Typography>
                        )}
                      </Stack>
                    </Box>
                  </Stack>
                  <Typography variant="caption" color="text.secondary" sx={{ ml: 2, whiteSpace: 'nowrap' }}>
                    {job.started_at ? new Date(job.started_at).toLocaleString() : 'N/A'}
                  </Typography>
                </Box>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Empty State for Recent Jobs */}
      {status?.data?.recent_jobs && status.data.recent_jobs.length === 0 && (
        <Card>
          <CardContent sx={{ textAlign: 'center', py: 6 }}>
            <Clock size={48} color="rgba(0,0,0,0.3)" style={{ marginBottom: 16 }} />
            <Typography variant="h6" gutterBottom>
              No Recent Backup Jobs
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Your recent backup jobs will appear here once you start running backups
            </Typography>
          </CardContent>
        </Card>
      )}
    </Box>
  )
}
