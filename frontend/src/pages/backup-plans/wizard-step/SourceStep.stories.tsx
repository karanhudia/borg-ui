import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import { createInitialState } from '../state'
import { SourceStep } from './SourceStep'
import type { SSHConnection, WizardState } from '../types'

const sshConnections: SSHConnection[] = [
  {
    id: 11,
    host: 'server-a.example',
    username: 'backup-a',
    port: 22,
    ssh_key_id: 1,
    default_path: '/home/backup-a',
    status: 'connected',
  },
  {
    id: 12,
    host: 'server-b.example',
    username: 'backup-b',
    port: 2222,
    ssh_key_id: 2,
    default_path: '/var/lib',
    status: 'connected',
  },
]

const emptyState: WizardState = {
  ...createInitialState(),
  name: 'New backup plan',
  description: '',
}

const singleLocalState: WizardState = {
  ...createInitialState(),
  name: 'Documents Backup Plan',
  description: 'Created from repository "Documents".',
  sourceType: 'local',
  sourceDirectories: [
    '/local/Users/karanhudia/Documents/DeepikaPanCard.jpg',
    '/local/Users/karanhudia/Documents/eTicket_6BD9FFC000A77AA2F3B4E91FBB4402E72A460278CF6E4A3B88C17FAD.pdf',
    '/local/Users/karanhudia/Documents/Karan Passport-2.pdf',
    '/local/Users/karanhudia/Documents/keyfile_without_docker',
    '/local/Users/karanhudia/Documents/Karan Passport.pdf',
    '/local/Users/karanhudia/Documents/Karan Passport-12.pdf',
    '/local/Users/karanhudia/Documents/test',
    '/local/Users/karanhudia/Documents/test_keyfile',
    '/local/Users/karanhudia/Documents/VFS Global _ Official partner of the Government.pdf',
  ],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: [
        '/local/Users/karanhudia/Documents/DeepikaPanCard.jpg',
        '/local/Users/karanhudia/Documents/eTicket_6BD9FFC000A77AA2F3B4E91FBB4402E72A460278CF6E4A3B88C17FAD.pdf',
        '/local/Users/karanhudia/Documents/Karan Passport-2.pdf',
        '/local/Users/karanhudia/Documents/keyfile_without_docker',
        '/local/Users/karanhudia/Documents/Karan Passport.pdf',
        '/local/Users/karanhudia/Documents/Karan Passport-12.pdf',
        '/local/Users/karanhudia/Documents/test',
        '/local/Users/karanhudia/Documents/test_keyfile',
        '/local/Users/karanhudia/Documents/VFS Global _ Official partner of the Government.pdf',
      ],
    },
  ],
}

const mixedSourceState: WizardState = {
  ...createInitialState(),
  name: 'Production multi-source backup',
  description: 'Local app data plus two remote service volumes.',
  sourceType: 'mixed',
  sourceDirectories: ['/srv/app', '/home/app/data', '/var/lib/service'],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: ['/srv/app'],
    },
    {
      source_type: 'remote',
      source_ssh_connection_id: 11,
      paths: ['/home/app/data'],
    },
    {
      source_type: 'remote',
      source_ssh_connection_id: 12,
      paths: ['/var/lib/service'],
    },
  ],
  excludePatterns: ['*.tmp', 'node_modules'],
}

const databaseDumpState: WizardState = {
  ...createInitialState(),
  name: 'PostgreSQL nightly',
  description: 'Logical dump of the production Postgres cluster.',
  sourceType: 'local',
  sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
    },
  ],
  preBackupScriptId: 101,
  postBackupScriptId: 102,
}

const translations: Record<string, string> = {
  'backupPlans.wizard.fields.planName': 'Plan name',
  'backupPlans.wizard.fields.description': 'Description',
  'backupPlans.sourceChooser.summaryTitle': 'Backup source',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
  'backupPlans.sourceChooser.summaryEmpty': 'No source selected yet',
  'backupPlans.sourceChooser.chooseSource': 'Choose source',
  'backupPlans.sourceChooser.change': 'Change',
  'backupPlans.sourceChooser.edit': 'Edit',
  'backupPlans.sourceChooser.databaseTitle': 'Database scan',
  'backupPlans.sourceChooser.filesTitle': 'Files and folders',
  'backupPlans.sourceChooser.localSource': 'Local source',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.agentFallback': 'Agent #{{id}}',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.sshSourceDescription': 'Remote machine',
  'backupPlans.sourceChooser.showLessPaths': 'Show less',
  'backupPlans.sourceChooser.inPrefix': 'in',
  'backupPlans.wizard.review.connectionFallback': 'Connection #{{id}}',
}

const t = (key: string, options?: Record<string, unknown>) => {
  if (key === 'backupPlans.sourceChooser.pathCount') {
    const count = Number(options?.count ?? 0)
    return `${count} ${count === 1 ? 'path' : 'paths'}`
  }
  if (key === 'backupPlans.sourceChooser.showMorePaths') {
    const count = Number(options?.count ?? 0)
    return `Show ${count} more ${count === 1 ? 'path' : 'paths'}`
  }
  const template = translations[key] || key
  return template.replace('{{id}}', String(options?.id ?? ''))
}

interface RenderArgs {
  wizardState: WizardState
}

function renderStep({ wizardState }: RenderArgs) {
  return (
    <Box sx={{ width: 680, maxWidth: 'calc(100vw - 32px)' }}>
      <SourceStep
        wizardState={wizardState}
        sshConnections={sshConnections}
        agentMachines={[]}
        fullRepositories={[]}
        scripts={[]}
        loadingScripts={false}
        updateState={() => {}}
        openExcludeExplorer={() => {}}
        onCreateScript={async () => ({ id: 1 })}
        t={t as never}
      />
    </Box>
  )
}

const meta: Meta = {
  title: 'Backup Plans/SourceStep',
  parameters: {
    layout: 'centered',
  },
}

export default meta

type Story = StoryObj

export const EmptyState: Story = {
  render: () => renderStep({ wizardState: emptyState }),
}

export const SingleLocalGroup: Story = {
  render: () => renderStep({ wizardState: singleLocalState }),
}

export const MixedSourceGroups: Story = {
  render: () => renderStep({ wizardState: mixedSourceState }),
}

export const DatabaseDumpSource: Story = {
  render: () => renderStep({ wizardState: databaseDumpState }),
}
