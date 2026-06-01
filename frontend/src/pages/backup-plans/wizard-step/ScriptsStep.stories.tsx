import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import { createInitialState } from '../state'
import type { WizardState } from '../types'
import { ScriptsStep } from './ScriptsStep'

const scripts = [
  { id: 101, name: 'Prepare SQLite source dump' },
  { id: 102, name: 'Clean SQLite source dump' },
  { id: 201, name: 'Notify backup window' },
]

const databaseSourceState: WizardState = {
  ...createInitialState(),
  name: 'SQLite nightly',
  sourceType: 'local',
  sourceDirectories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
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
        pre_backup_script_id: 101,
        post_backup_script_id: 102,
        pre_backup_script_parameters: {
          SQLITE_DATABASE_PATH: '/home/app/state.sqlite',
        },
        post_backup_script_parameters: {
          SQLITE_DUMP_PATH: '/var/tmp/borg-ui/database-dumps/sqlite',
        },
        script_execution_order: 1,
      },
    },
  ],
}

const translations: Record<string, string> = {
  'backupPlans.wizard.scripts.loading': 'Loading scripts...',
  'backupPlans.wizard.scripts.title': 'Plan scripts',
  'backupPlans.wizard.scripts.description':
    'Run scripts once for the whole backup plan, before the first repository copy and after all repository work finishes.',
  'backupPlans.wizard.scripts.runRepositoryScripts': 'Also run repository scripts',
  'backupPlans.wizard.scripts.runRepositoryScriptsHelper':
    "Use each repository's configured pre/post backup scripts during its own copy.",
  'backupPlans.wizard.scripts.databaseSourceScripts': 'Database source scripts',
  'backupPlans.wizard.scripts.databaseSourceScriptsDescription':
    'These run once per selected database source before and after repository backups.',
  'backupPlans.wizard.scripts.preSourceScript': 'Pre',
  'backupPlans.wizard.scripts.postSourceScript': 'Post',
  'backupPlans.wizard.scripts.autoFilledSourceParameters': 'Auto-filled from source',
  'backupPlans.wizard.scripts.viewAutoFilledSourceParameters':
    'View auto-filled source values for {{database}}',
  'scriptSelector.preBackupScript': 'Pre-Backup Script',
  'scriptSelector.postBackupScript': 'Post-Backup Script',
  'scriptSelector.selectPreBackup': 'Select pre-backup script',
  'scriptSelector.selectPostBackup': 'Select post-backup script',
  'scriptSelector.none': 'None',
  'scriptSelector.runOn': 'Run on',
  'scriptSelector.always': 'Always',
  'scriptSelector.manualOnly': 'Manual only',
  'scriptSelector.scheduledOnly': 'Scheduled only',
}

const t = (key: string, options?: Record<string, string>) => {
  const template = translations[key] || key
  return Object.entries(options || {}).reduce(
    (text, [name, value]) => text.replace(`{{${name}}}`, value),
    template
  )
}

function renderStep(wizardState: WizardState = databaseSourceState) {
  return (
    <Box sx={{ width: 760, maxWidth: 'calc(100vw - 32px)' }}>
      <ScriptsStep
        wizardState={wizardState}
        scripts={scripts}
        loadingScripts={false}
        updateState={() => {}}
        t={t as never}
      />
    </Box>
  )
}

const meta: Meta = {
  title: 'Backup Plans/ScriptsStep',
  parameters: {
    layout: 'centered',
  },
}

export default meta

type Story = StoryObj

export const DatabaseSourceScripts: Story = {
  render: () => renderStep(),
}
