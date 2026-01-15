import { useQuery } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import {
  Box,
  Card,
  CardContent,
  Typography,
  CircularProgress,
  Stack,
  LinearProgress,
  Alert,
  Chip,
  Button,
  IconButton,
  Divider,
} from '@mui/material'
import {
  Activity,
  HardDrive,
  Calendar,
  CheckCircle,
  AlertTriangle,
  XCircle,
  Clock,
  Server,
  TrendingUp,
  Wrench,
  Database,
  Cpu,
  MemoryStick,
  ArrowRight,
} from 'lucide-react'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip as RechartsTooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import { formatDistanceToNow } from 'date-fns'

interface DashboardOverview {
  summary: {
    total_repositories: number
    local_repositories: number
    ssh_repositories: number
    active_schedules: number
    total_schedules: number
    ssh_connections_active: number
    ssh_connections_total: number
    success_rate_30d: number
    successful_jobs_30d: number
    failed_jobs_30d: number
    total_jobs_30d: number
  }
  storage: {
    total_size: string
    total_size_bytes: number
    total_archives: number
    average_dedup_ratio: number | null
  }
  repository_health: Array<{
    id: number
    name: string
    path: string
    type: string
    last_backup: string | null
    last_check: string | null
    last_compact: string | null
    archive_count: number
    total_size: string
    size_bytes: number
    health_status: 'healthy' | 'warning' | 'critical'
    health_color: string
    warnings: string[]
    dedup_ratio: number | null
    has_schedule: boolean
    schedule_enabled: boolean
  }>
  backup_trends: Array<{
    week: string
    success_rate: number
    successful: number
    failed: number
    total: number
  }>
  upcoming_tasks: Array<any>
  maintenance_alerts: Array<{
    type: string
    severity: string
    repository: string
    repository_id: number
    message: string
    action: string
  }>
  activity_feed: Array<{
    id: number
    type: string
    status: string
    repository: string
    timestamp: string
    message: string
    error: string | null
  }>
  system_metrics: {
    cpu_usage: number
    memory_usage: number
    memory_total: number
    memory_available: number
    disk_usage: number
    disk_total: number
    disk_free: number
  }
  last_updated: string
}

