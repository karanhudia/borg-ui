import { describe, expect, it } from 'vitest'

import type { AppTemplate } from '../../../../services/api'
import { createInitialState } from '../../state'
import { applyAppTemplate } from '../appTemplateApply'

const immich = { name: 'Immich', schedule_cron: '0 3 * * *' } as AppTemplate

describe('applyAppTemplate', () => {
  it('fills an empty plan with the app folder, excludes, schedule and check hook', () => {
    const patch = applyAppTemplate(createInitialState(), {
      template: immich,
      sshConnectionId: null,
      root: '/local/srv/immich',
      excludes: ['thumbs'],
      scriptId: 7,
    })

    expect(patch).toMatchObject({
      name: 'Immich',
      sourceType: 'local',
      sourceDirectories: ['/local/srv/immich'],
      excludePatterns: ['/local/srv/immich/thumbs'],
      scheduleEnabled: true,
      cronExpression: '0 3 * * *',
      scriptHooks: [{ script_id: 7, hook_type: 'pre-backup', execution_order: 1, enabled: true }],
    })
  })

  it('adds to the existing local source and keeps the user schedule and scripts', () => {
    const state = {
      ...createInitialState(),
      name: 'Home server',
      scheduleEnabled: true,
      cronExpression: '0 1 * * *',
      preBackupScriptId: 3,
      excludePatterns: ['*.tmp'],
      sourceLocations: [
        {
          source_type: 'local' as const,
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/local/home'],
        },
      ],
    }

    const patch = applyAppTemplate(state, {
      template: immich,
      sshConnectionId: null,
      root: '/local/srv/immich',
      excludes: [],
      scriptId: 8,
    })

    expect(patch.name).toBe('Home server')
    expect(patch.cronExpression).toBeUndefined()
    expect(patch.sourceLocations).toHaveLength(1)
    expect(patch.sourceDirectories).toEqual(['/local/home', '/local/srv/immich'])
    expect(patch.excludePatterns).toEqual(['*.tmp'])
    expect(patch.scriptHooks?.map((hook) => [hook.script_id, hook.execution_order])).toEqual([
      [3, 1],
      [8, 2],
    ])
  })

  it('adds a remote source for an app on an SSH machine', () => {
    const patch = applyAppTemplate(createInitialState(), {
      template: immich,
      sshConnectionId: 5,
      root: '/srv/immich',
      excludes: [],
      scriptId: null,
    })

    expect(patch.sourceLocations?.[0]).toMatchObject({
      source_type: 'remote',
      source_ssh_connection_id: 5,
      paths: ['/srv/immich'],
    })
    expect(patch.scriptHooks).toBeUndefined()
  })

  it('adds external folders next to the app folder, excludes only under the app folder', () => {
    const patch = applyAppTemplate(createInitialState(), {
      template: immich,
      sshConnectionId: 5,
      root: '/srv/immich',
      extraPaths: ['/srv/photos'],
      excludes: ['thumbs'],
      scriptId: null,
    })

    expect(patch.sourceLocations?.[0].paths).toEqual(['/srv/immich', '/srv/photos'])
    expect(patch.excludePatterns).toEqual(['/srv/immich/thumbs'])
  })
})
