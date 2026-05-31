import type {
  BackupPlanData,
  SourceDatabaseSelection,
  SourceLocation,
  SourceSnapshotConfig,
  SourceType,
} from '../types'

export interface BackupPlanPayloadState {
  name: string
  description: string
  enabled: boolean
  sourceType: SourceType
  sourceSshConnectionId: number | ''
  sourceDirectories: string[]
  sourceLocations?: SourceLocation[]
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
  checkExtraFlags: string
  pruneKeepHourly: number
  pruneKeepDaily: number
  pruneKeepWeekly: number
  pruneKeepMonthly: number
  pruneKeepQuarterly: number
  pruneKeepYearly: number
  // Set when the plan source came in via the Database tab (detected DB or
  // template pick). Lets the dialog open on the right tab on edit and the
  // backend remember the template choice across reloads. Null/undefined for
  // plain file plans.
  databaseTemplateId?: string | null
}

function mbToKib(value: string): number | null {
  const parsed = Number(value)
  if (!Number.isFinite(parsed) || parsed <= 0) return null
  return Math.round(parsed * 1024)
}

function normalizeSourceLocations(state: BackupPlanPayloadState): SourceLocation[] {
  const normalizeScriptId = (value?: number | null): number | null => {
    const parsed = Number(value)
    return Number.isInteger(parsed) && parsed > 0 ? parsed : null
  }

  const normalizeScriptParameters = (
    parameters?: Record<string, string> | null
  ): Record<string, string> => {
    return Object.fromEntries(
      Object.entries(parameters || {})
        .map(([key, value]) => [key.trim(), String(value).trim()] as const)
        .filter(([key, value]) => key.length > 0 && value.length > 0)
    )
  }

  const normalizeSnapshot = (location: SourceLocation): SourceSnapshotConfig | undefined => {
    if (location.source_type !== 'local' || !location.snapshot) return undefined
    if (location.snapshot.provider === 'btrfs') {
      return {
        provider: 'btrfs',
        staging_path: location.snapshot.staging_path?.trim() || '/var/tmp/borg-ui/snapshots',
        recursive: Boolean(location.snapshot.recursive),
      }
    }
    if (location.snapshot.provider === 'zfs') {
      const dataset = location.snapshot.dataset?.trim()
      const mountpoint = location.snapshot.mountpoint?.trim()
      if (!dataset || !mountpoint) return undefined
      return {
        provider: 'zfs',
        dataset,
        mountpoint,
        recursive: Boolean(location.snapshot.recursive),
      }
    }
    return undefined
  }

  const normalizeDatabase = (
    location: SourceLocation,
    paths: string[]
  ): SourceDatabaseSelection | undefined => {
    if (!location.database) return undefined
    const backupPaths = (location.database.backup_paths || paths)
      .map((path) => path.trim())
      .filter(Boolean)
    if (backupPaths.length === 0) return undefined
    const captureMode = location.database.capture_mode === 'original' ? 'original' : 'dump'
    const dumpPath =
      captureMode === 'dump' ? location.database.dump_path?.trim() || backupPaths[0] : null
    const normalized: SourceDatabaseSelection = {
      template_id: location.database.template_id?.trim() || 'database',
      engine: location.database.engine?.trim() || 'Database',
      display_name:
        location.database.display_name?.trim() || location.database.engine?.trim() || 'Database',
      backup_strategy: location.database.backup_strategy?.trim() || 'logical_dump',
      detected_source_path: location.database.detected_source_path?.trim() || null,
      detection_label: location.database.detection_label?.trim() || null,
      capture_mode: captureMode,
      dump_path: dumpPath,
      backup_paths: backupPaths,
      script_execution_target: location.database.script_execution_target || 'source',
    }
    const preScriptId = normalizeScriptId(location.database.pre_backup_script_id)
    const postScriptId = normalizeScriptId(location.database.post_backup_script_id)
    if (preScriptId) normalized.pre_backup_script_id = preScriptId
    if (postScriptId) normalized.post_backup_script_id = postScriptId
    if (preScriptId || location.database.pre_backup_script_parameters) {
      normalized.pre_backup_script_parameters = normalizeScriptParameters(
        location.database.pre_backup_script_parameters
      )
    }
    if (postScriptId || location.database.post_backup_script_parameters) {
      normalized.post_backup_script_parameters = normalizeScriptParameters(
        location.database.post_backup_script_parameters
      )
    }
    const scriptExecutionOrder = normalizeScriptId(location.database.script_execution_order)
    if (scriptExecutionOrder) normalized.script_execution_order = scriptExecutionOrder
    return normalized
  }

  const grouped: SourceLocation[] = (state.sourceLocations || [])
    .map<SourceLocation | null>((location) => {
      const paths = location.paths.map((path) => path.trim()).filter(Boolean)
      if (paths.length === 0) return null
      if (location.source_type === 'remote') {
        const connectionId = location.source_ssh_connection_id
        if (!connectionId) return null
        const database = normalizeDatabase(location, paths)
        return {
          source_type: 'remote' as const,
          source_ssh_connection_id: Number(connectionId),
          agent_machine_id: null,
          paths,
          ...(database ? { database } : {}),
        }
      }
      if (location.source_type === 'agent') {
        const agentMachineId = location.agent_machine_id
        if (!agentMachineId) return null
        const database = normalizeDatabase(location, paths)
        return {
          source_type: 'agent' as const,
          source_ssh_connection_id: null,
          agent_machine_id: Number(agentMachineId),
          paths,
          ...(database ? { database } : {}),
        }
      }
      const snapshot = normalizeSnapshot(location)
      const database = normalizeDatabase(location, paths)
      return {
        source_type: 'local' as const,
        source_ssh_connection_id: null,
        agent_machine_id: null,
        paths,
        ...(snapshot ? { snapshot } : {}),
        ...(database ? { database } : {}),
      }
    })
    .filter((location): location is SourceLocation => location !== null)

  if (grouped.length > 0) return grouped
  if (state.sourceDirectories.length === 0) return []

  if (state.sourceType === 'remote' && state.sourceSshConnectionId) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: Number(state.sourceSshConnectionId),
        agent_machine_id: null,
        paths: state.sourceDirectories,
      },
    ]
  }

  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: state.sourceDirectories,
    },
  ]
}

function sourceTypeFromLocations(locations: SourceLocation[], fallback: SourceType): SourceType {
  if (locations.length === 0) return fallback
  if (locations.length > 1) return 'mixed'
  return locations[0].source_type
}

function sourceConnectionFromLocations(locations: SourceLocation[]): number | null {
  if (locations.length !== 1 || locations[0].source_type !== 'remote') return null
  return locations[0].source_ssh_connection_id
    ? Number(locations[0].source_ssh_connection_id)
    : null
}

export function buildBackupPlanPayload(
  state: BackupPlanPayloadState,
  clearLegacySourceRepositoryIds: number[] = []
): BackupPlanData {
  const sourceLocations = normalizeSourceLocations(state)
  const sourceDirectories = sourceLocations.length
    ? sourceLocations.flatMap((location) => location.paths)
    : state.sourceDirectories

  return {
    name: state.name.trim(),
    description: state.description.trim() || null,
    enabled: state.enabled,
    source_type: sourceTypeFromLocations(sourceLocations, state.sourceType),
    source_ssh_connection_id: sourceConnectionFromLocations(sourceLocations),
    source_directories: sourceDirectories,
    source_locations: sourceLocations,
    exclude_patterns: state.excludePatterns,
    database_template_id: state.databaseTemplateId ?? null,
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
    check_extra_flags: state.checkExtraFlags.trim() || null,
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