export default function DashboardNew() {
  const navigate = useNavigate()

  const {
    data: overview,
    isLoading,
    error,
  } = useQuery<DashboardOverview>({
    queryKey: ['dashboard-overview'],
    queryFn: async () => {
      const response = await fetch('/api/dashboard/overview', {
        headers: {
          Authorization: `Bearer ${localStorage.getItem('access_token')}`,
        },
      })
      if (!response.ok) throw new Error('Failed to fetch dashboard data')
      return response.json()
    },
    refetchInterval: 30000, // Refresh every 30 seconds
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

  if (error || !overview) {
    return (
      <Alert severity="error">Failed to load dashboard data. Please try refreshing the page.</Alert>
    )
  }

  const formatBytes = (bytes: number): string => {
    return (bytes / 1024 / 1024 / 1024).toFixed(1)
  }

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'healthy':
        return <CheckCircle size={16} color="#4caf50" />
      case 'warning':
        return <AlertTriangle size={16} color="#ff9800" />
      case 'critical':
        return <XCircle size={16} color="#f44336" />
      default:
        return <CheckCircle size={16} color="#9e9e9e" />
    }
  }

  const getActivityIcon = (type: string, status: string) => {
    if (status === 'failed') return <XCircle size={18} color="#f44336" />
    if (status === 'completed') {
      switch (type) {
        case 'backup':
          return <CheckCircle size={18} color="#4caf50" />
        case 'check':
          return <CheckCircle size={18} color="#2196f3" />
        case 'compact':
          return <Database size={18} color="#9c27b0" />
        default:
          return <CheckCircle size={18} color="#4caf50" />
      }
    }
    return <Clock size={18} color="#ff9800" />
  }

  return (
    <Box>
      {/* Header */}
      <Box sx={{ mb: 4 }}>
        <Typography variant="h4" fontWeight={600} gutterBottom>
          Command Center
        </Typography>
        <Typography variant="body2" color="text.secondary">
          Comprehensive overview of your backup infrastructure
        </Typography>
      </Box>

      {/* Summary Cards */}
      <Box
        sx={{
          display: 'grid',
          gridTemplateColumns: { xs: '1fr', sm: 'repeat(2, 1fr)', lg: 'repeat(4, 1fr)' },
          gap: 2,
          mb: 3,
        }}
      >
        {/* Repositories Card */}
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
                }}
              >
                <Database size={24} color="white" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary" noWrap>
                  Repositories
                </Typography>
                <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                  {overview.summary.total_repositories}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {overview.summary.ssh_repositories} SSH remote
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Active Schedules Card */}
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
                }}
              >
                <Calendar size={24} color="white" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary" noWrap>
                  Active Schedules
                </Typography>
                <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                  {overview.summary.active_schedules}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  of {overview.summary.total_schedules} total
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Success Rate Card */}
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
                }}
              >
                <TrendingUp size={24} color="white" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary" noWrap>
                  Success Rate (30d)
                </Typography>
                <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                  {overview.summary.success_rate_30d.toFixed(1)}%
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {overview.summary.successful_jobs_30d}/{overview.summary.total_jobs_30d} backups
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>

        {/* Failed Jobs Card */}
        <Card>
          <CardContent>
            <Stack direction="row" spacing={2} alignItems="flex-start">
              <Box
                sx={{
                  backgroundColor:
                    overview.summary.failed_jobs_30d > 0 ? 'error.light' : 'grey.400',
                  borderRadius: 2,
                  p: 1.5,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <AlertTriangle size={24} color="white" />
              </Box>
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body2" color="text.secondary" noWrap>
                  Failed (Last 7d)
                </Typography>
                <Typography variant="h5" fontWeight={600} sx={{ mt: 0.5 }}>
                  {overview.summary.failed_jobs_30d}
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  Requires attention
                </Typography>
              </Box>
            </Stack>
          </CardContent>
        </Card>
      </Box>

      {/* Repository Health */}
      <Card sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
            <Server size={20} />
            <Typography variant="h6" fontWeight={600}>
              Repository Health
            </Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
            Current status and maintenance overview for all repositories
          </Typography>

          <Stack spacing={2}>
            {overview.repository_health.slice(0, 5).map((repo) => (
              <Card
                key={repo.id}
                variant="outlined"
                sx={{
                  borderLeft: 4,
                  borderLeftColor:
                    repo.health_status === 'critical'
                      ? 'error.main'
                      : repo.health_status === 'warning'
                        ? 'warning.main'
                        : 'success.main',
                  '&:hover': { bgcolor: 'action.hover', cursor: 'pointer' },
                }}
                onClick={() => navigate(`/repositories`)}
              >
                <CardContent>
                  <Stack direction="row" spacing={2} alignItems="flex-start">
                    <Box sx={{ flex: 1 }}>
                      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                        <Typography variant="subtitle1" fontWeight={600}>
                          {repo.name}
                        </Typography>
                        {getStatusIcon(repo.health_status)}
                        <Chip
                          label={repo.type.toUpperCase()}
                          size="small"
                          sx={{ height: 20, fontSize: '0.7rem' }}
                        />
                      </Stack>

                      <Stack direction="row" spacing={3} sx={{ mb: 1 }}>
                        <Typography variant="body2" color="text.secondary">
                          Last backup:{' '}
                          {repo.last_backup
                            ? formatDistanceToNow(new Date(repo.last_backup), { addSuffix: true })
                            : 'Never'}
                        </Typography>
                        {repo.has_schedule && (
                          <Typography variant="body2" color="text.secondary">
                            Next: {repo.schedule_enabled ? 'Scheduled' : 'Paused'}
                          </Typography>
                        )}
                      </Stack>

                      <Stack direction="row" spacing={3}>
                        <Typography variant="body2" color="text.secondary">
                          {repo.archive_count} archives
                        </Typography>
                        {repo.dedup_ratio !== null && (
                          <Typography variant="body2" color="text.secondary">
                            Dedup: {repo.dedup_ratio}%
                          </Typography>
                        )}
                      </Stack>

                      {repo.warnings.length > 0 && (
                        <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: 'wrap' }}>
                          {repo.warnings.map((warning, idx) => (
                            <Chip
                              key={idx}
                              label={warning}
                              size="small"
                              color={repo.health_status === 'critical' ? 'error' : 'warning'}
                              sx={{ height: 22 }}
                            />
                          ))}
                        </Stack>
                      )}
                    </Box>

                    <Box sx={{ textAlign: 'right' }}>
                      <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                        Storage
                      </Typography>
                      <Typography variant="h6" fontWeight={600}>
                        {repo.total_size}
                      </Typography>
                      {repo.size_bytes > 0 && (
                        <LinearProgress
                          variant="determinate"
                          value={Math.min(
                            (repo.size_bytes / overview.storage.total_size_bytes) * 100,
                            100
                          )}
                          sx={{ mt: 1, height: 6, borderRadius: 1, width: 100 }}
                        />
                      )}
                    </Box>
                  </Stack>
                </CardContent>
              </Card>
            ))}

            {overview.repository_health.length > 5 && (
              <Button
                variant="text"
                endIcon={<ArrowRight size={18} />}
                onClick={() => navigate('/repositories')}
                sx={{ alignSelf: 'flex-start' }}
              >
                View All {overview.repository_health.length} Repositories
              </Button>
            )}

            {overview.repository_health.length === 0 && (
              <Alert severity="info">
                No repositories configured yet. Create your first repository to start backing up!
              </Alert>
            )}
          </Stack>
        </CardContent>
      </Card>

      {/* Backup Trends & Upcoming Tasks */}
      <Box
        sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '2fr 1fr' }, gap: 3, mb: 3 }}
      >
        {/* Backup Success Rate Chart */}
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
              <TrendingUp size={20} />
              <Typography variant="h6" fontWeight={600}>
                Backup Success Rate (Last 30 Days)
              </Typography>
            </Stack>

            <Box sx={{ mb: 2 }}>
              <Typography variant="h4" fontWeight={600} display="inline">
                {overview.summary.success_rate_30d.toFixed(1)}%
              </Typography>
              <Typography variant="body2" color="text.secondary" display="inline" sx={{ ml: 2 }}>
                {overview.summary.successful_jobs_30d} successful,{' '}
                {overview.summary.failed_jobs_30d} failed
              </Typography>
            </Box>

            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={overview.backup_trends}>
                <CartesianGrid strokeDasharray="3 3" />
                <XAxis dataKey="week" />
                <YAxis />
                <RechartsTooltip
                  content={({ active, payload }) => {
                    if (active && payload && payload.length) {
                      const data = payload[0].payload
                      return (
                        <Card sx={{ p: 1.5 }}>
                          <Typography variant="body2" fontWeight={600}>
                            {data.week}
                          </Typography>
                          <Typography variant="body2" color="success.main">
                            Success: {data.successful} ({data.success_rate}%)
                          </Typography>
                          <Typography variant="body2" color="error.main">
                            Failed: {data.failed}
                          </Typography>
                          <Typography variant="body2" color="text.secondary">
                            Total: {data.total}
                          </Typography>
                        </Card>
                      )
                    }
                    return null
                  }}
                />
                <Bar dataKey="success_rate" radius={[8, 8, 0, 0]}>
                  {overview.backup_trends.map((entry, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={
                        entry.success_rate >= 95
                          ? '#4caf50'
                          : entry.success_rate >= 80
                            ? '#ff9800'
                            : '#f44336'
                      }
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>

        {/* Upcoming Tasks & Maintenance */}
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
              <Clock size={20} />
              <Typography variant="h6" fontWeight={600}>
                Upcoming & Maintenance
              </Typography>
            </Stack>

            {/* Upcoming Schedules */}
            {overview.upcoming_tasks.length > 0 && (
              <Box sx={{ mb: 3 }}>
                <Typography variant="subtitle2" fontWeight={600} sx={{ mb: 1 }}>
                  Next 24 hours
                </Typography>
                <Stack spacing={1}>
                  {overview.upcoming_tasks.slice(0, 3).map((task) => (
                    <Box key={task.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      <Calendar size={14} />
                      <Typography variant="body2">{task.name}</Typography>
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {/* Maintenance Alerts */}
            <Box>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1 }}>
                <Wrench size={16} />
                <Typography variant="subtitle2" fontWeight={600}>
                  Maintenance Needed
                </Typography>
              </Stack>

              {overview.maintenance_alerts.length === 0 ? (
                <Alert severity="success" sx={{ mt: 1 }}>
                  All systems healthy!
                </Alert>
              ) : (
                <Stack spacing={1}>
                  {overview.maintenance_alerts.slice(0, 5).map((alert, idx) => (
                    <Alert
                      key={idx}
                      severity={alert.severity as any}
                      sx={{ py: 0.5, '& .MuiAlert-message': { py: 0.5 } }}
                      action={
                        <IconButton size="small" onClick={() => navigate('/repositories')}>
                          <ArrowRight size={16} />
                        </IconButton>
                      }
                    >
                      <Typography variant="caption" fontWeight={600}>
                        {alert.repository}
                      </Typography>
                      <Typography variant="caption" display="block">
                        {alert.message}
                      </Typography>
                    </Alert>
                  ))}

                  {overview.maintenance_alerts.length > 5 && (
                    <Typography
                      variant="caption"
                      color="text.secondary"
                      sx={{ textAlign: 'center' }}
                    >
                      +{overview.maintenance_alerts.length - 5} more alerts
                    </Typography>
                  )}
                </Stack>
              )}
            </Box>
          </CardContent>
        </Card>
      </Box>

      {/* Activity Feed & Storage Overview */}
      <Box
        sx={{ display: 'grid', gridTemplateColumns: { xs: '1fr', lg: '2fr 1fr' }, gap: 3, mb: 3 }}
      >
        {/* Activity Feed */}
        <Card>
          <CardContent>
            <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
              <Activity size={20} />
              <Typography variant="h6" fontWeight={600}>
                Recent Activity
              </Typography>
            </Stack>

            <Stack spacing={1.5} divider={<Divider />}>
              {overview.activity_feed.map((activity) => (
                <Box key={`${activity.type}-${activity.id}`}>
                  <Stack direction="row" spacing={1.5} alignItems="flex-start">
                    <Box sx={{ mt: 0.5 }}>{getActivityIcon(activity.type, activity.status)}</Box>
                    <Box sx={{ flex: 1 }}>
                      <Typography variant="body2" fontWeight={600}>
                        {activity.message}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {activity.repository} •{' '}
                        {formatDistanceToNow(new Date(activity.timestamp), { addSuffix: true })}
                      </Typography>
                      {activity.error && (
                        <Typography
                          variant="caption"
                          color="error.main"
                          display="block"
                          sx={{ mt: 0.5 }}
                        >
                          {activity.error}
                        </Typography>
                      )}
                    </Box>
                  </Stack>
                </Box>
              ))}

              {overview.activity_feed.length === 0 && (
                <Typography
                  variant="body2"
                  color="text.secondary"
                  textAlign="center"
                  sx={{ py: 2 }}
                >
                  No recent activity
                </Typography>
              )}
            </Stack>

            <Button
              variant="text"
              endIcon={<ArrowRight size={18} />}
              onClick={() => navigate('/activity')}
              sx={{ mt: 2 }}
            >
              View All Activity
            </Button>
          </CardContent>
        </Card>

        {/* Storage & System Metrics */}
        <Stack spacing={3}>
          {/* Storage Overview */}
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <HardDrive size={20} />
                <Typography variant="h6" fontWeight={600}>
                  Storage Overview
                </Typography>
              </Stack>

              <Typography variant="h4" fontWeight={600}>
                {overview.storage.total_size}
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
                Total backup data
              </Typography>

              <Stack spacing={1}>
                <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                  <Typography variant="body2" color="text.secondary">
                    Total Archives
                  </Typography>
                  <Typography variant="body2" fontWeight={600}>
                    {overview.storage.total_archives}
                  </Typography>
                </Box>
                {overview.storage.average_dedup_ratio !== null && (
                  <Box sx={{ display: 'flex', justifyContent: 'space-between' }}>
                    <Typography variant="body2" color="text.secondary">
                      Dedup Ratio
                    </Typography>
                    <Typography variant="body2" fontWeight={600}>
                      {overview.storage.average_dedup_ratio}%
                    </Typography>
                  </Box>
                )}
              </Stack>
            </CardContent>
          </Card>

          {/* System Resources */}
          <Card>
            <CardContent>
              <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
                <Server size={20} />
                <Typography variant="h6" fontWeight={600}>
                  System Resources
                </Typography>
              </Stack>

              <Stack spacing={2}>
                <Box>
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <Cpu size={14} />
                      <Typography variant="body2">CPU</Typography>
                    </Stack>
                    <Typography variant="body2" fontWeight={600}>
                      {overview.system_metrics.cpu_usage.toFixed(1)}%
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(overview.system_metrics.cpu_usage, 100)}
                    sx={{ height: 6, borderRadius: 1 }}
                    color={
                      overview.system_metrics.cpu_usage > 80
                        ? 'error'
                        : overview.system_metrics.cpu_usage > 60
                          ? 'warning'
                          : 'info'
                    }
                  />
                </Box>

                <Box>
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <MemoryStick size={14} />
                      <Typography variant="body2">Memory</Typography>
                    </Stack>
                    <Typography variant="body2" fontWeight={600}>
                      {formatBytes(
                        overview.system_metrics.memory_total -
                          overview.system_metrics.memory_available
                      )}{' '}
                      / {formatBytes(overview.system_metrics.memory_total)} GB
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(overview.system_metrics.memory_usage, 100)}
                    sx={{ height: 6, borderRadius: 1 }}
                    color={
                      overview.system_metrics.memory_usage > 80
                        ? 'error'
                        : overview.system_metrics.memory_usage > 60
                          ? 'warning'
                          : 'success'
                    }
                  />
                </Box>

                <Box>
                  <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                    <Stack direction="row" spacing={0.5} alignItems="center">
                      <HardDrive size={14} />
                      <Typography variant="body2">Disk</Typography>
                    </Stack>
                    <Typography variant="body2" fontWeight={600}>
                      {formatBytes(
                        overview.system_metrics.disk_total - overview.system_metrics.disk_free
                      )}{' '}
                      / {formatBytes(overview.system_metrics.disk_total)} GB
                    </Typography>
                  </Stack>
                  <LinearProgress
                    variant="determinate"
                    value={Math.min(overview.system_metrics.disk_usage, 100)}
                    sx={{ height: 6, borderRadius: 1 }}
                    color={
                      overview.system_metrics.disk_usage > 80
                        ? 'error'
                        : overview.system_metrics.disk_usage > 60
                          ? 'warning'
                          : 'warning'
                    }
                  />
                </Box>
              </Stack>
            </CardContent>
          </Card>
        </Stack>
      </Box>
    </Box>
  )
}
