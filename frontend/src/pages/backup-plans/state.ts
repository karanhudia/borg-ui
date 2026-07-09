import { getDefaultRepositoryEncryption } from '../../components/wizard'
import { getBrowserTimeZone } from '../../utils/dateUtils'
import type {
  BackupPlan,
  BackupPlanScriptHook,
  SourceContainerSelection,
  SourceDatabaseSelection,
  SourceLocation,
  SourceType,
  UploadRatelimitSchedulePolicy,
} from '../../types'
import type { BasicRepositoryState, WizardState } from './types'

export const createInitialState = (): WizardState => ({
  name: '',
  description: '',
  enabled: true,
  sourceType: 'local',
  sourceSshConnectionId: '',
  sourceDirectories: [],
  sourceLocations: [],
  excludePatterns: [],
  repositoryIds: [],
  compression: 'lz4',
  archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
  customFlags: '',
  uploadRatelimitMb: '',
  uploadRatelimitSchedulePolicies: [],
  repositoryRunMode: 'series',
  maxParallelRepositories: 1,
  failureBehavior: 'continue',
  scheduleEnabled: false,
  cronExpression: '0 21 * * *',
  timezone: getBrowserTimeZone(),
  preBackupScriptId: null,
  postBackupScriptId: null,
  preBackupScriptParameters: {},
  postBackupScriptParameters: {},
  scriptHooks: [],
  runRepositoryScripts: true,
  runPruneAfter: false,
  runCompactAfter: false,
  runCheckAfter: false,
  checkMaxDuration: 3600,
  checkExtraFlags: '',
  pruneKeepHourly: 0,
  pruneKeepDaily: 7,
  pruneKeepWeekly: 4,
  pruneKeepMonthly: 6,
  pruneKeepQuarterly: 0,
  pruneKeepYearly: 1,
  pruneKeepWithin: '',
  databaseTemplateId: null,
})

export const createInitialBasicRepositoryState = (): BasicRepositoryState => ({
  name: '',
  borgVersion: 1,
  path: '',
  encryption: getDefaultRepositoryEncryption(1),
  passphrase: '',
})

function kibToMb(value?: number | null): string {
  if (!value || value <= 0) return ''
  return String(Math.round((value / 1024) * 100) / 100)
}

function normalizeUploadRatelimitSchedulePolicies(
  policies?: UploadRatelimitSchedulePolicy[] | null
) {
  return (policies || []).map((policy) => ({
    label: policy.label || '',
    startTime: policy.start_time || '',
    endTime: policy.end_time || '',
    uploadRatelimitMb: kibToMb(policy.upload_ratelimit_kib),
  }))
}

