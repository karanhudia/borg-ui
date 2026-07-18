import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createInitialState } from '../state'
import { ScriptsStep } from '../wizard-step/ScriptsStep'

vi.mock('../../../services/api', () => ({
  managedAgentsAPI: {
    listAgentScripts: vi.fn().mockResolvedValue({ data: { scripts: [], agent_online: true } }),
  },
}))

const translations: Record<string, string> = {
  'backupPlans.wizard.scripts.loading': 'Loading scripts...',
  'backupPlans.wizard.scripts.title': 'Plan scripts',
  'backupPlans.wizard.scripts.description': 'Run scripts once for the whole backup plan.',
  'backupPlans.wizard.scripts.runRepositoryScripts': 'Also run repository scripts',
  'backupPlans.wizard.scripts.runRepositoryScriptsHelper':
    'Use each repository script during its own copy.',
  'backupPlans.wizard.scripts.databaseSourceScripts': 'Database source scripts',
  'backupPlans.wizard.scripts.databaseSourceScriptsDescription':
    'These run once per selected database source.',
  'backupPlans.wizard.scripts.preSourceScript': 'Pre',
  'backupPlans.wizard.scripts.postSourceScript': 'Post',
  'backupPlans.wizard.scripts.autoFilledSourceParameters': 'Auto-filled from source',
  'backupPlans.wizard.scripts.viewAutoFilledSourceParameters':
    'View auto-filled source parameter details for {{database}}',
  'backupPlans.wizard.scripts.noAutoFilledSourceParameters':
    'No parameter values were auto-filled from this source.',
  'backupPlans.wizard.scripts.preBackupScripts': 'Pre-backup scripts',
  'backupPlans.wizard.scripts.postBackupScripts': 'Post-backup scripts',
  'backupPlans.wizard.scripts.addPreBackupScript': 'Add pre-backup script',
  'backupPlans.wizard.scripts.addPostBackupScript': 'Add post-backup script',
  'backupPlans.wizard.scripts.noPreBackupScripts': 'No pre-backup scripts configured.',
  'backupPlans.wizard.scripts.noPostBackupScripts': 'No post-backup scripts configured.',
  'backupPlans.wizard.scripts.onFailure': 'On failure',
  'backupPlans.wizard.scripts.onFailureFail': 'Fail plan',
  'backupPlans.wizard.scripts.onFailureContinue': 'Continue backup',
  'backupPlans.wizard.scripts.onFailureSkip': 'Skip backup',
  'backupPlans.wizard.scripts.runCondition': 'Run condition',
  'backupPlans.wizard.scripts.runAlways': 'Always',
  'backupPlans.wizard.scripts.runOnSuccess': 'On success',
  'backupPlans.wizard.scripts.runOnFailure': 'On failure',
  'backupPlans.wizard.scripts.runOnWarning': 'On warning',
  'backupPlans.wizard.scripts.removeScript': 'Remove {{script}}',
  'backupPlans.wizard.scripts.moveScriptUp': 'Move {{script}} up',
  'backupPlans.wizard.scripts.moveScriptDown': 'Move {{script}} down',
  'scriptParameters.title': 'Script Parameters',
}

const t = (key: string, options?: Record<string, string>) => {
  const template = translations[key] || key
  return Object.entries(options || {}).reduce(
    (text, [name, value]) => text.replace(`{{${name}}}`, value),
    template
  )
}

