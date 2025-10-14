import { useQuery } from 'react-query';
import { dashboardAPI } from '../services/api';
import { Activity, HardDrive, MemoryStick, Cpu, Clock, AlertTriangle } from 'lucide-react';

export default function Dashboard() {
  // Poll data every 30 seconds for fresh data
  const { data: status, isLoading: statusLoading } = useQuery(
    'dashboard-status',
    dashboardAPI.getStatus,
    { refetchInterval: 30000 }
  );
  const { data: metrics, isLoading: metricsLoading } = useQuery(
    'dashboard-metrics',
    dashboardAPI.getMetrics,
    { refetchInterval: 30000 }
  );
  const { data: health, isLoading: healthLoading } = useQuery(
    'dashboard-health',
    dashboardAPI.getHealth,
    { refetchInterval: 30000 }
  );

  const isLoading = statusLoading || metricsLoading || healthLoading;

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="animate-spin rounded-full h-32 w-32 border-b-2 border-primary-600"></div>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
          <p className="mt-1 text-sm text-gray-500">
            Overview of your backup system status and performance
          </p>
        </div>
      </div>

      {/* Status Cards */}
      <div className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <Activity className="h-8 w-8 text-primary-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">System Status</dt>
                <dd className="text-lg font-medium text-gray-900">
                  {status?.status || 'Unknown'}
                </dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <Cpu className="h-8 w-8 text-blue-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">CPU Usage</dt>
                <dd className="text-lg font-medium text-gray-900">
                  {metrics?.data?.cpu_usage ? `${metrics.data.cpu_usage.toFixed(1)}%` : 'N/A'}
                </dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <MemoryStick className="h-8 w-8 text-green-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Memory Usage</dt>
                <dd className="text-lg font-medium text-gray-900">
                  {metrics?.data?.memory_usage ? `${metrics.data.memory_usage.toFixed(1)}%` : 'N/A'}
                </dd>
              </dl>
            </div>
          </div>
        </div>

        <div className="card">
          <div className="flex items-center">
            <div className="flex-shrink-0">
              <HardDrive className="h-8 w-8 text-orange-600" />
            </div>
            <div className="ml-5 w-0 flex-1">
              <dl>
                <dt className="text-sm font-medium text-gray-500 truncate">Disk Usage</dt>
                <dd className="text-lg font-medium text-gray-900">
                  {metrics?.data?.disk_usage ? `${metrics.data.disk_usage.toFixed(1)}%` : 'N/A'}
                </dd>
              </dl>
            </div>
          </div>
        </div>
      </div>


      {/* Health Status */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">System Health</h3>
        <div className="space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center">
              <div className={`w-3 h-3 rounded-full mr-3 ${
                health?.data?.status === 'healthy' ? 'bg-success-500' : 'bg-danger-500'
              }`} />
              <span className="text-sm font-medium text-gray-900">Overall Status</span>
            </div>
            <span className={`text-sm font-medium ${
              health?.data?.status === 'healthy' ? 'text-success-600' : 'text-danger-600'
            }`}>
                              {health?.data?.status || 'Unknown'}
            </span>
          </div>
          
          {health?.data?.cpu_usage !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">CPU Usage</span>
                              <span className="text-sm font-medium text-gray-900">{health.data.cpu_usage.toFixed(1)}%</span>
            </div>
          )}
          
          {health?.data?.memory_usage !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">Memory Usage</span>
                              <span className="text-sm font-medium text-gray-900">{health.data.memory_usage.toFixed(1)}%</span>
            </div>
          )}
          
          {health?.data?.disk_usage !== undefined && (
            <div className="flex items-center justify-between">
              <span className="text-sm text-gray-500">Disk Usage</span>
                              <span className="text-sm font-medium text-gray-900">{health.data.disk_usage.toFixed(1)}%</span>
            </div>
          )}
        </div>
      </div>

      {/* Recent Activity */}
      <div className="card">
        <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Activity</h3>
        <div className="space-y-3">
          {status?.data?.recent_jobs?.length > 0 ? (
            status?.data?.recent_jobs?.map((job: any, index: number) => (
              <div key={index} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-b-0">
                <div className="flex items-center">
                  <Clock className="h-4 w-4 text-gray-400 mr-3" />
                  <div>
                    <p className="text-sm font-medium text-gray-900">{job.name}</p>
                    <p className="text-xs text-gray-500">{job.status}</p>
                  </div>
                </div>
                <span className="text-xs text-gray-500">{job.timestamp}</span>
              </div>
            ))
          ) : (
            <div className="text-center py-8">
              <AlertTriangle className="h-8 w-8 text-gray-400 mx-auto mb-2" />
              <p className="text-sm text-gray-500">No recent activity</p>
            </div>
          )}
        </div>
      </div>
    </div>
  )
} 