export type SourceLocationKind = 'local' | 'remote' | 'agent'
export type SourceType = SourceLocationKind | 'mixed'
export type FilesystemSnapshotProvider = 'btrfs' | 'zfs'

export interface SourceSnapshotConfig {
  provider: FilesystemSnapshotProvider
  staging_path?: string
  dataset?: string
  mountpoint?: string
  recursive?: boolean
}

export type DatabaseCaptureMode = 'dump' | 'original'

export interface SourceDatabaseSelection {
  template_id: string
  engine: string
  display_name: string
  backup_strategy: string
  detected_source_path?: string | null
  detection_label?: string | null
  capture_mode: DatabaseCaptureMode
  dump_path?: string | null
  backup_paths: string[]
  script_execution_target: 'source' | 'server'
  pre_backup_script_id?: number | null
  post_backup_script_id?: number | null
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  script_execution_order?: number
}

export interface SourceContainerSelection {
  container_name: string
  display_name: string
  image?: string | null
  backup_mode: 'export'
  export_path: string
  script_execution_target: 'source' | 'server'
  pre_backup_script_id?: number | null
  post_backup_script_id?: number | null
  pre_backup_script_parameters?: Record<string, string> | null
  post_backup_script_parameters?: Record<string, string> | null
  script_execution_order?: number
}

export interface SourceLocation {
  source_type: SourceLocationKind
  source_ssh_connection_id?: number | null
  agent_machine_id?: number | null
  paths: string[]
  snapshot?: SourceSnapshotConfig
  database?: SourceDatabaseSelection
  container?: SourceContainerSelection
}

export interface Repository {
  id: number
  name: string
  path: string
  repository_type?: 'local' | 'ssh' | 'sftp' | 'rclone'
  storage_backend?: 'local' | 'ssh' | 'agent_local' | 'rclone' | 'rclone_direct'
  execution_target?: 'local' | 'ssh' | 'agent'
  executor_type?: 'server' | 'agent'
  agent_machine_id?: number | null
  agent_machine_name?: string | null
  agent_machine_status?: string | null
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
  source_locations?: SourceLocation[]
  exclude_patterns?: string[]
  mode?: 'full' | 'observe'
  bypass_lock?: boolean
  custom_flags?: string | null
  upload_ratelimit_kib?: number | null
  check_extra_flags?: string | null
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
  rclone_storage?: RcloneStorage | null
  [key: string]: unknown
}

export interface RcloneStorage {
  repository_id: number
  backend: 'rclone'
  rclone_remote_id: number
  rclone_remote_name?: string | null
  rclone_remote_path: string
  rclone_target?: string | null
  cache_path?: string | null
  cache_present?: boolean
  sync_direction?: 'primary_to_remote' | 'remote_to_cache' | string | null
  sync_policy: 'after_success' | 'manual' | 'scheduled'
  sync_status: 'current' | 'pending' | 'syncing' | 'failed' | 'hydrating' | string
  sync_cron_expression?: string | null
  sync_timezone?: string | null
  last_scheduled_sync_at?: string | null
  next_scheduled_sync_at?: string | null
  last_synced_at?: string | null
  last_hydrated_at?: string | null
  last_remote_check_at?: string | null
  last_sync_error?: string | null
  extra_flags?: string[]
  agent_machine_name?: string | null
  agent_machine_status?: string | null
  latest_sync_job?: {
    id: number
    triggered_by?: 'manual' | 'schedule' | 'scheduled' | string | null
    status?: string | null
    scheduled_for?: string | null
    started_at?: string | null
    completed_at?: string | null
    error_text?: string | null
    has_log?: boolean
  } | null
}

export interface Archive {
  id: string
  archive: string
  name: string
  start: string
  time: string
  triggered_by?: 'manual' | 'schedule' | 'scheduled' | string | null
  backup_job_id?: number | null
  backup_plan_id?: number | null
  backup_plan_run_id?: number | null
  scheduled_job_id?: number | null
}

