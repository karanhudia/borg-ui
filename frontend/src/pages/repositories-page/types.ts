import type { RepositoryData } from '../../services/api'

export interface Repository extends RepositoryData {
  id: number
  name: string
  path: string
  encryption: string
  compression: string
  source_directories: string[]
  exclude_patterns: string[]
  last_backup: string | null
  last_check: string | null
  last_compact: string | null
  has_schedule?: boolean
  schedule_enabled?: boolean
  schedule_name?: string | null
  schedule_timezone?: string | null
  next_run?: string | null
  total_size: string | null
  archive_count: number
  created_at: string
  updated_at: string | null
  mode: 'full' | 'observe'
  custom_flags?: string | null
  has_running_maintenance?: boolean
  has_keyfile?: boolean
  remote_path?: string
  pre_backup_script?: string
  post_backup_script?: string
  hook_timeout?: number
  pre_hook_timeout?: number
  post_hook_timeout?: number
  continue_on_hook_failure?: boolean
  skip_on_hook_failure?: boolean
  bypass_lock?: boolean
  source_ssh_connection_id?: number | null
  repository_type?: 'local' | 'ssh' | 'sftp'
  borg_version?: 1 | 2
}

export interface PruneForm {
  keep_hourly: number
  keep_daily: number
  keep_weekly: number
  keep_monthly: number
  keep_quarterly: number
  keep_yearly: number
  dry_run?: boolean
}

export interface RepositoryGroup {
  name: string | null
  repositories: Repository[]
}

export interface ProcessedRepositories {
  groups: RepositoryGroup[]
}
