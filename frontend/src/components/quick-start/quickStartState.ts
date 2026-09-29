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
  sourcePaths: string[]
  destinationKind: QuickStartDestinationKind
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
    sourcePaths: [],
    destinationKind: 'server',
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

function isInsidePath(child: string, parent: string): boolean {
  const normalize = normalizePath
  const c = normalize(child)
  const p = normalize(parent)
  if (p === '/') return true
  return c === p || c.startsWith(`${p}/`)
}

// A local repository inside one of the folders it backs up would back itself up.
export function destinationInsideSource(answers: QuickStartAnswers): boolean {
  if (answers.sourceKind !== 'server' || answers.destinationKind !== 'server') return false
  if (!answers.destinationPath.trim()) return false
  return answers.sourcePaths.some((source) => isInsidePath(answers.destinationPath, source))
}

export function isStepValid(step: QuickStartStepKey, answers: QuickStartAnswers): boolean {
  switch (step) {
    case 'what':
    case 'connect':
    case 'review':
      return true
    case 'folders':
      return answers.sourcePaths.some((path) => path.trim())
    case 'destination':
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

// /local is the default host mount inside the container (LOCAL_MOUNT_POINTS).
export function suggestedDestinationPath(name: string): string {
  const slug = name
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
  return `/local/borg-backups/${slug || 'backup'}`
}

export interface QuickStartStepProps {
  answers: QuickStartAnswers
  onChange: (patch: Partial<QuickStartAnswers>) => void
}

// Must be referentially stable: CompressionSettings calls it from an effect.
export type QuickStartSettingsChange = (patch: Partial<QuickStartSettings>) => void
