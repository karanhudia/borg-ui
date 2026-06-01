import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { createInitialState } from '../state'
import { ScriptsStep } from '../wizard-step/ScriptsStep'

vi.mock('../../../components/ScriptSelectorSection', () => ({
  default: () => <div>Plan script selector</div>,
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
    expect(screen.getByText('Plan script selector')).toBeInTheDocument()
  })
})
