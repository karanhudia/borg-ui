import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import { createInitialState } from '../state'
import { SourceStep } from './SourceStep'
import type { SSHConnection } from '../types'

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

const mixedSourceState = {
  ...createInitialState(),
  name: 'Production multi-source backup',
  description: 'Local app data plus two remote service volumes.',
  sourceType: 'mixed' as const,
  sourceDirectories: ['/srv/app', '/home/app/data', '/var/lib/service'],
  sourceLocations: [
    {
      source_type: 'local' as const,
      source_ssh_connection_id: null,
      paths: ['/srv/app'],
    },
    {
      source_type: 'remote' as const,
      source_ssh_connection_id: 11,
      paths: ['/home/app/data'],
    },
    {
      source_type: 'remote' as const,
      source_ssh_connection_id: 12,
      paths: ['/var/lib/service'],
    },
  ],
  excludePatterns: ['*.tmp', 'node_modules'],
}

const translations: Record<string, string> = {
  'backupPlans.wizard.fields.planName': 'Plan name',
  'backupPlans.wizard.fields.description': 'Description',
  'backupPlans.sourceChooser.summaryTitle': 'Backup source',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
  'backupPlans.sourceChooser.summaryEmpty': 'No source selected yet',
  'backupPlans.sourceChooser.chooseSource': 'Choose source',
  'backupPlans.sourceChooser.filesTitle': 'Files and folders',
  'backupPlans.sourceChooser.localSource': 'Local source',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.sshSourceDescription': 'Remote machine',
  'backupPlans.wizard.review.connectionFallback': 'Connection #{{id}}',
}

const t = (key: string, options?: Record<string, unknown>) => {
  if (key === 'backupPlans.sourceChooser.pathCount') {
    const count = Number(options?.count ?? 0)
    return `${count} ${count === 1 ? 'path' : 'paths'}`
  }
  const template = translations[key] || key
  return template.replace('{{id}}', String(options?.id ?? ''))
}

const meta: Meta = {
  title: 'Backup Plans/SourceStep',
  parameters: {
    layout: 'centered',
  },
}

export default meta

type Story = StoryObj

export const MixedSourceGroups: Story = {
  render: () => (
    <Box sx={{ width: 680, maxWidth: 'calc(100vw - 32px)' }}>
      <SourceStep
        wizardState={mixedSourceState}
        sshConnections={sshConnections}
        scripts={[]}
        loadingScripts={false}
        updateState={() => {}}
        openExcludeExplorer={() => {}}
        onCreateScript={async () => ({ id: 1 })}
        t={t as never}
      />
    </Box>
  ),
}
