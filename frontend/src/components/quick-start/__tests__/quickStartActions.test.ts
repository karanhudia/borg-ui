import { describe, expect, it } from 'vitest'

import { immichTemplate } from '../../app-templates/appTemplates.fixtures'
import {
  appScriptPayload,
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
  it('stores the repository on the chosen SSH connection', () => {
    const payload = buildRepositoryPayload(
      localAnswers({
        destinationKind: 'ssh',
        destinationConnectionId: 5,
        destinationPath: '/srv/borg/home',
      })
    )
    expect(payload).toMatchObject({
      path: '/srv/borg/home',
      connection_id: 5,
      storage_backend: 'ssh',
      execution_target: 'ssh',
      executor_type: 'server',
    })
  })

  it('pulls the folders over the chosen SSH connection', () => {
    const payload = buildPlanPayload(
      localAnswers({ sourceKind: 'ssh', sourceConnectionId: 3, sourcePaths: ['/srv/data'] }),
      4
    )
    expect(payload).toMatchObject({
      source_type: 'remote',
      source_ssh_connection_id: 3,
      source_directories: ['/srv/data'],
    })
    expect(payload.source_locations).toEqual([
      expect.objectContaining({
        source_type: 'remote',
        source_ssh_connection_id: 3,
        paths: ['/srv/data'],
      }),
    ])
  })
  it('runs an agent backup into a repository on the same agent', () => {
    const agent = localAnswers({
      sourceKind: 'agent',
      sourceAgentId: 7,
      sourcePaths: ['/home/alex'],
      destinationKind: 'agent',
      destinationPath: '/srv/borg/alex',
    })
    expect(buildRepositoryPayload(agent)).toMatchObject({
      path: '/srv/borg/alex',
      executor_type: 'agent',
      execution_target: 'agent',
      storage_backend: 'agent_local',
      agent_machine_id: 7,
    })
    const plan = buildPlanPayload(agent, 4)
    expect(plan.source_type).toBe('agent')
    expect(plan.source_locations).toEqual([
      expect.objectContaining({ source_type: 'agent', agent_machine_id: 7, paths: ['/home/alex'] }),
    ])
  })

  describe('with an app', () => {
    const immich = (overrides: Partial<QuickStartAnswers> = {}) =>
      localAnswers({
        appChoice: 'app',
        app: immichTemplate,
        appRoot: '/local/srv/immich',
        appExcludes: ['thumbs'],
        sourcePaths: ['/local/srv/immich', '/local/srv/photos'],
        ...overrides,
      })

    it('builds excludes and the check from the app folder, wherever it sits in the list', () => {
      const answers = immich({ sourcePaths: ['/local/srv/photos', '/local/srv/immich'] })
      expect(buildPlanPayload(answers, 1, 3).exclude_patterns).toEqual(['/local/srv/immich/thumbs'])
      expect(appScriptPayload(answers)?.content).toContain("'/local/srv/immich'")
    })

    it('drops excludes and the check once the app folder is removed', () => {
      // Removing the app folder must not turn the next folder into "the app's folder".
      const answers = immich({ sourcePaths: ['/local/srv/photos'] })
      expect(buildPlanPayload(answers, 1).exclude_patterns).toEqual([])
      expect(appScriptPayload(answers)).toBeNull()
      expect(buildQuickStartActions(answers)).toEqual(['create_repository', 'create_plan'])
    })
  })
})