function normalizePlanSourceLocations(plan: BackupPlan): SourceLocation[] {
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
        .filter(([key]) => key.length > 0)
    )
  }

  const normalizeScriptExecutionTarget = (
    value?: SourceDatabaseSelection['script_execution_target'] | string | null
  ): SourceDatabaseSelection['script_execution_target'] => {
    return value === 'server' ? 'server' : 'source'
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
    const normalized: SourceDatabaseSelection = {
      template_id: location.database.template_id?.trim() || 'database',
      engine: location.database.engine?.trim() || 'Database',
      display_name:
        location.database.display_name?.trim() || location.database.engine?.trim() || 'Database',
      backup_strategy: location.database.backup_strategy?.trim() || 'logical_dump',
      detected_source_path: location.database.detected_source_path?.trim() || null,
      detection_label: location.database.detection_label?.trim() || null,
      capture_mode: captureMode,
      dump_path:
        captureMode === 'dump' ? location.database.dump_path?.trim() || backupPaths[0] : null,
      backup_paths: backupPaths,
      script_execution_target: normalizeScriptExecutionTarget(
        location.database.script_execution_target
      ),
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

  const normalizeContainer = (
    location: SourceLocation,
    paths: string[]
  ): SourceContainerSelection | undefined => {
    if (!location.container) return undefined
    const containerName = location.container.container_name?.trim()
    const exportPath = location.container.export_path?.trim() || paths[0]
    if (!containerName || !exportPath) return undefined
    const normalized: SourceContainerSelection = {
      container_name: containerName,
      display_name: location.container.display_name?.trim() || containerName,
      image: location.container.image?.trim() || null,
      backup_mode: 'export',
      export_path: exportPath,
      script_execution_target: normalizeScriptExecutionTarget(
        location.container.script_execution_target
      ),
    }
    const preScriptId = normalizeScriptId(location.container.pre_backup_script_id)
    const postScriptId = normalizeScriptId(location.container.post_backup_script_id)
    if (preScriptId) normalized.pre_backup_script_id = preScriptId
    if (postScriptId) normalized.post_backup_script_id = postScriptId
    if (preScriptId || location.container.pre_backup_script_parameters) {
      normalized.pre_backup_script_parameters = normalizeScriptParameters(
        location.container.pre_backup_script_parameters
      )
    }
    if (postScriptId || location.container.post_backup_script_parameters) {
      normalized.post_backup_script_parameters = normalizeScriptParameters(
        location.container.post_backup_script_parameters
      )
    }
    const scriptExecutionOrder = normalizeScriptId(location.container.script_execution_order)
    if (scriptExecutionOrder) normalized.script_execution_order = scriptExecutionOrder
    return normalized
  }

  const grouped: SourceLocation[] = (plan.source_locations || [])
    .map<SourceLocation | null>((location) => {
      const paths = (location.paths || []).map((path) => path.trim()).filter(Boolean)
      if (paths.length === 0) return null
      if (location.source_type === 'remote') {
        const connectionId = location.source_ssh_connection_id
        if (!connectionId) return null
        const database = normalizeDatabase(location, paths)
        const container = normalizeContainer(location, paths)
        return {
          source_type: 'remote' as const,
          source_ssh_connection_id: Number(connectionId),
          agent_machine_id: null,
          paths,
          ...(database ? { database } : {}),
          ...(container ? { container } : {}),
        }
      }
      if (location.source_type === 'agent') {
        const agentMachineId = location.agent_machine_id
        if (!agentMachineId) return null
        const database = normalizeDatabase(location, paths)
        const container = normalizeContainer(location, paths)
        return {
          source_type: 'agent' as const,
          source_ssh_connection_id: null,
          agent_machine_id: Number(agentMachineId),
          paths,
          ...(database ? { database } : {}),
          ...(container ? { container } : {}),
        }
      }
      const database = normalizeDatabase(location, paths)
      const container = normalizeContainer(location, paths)
      return {
        source_type: 'local' as const,
        source_ssh_connection_id: null,
        agent_machine_id: null,
        paths,
        ...(database ? { database } : {}),
        ...(container ? { container } : {}),
      }
    })
    .filter((location): location is SourceLocation => location !== null)

  if (grouped.length > 0) return grouped
  if (!plan.source_directories?.length) return []
  if (plan.source_type === 'remote' || plan.source_ssh_connection_id) {
    return [
      {
        source_type: 'remote',
        source_ssh_connection_id: plan.source_ssh_connection_id || null,
        agent_machine_id: null,
        paths: plan.source_directories,
      },
    ]
  }
  if (plan.source_type === 'agent') {
    return []
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: plan.source_directories,
    },
  ]
}

function sourceTypeFromLocations(locations: SourceLocation[], fallback: SourceType): SourceType {
  if (locations.length === 0) return fallback
  if (locations.length > 1) return 'mixed'
  return locations[0].source_type
}

function sourceConnectionFromLocations(locations: SourceLocation[]): number | '' {
  if (locations.length !== 1 || locations[0].source_type !== 'remote') return ''
  return locations[0].source_ssh_connection_id ? Number(locations[0].source_ssh_connection_id) : ''
}

function normalizePlanScriptHooks(plan: BackupPlan): BackupPlanScriptHook[] {
  if (plan.script_hooks && plan.script_hooks.length > 0) {
    return plan.script_hooks
      .filter((hook) => {
        const hasLibrary =
          Number.isInteger(Number(hook.script_id)) && Number(hook.script_id) > 0
        const hasAgent = Boolean((hook.agent_script_name || '').trim())
        return hasLibrary || hasAgent
      })
      .map((hook, index) => {
        const agentName = (hook.agent_script_name || '').trim()
        const isAgent = Boolean(agentName)
        return {
          ...hook,
          script_id: isAgent ? null : Number(hook.script_id),
          agent_script_name: isAgent ? agentName : null,
          is_agent_script: isAgent,
          execution_order:
            Number(hook.execution_order) > 0 ? Number(hook.execution_order) : index + 1,
          enabled: hook.enabled !== false,
          continue_on_error: Boolean(hook.continue_on_error),
          skip_on_failure: Boolean(hook.skip_on_failure),
          parameter_values: hook.parameter_values || {},
        }
      })
  }

  const hooks: BackupPlanScriptHook[] = []
  if (plan.pre_backup_script_id) {
    hooks.push({
      script_id: plan.pre_backup_script_id,
      hook_type: 'pre-backup',
      execution_order: 1,
      enabled: true,
      continue_on_error: false,
      skip_on_failure: false,
      parameter_values: plan.pre_backup_script_parameters || {},
    })
  }
  if (plan.post_backup_script_id) {
    hooks.push({
      script_id: plan.post_backup_script_id,
      hook_type: 'post-backup',
      execution_order: 1,
      enabled: true,
      parameter_values: plan.post_backup_script_parameters || {},
    })
  }
  return hooks
}