describe('ScriptsStep', () => {
  it('summarizes database source scripts separately from plan scripts', async () => {
    const user = userEvent.setup()

    render(
      <ScriptsStep
        wizardState={{
          ...createInitialState(),
          sourceLocations: [
            {
              source_type: 'local',
              source_ssh_connection_id: null,
              agent_machine_id: null,
              paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
              database: {
                template_id: 'sqlite',
                engine: 'SQLite',
                display_name: 'SQLite database',
                backup_strategy: 'online_backup',
                detected_source_path: '/home/app/state.sqlite',
                detection_label: 'Borg UI server',
                capture_mode: 'dump',
                dump_path: '/var/tmp/borg-ui/database-dumps/sqlite',
                backup_paths: ['/var/tmp/borg-ui/database-dumps/sqlite'],
                script_execution_target: 'source',
                pre_backup_script_id: 11,
                post_backup_script_id: 12,
                pre_backup_script_parameters: {
                  SQLITE_DATABASE_PATH: '/home/app/state.sqlite',
                },
                post_backup_script_parameters: {
                  SQLITE_DUMP_PATH: '/var/tmp/borg-ui/database-dumps/sqlite',
                },
                script_execution_order: 1,
              },
            },
            {
              source_type: 'local',
              source_ssh_connection_id: null,
              agent_machine_id: null,
              paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
              database: {
                template_id: 'mysql',
                engine: 'MySQL',
                display_name: 'MySQL database',
                backup_strategy: 'logical_dump',
                detected_source_path: '/var/lib/mysql',
                detection_label: 'Borg UI server',
                capture_mode: 'dump',
                dump_path: '/var/tmp/borg-ui/database-dumps/mysql',
                backup_paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
                script_execution_target: 'source',
                pre_backup_script_id: 13,
                post_backup_script_id: 14,
                pre_backup_script_parameters: {},
                post_backup_script_parameters: {},
                script_execution_order: 2,
              },
            },
          ],
        }}
        scripts={[
          { id: 11, name: 'Generic SQLite prepare' },
          { id: 12, name: 'Generic SQLite cleanup' },
          { id: 13, name: 'Generic MySQL prepare' },
          { id: 14, name: 'Generic MySQL cleanup' },
        ]}
        loadingScripts={false}
        updateState={vi.fn()}
        t={t as never}
      />
    )

    expect(screen.getByText('Database source scripts')).toBeInTheDocument()
    expect(screen.getByText('SQLite database')).toBeInTheDocument()
    expect(screen.getByText('MySQL database')).toBeInTheDocument()
    expect(screen.getByText(/Generic SQLite prepare/)).toBeInTheDocument()
    expect(screen.getByText(/Generic SQLite cleanup/)).toBeInTheDocument()
    expect(screen.getByText(/Generic MySQL prepare/)).toBeInTheDocument()
    expect(screen.getByText(/Generic MySQL cleanup/)).toBeInTheDocument()
    expect(screen.getAllByText('Auto-filled from source')).toHaveLength(2)

    const sqliteValuesButton = screen.getByRole('button', {
      name: 'View auto-filled source parameter details for SQLite database',
    })
    const mysqlValuesButton = screen.getByRole('button', {
      name: 'View auto-filled source parameter details for MySQL database',
    })
    const mysqlTriggerGroup = mysqlValuesButton.parentElement
    expect(mysqlTriggerGroup).not.toBeNull()
    expect(within(mysqlTriggerGroup!).getByText('Auto-filled from source')).toBeInTheDocument()
    expect(within(mysqlTriggerGroup!).queryByText('MySQL database')).not.toBeInTheDocument()

    await user.hover(sqliteValuesButton)

    expect(
      await screen.findByText('Pre: SQLITE_DATABASE_PATH=/home/app/state.sqlite')
    ).toBeInTheDocument()
    expect(
      screen.getByText('Post: SQLITE_DUMP_PATH=/var/tmp/borg-ui/database-dumps/sqlite')
    ).toBeInTheDocument()

    await user.unhover(sqliteValuesButton)
    await user.hover(mysqlValuesButton)

    expect(
      await screen.findByText('No parameter values were auto-filled from this source.')
    ).toBeInTheDocument()
    expect(screen.getByText('Pre-backup scripts')).toBeInTheDocument()
    expect(screen.getByText('Post-backup scripts')).toBeInTheDocument()
  })

  it('adds a saved script to the pre-backup chain', async () => {
    const user = userEvent.setup()
    const updateState = vi.fn()

    render(
      <ScriptsStep
        wizardState={createInitialState()}
        scripts={[
          { id: 21, name: 'Prepare database' },
          { id: 22, name: 'Notify operator' },
        ]}
        loadingScripts={false}
        updateState={updateState}
        t={t as never}
      />
    )

    fireEvent.mouseDown(screen.getByRole('combobox', { name: 'Add pre-backup script' }))
    await user.click(screen.getByRole('option', { name: 'Prepare database' }))

    expect(updateState).toHaveBeenCalledWith(
      expect.objectContaining({
        scriptHooks: [
          expect.objectContaining({
            script_id: 21,
            hook_type: 'pre-backup',
            execution_order: 1,
            enabled: true,
          }),
        ],
        preBackupScriptId: 21,
        preBackupScriptParameters: {},
      })
    )
  })

  it('updates hook-specific failure behavior and run conditions', async () => {
    const user = userEvent.setup()
    const updateState = vi.fn()

    render(
      <ScriptsStep
        wizardState={{
          ...createInitialState(),
          scriptHooks: [
            {
              script_id: 31,
              hook_type: 'pre-backup',
              execution_order: 1,
              enabled: true,
              continue_on_error: false,
              skip_on_failure: false,
              parameter_values: {},
            },
            {
              script_id: 32,
              hook_type: 'post-backup',
              execution_order: 1,
              enabled: true,
              custom_run_on: 'success',
              parameter_values: {},
            },
          ],
        }}
        scripts={[
          { id: 31, name: 'Stop database' },
          { id: 32, name: 'Send failure alert' },
        ]}
        loadingScripts={false}
        updateState={updateState}
        t={t as never}
      />
    )

    await user.click(screen.getByRole('radio', { name: 'Continue backup' }))
    expect(updateState).toHaveBeenCalledWith(
      expect.objectContaining({
        scriptHooks: [
          expect.objectContaining({
            script_id: 31,
            continue_on_error: true,
            skip_on_failure: false,
          }),
          expect.objectContaining({ script_id: 32 }),
        ],
      })
    )

    await user.click(screen.getByRole('radio', { name: 'On failure' }))
    expect(updateState).toHaveBeenLastCalledWith(
      expect.objectContaining({
        scriptHooks: [
          expect.objectContaining({ script_id: 31 }),
          expect.objectContaining({
            script_id: 32,
            custom_run_on: 'failure',
          }),
        ],
      })
    )
  })

  it('falls back to always for unsupported saved script run conditions', () => {
    render(
      <ScriptsStep
        wizardState={{
          ...createInitialState(),
          scriptHooks: [
            {
              script_id: 42,
              hook_type: 'post-backup',
              execution_order: 1,
              enabled: true,
              parameter_values: {},
            },
          ],
        }}
        scripts={[{ id: 42, name: 'Legacy runner', run_on: 'manual-only' }]}
        loadingScripts={false}
        updateState={vi.fn()}
        t={t as never}
      />
    )

    expect(screen.getByRole('radio', { name: 'Always' })).toBeChecked()
  })

  it('drops agent hooks when the resolved plan agent changes', async () => {
    const updateState = vi.fn()
    const repositories = [
      { id: 1, name: 'Repo A', executor_type: 'agent', agent_machine_id: 1 },
      { id: 2, name: 'Repo B', executor_type: 'agent', agent_machine_id: 2 },
    ]
    const agentMachines = [
      { id: 1, name: 'agent-a' },
      { id: 2, name: 'agent-b' },
    ]
    const baseState = {
      ...createInitialState(),
      repositoryIds: [1],
      scriptHooks: [
        {
          agent_script_name: 'dump-db',
          is_agent_script: true,
          hook_type: 'pre-backup' as const,
          execution_order: 1,
          enabled: true,
          continue_on_error: false,
          skip_on_failure: false,
          parameter_values: {},
        },
      ],
    }

    const props = {
      scripts: [],
      loadingScripts: false,
      updateState,
      t: t as never,
      repositories: repositories as never,
      agentMachines: agentMachines as never,
    }

    const { rerender } = render(<ScriptsStep wizardState={baseState} {...props} />)
    // Mounting with the plan already bound to agent 1 must not wipe saved hooks.
    expect(updateState).not.toHaveBeenCalled()

    // Re-pick the repositories so the plan now resolves to agent 2.
    rerender(<ScriptsStep wizardState={{ ...baseState, repositoryIds: [2] }} {...props} />)

    await waitFor(() =>
      expect(updateState).toHaveBeenCalledWith(expect.objectContaining({ scriptHooks: [] }))
    )
  })

  it('does not render legacy inline script controls', () => {
    render(
      <ScriptsStep
        wizardState={createInitialState()}
        scripts={[{ id: 41, name: 'Saved script' }]}
        loadingScripts={false}
        updateState={vi.fn()}
        t={t as never}
      />
    )

    expect(screen.queryByText(/inline script/i)).not.toBeInTheDocument()
  })
})
