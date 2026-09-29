import { describe, expect, it } from 'vitest'

import {
  createInitialQuickStartAnswers,
  destinationInsideSource,
  isStepValid,
  suggestedDestinationPath,
  sourceKindPatch,
  suggestedName,
  suggestedRemoteDestinationPath,
  visibleSteps,
  type QuickStartAnswers,
} from '../quickStartState'

function answers(overrides: Partial<QuickStartAnswers> = {}): QuickStartAnswers {
  return { ...createInitialQuickStartAnswers(), ...overrides }
}

describe('quickStartState', () => {
  it('defaults to a scheduled, self-maintaining backup', () => {
    const initial = createInitialQuickStartAnswers()
    expect(initial.settings).toMatchObject({
      scheduleEnabled: true,
      runPruneAfter: true,
      runCompactAfter: true,
      runCheckAfter: true,
      borgVersion: 1,
    })
    expect(initial.cronExpression).toBe('0 2 * * *')
  })

  it('skips the connect step for files on this server', () => {
    expect(visibleSteps(answers())).toEqual([
      'what',
      'folders',
      'destination',
      'protect',
      'schedule',
      'review',
    ])
    expect(visibleSteps(answers({ sourceKind: 'ssh' }))).toContain('connect')
  })

  it('needs at least one folder', () => {
    expect(isStepValid('folders', answers())).toBe(false)
    expect(isStepValid('folders', answers({ sourcePaths: ['  '] }))).toBe(false)
    expect(isStepValid('folders', answers({ sourcePaths: ['/local/home'] }))).toBe(true)
  })

  it('rejects a local destination inside a source folder', () => {
    const inside = answers({
      sourcePaths: ['/local/home/'],
      destinationPath: '/local/home/backups',
    })
    expect(destinationInsideSource(inside)).toBe(true)
    expect(isStepValid('destination', inside)).toBe(false)

    const sibling = answers({
      sourcePaths: ['/local/home'],
      destinationPath: '/local/homework',
    })
    expect(destinationInsideSource(sibling)).toBe(false)
    expect(isStepValid('destination', sibling)).toBe(true)

    expect(
      destinationInsideSource(answers({ sourcePaths: ['/'], destinationPath: '/local/x' }))
    ).toBe(true)
    expect(
      destinationInsideSource(
        answers({ sourcePaths: ['/local/data'], destinationPath: '/local/other/../data/./repo' })
      )
    ).toBe(true)
  })

  it('requires a matching passphrase that the user confirmed saving', () => {
    const base = answers({ name: 'home' })
    expect(isStepValid('protect', base)).toBe(false)
    const typed = { ...base, passphrase: 'correct horse', passphraseConfirm: 'correct horse' }
    expect(isStepValid('protect', typed)).toBe(false)
    expect(isStepValid('protect', { ...typed, passphraseSaved: true })).toBe(true)
    expect(
      isStepValid('protect', { ...typed, passphraseConfirm: 'other', passphraseSaved: true })
    ).toBe(false)
    expect(
      isStepValid('protect', {
        ...typed,
        passphrase: 'short',
        passphraseConfirm: 'short',
        passphraseSaved: true,
      })
    ).toBe(false)
  })

  it('skips the passphrase when encryption is off', () => {
    const unencrypted = answers({ name: 'home' })
    unencrypted.settings = { ...unencrypted.settings, encryption: 'none' }
    expect(isStepValid('protect', unencrypted)).toBe(true)
    expect(isStepValid('protect', { ...unencrypted, name: ' ' })).toBe(false)
  })

  it('needs a cron expression only while the schedule is on', () => {
    const blank = answers({ cronExpression: '' })
    expect(isStepValid('schedule', blank)).toBe(false)
    blank.settings = { ...blank.settings, scheduleEnabled: false }
    expect(isStepValid('schedule', blank)).toBe(true)
  })

  it('suggests a name and destination from the first folder', () => {
    expect(suggestedName(answers({ sourcePaths: ['/local/home/'] }))).toBe('home')
    expect(suggestedName(answers({ sourcePaths: ['/'] }))).toBe('root')
    expect(suggestedName(answers())).toBe('')
    expect(suggestedDestinationPath('My Photos!')).toBe('/local/borg-backups/my-photos')
    expect(suggestedDestinationPath('')).toBe('/local/borg-backups/backup')
  })
  it('needs a chosen connection for SSH sources and destinations', () => {
    expect(isStepValid('connect', answers({ sourceKind: 'ssh' }))).toBe(false)
    expect(isStepValid('connect', answers({ sourceKind: 'ssh', sourceConnectionId: 3 }))).toBe(true)
    const ssh = answers({ destinationKind: 'ssh', destinationPath: '/srv/borg/home' })
    expect(isStepValid('destination', ssh)).toBe(false)
    expect(isStepValid('destination', { ...ssh, destinationConnectionId: 5 })).toBe(true)
  })

  it('treats the same SSH connection as the same machine', () => {
    const same = answers({
      sourceKind: 'ssh',
      sourceConnectionId: 3,
      sourcePaths: ['/srv/data'],
      destinationKind: 'ssh',
      destinationConnectionId: 3,
      destinationPath: '/srv/data/borg',
    })
    expect(destinationInsideSource(same)).toBe(true)
    expect(destinationInsideSource({ ...same, destinationConnectionId: 4 })).toBe(false)
    // Pulled files stored on this server live on a different machine.
    expect(destinationInsideSource({ ...same, destinationKind: 'server' })).toBe(false)
  })

  it('suggests a remote path under the base path', () => {
    expect(suggestedRemoteDestinationPath('Home', '/srv/')).toBe('/srv/borg-backups/home')
    expect(suggestedRemoteDestinationPath('My Laptop', '/home/alex')).toBe(
      '/home/alex/borg-backups/my-laptop'
    )
  })
  it('starts folders and destination over when the source kind changes', () => {
    const picked = answers({
      sourceKind: 'ssh',
      sourceConnectionId: 3,
      sourcePaths: ['/srv/data'],
      destinationKind: 'ssh',
      destinationConnectionId: 5,
      destinationPath: '/home/bob/borg-backups/data',
    })
    expect(sourceKindPatch(picked, 'ssh')).toEqual({})
    expect(sourceKindPatch(picked, 'server')).toEqual({
      sourceKind: 'server',
      sourcePaths: [],
      destinationKind: 'server',
      destinationConnectionId: '',
      destinationPath: '',
    })
    expect(sourceKindPatch(picked, 'agent').destinationKind).toBe('agent')
  })

  it('needs a chosen agent, and an agent backs up to its own disk', () => {
    expect(isStepValid('connect', answers({ sourceKind: 'agent' }))).toBe(false)
    expect(isStepValid('connect', answers({ sourceKind: 'agent', sourceAgentId: 7 }))).toBe(true)
    const agent = answers({
      sourceKind: 'agent',
      sourceAgentId: 7,
      sourcePaths: ['/home/alex'],
      destinationKind: 'agent',
      destinationPath: '/home/alex/borg',
    })
    expect(destinationInsideSource(agent)).toBe(true)
    expect(destinationInsideSource({ ...agent, destinationPath: '/srv/borg' })).toBe(false)
  })
})
