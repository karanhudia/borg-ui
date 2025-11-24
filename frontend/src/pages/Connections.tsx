import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from 'react-query'
import {
  Wifi,
  Plus,
  TestTube,
  Clock,
  CheckCircle,
  AlertTriangle,
  XCircle,
  RefreshCw
} from 'lucide-react'
import { toast } from 'react-hot-toast'
import { sshKeysAPI } from '../services/api'
import { formatDate as formatDateUtil } from '../utils/dateUtils'

interface SSHConnection {
  id: number
  ssh_key_id: number
  ssh_key_name: string
  host: string
  username: string
  port: number
  status: string
  last_test: string | null
  last_success: string | null
  error_message: string | null
  created_at: string
}

interface SSHKey {
  id: number
  name: string
  key_type: string
  is_active: boolean
}

const Connections: React.FC = () => {
  const [showAddConnectionModal, setShowAddConnectionModal] = useState(false)

  const queryClient = useQueryClient()

  // Queries
  const { data: connectionsData, isLoading: loadingConnections, refetch: refetchConnections } = useQuery({
    queryKey: ['ssh-connections'],
    queryFn: sshKeysAPI.getSSHConnections,
    refetchInterval: 30000, // Auto-refresh every 30 seconds
  })

  const { data: sshKeysData } = useQuery({
    queryKey: ['ssh-keys'],
    queryFn: sshKeysAPI.getSSHKeys,
  })

  // Form state
  const [connectionForm, setConnectionForm] = useState({
    ssh_key_id: '',
    host: '',
    username: '',
    port: 22,
  })

  // Mutations
  const testConnectionMutation = useMutation({
    mutationFn: ({ keyId, data }: { keyId: number; data: any }) =>
      sshKeysAPI.testSSHConnection(keyId, data),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries(['ssh-connections'])
      if (data.success) {
        toast.success('SSH connection test successful!')
      } else {
        toast.error(`SSH connection test failed: ${data.connection?.error_message || 'Unknown error'}`)
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to test SSH connection')
    },
  })

  const retryConnectionMutation = useMutation({
    mutationFn: ({ keyId, data }: { keyId: number; data: any }) =>
      sshKeysAPI.testSSHConnection(keyId, data),
    onSuccess: (data: any) => {
      queryClient.invalidateQueries(['ssh-connections'])
      if (data.success) {
        toast.success('Connection re-established successfully!')
      } else {
        toast.error(`Connection retry failed: ${data.connection?.error_message || 'Unknown error'}`)
      }
    },
    onError: (error: any) => {
      toast.error(error.response?.data?.detail || 'Failed to retry connection')
    },
  })

  // Event handlers
  const handleAddConnection = (e: React.FormEvent) => {
    e.preventDefault()
    const keyId = parseInt(connectionForm.ssh_key_id)
    if (isNaN(keyId)) {
      toast.error('Please select a valid SSH key')
      return
    }

    testConnectionMutation.mutate({
      keyId,
      data: {
        host: connectionForm.host,
        username: connectionForm.username,
        port: connectionForm.port,
      }
    })
    setShowAddConnectionModal(false)
    setConnectionForm({
      ssh_key_id: '',
      host: '',
      username: '',
      port: 22,
    })
  }

  const handleRetryConnection = (connection: SSHConnection) => {
    retryConnectionMutation.mutate({
      keyId: connection.ssh_key_id,
      data: {
        host: connection.host,
        username: connection.username,
        port: connection.port
      }
    })
  }

  const handleTestConnection = (connection: SSHConnection) => {
    testConnectionMutation.mutate({
      keyId: connection.ssh_key_id,
      data: {
        host: connection.host,
        username: connection.username,
        port: connection.port
      }
    })
  }

  const handleRefreshAll = () => {
    refetchConnections()
    toast.success('Refreshing all connections...')
  }

  // Utility functions
  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'connected':
        return <CheckCircle className="w-5 h-5 text-green-500" strokeWidth={1.5} />
      case 'failed':
        return <XCircle className="w-5 h-5 text-red-500" strokeWidth={1.5} />
      case 'testing':
        return <Clock className="w-5 h-5 text-yellow-500" strokeWidth={1.5} />
      default:
        return <AlertTriangle className="w-5 h-5 text-gray-500" strokeWidth={1.5} />
    }
  }

  const getStatusColor = (status: string) => {
    switch (status) {
      case 'connected':
        return 'text-green-600 bg-green-100'
      case 'failed':
        return 'text-red-600 bg-red-100'
      case 'testing':
        return 'text-yellow-600 bg-yellow-100'
      default:
        return 'text-gray-600 bg-gray-100'
    }
  }

  const getTimeSince = (dateString: string | null) => {
    if (!dateString) return 'Never'
    const date = new Date(dateString)
    const now = new Date()
    const diffMs = now.getTime() - date.getTime()
    const diffMins = Math.floor(diffMs / 60000)
    const diffHours = Math.floor(diffMins / 60)
    const diffDays = Math.floor(diffHours / 24)

    if (diffMins < 1) return 'Just now'
    if (diffMins < 60) return `${diffMins} minute${diffMins > 1 ? 's' : ''} ago`
    if (diffHours < 24) return `${diffHours} hour${diffHours > 1 ? 's' : ''} ago`
    return `${diffDays} day${diffDays > 1 ? 's' : ''} ago`
  }

  const connections = connectionsData?.data?.connections || []
  const sshKeys = sshKeysData?.data?.ssh_keys || []
  const activeKeys = sshKeys.filter((key: SSHKey) => key.is_active)

  const connectedCount = connections.filter((c: SSHConnection) => c.status === 'connected').length
  const failedCount = connections.filter((c: SSHConnection) => c.status === 'failed').length

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">SSH Connections</h1>
          <p className="mt-1 text-sm text-gray-500">
            Monitor and manage SSH connections to remote machines
          </p>
        </div>
        <div className="flex items-center space-x-3">
          <button
            onClick={handleRefreshAll}
            disabled={loadingConnections}
            className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md text-gray-700 bg-white hover:bg-gray-50 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500 disabled:opacity-50"
          >
            <RefreshCw className={`w-4 h-4 mr-2 ${loadingConnections ? 'animate-spin' : ''}`} strokeWidth={1.5} />
            Refresh
          </button>
          <button
            onClick={() => setShowAddConnectionModal(true)}
            className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-indigo-500"
          >
            <Plus className="w-4 h-4 mr-2" strokeWidth={1.5} />
            Add Connection
          </button>
        </div>
      </div>

      {/* Statistics Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-white rounded-lg border shadow-sm p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Total Connections</p>
              <p className="text-3xl font-bold text-gray-900 mt-2">{connections.length}</p>
            </div>
            <Wifi className="w-10 h-10 text-indigo-500" strokeWidth={1.5} />
          </div>
        </div>

        <div className="bg-white rounded-lg border shadow-sm p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Active Connections</p>
              <p className="text-3xl font-bold text-green-600 mt-2">{connectedCount}</p>
            </div>
            <CheckCircle className="w-10 h-10 text-green-500" strokeWidth={1.5} />
          </div>
        </div>

        <div className="bg-white rounded-lg border shadow-sm p-6">
          <div className="flex items-center justify-between">
            <div>
              <p className="text-sm font-medium text-gray-500">Failed Connections</p>
              <p className="text-3xl font-bold text-red-600 mt-2">{failedCount}</p>
            </div>
            <XCircle className="w-10 h-10 text-red-500" strokeWidth={1.5} />
          </div>
        </div>
      </div>

      {/* Failed Connections Alert */}
      {failedCount > 0 && (
        <div className="bg-yellow-50 border border-yellow-200 rounded-md p-4">
          <div className="flex">
            <AlertTriangle className="w-5 h-5 text-yellow-400 mr-2 mt-0.5" strokeWidth={1.5} />
            <div>
              <h3 className="text-sm font-medium text-yellow-800">
                Failed Connections Detected
              </h3>
              <p className="text-sm text-yellow-700 mt-1">
                {failedCount} connection{failedCount > 1 ? 's have' : ' has'} failed. You can retry them using the "Retry" button next to each failed connection.
              </p>
            </div>
          </div>
        </div>
      )}

      {/* Connections List */}
      <div className="space-y-4">
        {loadingConnections ? (
          <div className="text-center py-12">
            <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-indigo-600 mx-auto"></div>
            <p className="mt-4 text-gray-600">Loading connections...</p>
          </div>
        ) : connections.length === 0 ? (
          <div className="bg-white rounded-lg border shadow-sm p-12 text-center">
            <Wifi className="w-16 h-16 text-gray-400 mx-auto mb-4" strokeWidth={1.5} />
            <h3 className="text-lg font-medium text-gray-900 mb-2">No Connections Yet</h3>
            <p className="text-gray-500 mb-6">
              Start by adding a new connection to a remote machine using an existing SSH key.
            </p>
            <button
              onClick={() => setShowAddConnectionModal(true)}
              className="inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md text-white bg-indigo-600 hover:bg-indigo-700"
            >
              <Plus className="w-4 h-4 mr-2" strokeWidth={1.5} />
              Add Your First Connection
            </button>
          </div>
        ) : (
          connections.map((connection: SSHConnection) => (
            <div key={connection.id} className="bg-white rounded-lg border shadow-sm p-6 hover:shadow-md transition-shadow">
              <div className="flex items-start justify-between">
                <div className="flex items-start space-x-4 flex-1">
                  {getStatusIcon(connection.status)}
                  <div className="flex-1">
                    <div className="flex items-center space-x-3 mb-2">
                      <h3 className="text-lg font-medium text-gray-900">
                        {connection.username}@{connection.host}:{connection.port}
                      </h3>
                      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${getStatusColor(connection.status)}`}>
                        {connection.status}
                      </span>
                    </div>

                    <div className="flex items-center space-x-4 text-sm text-gray-500 mb-3">
                      <span className="inline-flex items-center">
                        <CheckCircle className="w-4 h-4 mr-1" strokeWidth={1.5} />
                        SSH Key: <span className="font-medium ml-1">{connection.ssh_key_name}</span>
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-4 text-sm">
                      <div>
                        <label className="text-gray-500 block">Last Test</label>
                        <p className="font-medium text-gray-900">{formatDateUtil(connection.last_test)}</p>
                        <p className="text-xs text-gray-500">{getTimeSince(connection.last_test)}</p>
                      </div>
                      <div>
                        <label className="text-gray-500 block">Last Success</label>
                        <p className="font-medium text-gray-900">{formatDateUtil(connection.last_success)}</p>
                        <p className="text-xs text-gray-500">{getTimeSince(connection.last_success)}</p>
                      </div>
                    </div>

                    {connection.error_message && (
                      <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-md">
                        <label className="text-sm font-medium text-red-800 block mb-1">Error Message</label>
                        <p className="text-sm text-red-700">{connection.error_message}</p>
                      </div>
                    )}
                  </div>
                </div>

                {/* Actions */}
                <div className="flex flex-col space-y-2 ml-4">
                  <button
                    onClick={() => handleTestConnection(connection)}
                    disabled={testConnectionMutation.isLoading}
                    className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-green-600 hover:text-green-800 hover:bg-green-50 rounded-md disabled:opacity-50"
                  >
                    {testConnectionMutation.isLoading ? (
                      <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-green-600 mr-2"></div>
                    ) : (
                      <TestTube className="w-4 h-4 mr-2" strokeWidth={1.5} />
                    )}
                    Test
                  </button>

                  {connection.status === 'failed' && (
                    <button
                      onClick={() => handleRetryConnection(connection)}
                      disabled={retryConnectionMutation.isLoading}
                      className="inline-flex items-center px-3 py-1.5 text-sm font-medium text-blue-600 hover:text-blue-800 hover:bg-blue-50 rounded-md disabled:opacity-50"
                    >
                      {retryConnectionMutation.isLoading ? (
                        <div className="animate-spin rounded-full h-4 w-4 border-b-2 border-blue-600 mr-2"></div>
                      ) : (
                        <RefreshCw className="w-4 h-4 mr-2" strokeWidth={1.5} />
                      )}
                      Retry
                    </button>
                  )}
                </div>
              </div>
            </div>
          ))
        )}
      </div>

      {/* Add Connection Modal */}
      {showAddConnectionModal && (
        <div className="fixed inset-0 bg-gray-600 bg-opacity-50 overflow-y-auto h-full w-full z-50">
          <div className="relative top-20 mx-auto p-5 border w-96 shadow-lg rounded-md bg-white">
            <div className="mt-3">
              <h3 className="text-lg font-medium text-gray-900 mb-4">Add New Connection</h3>
              <form onSubmit={handleAddConnection} className="space-y-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">SSH Key</label>
                  <select
                    value={connectionForm.ssh_key_id}
                    onChange={(e) => setConnectionForm({ ...connectionForm, ssh_key_id: e.target.value })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    required
                  >
                    <option value="">Select an SSH key</option>
                    {activeKeys.map((key: SSHKey) => (
                      <option key={key.id} value={key.id}>
                        {key.name} ({key.key_type})
                      </option>
                    ))}
                  </select>
                  {activeKeys.length === 0 && (
                    <p className="text-xs text-red-600 mt-1">No active SSH keys available. Please create one first.</p>
                  )}
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Host</label>
                  <input
                    type="text"
                    value={connectionForm.host}
                    onChange={(e) => setConnectionForm({ ...connectionForm, host: e.target.value })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="192.168.1.250"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                  <input
                    type="text"
                    value={connectionForm.username}
                    onChange={(e) => setConnectionForm({ ...connectionForm, username: e.target.value })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    placeholder="karanhudia"
                    required
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">Port</label>
                  <input
                    type="number"
                    value={connectionForm.port}
                    onChange={(e) => setConnectionForm({ ...connectionForm, port: parseInt(e.target.value) })}
                    className="block w-full px-3 py-2 border border-gray-300 rounded-md shadow-sm focus:outline-none focus:ring-indigo-500 focus:border-indigo-500"
                    min="1"
                    max="65535"
                    required
                  />
                </div>

                <div className="bg-blue-50 border border-blue-200 rounded-md p-3">
                  <p className="text-xs text-blue-800">
                    This will test the SSH connection to the specified host. Make sure the SSH key is already deployed to the remote machine.
                  </p>
                </div>

                <div className="flex justify-end space-x-3">
                  <button
                    type="button"
                    onClick={() => {
                      setShowAddConnectionModal(false)
                      setConnectionForm({
                        ssh_key_id: '',
                        host: '',
                        username: '',
                        port: 22,
                      })
                    }}
                    className="px-4 py-2 border border-gray-300 rounded-md text-sm font-medium text-gray-700 hover:bg-gray-50"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={testConnectionMutation.isLoading || activeKeys.length === 0}
                    className="px-4 py-2 border border-transparent rounded-md shadow-sm text-sm font-medium text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50"
                  >
                    {testConnectionMutation.isLoading ? 'Testing...' : 'Add & Test Connection'}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

export default Connections