export function planToState(plan: BackupPlan): WizardState {
  const repositoryLinks = (plan.repositories || [])
    .filter((link) => link.enabled)
    .sort((a, b) => a.execution_order - b.execution_order)
  const sourceLocations = normalizePlanSourceLocations(plan)
  const sourceDirectories = sourceLocations.length
    ? sourceLocations.flatMap((location) => location.paths)
    : plan.source_directories || []
  const scriptHooks = normalizePlanScriptHooks(plan)
  // Legacy single-FK fields are library-only; agent hooks are excluded.
  const firstPreHook = scriptHooks
    .filter((hook) => hook.hook_type === 'pre-backup' && hook.enabled !== false && hook.script_id)
    .sort((left, right) => left.execution_order - right.execution_order)[0]
  const firstPostHook = scriptHooks
    .filter((hook) => hook.hook_type === 'post-backup' && hook.enabled !== false && hook.script_id)
    .sort((left, right) => left.execution_order - right.execution_order)[0]

  return {
    name: plan.name,
    description: plan.description || '',
    enabled: plan.enabled,
    sourceType: sourceTypeFromLocations(sourceLocations, plan.source_type),
    sourceSshConnectionId: sourceConnectionFromLocations(sourceLocations),
    sourceDirectories,
    sourceLocations,
    excludePatterns: plan.exclude_patterns || [],
    repositoryIds: repositoryLinks.map((link) => link.repository_id),
    compression: plan.compression || 'lz4',
    archiveNameTemplate: plan.archive_name_template || '{plan_name}-{repo_name}-{now}',
    customFlags: plan.custom_flags || '',
    uploadRatelimitMb: kibToMb(plan.upload_ratelimit_kib),
    uploadRatelimitSchedulePolicies: normalizeUploadRatelimitSchedulePolicies(
      plan.upload_ratelimit_schedule_policies
    ),
    repositoryRunMode: plan.repository_run_mode || 'series',
    maxParallelRepositories: plan.max_parallel_repositories || 1,
    failureBehavior: plan.failure_behavior || 'continue',
    scheduleEnabled: Boolean(plan.schedule_enabled),
    cronExpression: plan.cron_expression || '0 21 * * *',
    timezone: plan.timezone || getBrowserTimeZone(),
    preBackupScriptId: firstPreHook?.script_id ?? plan.pre_backup_script_id ?? null,
    postBackupScriptId: firstPostHook?.script_id ?? plan.post_backup_script_id ?? null,
    preBackupScriptParameters:
      firstPreHook?.parameter_values ?? plan.pre_backup_script_parameters ?? {},
    postBackupScriptParameters:
      firstPostHook?.parameter_values ?? plan.post_backup_script_parameters ?? {},
    scriptHooks,
    runRepositoryScripts: plan.run_repository_scripts ?? true,
    runPruneAfter: Boolean(plan.run_prune_after),
    runCompactAfter: Boolean(plan.run_compact_after),
    runCheckAfter: Boolean(plan.run_check_after),
    checkMaxDuration: plan.check_max_duration ?? 3600,
    checkExtraFlags: plan.check_extra_flags || '',
    pruneKeepHourly: plan.prune_keep_hourly ?? 0,
    pruneKeepDaily: plan.prune_keep_daily ?? 7,
    pruneKeepWeekly: plan.prune_keep_weekly ?? 4,
    pruneKeepMonthly: plan.prune_keep_monthly ?? 6,
    pruneKeepQuarterly: plan.prune_keep_quarterly ?? 0,
    pruneKeepYearly: plan.prune_keep_yearly ?? 1,
    pruneKeepWithin: plan.prune_keep_within || '',
    databaseTemplateId: plan.database_template_id ?? null,
  }
}

export function getCreatedRepositoryId(response: unknown): number | null {
  const data = (response as { data?: { id?: number; repository?: { id?: number } } })?.data
  return data?.repository?.id ?? data?.id ?? null
}
