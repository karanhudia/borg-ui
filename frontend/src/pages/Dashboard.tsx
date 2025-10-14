import { useQuery } from 'react-query';
import { dashboardAPI } from '../services/api';
import { Activity, HardDrive, MemoryStick, Cpu, Clock } from 'lucide-react';

export default function Dashboard() {
  // Poll data every 30 seconds for fresh data
  const { data: status, isLoading } = useQuery(
    'dashboard-status',
    dashboardAPI.getStatus,
    { refetchInterval: 30000 }
  );

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
                <dt className="text-sm font-medium text-gray-500 truncate">Borgmatic Status</dt>
                <dd className="text-lg font-medium text-gray-900">
                  Running
                </dd>
              </dl>
            </div>
          </div>
        </div>

        {status?.data?.system_metrics && (
          <>
            <div className="card">
              <div className="flex items-center">
                <div className="flex-shrink-0">
                  <Cpu className="h-8 w-8 text-blue-600" />
                </div>
                <div className="ml-5 w-0 flex-1">
                  <dl>
                    <dt className="text-sm font-medium text-gray-500 truncate">CPU Usage</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {status.data.system_metrics.cpu_usage.toFixed(1)}%
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
                    <dt className="text-sm font-medium text-gray-500 truncate">Memory</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {(status.data.system_metrics.memory_total / 1024 / 1024 / 1024 - status.data.system_metrics.memory_available / 1024 / 1024 / 1024).toFixed(1)} GB / {(status.data.system_metrics.memory_total / 1024 / 1024 / 1024).toFixed(1)} GB
                    </dd>
                    <dd className="text-xs text-gray-500 mt-1">
                      {status.data.system_metrics.memory_usage.toFixed(1)}% used
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
                    <dt className="text-sm font-medium text-gray-500 truncate">Disk Space</dt>
                    <dd className="text-lg font-medium text-gray-900">
                      {((status.data.system_metrics.disk_total - status.data.system_metrics.disk_free) / 1024 / 1024 / 1024).toFixed(1)} GB / {(status.data.system_metrics.disk_total / 1024 / 1024 / 1024).toFixed(1)} GB
                    </dd>
                    <dd className="text-xs text-gray-500 mt-1">
                      {status.data.system_metrics.disk_usage.toFixed(1)}% used
                    </dd>
                  </dl>
                </div>
              </div>
            </div>
          </>
        )}
      </div>


      {/* Recent Backup Jobs */}
      {status?.data?.recent_jobs && status.data.recent_jobs.length > 0 && (
        <div className="card">
          <h3 className="text-lg font-medium text-gray-900 mb-4">Recent Backup Jobs</h3>
          <div className="space-y-3">
            {status.data.recent_jobs.map((job: any) => (
              <div key={job.id} className="flex items-center justify-between py-2 border-b border-gray-100 last:border-b-0">
                <div className="flex items-center">
                  <Clock className="h-4 w-4 text-gray-400 mr-3" />
                  <div>
                    <p className="text-sm font-medium text-gray-900">{job.repository}</p>
                    <p className="text-xs text-gray-500">
                      Status: {job.status}
                      {job.progress && ` (${job.progress}%)`}
                    </p>
                  </div>
                </div>
                <span className="text-xs text-gray-500">
                  {job.started_at ? new Date(job.started_at).toLocaleString() : 'N/A'}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
} 