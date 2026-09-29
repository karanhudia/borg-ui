import type { PruneSettings } from '../PruneSettingsInput'
import { getDefaultRepositoryEncryption } from '../wizard/repositoryEncryption'
import { getBrowserTimeZone } from '../../utils/dateUtils'

export type QuickStartSourceKind = 'server' | 'ssh' | 'agent'
export type QuickStartDestinationKind = 'server' | 'ssh' | 'agent'
export type QuickStartSchedulePreset = 'daily' | 'every6h' | 'weekly' | 'custom'
export type QuickStartStepKey =
  'what' | 'connect' | 'folders' | 'destination' | 'protect' | 'schedule' | 'review'

export interface QuickStartSettings {
  borgVersion: 1 | 2
  encryption: string
  compression: string
  scheduleEnabled: boolean
  runPruneAfter: boolean
  runCompactAfter: boolean
  runCheckAfter: boolean
  prune: PruneSettings
}

export interface QuickStartAnswers {
  sourceKind: QuickStartSourceKind
  /** SSH connection the files are pulled from (sourceKind 'ssh'). */
  sourceConnectionId: number | ''
  /** Managed agent the files live on (sourceKind 'agent'); its repository lives there too. */
  sourceAgentId: number | ''
  sourcePaths: string[]
  destinationKind: QuickStartDestinationKind
  /** SSH connection the repository lives on (destinationKind 'ssh'). */
  destinationConnectionId: number | ''
  destinationPath: string
  name: string
  passphrase: string
  passphraseConfirm: string
  passphraseSaved: boolean
  schedulePreset: QuickStartSchedulePreset
  cronExpression: string
  timezone: string
  settings: QuickStartSettings
}

export const MIN_PASSPHRASE_LENGTH = 8

export const SCHEDULE_PRESET_CRON: Record<Exclude<QuickStartSchedulePreset, 'custom'>, string> = {
  daily: '0 2 * * *',
  every6h: '0 */6 * * *',
  weekly: '0 2 * * 0',
}

export function createInitialQuickStartAnswers(): QuickStartAnswers {
  return {
    sourceKind: 'server',
    sourceConnectionId: '',
    sourceAgentId: '',
    sourcePaths: [],
    destinationKind: 'server',
    destinationConnectionId: '',
    destinationPath: '',
    name: '',
    passphrase: '',
    passphraseConfirm: '',
    passphraseSaved: false,
    schedulePreset: 'daily',
    cronExpression: SCHEDULE_PRESET_CRON.daily,
    timezone: getBrowserTimeZone(),
    settings: {
      borgVersion: 1,
      encryption: getDefaultRepositoryEncryption(1),
      compression: 'zstd,3',
      scheduleEnabled: true,
      runPruneAfter: true,
      runCompactAfter: true,
      runCheckAfter: true,
      prune: {
        keepWithin: '',
        keepHourly: 0,
        keepDaily: 7,
        keepWeekly: 4,
        keepMonthly: 6,
        keepQuarterly: 0,
        keepYearly: 1,
      },
    },
  }
}

export function visibleSteps(answers: QuickStartAnswers): QuickStartStepKey[] {
  const steps: QuickStartStepKey[] = ['what']
  if (answers.sourceKind !== 'server') steps.push('connect')
  steps.push('folders', 'destination', 'protect', 'schedule', 'review')
  return steps
}

/**
 * The patch for picking a source kind. Folders and the destination belong to
 * the previous machine, so a real change starts them over; re-picking the same
 * kind changes nothing.
 */
export function sourceKindPatch(
  answers: QuickStartAnswers,
  sourceKind: QuickStartSourceKind
): Partial<QuickStartAnswers> {
  if (answers.sourceKind === sourceKind) return {}
  return {
    sourceKind,
    sourcePaths: [],
    // An agent can only back up to its own disk (route planner).
    destinationKind: sourceKind === 'agent' ? 'agent' : 'server',
    destinationConnectionId: '',
    destinationPath: '',
  }
}

export function usesEncryption(answers: QuickStartAnswers): boolean {
  return answers.settings.encryption !== 'none'
}

