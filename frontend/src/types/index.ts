export interface Repository {
  id: number
  name: string
  path: string
  repository_type?: 'local' | 'ssh' | 'sftp'
  has_running_maintenance?: boolean
  borg_version?: number
  host?: string
  port?: number
  username?: string
  encryption?: string
  compression?: string
  passphrase?: string
  remote_path?: string
  connection_id?: number | null
  source_directories?: string[]
  exclude_patterns?: string[]
  mode?: 'full' | 'observe'
  bypass_lock?: boolean
  custom_flags?: string | null
  archive_count?: number
  total_size?: string | null
  last_backup?: string | null
  last_check?: string | null
  last_compact?: string | null
  has_schedule?: boolean
  schedule_enabled?: boolean
  schedule_name?: string | null
  next_run?: string | null
  has_keyfile?: boolean
  source_ssh_connection_id?: number | null
  [key: string]: unknown
}

export interface Archive {
  id: string
  archive: string
  name: string
  start: string
  time: string
}

export interface BackupJob {
  id: string | number
  repository: string
  status: 'running' | 'completed' | 'completed_with_warnings' | 'failed' | 'cancelled' | string
  started_at?: string
  completed_at?: string
  progress?: number
  total_files?: number
  processed_files?: number
  total_size?: string
  processed_size?: string
  current_file?: string
  message?: string
  error_message?: string
  triggered_by?: string
  schedule_id?: number | null
  has_logs?: boolean
  maintenance_status?: string
  progress_details?: {
    original_size: number
    compressed_size?: number
    deduplicated_size?: number
    nfiles: number
    current_file: string
    backup_speed?: number
    total_expected_size?: number
    estimated_time_remaining?: number
    [key: string]: unknown
  }
}
