import React from 'react';
import { useSSE, useSystemStatus, useBackupProgress } from '../hooks/useSSE';
import { Wifi, WifiOff } from 'lucide-react';

const RealTimeStatus: React.FC = () => {
  const { isConnected, events, clearEvents } = useSSE();
  const { systemStatus } = useSystemStatus();
  const { progress: backupProgress } = useBackupProgress();

  return (
    <div className="bg-white rounded-lg border p-4 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-lg font-medium text-gray-900">Real-Time Status</h3>
        <div className="flex items-center space-x-2">
          {isConnected ? (
            <div className="flex items-center text-green-600">
              <Wifi className="w-4 h-4 mr-1" />
              <span className="text-sm font-medium">Connected</span>
            </div>
          ) : (
            <div className="flex items-center text-gray-500">
              <WifiOff className="w-4 h-4 mr-1" />
              <span className="text-sm font-medium">Disconnected</span>
            </div>
          )}
          <button
            onClick={clearEvents}
            className="text-sm text-gray-500 hover:text-gray-700"
          >
            Clear Events
          </button>
        </div>
      </div>

      {/* System Status */}
      {systemStatus && (
        <div className="bg-blue-50 rounded-lg p-3">
          <h4 className="text-sm font-medium text-blue-900 mb-2">System Status</h4>
          <div className="text-sm text-blue-800">
            <pre className="whitespace-pre-wrap">{JSON.stringify(systemStatus, null, 2)}</pre>
          </div>
        </div>
      )}

      {/* Backup Progress */}
      {backupProgress && (
        <div className="bg-green-50 rounded-lg p-3">
          <h4 className="text-sm font-medium text-green-900 mb-2">Backup Progress</h4>
          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <span className="text-sm text-green-800">Job #{backupProgress.job_id}</span>
              <span className={`px-2 py-1 text-xs font-medium rounded-full ${
                backupProgress.status === 'completed' ? 'bg-green-100 text-green-800' :
                backupProgress.status === 'failed' ? 'bg-red-100 text-red-800' :
                'bg-blue-100 text-blue-800'
              }`}>
                {backupProgress.status}
              </span>
            </div>
            {backupProgress.status === 'running' && backupProgress.progress !== undefined && (
              <div className="flex items-center space-x-2">
                <div className="w-2 h-2 bg-blue-600 rounded-full animate-pulse"></div>
                <span className="text-sm font-medium text-blue-800">
                  {backupProgress.progress === 0
                    ? 'Initializing backup...'
                    : backupProgress.progress >= 100
                    ? 'Finalizing...'
                    : 'Processing files...'}
                </span>
              </div>
            )}
            {backupProgress.message && (
              <p className="text-sm text-green-800">{backupProgress.message}</p>
            )}
          </div>
        </div>
      )}

      {/* Recent Events */}
      <div>
        <h4 className="text-sm font-medium text-gray-900 mb-2">Recent Events ({events.length})</h4>
        <div className="space-y-2 max-h-40 overflow-y-auto">
          {events.slice(-5).map((event, index) => (
            <div key={index} className="bg-gray-50 rounded p-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-medium text-gray-700">{event.type}</span>
                <span className="text-xs text-gray-500">
                  {new Date(event.timestamp).toLocaleTimeString()}
                </span>
              </div>
              <div className="text-xs text-gray-600 mt-1">
                {JSON.stringify(event.data).substring(0, 100)}
                {JSON.stringify(event.data).length > 100 && '...'}
              </div>
            </div>
          ))}
          {events.length === 0 && (
            <p className="text-sm text-gray-500 text-center py-4">No events yet</p>
          )}
        </div>
      </div>
    </div>
  );
};

export default RealTimeStatus;
