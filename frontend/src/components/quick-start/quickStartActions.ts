import { createInitialState } from '../../pages/backup-plans/state'
import type { RepositoryData } from '../../services/api'
import type { BackupPlanData } from '../../types'
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
  }
}

export function buildPlanPayload(answers: QuickStartAnswers, repositoryId: number): BackupPlanData {
  const { settings } = answers
  const paths = answers.sourcePaths.map((path) => path.trim()).filter(Boolean)
  return buildBackupPlanPayload({
    ...createInitialState(),
    name: answers.name.trim(),
    sourceType: 'local',
    sourceDirectories: paths,
    sourceLocations: [
      { source_type: 'local', source_ssh_connection_id: null, agent_machine_id: null, paths },
    ],
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
