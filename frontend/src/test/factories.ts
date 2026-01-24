/**
 * Test data factories for creating mock objects
 * These provide consistent mock data across tests
 */

export interface MockRepository {
  id: number
  name: string
  path: string
  mode: 'full' | 'observe'
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  custom_borg_flags?: string
  passphrase?: string
  repoSshConnectionId?: number
  sourceSshConnectionId?: number
  remote_path?: string
  created_at?: string
  updated_at?: string
}

export interface MockSSHConnection {
  id: number
  host: string
  username: string
  port: number
  status: 'connected' | 'disconnected' | 'error'
  name?: string
  last_connected?: string
}

export interface MockBackupJob {
  id: number
  repository_id: number
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: number
  progress_message?: string
  started_at?: string
  completed_at?: string
  error_message?: string
  archive_name?: string
}

export interface MockMaintenanceJob {
  id: number
  repository_id: number
  job_type: 'check' | 'compact' | 'prune'
  status: 'pending' | 'running' | 'completed' | 'failed'
  progress?: number
  progress_message?: string
  started_at?: string
  completed_at?: string
  error_message?: string
}

export const mockRepository = (overrides: Partial<MockRepository> = {}): MockRepository => ({
  id: 1,
  name: 'Test Repo',
  path: '/backups/test',
  mode: 'full',
  encryption: 'repokey',
  compression: 'lz4',
  source_directories: ['/data'],
  exclude_patterns: [],
  custom_borg_flags: '',
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
  ...overrides,
})

export const mockSSHConnection = (
  overrides: Partial<MockSSHConnection> = {}
): MockSSHConnection => ({
  id: 1,
  host: 'example.com',
  username: 'user',
  port: 22,
  status: 'connected',
  name: 'Example Server',
  last_connected: '2025-01-24T00:00:00Z',
  ...overrides,
})

export const mockBackupJob = (overrides: Partial<MockBackupJob> = {}): MockBackupJob => ({
  id: 1,
  repository_id: 1,
  status: 'completed',
  progress: 100,
  progress_message: 'Backup complete',
  started_at: '2025-01-24T10:00:00Z',
  completed_at: '2025-01-24T10:30:00Z',
  archive_name: 'test-backup-2025-01-24',
  ...overrides,
})

export const mockMaintenanceJob = (
  overrides: Partial<MockMaintenanceJob> = {}
): MockMaintenanceJob => ({
  id: 1,
  repository_id: 1,
  job_type: 'check',
  status: 'completed',
  progress: 100,
  progress_message: 'Check complete',
  started_at: '2025-01-24T10:00:00Z',
  completed_at: '2025-01-24T10:15:00Z',
  ...overrides,
})

export const mockSSHRepository = (overrides: Partial<MockRepository> = {}): MockRepository => ({
  ...mockRepository(),
  path: 'ssh://user@example.com:22/backups/test',
  repoSshConnectionId: 1,
  ...overrides,
})

export const mockRemoteSourceRepository = (
  overrides: Partial<MockRepository> = {}
): MockRepository => ({
  ...mockRepository(),
  sourceSshConnectionId: 2,
  source_directories: ['/remote/data'],
  ...overrides,
})
