/**
 * Type definitions for jobs and repositories used across the application
 *
 * Note: Job interface is intentionally flexible to accommodate various job types
 * (backup, restore, check, compact, prune, package) across different pages.
 * Most fields are optional as different contexts provide different subsets of data.
 */

export interface Job {
  id: string | number
  repository_id?: number
  repository?: string | null
  repository_path?: string | null
  type?: string
  status: string
  progress?: number
  progress_message?: string
  started_at?: string | null
  completed_at?: string | null
  error_message?: string | null
  archive_name?: string | null
  package_name?: string | null
  has_logs?: boolean
  triggered_by?: string
  schedule_id?: number | null
  log_file_path?: string | null
  total_files?: number
  processed_files?: number
  total_size?: string
  processed_size?: string
  maintenance_status?: string | null
  scheduled_job_id?: number | null
  progress_details?: unknown
}

export interface Repository {
  id: number
  name: string
  path: string
  mode?: 'full' | 'observe'
  encryption?: string
  compression?: string
  source_directories?: string[]
  exclude_patterns?: string[]
  custom_borg_flags?: string
  passphrase?: string
  repoSshConnectionId?: number
  sourceSshConnectionId?: number
  remote_path?: string
  created_at?: string
  updated_at?: string
}
