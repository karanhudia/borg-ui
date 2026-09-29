import { describe, expect, it } from 'vitest'

import {
  buildPlanPayload,
  buildQuickStartActions,
  buildRepositoryPayload,
  pendingActions,
} from '../quickStartActions'
import { createInitialQuickStartAnswers, type QuickStartAnswers } from '../quickStartState'

function localAnswers(overrides: Partial<QuickStartAnswers> = {}): QuickStartAnswers {
  return {
    ...createInitialQuickStartAnswers(),
    sourcePaths: ['/local/home', '/local/etc'],
    destinationPath: '/local/borg-backups/home',
    name: '  home  ',
    passphrase: 'correct horse',
    passphraseConfirm: 'correct horse',
    passphraseSaved: true,
    timezone: 'Europe/Berlin',
    ...overrides,
  }
}

describe('quickStartActions', () => {
  it('creates a repository and then a plan for a local setup', () => {
    expect(buildQuickStartActions(localAnswers())).toEqual(['create_repository', 'create_plan'])
  })

  it('resumes after the actions that already finished', () => {
    const actions = buildQuickStartActions(localAnswers())
    expect(pendingActions(actions, {})).toEqual(['create_repository', 'create_plan'])
    expect(pendingActions(actions, { repositoryId: 4 })).toEqual(['create_plan'])
    expect(pendingActions(actions, { repositoryId: 4, planId: 9 })).toEqual([])
  })

  it('builds a local repository payload', () => {
    expect(buildRepositoryPayload(localAnswers())).toEqual({
      name: 'home',
      borg_version: 1,
      path: '/local/borg-backups/home',
      encryption: 'repokey',
      passphrase: 'correct horse',
      compression: 'zstd,3',
      source_directories: [],
      exclude_patterns: [],
      custom_flags: null,
      mode: 'full',
    })
  })

  it('leaves the passphrase out when encryption is off', () => {
    const answers = localAnswers()
    answers.settings = { ...answers.settings, encryption: 'none' }
    expect(buildRepositoryPayload(answers).passphrase).toBeUndefined()
  })

  it('builds a scheduled plan with prune, compact and check', () => {
    const payload = buildPlanPayload(localAnswers(), 4)
    expect(payload).toMatchObject({
      name: 'home',
      enabled: true,
      source_type: 'local',
      source_directories: ['/local/home', '/local/etc'],
      compression: 'zstd,3',
      schedule_enabled: true,
      cron_expression: '0 2 * * *',
      timezone: 'Europe/Berlin',
      run_prune_after: true,
      run_compact_after: true,
      run_check_after: true,
      prune_keep_daily: 7,
      prune_keep_weekly: 4,
      prune_keep_monthly: 6,
      prune_keep_yearly: 1,
    })
    expect(payload.repositories).toEqual([
      expect.objectContaining({ repository_id: 4, enabled: true }),
    ])
  })

  it('sends no cron expression when the schedule is off', () => {
    const answers = localAnswers()
    answers.settings = { ...answers.settings, scheduleEnabled: false }
    const payload = buildPlanPayload(answers, 4)
    expect(payload.schedule_enabled).toBe(false)
    expect(payload.cron_expression).toBeNull()
  })
})
