import React, { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from 'react-query';
import { Play, Square, Clock, CheckCircle, AlertCircle, RefreshCw, FileText, HardDrive } from 'lucide-react';
import { backupAPI, repositoriesAPI } from '../services/api';
import { toast } from 'react-hot-toast';
import { useBackupProgress } from '../hooks/useSSE';

interface BackupJob {
  id: string
  repository: string
  status: 'running' | 'completed' | 'failed' | 'cancelled'
  started_at: string
  completed_at?: string
  progress: number
  total_files?: number
  processed_files: number
  total_size?: string
  processed_size?: string
  error_message?: string
}

const Backup: React.FC = () => {
  const [selectedRepository, setSelectedRepository] = useState<string>('');
  const [showJobDetails, setShowJobDetails] = useState<string | null>(null);
  const queryClient = useQueryClient();
  
  // Real-time backup progress
  const { progress: realtimeProgress, isConnected } = useBackupProgress();

  // Get backup status and history
  const { data: backupStatus, isLoading: loadingStatus } = useQuery({
    queryKey: ['backup-status'],
    queryFn: backupAPI.getAllJobs,
    refetchInterval: realtimeProgress ? 0 : 5000 // Use real-time updates if available, otherwise poll
  });

  // Get repositories
  const { data: repositoriesData, isLoading: loadingRepositories } = useQuery({
    queryKey: ['repositories'],
    queryFn: repositoriesAPI.getRepositories,
  });

  // Start backup mutation
  const startBackupMutation = useMutation({
    mutationFn: (repository: string) => backupAPI.startBackup(repository),
    onSuccess: () => {
      toast.success('Backup started successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to start backup: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Cancel backup mutation
  const cancelBackupMutation = useMutation({
    mutationFn: (jobId: string) => backupAPI.cancelJob(jobId),
    onSuccess: () => {
      toast.success('Backup cancelled successfully!')
      queryClient.invalidateQueries({ queryKey: ['backup-status'] })
    },
    onError: (error: any) => {
      toast.error(`Failed to cancel backup: ${error.response?.data?.detail || error.message}`)
    }
  })

  // Handle start backup
  const handleStartBackup = () => {
    if (!selectedRepository) {
      toast.error('Please select a repository first')
      return
    }
    startBackupMutation.mutate(selectedRepository)
  }

  // Handle cancel backup
  const handleCancelBackup = (jobId: string) => {
    cancelBackupMutation.mutate(jobId)
  }

  // Get status icon
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'running':
        return <RefreshCw className="h-5 w-5 text-blue-500 animate-spin" />
      case 'completed':
        return <CheckCircle className="h-5 w-5 text-green-500" />
      case 'failed':
        return <AlertCircle className="h-5 w-5 text-red-500" />
      case 'cancelled':
        return <Square className="h-5 w-5 text-gray-500" />
      default:
        return <Clock className="h-5 w-5 text-gray-400" />
    }
  }

  // Get status color
  const getStatusColor = (status: string) => {
    switch (status) {
      case 'running':
        return 'text-blue-600 bg-blue-100'
      case 'completed':
        return 'text-green-600 bg-green-100'
      case 'failed':
        return 'text-red-600 bg-red-100'
      case 'cancelled':
        return 'text-gray-600 bg-gray-100'
      default:
        return 'text-gray-600 bg-gray-100'
    }
  }

  // Format file size
  const formatFileSize = (size?: string) => {
    if (!size) return 'Unknown'
    return size
  }

  // Format duration
  const formatDuration = (startTime: string, endTime?: string) => {
    const start = new Date(startTime)
    const end = endTime ? new Date(endTime) : new Date()
    const diff = Math.floor((end.getTime() - start.getTime()) / 1000)
    
    const hours = Math.floor(diff / 3600)
    const minutes = Math.floor((diff % 3600) / 60)
    const seconds = diff % 60
    
    if (hours > 0) {
      return `${hours}h ${minutes}m ${seconds}s`
    } else if (minutes > 0) {
      return `${minutes}m ${seconds}s`
    } else {
      return `${seconds}s`
    }
  }

  const runningJobs = backupStatus?.data?.filter((job: BackupJob) => job.status === 'running') || []
  const recentJobs = backupStatus?.data?.slice(0, 10) || []

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Backup Operations</h1>
          <p className="text-gray-600">Manage and monitor your backup jobs</p>
        </div>
        <div className="flex items-center space-x-3">
          {/* Real-time connection status */}
          <div className="flex items-center space-x-2">
            {isConnected ? (
              <div className="flex items-center text-green-600">
                <RefreshCw className="w-4 h-4 mr-1 animate-spin" />
                <span className="text-sm font-medium">Live Updates</span>
              </div>
            ) : (
              <div className="flex items-center text-gray-500">
                <Clock className="w-4 h-4 mr-1" />
                <span className="text-sm font-medium">Polling</span>
              </div>
            )}
          </div>
          
          <button
            onClick={() => queryClient.invalidateQueries({ queryKey: ['backup-status'] })}
            className="inline-flex items-center px-3 py-2 border border-gray-300 shadow-sm text-sm leading-4 font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh
          </button>
        </div>
      </div>

      {/* Manual Backup Control */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-4 py-3 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Manual Backup</h3>
          <p className="text-sm text-gray-600">Start a new backup job</p>
        </div>
        
        <div className="p-4">
          <div className="flex items-center space-x-4">
            <div className="flex-1">
              <label htmlFor="repository" className="block text-sm font-medium text-gray-700 mb-1">
                Repository
              </label>
              <select
                id="repository"
                value={selectedRepository}
                onChange={(e) => setSelectedRepository(e.target.value)}
                className="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500"
                disabled={loadingRepositories}
              >
                <option value="">
                  {loadingRepositories ? 'Loading repositories...' : 'Select a repository...'}
                </option>
                {repositoriesData?.data?.repositories?.map((repo: any) => (
                  <option key={repo.id} value={repo.path}>
                    {repo.name} ({repo.path})
                  </option>
                ))}
              </select>
            </div>
            
            <button
              onClick={handleStartBackup}
              disabled={startBackupMutation.isLoading || !selectedRepository}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {startBackupMutation.isLoading ? (
                <>
                  <RefreshCw className="h-4 w-4 mr-2 animate-spin" />
                  Starting...
                </>
              ) : (
                <>
                  <Play className="h-4 w-4 mr-2" />
                  Start Backup
                </>
              )}
            </button>
          </div>
        </div>
      </div>

      {/* Running Jobs */}
      {runningJobs.length > 0 && (
        <div className="bg-white rounded-lg shadow">
          <div className="px-4 py-3 border-b border-gray-200">
            <h3 className="text-lg font-medium text-gray-900">Running Jobs</h3>
            <p className="text-sm text-gray-600">Currently active backup operations</p>
          </div>
          
          <div className="p-4 space-y-4">
            {runningJobs.map((job: BackupJob) => (
              <div key={job.id} className="border rounded-lg p-4">
                <div className="flex items-center justify-between mb-3">
                  <div className="flex items-center space-x-3">
                    {getStatusIcon(job.status)}
                    <div>
                      <h4 className="font-medium text-gray-900">Backup Job {job.id}</h4>
                      <p className="text-sm text-gray-600">Repository: {job.repository}</p>
                    </div>
                  </div>
                  <button
                    onClick={() => handleCancelBackup(job.id)}
                    disabled={cancelBackupMutation.isLoading}
                    className="inline-flex items-center px-3 py-1 border border-red-300 text-sm font-medium rounded-md text-red-700 bg-white hover:bg-red-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500 disabled:opacity-50"
                  >
                    <Square className="h-4 w-4 mr-1" />
                    Cancel
                  </button>
                </div>
                
                {/* Progress Bar */}
                <div className="mb-3">
                  <div className="flex justify-between text-sm text-gray-600 mb-1">
                    <span>Progress: {job.progress}%</span>
                    <span>{formatDuration(job.started_at)}</span>
                  </div>
                  <div className="w-full bg-gray-200 rounded-full h-2">
                    <div
                      className="bg-blue-600 h-2 rounded-full transition-all duration-300"
                      style={{ width: `${job.progress}%` }}
                    ></div>
                  </div>
                </div>
                
                {/* Job Details */}
                <div className="grid grid-cols-2 gap-4 text-sm">
                  <div>
                    <span className="text-gray-600">Files:</span>
                    <span className="ml-2 font-medium">
                      {job.processed_files.toLocaleString()}
                      {job.total_files && ` / ${job.total_files.toLocaleString()}`}
                    </span>
                  </div>
                  <div>
                    <span className="text-gray-600">Size:</span>
                    <span className="ml-2 font-medium">
                      {formatFileSize(job.processed_size)}
                      {job.total_size && ` / ${formatFileSize(job.total_size)}`}
                    </span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Recent Jobs */}
      <div className="bg-white rounded-lg shadow">
        <div className="px-4 py-3 border-b border-gray-200">
          <h3 className="text-lg font-medium text-gray-900">Recent Jobs</h3>
          <p className="text-sm text-gray-600">History of backup operations</p>
        </div>
        
        <div className="overflow-hidden">
          {loadingStatus ? (
            <div className="text-center py-8">
              <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-indigo-600 mx-auto"></div>
              <p className="mt-2 text-gray-600">Loading backup history...</p>
            </div>
          ) : recentJobs.length === 0 ? (
            <div className="text-center py-8">
              <FileText className="h-12 w-12 text-gray-400 mx-auto mb-4" />
              <p className="text-gray-600">No backup jobs found</p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Job ID
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Repository
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Status
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Started
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Duration
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Progress
                    </th>
                    <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {recentJobs.map((job: BackupJob) => (
                    <tr key={job.id} className="hover:bg-gray-50">
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium text-gray-900">
                        {job.id}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        <div className="flex items-center">
                          <HardDrive className="h-4 w-4 mr-2 text-gray-400" />
                          {job.repository}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          {getStatusIcon(job.status)}
                          <span className={`ml-2 inline-flex px-2 py-1 text-xs font-semibold rounded-full ${getStatusColor(job.status)}`}>
                            {job.status}
                          </span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        {new Date(job.started_at).toLocaleString()}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm text-gray-600">
                        {formatDuration(job.started_at, job.completed_at)}
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex items-center">
                          <div className="w-16 bg-gray-200 rounded-full h-2 mr-2">
                            <div
                              className="bg-blue-600 h-2 rounded-full"
                              style={{ width: `${job.progress}%` }}
                            ></div>
                          </div>
                          <span className="text-sm text-gray-600">{job.progress}%</span>
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap text-sm font-medium">
                        <button
                          onClick={() => setShowJobDetails(showJobDetails === job.id ? null : job.id)}
                          className="text-indigo-600 hover:text-indigo-900"
                        >
                          {showJobDetails === job.id ? 'Hide' : 'Details'}
                        </button>
                        {job.status === 'running' && (
                          <button
                            onClick={() => handleCancelBackup(job.id)}
                            className="ml-3 text-red-600 hover:text-red-900"
                          >
                            Cancel
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Job Details Modal */}
      {showJobDetails && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-11/12 max-w-2xl shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Job Details</h3>
              {(() => {
                const job = recentJobs.find((j: BackupJob) => j.id === showJobDetails)
                if (!job) return null
                
                return (
                  <div className="space-y-4">
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <span className="text-sm font-medium text-gray-600">Job ID:</span>
                        <p className="text-sm text-gray-900">{job.id}</p>
                      </div>
                      <div>
                        <span className="text-sm font-medium text-gray-600">Repository:</span>
                        <p className="text-sm text-gray-900">{job.repository}</p>
                      </div>
                      <div>
                        <span className="text-sm font-medium text-gray-600">Status:</span>
                        <p className="text-sm text-gray-900">{job.status}</p>
                      </div>
                      <div>
                        <span className="text-sm font-medium text-gray-600">Started:</span>
                        <p className="text-sm text-gray-900">{new Date(job.started_at).toLocaleString()}</p>
                      </div>
                      {job.completed_at && (
                        <div>
                          <span className="text-sm font-medium text-gray-600">Completed:</span>
                          <p className="text-sm text-gray-900">{new Date(job.completed_at).toLocaleString()}</p>
                        </div>
                      )}
                      <div>
                        <span className="text-sm font-medium text-gray-600">Duration:</span>
                        <p className="text-sm text-gray-900">{formatDuration(job.started_at, job.completed_at)}</p>
                      </div>
                    </div>
                    
                    {job.error_message && (
                      <div>
                        <span className="text-sm font-medium text-gray-600">Error:</span>
                        <p className="text-sm text-red-600 mt-1">{job.error_message}</p>
                      </div>
                    )}
                    
                    <div className="flex justify-end">
                      <button
                        onClick={() => setShowJobDetails(null)}
                        className="px-4 py-2 bg-gray-300 text-gray-700 rounded-md hover:bg-gray-400"
                      >
                        Close
                      </button>
                    </div>
                  </div>
                )
              })()}
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Backup 