// Resolves "." and ".." the way the backend's os.path.abspath will, so
// "/local/other/../data/repo" is seen as inside "/local/data".
function normalizePath(value: string): string {
  const segments: string[] = []
  for (const segment of value.trim().split('/')) {
    if (!segment || segment === '.') continue
    if (segment === '..') segments.pop()
    else segments.push(segment)
  }
  return `/${segments.join('/')}`
}

export function isInsidePath(child: string, parent: string): boolean {
  const normalize = normalizePath
  const c = normalize(child)
  const p = normalize(parent)
  if (p === '/') return true
  return c === p || c.startsWith(`${p}/`)
}

function sameMachine(answers: QuickStartAnswers): boolean {
  if (answers.sourceKind === 'server') return answers.destinationKind === 'server'
  if (answers.sourceKind === 'ssh') {
    return (
      answers.destinationKind === 'ssh' &&
      answers.sourceConnectionId !== '' &&
      answers.sourceConnectionId === answers.destinationConnectionId
    )
  }
  // The route planner only allows an agent source into a repository on the same agent.
  return answers.sourceKind === 'agent'
}

// A repository inside one of the folders it backs up would back itself up.
export function destinationInsideSource(answers: QuickStartAnswers): boolean {
  if (!sameMachine(answers)) return false
  if (!answers.destinationPath.trim()) return false
  return answers.sourcePaths.some((source) => isInsidePath(answers.destinationPath, source))
}

export function isStepValid(step: QuickStartStepKey, answers: QuickStartAnswers): boolean {
  switch (step) {
    case 'what':
    case 'review':
      return true
    case 'connect':
      if (answers.sourceKind === 'agent') return answers.sourceAgentId !== ''
      return answers.sourceKind !== 'ssh' || answers.sourceConnectionId !== ''
    case 'folders':
      return answers.sourcePaths.some((path) => path.trim())
    case 'destination':
      if (answers.destinationKind === 'ssh' && answers.destinationConnectionId === '') return false
      return Boolean(answers.destinationPath.trim()) && !destinationInsideSource(answers)
    case 'protect':
      if (!answers.name.trim()) return false
      if (!usesEncryption(answers)) return true
      return (
        answers.passphrase.length >= MIN_PASSPHRASE_LENGTH &&
        answers.passphrase === answers.passphraseConfirm &&
        answers.passphraseSaved
      )
    case 'schedule':
      return !answers.settings.scheduleEnabled || Boolean(answers.cronExpression.trim())
  }
}

// Last path segment of the first folder, used to prefill the name ("home", "etc").
export function suggestedName(answers: QuickStartAnswers): string {
  const first = answers.sourcePaths.find((path) => path.trim())
  if (!first) return ''
  return first.trim().replace(/\/+$/, '').split('/').pop() || 'root'
}

function slugify(name: string): string {
  return (
    name
      .trim()
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, '-')
      .replace(/^-+|-+$/g, '') || 'backup'
  )
}

// /local is the default host mount inside the container (LOCAL_MOUNT_POINTS).
export function suggestedDestinationPath(name: string): string {
  return `/local/borg-backups/${slugify(name)}`
}

/** Under the connection's default path, else the SSH user's home. */
export function suggestedRemoteDestinationPath(
  name: string,
  connection: { username: string; default_path?: string | null }
): string {
  const base =
    connection.default_path?.replace(/\/+$/, '') ||
    (connection.username === 'root' ? '/root' : `/home/${connection.username}`)
  return `${base}/borg-backups/${slugify(name)}`
}

export interface QuickStartStepProps {
  answers: QuickStartAnswers
  onChange: (patch: Partial<QuickStartAnswers>) => void
  /** settings.ssh.manage: may add a new SSH machine, not just pick one. */
  canAddMachine?: boolean
  /** True while the step talks to another machine; the dialog must not close meanwhile. */
  onBusyChange?: (busy: boolean) => void
}

// Must be referentially stable: CompressionSettings calls it from an effect.
export type QuickStartSettingsChange = (patch: Partial<QuickStartSettings>) => void
