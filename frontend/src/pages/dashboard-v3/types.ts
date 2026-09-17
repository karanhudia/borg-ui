import type { StoredPruneRetention } from '../../types/archives'

export interface SpaceSaving {
  repository_id: number
  repository_name: string
  candidate: string
  label: string
  retention: StoredPruneRetention | null
  freed_at_least: number
  computed_at: string
  stale: boolean
}

export type UpcomingTask = {
  id: number | string
  type: string
  name?: string
  repositories?: string[]
  repository?: string
  cron?: string
  timezone?: string | null
  next_run?: string | null
}

export type ActivityEntry = {
  id: number
  type: string
  status: string
  repository: string
  timestamp: string
  message: string
  error: string | null
}

export interface DashboardOverview {
  summary: {
    total_repositories: number
    local_repositories: number
    ssh_repositories: number
    active_schedules: number
    total_schedules: number
    active_backup_plans?: number
    total_backup_plans?: number
    active_automations?: number
    total_automations?: number
    success_rate_30d: number
    successful_jobs_30d: number
    failed_jobs_30d: number
    total_jobs_30d: number
  }
  storage: {
    total_size: string
    total_size_bytes: number
    total_archives: number
    average_dedup_ratio: number | null
    breakdown: Array<{ name: string; size: string; size_bytes: number; percentage: number }>
  }
  repository_health: Array<{
    id: number
    name: string
    type: string
    mode: 'full' | 'observe'
    last_backup: string | null
    last_check: string | null
    last_compact: string | null
    last_restore_check: string | null
    archive_count: number
    total_size: string
    health_status: 'healthy' | 'warning' | 'critical'
    warnings: string[]
    next_run: string | null
    has_schedule: boolean
    schedule_enabled: boolean
    schedule_name: string | null
    schedule_timezone?: string | null
    backup_plan_count?: number
    backup_plan_scheduled_count?: number
    backup_plan_names?: string[]
    backup_plan_next_run?: string | null
    restore_check_configured?: boolean
    latest_restore_check_status?: string | null
    latest_restore_check_error?: string | null
    dimension_health: {
      backup: 'healthy' | 'warning' | 'critical' | 'unknown'
      check: 'healthy' | 'warning' | 'critical' | 'unknown'
      compact: 'healthy' | 'warning' | 'critical' | 'unknown'
      restore?: 'healthy' | 'warning' | 'critical' | 'unknown'
    }
  }>
  upcoming_tasks: UpcomingTask[]
  space_savings: SpaceSaving[]
  // Per calendar day (in the zone the request named) and job type: how
  // many runs started and how many of them failed, last 14 days.
  // Optional for a remote backend of the same major version that still
  // sends `activity_feed` only; the page then derives both from the feed.
  activity_timeline?: Array<{
    date: string
    type: string
    total: number
    failed: number
  }>
  // Failed runs of the timeline window that no later completed run of the
  // same type on the same repository has resolved, newest first.
  current_failures?: Array<ActivityEntry>
  // The previous release's feed: every run of the window. A server of this
  // release fills it with the current failures for one release.
  activity_feed?: Array<ActivityEntry>
  system_metrics: {
    cpu_usage: number
    cpu_count: number
    memory_usage: number
    memory_total: number
    memory_available: number
    disk_usage: number
    disk_total: number
    disk_free: number
  }
}