export interface BackupJob {
  id: string | number
  repository: string
  repository_id?: number | null
  repository_path?: string | null
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
  scheduled_job_id?: number | null
  has_logs?: boolean
  maintenance_status?: string
  backup_plan_id?: number | null
  backup_plan_run_id?: number | null
  backup_plan_name?: string | null
  archive_name?: string | null
  execution_mode?: 'local' | 'remote_ssh' | 'agent' | string
  route_strategy?: string | null
  retry_attempt?: number | null
  retry_original_job_id?: number | null
  retry_source_job_id?: number | null
  retry_requested_by_user_id?: number | null
  retry_requested_at?: string | null
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

export interface RepositoryWipeArchive {
  identity: string
  name: string
  time?: string | null
  id?: string | null
  protected?: boolean
}

export type RepositoryWipeStatus =
  | 'previewed'
  | 'pending'
  | 'running'
  | 'completed'
  | 'completed_compaction_failed'
  | 'completed_with_warnings'
  | 'failed'
  | 'failed_partial'
  | 'cancelled'
  | string

export interface RepositoryWipeJob {
  id: number
  repository_id: number
  status: RepositoryWipeStatus
  phase?: string | null
  started_at?: string | null
  confirmed_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  progress?: number | null
  progress_message?: string | null
  archive_count: number
  archive_fingerprint: string
  run_compact: boolean
  has_logs: boolean
  logs?: string
  archives?: RepositoryWipeArchive[]
  dry_run_output?: string
  blocked?: boolean
  blocking_reason?: string | null
  protected_archives?: string[]
}

export interface RepositoryWipePreviewRequest {
  run_compact: boolean
}

export interface RepositoryWipeExecuteRequest {
  preview_id: number
  preview_fingerprint: string
  confirmation_phrase: string
  understood: boolean
  run_compact: boolean
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

export interface UploadRatelimitSchedulePolicy {
  label: string
  start_time: string
  end_time: string
  upload_ratelimit_kib?: number | null
}

export type BackupPlanScriptHookType = 'pre-backup' | 'post-backup'
export type BackupPlanScriptRunCondition = 'success' | 'failure' | 'warning' | 'always'

export interface BackupPlanScriptHook {
  id?: number | null
  // A hook references EITHER a server-side library script (script_id) OR a
  // script published by the agent (agent_script_name).
  script_id?: number | null
  agent_script_name?: string | null
  is_agent_script?: boolean
  script_name?: string
  script_description?: string | null
  hook_type: BackupPlanScriptHookType
  execution_order: number
  enabled: boolean
  custom_timeout?: number | null
  custom_run_on?: BackupPlanScriptRunCondition | null
  continue_on_error?: boolean | null
  skip_on_failure?: boolean | null
  default_timeout?: number | null
  default_run_on?: BackupPlanScriptRunCondition | string | null
  parameters?: Array<{
    name: string
    type: 'text' | 'password'
    default: string
    description: string
    required: boolean
  }> | null
  parameter_values?: Record<string, string> | null
}

export interface BackupPlan {
  id: number
  name: string
  description?: string | null
  enabled: boolean
  source_type: SourceType
  source_ssh_connection_id?: number | null
  source_directories: string[]
  source_locations?: SourceLocation[]
  exclude_patterns: string[]
  database_template_id?: string | null
  archive_name_template: string
  compression: string
  custom_flags?: string | null
  upload_ratelimit_kib?: number | null
  upload_ratelimit_schedule_policies?: UploadRatelimitSchedulePolicy[]
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
  script_hooks?: BackupPlanScriptHook[]
  run_repository_scripts?: boolean
  run_prune_after?: boolean
  run_compact_after?: boolean
  run_check_after?: boolean
  check_max_duration?: number
  check_extra_flags?: string | null
  prune_keep_hourly?: number
  prune_keep_daily?: number
  prune_keep_weekly?: number
  prune_keep_monthly?: number
  prune_keep_quarterly?: number
  prune_keep_yearly?: number
  prune_keep_within?: string | null
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
  retry_attempt?: number | null
  retry_original_run_id?: number | null
  retry_source_run_id?: number | null
  retry_requested_by_user_id?: number | null
  retry_requested_at?: string | null
  repositories: BackupPlanRunRepository[]
  script_executions?: BackupPlanScriptExecution[]
}

export interface BackupPlanData {
  name: string
  description?: string | null
  enabled: boolean
  source_type: SourceType
  source_ssh_connection_id?: number | null
  source_directories: string[]
  source_locations?: SourceLocation[]
  exclude_patterns?: string[]
  database_template_id?: string | null
  archive_name_template: string
  compression: string
  custom_flags?: string | null
  upload_ratelimit_kib?: number | null
  upload_ratelimit_schedule_policies?: UploadRatelimitSchedulePolicy[]
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
  script_hooks?: BackupPlanScriptHook[]
  run_repository_scripts: boolean
  run_prune_after: boolean
  run_compact_after: boolean
  run_check_after: boolean
  check_max_duration: number
  check_extra_flags?: string | null
  prune_keep_hourly: number
  prune_keep_daily: number
  prune_keep_weekly: number
  prune_keep_monthly: number
  prune_keep_quarterly: number
  prune_keep_yearly: number
  prune_keep_within?: string | null
  repositories: BackupPlanRepositoryLink[]
  clear_legacy_source_repository_ids?: number[]
}
