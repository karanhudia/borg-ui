import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import { createInitialState } from '../state'
import type { WizardState } from '../types'
import { ScriptsStep } from './ScriptsStep'

const scripts = [
  {
    id: 101,
    name: 'Prepare SQLite source dump',
    description: 'Pause writes and create a source-side SQLite dump.',
  },
  {
    id: 102,
    name: 'Clean SQLite source dump',
    description: 'Remove temporary dump files from the source host.',
    run_on: 'success',
  },
  { id: 111, name: 'Prepare MySQL source dump' },
  { id: 112, name: 'Clean MySQL source dump' },
  {
    id: 201,
    name: 'Notify backup window',
    description: 'Send an operator notification before the backup starts.',
  },
  {
    id: 202,
    name: 'Stop database service',
    description: 'Stop the database service before copying files.',
    parameters: [
      {
        name: 'SERVICE_NAME',
        type: 'text' as const,
        default: 'postgresql',
        description: 'System service to stop before the plan runs.',
        required: true,
      },
    ],
  },
  {
    id: 203,
    name: 'Send failure alert',
    description: 'Notify the on-call channel when the plan fails.',
    run_on: 'failure',
    parameters: [
      {
        name: 'CHANNEL',
        type: 'text' as const,
        default: '#backup-alerts',
        description: 'Notification destination.',
        required: true,
      },
    ],
  },
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
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
      database: {
        template_id: 'mysql',
        engine: 'MySQL',
        display_name: 'MySQL or MariaDB database',
        backup_strategy: 'logical_dump',
        detected_source_path: '/var/lib/mysql',
        detection_label: 'Borg UI server',
        capture_mode: 'dump',
        dump_path: '/var/tmp/borg-ui/database-dumps/mysql',
        backup_paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
        script_execution_target: 'source',
        pre_backup_script_id: 111,
        post_backup_script_id: 112,
        pre_backup_script_parameters: {},
        post_backup_script_parameters: {},
        script_execution_order: 2,
      },
    },
  ],
}

const planScriptChainState: WizardState = {
  ...createInitialState(),
  name: 'Nightly database plan',
  sourceType: 'local',
  sourceDirectories: ['/srv/database'],
  scriptHooks: [
    {
      script_id: 201,
      hook_type: 'pre-backup',
      execution_order: 1,
      enabled: true,
      continue_on_error: true,
      skip_on_failure: false,
      parameter_values: {},
    },
    {
      script_id: 202,
      hook_type: 'pre-backup',
      execution_order: 2,
      enabled: true,
      continue_on_error: false,
      skip_on_failure: false,
      parameter_values: {
        SERVICE_NAME: 'postgresql',
      },
    },
    {
      script_id: 203,
      hook_type: 'post-backup',
      execution_order: 1,
      enabled: true,
      custom_run_on: 'failure',
      parameter_values: {
        CHANNEL: '#backup-alerts',
      },
    },
  ],
  preBackupScriptId: 201,
  postBackupScriptId: 203,
}

const translations: Record<string, string> = {
  'backupPlans.wizard.scripts.loading': 'Loading scripts...',
  'backupPlans.wizard.scripts.title': 'Plan scripts',
  'backupPlans.wizard.scripts.description':
    'Run scripts once for the whole backup plan, before the first repository copy and after all repository work finishes.',
  'backupPlans.wizard.scripts.runRepositoryScripts': 'Also run repository scripts',
  'backupPlans.wizard.scripts.runRepositoryScriptsHelper':
    "Use each repository's configured pre/post backup scripts during its own copy.",
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
  'backupPlans.wizard.scripts.databaseSourceScripts': 'Database source scripts',
  'backupPlans.wizard.scripts.databaseSourceScriptsDescription':
    'These run once per selected database source before and after repository backups.',
  'backupPlans.wizard.scripts.preSourceScript': 'Pre',
  'backupPlans.wizard.scripts.postSourceScript': 'Post',
  'backupPlans.wizard.scripts.autoFilledSourceParameters': 'Auto-filled from source',
  'backupPlans.wizard.scripts.viewAutoFilledSourceParameters':
    'View auto-filled source parameter details for {{database}}',
  'backupPlans.wizard.scripts.noAutoFilledSourceParameters':
    'No parameter values were auto-filled from this source.',
  'scriptParameters.title': 'Script Parameters',
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

export const PlanScriptChains: Story = {
  render: () => renderStep(planScriptChainState),
}
