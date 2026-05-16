import type { BackupPlanData } from '../types'

export interface BackupPlanPayloadState {
  name: string
  description: string
  enabled: boolean
  sourceType: 'local' | 'remote'
  sourceSshConnectionId: number | ''
  sourceDirectories: string[]
  excludePatterns: string[]
  repositoryIds: number[]
  compression: string
  archiveNameTemplate: string
  customFlags: string
  uploadRatelimitMb: string
  repositoryRunMode: 'series' | 'parallel'
  maxParallelRepositories: number
  failureBehavior: 'continue' | 'stop'
  scheduleEnabled: boolean
  cronExpression: string
  timezone: string
  preBackupScriptId: number | null
  postBackupScriptId: number | null
  preBackupScriptParameters: Record<string, string>
  postBackupScriptParameters: Record<string, string>
  runRepositoryScripts: boolean
  runPruneAfter: boolean
  runCompactAfter: boolean
  runCheckAfter: boolean
  checkMaxDuration: number
  pruneKeepHourly: number
  pruneKeepDaily: number
  pruneKeepWeekly: number
  pruneKeepMonthly: number
  pruneKeepQuarterly: number
  pruneKeepYearly: number
}

function mbToKib(value: string): number | null {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return Math.round(parsed * 1024)
}

export function buildBackupPlanPayload(
  state: BackupPlanPayloadState,
  clearLegacySourceRepositoryIds: number[] = []
): BackupPlanData {
  return {
    name: state.name.trim(),
    description: state.description.trim() || null,
    enabled: state.enabled,
    source_type: state.sourceType,
    source_ssh_connection_id:
      state.sourceType === 'remote' && state.sourceSshConnectionId
        ? Number(state.sourceSshConnectionId)
        : null,
    source_directories: state.sourceDirectories,
    exclude_patterns: state.excludePatterns,
    archive_name_template: state.archiveNameTemplate.trim() || '{plan_name}-{repo_name}-{now}',
    compression: state.compression,
    custom_flags: state.customFlags.trim() || null,
    upload_ratelimit_kib: mbToKib(state.uploadRatelimitMb),
    repository_run_mode: state.repositoryRunMode,
    max_parallel_repositories:
      state.repositoryRunMode === 'parallel' ? state.maxParallelRepositories : 1,
    failure_behavior: state.failureBehavior,
    schedule_enabled: state.scheduleEnabled,
    cron_expression: state.scheduleEnabled ? state.cronExpression : null,
    timezone: state.timezone,
    pre_backup_script_id: state.preBackupScriptId,
    post_backup_script_id: state.postBackupScriptId,
    pre_backup_script_parameters: state.preBackupScriptParameters,
    post_backup_script_parameters: state.postBackupScriptParameters,
    run_repository_scripts: state.runRepositoryScripts,
    run_prune_after: state.runPruneAfter,
    run_compact_after: state.runCompactAfter,
    run_check_after: state.runCheckAfter,
    check_max_duration: state.checkMaxDuration,
    prune_keep_hourly: state.pruneKeepHourly,
    prune_keep_daily: state.pruneKeepDaily,
    prune_keep_weekly: state.pruneKeepWeekly,
    prune_keep_monthly: state.pruneKeepMonthly,
    prune_keep_quarterly: state.pruneKeepQuarterly,
    prune_keep_yearly: state.pruneKeepYearly,
    repositories: state.repositoryIds.map((repositoryId, index) => ({
      repository_id: repositoryId,
      enabled: true,
      execution_order: index + 1,
      compression_source: 'plan',
      compression_override: null,
      custom_flags_override: null,
      upload_ratelimit_kib_override: null,
      failure_behavior_override: null,
    })),
    clear_legacy_source_repository_ids: clearLegacySourceRepositoryIds,
  }
}
