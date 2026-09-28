import { createInitialState } from '../../pages/backup-plans/state'
import type { RepositoryData } from '../../services/api'
import type { BackupPlanData, SourceLocation } from '../../types'
import { buildBackupPlanPayload } from '../../utils/backupPlanPayload'
import { usesEncryption, type QuickStartAnswers } from './quickStartState'

export type QuickStartAction = 'create_repository' | 'create_plan'

// Ids of what each finished action created. Retry skips any action whose id is set.
export interface QuickStartResults {
  repositoryId?: number
  planId?: number
}

const RESULT_KEY: Record<QuickStartAction, keyof QuickStartResults> = {
  create_repository: 'repositoryId',
  create_plan: 'planId',
}

export function buildQuickStartActions(_answers: QuickStartAnswers): QuickStartAction[] {
  return ['create_repository', 'create_plan']
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

export function buildPlanPayload(answers: QuickStartAnswers, repositoryId: number): BackupPlanData {
  const { settings } = answers
  const paths = answers.sourcePaths.map((path) => path.trim()).filter(Boolean)
  return buildBackupPlanPayload({
    ...createInitialState(),
    name: answers.name.trim(),
    sourceDirectories: paths,
    sourceLocations: [sourceLocation(answers, paths)],
    repositoryIds: [repositoryId],
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
