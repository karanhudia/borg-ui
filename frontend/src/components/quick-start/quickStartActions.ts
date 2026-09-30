import { createInitialState } from '../../pages/backup-plans/state'
import type { RepositoryData } from '../../services/api'
import type { BackupPlanData, SourceLocation } from '../../types'
import { buildBackupPlanPayload } from '../../utils/backupPlanPayload'
import { appExcludePatterns, renderAppScript } from '../app-templates/appTemplates'
import { usesEncryption, type QuickStartAnswers } from './quickStartState'

export type QuickStartAction = 'create_repository' | 'create_script' | 'create_plan'

// Ids of what each finished action created. Retry skips any action whose id is set.
export interface QuickStartResults {
  repositoryId?: number
  scriptId?: number
  planId?: number
}

const RESULT_KEY: Record<QuickStartAction, keyof QuickStartResults> = {
  create_repository: 'repositoryId',
  create_script: 'scriptId',
  create_plan: 'planId',
}

export function buildQuickStartActions(answers: QuickStartAnswers): QuickStartAction[] {
  return appScriptPayload(answers)
    ? ['create_repository', 'create_script', 'create_plan']
    : ['create_repository', 'create_plan']
}

function appRoot(answers: QuickStartAnswers): string {
  return answers.sourcePaths.find((path) => path.trim()) ?? ''
}

/**
 * The app's pre-backup check as a library script. Plan scripts run on the Borg
 * UI server, so it only applies when the app's folder is on this server.
 */
// ponytail: server-only; SSH/agent sources need per-source script hooks like databases have.
export function appScriptPayload(answers: QuickStartAnswers) {
  const script = answers.app?.pre_backup_script
  if (!answers.app || !script || answers.sourceKind !== 'server' || !appRoot(answers)) return null
  return {
    name: `${script.name}: ${answers.name.trim() || answers.app.name}`,
    description: script.description,
    content: renderAppScript(answers.app, appRoot(answers)) as string,
    timeout: script.timeout,
    run_on: 'always',
    category: 'template',
  }
}

export function pendingActions(
  actions: QuickStartAction[],
  results: QuickStartResults
): QuickStartAction[] {
  return actions.filter((action) => results[RESULT_KEY[action]] === undefined)
}

export function buildRepositoryPayload(answers: QuickStartAnswers): RepositoryData {
  const { settings } = answers
  return {
    name: answers.name.trim(),
    borg_version: settings.borgVersion,
    path: answers.destinationPath.trim(),
    encryption: settings.encryption,
    passphrase: usesEncryption(answers) ? answers.passphrase : undefined,
    compression: settings.compression,
    source_directories: [],
    exclude_patterns: [],
    custom_flags: null,
    mode: 'full',
    ...(answers.destinationKind === 'agent' && answers.sourceAgentId !== ''
      ? {
          executor_type: 'agent' as const,
          execution_target: 'agent' as const,
          storage_backend: 'agent_local' as const,
          agent_machine_id: answers.sourceAgentId,
        }
      : {}),
    ...(answers.destinationKind === 'ssh' && answers.destinationConnectionId !== ''
      ? {
          connection_id: answers.destinationConnectionId,
          storage_backend: 'ssh' as const,
          execution_target: 'ssh' as const,
          executor_type: 'server' as const,
        }
      : {}),
  }
}

function sourceLocation(answers: QuickStartAnswers, paths: string[]): SourceLocation {
  if (answers.sourceKind === 'ssh' && answers.sourceConnectionId !== '') {
    return {
      source_type: 'remote',
      source_ssh_connection_id: answers.sourceConnectionId,
      agent_machine_id: null,
      paths,
    }
  }
  if (answers.sourceKind === 'agent' && answers.sourceAgentId !== '') {
    return {
      source_type: 'agent',
      source_ssh_connection_id: null,
      agent_machine_id: answers.sourceAgentId,
      paths,
    }
  }
  return { source_type: 'local', source_ssh_connection_id: null, agent_machine_id: null, paths }
}

export function buildPlanPayload(
  answers: QuickStartAnswers,
  repositoryId: number,
  scriptId?: number
): BackupPlanData {
  const { settings } = answers
  const paths = answers.sourcePaths.map((path) => path.trim()).filter(Boolean)
  return buildBackupPlanPayload({
    ...createInitialState(),
    name: answers.name.trim(),
    sourceDirectories: paths,
    sourceLocations: [sourceLocation(answers, paths)],
    repositoryIds: [repositoryId],
    excludePatterns: answers.app ? appExcludePatterns(appRoot(answers), answers.appExcludes) : [],
    preBackupScriptId: scriptId ?? null,
    compression: settings.compression,
    scheduleEnabled: settings.scheduleEnabled,
    cronExpression: answers.cronExpression,
    timezone: answers.timezone,
    runPruneAfter: settings.runPruneAfter,
    runCompactAfter: settings.runCompactAfter,
    runCheckAfter: settings.runCheckAfter,
    pruneKeepWithin: settings.prune.keepWithin,
    pruneKeepHourly: settings.prune.keepHourly,
    pruneKeepDaily: settings.prune.keepDaily,
    pruneKeepWeekly: settings.prune.keepWeekly,
    pruneKeepMonthly: settings.prune.keepMonthly,
    pruneKeepQuarterly: settings.prune.keepQuarterly,
    pruneKeepYearly: settings.prune.keepYearly,
  })
}
