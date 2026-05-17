import { getDefaultRepositoryEncryption } from '../../components/wizard'
import { getBrowserTimeZone } from '../../utils/dateUtils'
import type { BackupPlan, SourceLocation, SourceType } from '../../types'
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
  runRepositoryScripts: true,
  runPruneAfter: false,
  runCompactAfter: false,
  runCheckAfter: false,
  checkMaxDuration: 3600,
  pruneKeepHourly: 0,
  pruneKeepDaily: 7,
  pruneKeepWeekly: 4,
  pruneKeepMonthly: 6,
  pruneKeepQuarterly: 0,
  pruneKeepYearly: 1,
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

function normalizePlanSourceLocations(plan: BackupPlan): SourceLocation[] {
  const grouped: SourceLocation[] = (plan.source_locations || [])
    .map<SourceLocation | null>((location) => {
      const paths = (location.paths || []).map((path) => path.trim()).filter(Boolean)
      if (paths.length === 0) return null
      if (location.source_type === 'remote') {
        const connectionId = location.source_ssh_connection_id
        if (!connectionId) return null
        return {
          source_type: 'remote' as const,
          source_ssh_connection_id: Number(connectionId),
          paths,
        }
      }
      return {
        source_type: 'local' as const,
        source_ssh_connection_id: null,
        paths,
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
        paths: plan.source_directories,
      },
    ]
  }
  return [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
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

export function planToState(plan: BackupPlan): WizardState {
  const repositoryLinks = (plan.repositories || [])
    .filter((link) => link.enabled)
    .sort((a, b) => a.execution_order - b.execution_order)
  const sourceLocations = normalizePlanSourceLocations(plan)
  const sourceDirectories = sourceLocations.length
    ? sourceLocations.flatMap((location) => location.paths)
    : plan.source_directories || []

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
    repositoryRunMode: plan.repository_run_mode || 'series',
    maxParallelRepositories: plan.max_parallel_repositories || 1,
    failureBehavior: plan.failure_behavior || 'continue',
    scheduleEnabled: Boolean(plan.schedule_enabled),
    cronExpression: plan.cron_expression || '0 21 * * *',
    timezone: plan.timezone || getBrowserTimeZone(),
    preBackupScriptId: plan.pre_backup_script_id || null,
    postBackupScriptId: plan.post_backup_script_id || null,
    preBackupScriptParameters: plan.pre_backup_script_parameters || {},
    postBackupScriptParameters: plan.post_backup_script_parameters || {},
    runRepositoryScripts: plan.run_repository_scripts ?? true,
    runPruneAfter: Boolean(plan.run_prune_after),
    runCompactAfter: Boolean(plan.run_compact_after),
    runCheckAfter: Boolean(plan.run_check_after),
    checkMaxDuration: plan.check_max_duration ?? 3600,
    pruneKeepHourly: plan.prune_keep_hourly ?? 0,
    pruneKeepDaily: plan.prune_keep_daily ?? 7,
    pruneKeepWeekly: plan.prune_keep_weekly ?? 4,
    pruneKeepMonthly: plan.prune_keep_monthly ?? 6,
    pruneKeepQuarterly: plan.prune_keep_quarterly ?? 0,
    pruneKeepYearly: plan.prune_keep_yearly ?? 1,
  }
}

export function getCreatedRepositoryId(response: unknown): number | null {
  const data = (response as { data?: { id?: number; repository?: { id?: number } } })?.data
  return data?.repository?.id ?? data?.id ?? null
}
