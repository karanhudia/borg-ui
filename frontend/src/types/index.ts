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
  schedule_timezone?: string | null
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
  repository_id?: number | null
  type?: string
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
  backup_plan_id?: number | null
  backup_plan_run_id?: number | null
  backup_plan_name?: string | null
  archive_name?: string | null
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

export interface BackupPlanRepositoryLink {
  id?: number
  repository_id: number
  enabled: boolean
  execution_order: number
  compression_source?: 'plan' | 'repository' | 'custom'
  compression_override?: string | null
  custom_flags_override?: string | null
  upload_ratelimit_kib_override?: number | null
  failure_behavior_override?: 'continue' | 'stop' | null
  repository?: Repository | null
}

export interface BackupPlan {
  id: number
  name: string
  description?: string | null
  enabled: boolean
  source_type: 'local' | 'remote'
  source_ssh_connection_id?: number | null
  source_directories: string[]
  exclude_patterns: string[]
  archive_name_template: string
  compression: string
  custom_flags?: string | null
  upload_ratelimit_kib?: number | null
  repository_run_mode: 'series' | 'parallel'
  max_parallel_repositories: number
  failure_behavior: 'continue' | 'stop'
  schedule_enabled: boolean
  cron_expression?: string | null
  timezone: string
  last_run?: string | null
  next_run?: string | null
  repository_count: number
  repositories?: BackupPlanRepositoryLink[]
  pre_backup_script_id?: number | null
  post_backup_script_id?: number | null
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  run_repository_scripts?: boolean
  run_prune_after?: boolean
  run_compact_after?: boolean
  run_check_after?: boolean
  check_max_duration?: number
  prune_keep_hourly?: number
  prune_keep_daily?: number
  prune_keep_weekly?: number
  prune_keep_monthly?: number
  prune_keep_quarterly?: number
  prune_keep_yearly?: number
  created_at?: string | null
  updated_at?: string | null
}

export interface BackupPlanRunRepository {
  id: number
  repository_id?: number | null
  status: string
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  repository?: Repository | null
  backup_job?: BackupJob | null
}

export interface BackupPlanScriptExecution {
  id: number
  script_id: number
  script_name: string
  hook_type?: string | null
  status: string
  started_at?: string | null
  completed_at?: string | null
  execution_time?: number | null
  exit_code?: number | null
  error_message?: string | null
  has_logs?: boolean
}

export interface BackupPlanRun {
  id: number
  backup_plan_id?: number | null
  trigger: string
  status: string
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  created_at?: string | null
  repositories: BackupPlanRunRepository[]
  script_executions?: BackupPlanScriptExecution[]
}

export interface BackupPlanData {
  name: string
  description?: string | null
  enabled: boolean
  source_type: 'local' | 'remote'
  source_ssh_connection_id?: number | null
  source_directories: string[]
  exclude_patterns?: string[]
  archive_name_template: string
  compression: string
  custom_flags?: string | null
  upload_ratelimit_kib?: number | null
  repository_run_mode: 'series' | 'parallel'
  max_parallel_repositories: number
  failure_behavior: 'continue' | 'stop'
  schedule_enabled: boolean
  cron_expression?: string | null
  timezone: string
  pre_backup_script_id?: number | null
  post_backup_script_id?: number | null
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  run_repository_scripts: boolean
  run_prune_after: boolean
  run_compact_after: boolean
  run_check_after: boolean
  check_max_duration: number
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  repositories: BackupPlanRepositoryLink[]
  clear_legacy_source_repository_ids?: number[]
}
