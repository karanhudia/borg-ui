import { useEffect, useMemo } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'

import api from '../../../services/api'
import { SourceSelectionDialog } from './SourceSelectionDialog'
import type { SSHConnection, WizardState } from '../types'
import type { SourceDiscoveryDatabase } from '../../../services/api'
import { createInitialState } from '../state'

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

const postgresqlTemplate: SourceDiscoveryDatabase = {
  id: 'postgresql',
  engine: 'PostgreSQL',
  display_name: 'PostgreSQL database',
  backup_strategy: 'logical_dump',
  source_directories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
  client_commands: ['pg_dump'],
  documentation_url: 'https://www.postgresql.org/docs/17/app-pgdump.html',
  detected: false,
  detection_source: null,
  notes: ['Uses pg_dump custom format.'],
  script_drafts: {
    pre_backup: {
      name: 'Prepare PostgreSQL dump',
      description: 'Create a PostgreSQL custom-format dump.',
      content: '#!/usr/bin/env bash\nset -euo pipefail\npg_dump postgres\n',
      timeout: 900,
    },
    post_backup: {
      name: 'Clean PostgreSQL dump',
      description: 'Remove transient dump files.',
      content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui\n',
      timeout: 120,
    },
  },
}

const mysqlTemplate: SourceDiscoveryDatabase = {
  ...postgresqlTemplate,
  id: 'mysql',
  engine: 'MySQL / MariaDB',
  display_name: 'MySQL or MariaDB database',
  source_directories: ['/var/tmp/borg-ui/database-dumps/mysql'],
  client_commands: ['mysqldump'],
}

const mongoTemplate: SourceDiscoveryDatabase = {
  ...postgresqlTemplate,
  id: 'mongodb',
  engine: 'MongoDB',
  display_name: 'MongoDB database',
  source_directories: ['/var/tmp/borg-ui/database-dumps/mongodb'],
  client_commands: ['mongodump'],
}

const redisTemplate: SourceDiscoveryDatabase = {
  ...postgresqlTemplate,
  id: 'redis',
  engine: 'Redis',
  display_name: 'Redis database',
  source_directories: ['/var/tmp/borg-ui/database-dumps/redis'],
  client_commands: ['redis-cli'],
}

const allTemplates = [postgresqlTemplate, mysqlTemplate, mongoTemplate, redisTemplate]

const legacyDiscoveryResponse = {
  source_types: [],
  detections: [],
  templates: allTemplates,
}

const detectedScanResponse = {
  scan_target: {
    source_type: 'local' as const,
    source_ssh_connection_id: null,
    label: 'This Borg UI server',
  },
  scanned_paths: ['/var/lib/postgresql', '/var/lib/mysql', '/var/lib/mongodb', '/var/lib/redis'],
  detections: [
    { ...postgresqlTemplate, detected: true, detection_source: '/var/lib/postgresql' },
    { ...mysqlTemplate, detected: true, detection_source: '/var/lib/mysql' },
  ],
  templates: allTemplates,
  warnings: [],
}

const nothingFoundScanResponse = {
  ...detectedScanResponse,
  detections: [],
}

interface MockOptions {
  scanStatus?: 'detected' | 'nothing-found' | 'failed' | 'endpoint-missing'
  legacyTemplates?: boolean
}

function useMockedDiscovery({ scanStatus = 'detected', legacyTemplates = true }: MockOptions) {
  useEffect(() => {
    const mock = new MockAdapter(api, { onNoMatch: 'passthrough' })

    if (legacyTemplates) {
      mock.onGet('/source-discovery/databases').reply(200, legacyDiscoveryResponse)
    }

    if (scanStatus === 'detected') {
      mock.onPost('/source-discovery/databases/scan').reply(200, detectedScanResponse)
    } else if (scanStatus === 'nothing-found') {
      mock.onPost('/source-discovery/databases/scan').reply(200, nothingFoundScanResponse)
    } else if (scanStatus === 'endpoint-missing') {
      mock.onPost('/source-discovery/databases/scan').reply(404)
    } else {
      mock.onPost('/source-discovery/databases/scan').reply(502, {
        detail: 'Connection refused to user@server-a.example',
      })
    }

    return () => {
      mock.restore()
    }
  }, [scanStatus, legacyTemplates])
}

const emptyWizardState: WizardState = createInitialState()

const localPathsState: WizardState = {
  ...createInitialState(),
  sourceType: 'local',
  sourceDirectories: [
    '/local/Users/karanhudia/Documents/DeepikaPanCard.jpg',
    '/local/Users/karanhudia/Documents/Karan Passport-2.pdf',
    '/local/Users/karanhudia/Documents/Karan Passport.pdf',
  ],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: [
        '/local/Users/karanhudia/Documents/DeepikaPanCard.jpg',
        '/local/Users/karanhudia/Documents/Karan Passport-2.pdf',
        '/local/Users/karanhudia/Documents/Karan Passport.pdf',
      ],
    },
  ],
}

const translations: Record<string, string> = {
  'backupPlans.sourceChooser.title': 'Choose backup source',
  'backupPlans.sourceChooser.where': 'Where are the files?',
  'backupPlans.sourceChooser.localSource': 'Local source',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.remoteMachine': 'Remote machine',
  'backupPlans.sourceChooser.remoteMachineDescription': 'Pull from an SSH connection',
  'backupPlans.sourceChooser.selectRemoteMachine': 'Select a remote machine',
  'backupPlans.sourceChooser.noRemoteMachines': 'No SSH connections available',
  'backupPlans.sourceChooser.readingFromLocal': 'Reading directly from this server',
  'backupPlans.sourceChooser.scanDatabaseInstead': 'Scan a database instead',
  'backupPlans.sourceChooser.databaseBackupTitle': 'Add database backup',
  'backupPlans.sourceChooser.scanTarget': 'Scan where?',
  'backupPlans.sourceChooser.pathsToScan': 'Paths to scan',
  'backupPlans.sourceChooser.noScanPaths': 'Add at least one path to scan.',
  'backupPlans.sourceChooser.scanning': 'Scanning…',
  'backupPlans.sourceChooser.rescan': 'Re-scan',
  'backupPlans.sourceChooser.scanFailedBody': 'Check the connection or try again.',
  'backupPlans.sourceChooser.scanEndpointMissing':
    "Database scanning isn't available on this server yet. Pick a template below to configure manually.",
  'backupPlans.sourceChooser.nothingFoundBody':
    'Add another path above, or pick a template below to set one up manually.',
  'backupPlans.sourceChooser.detectedSection': 'Detected',
  'backupPlans.sourceChooser.detectedBadge': 'Detected',
  'backupPlans.sourceChooser.orPickTemplate': 'Or pick a template',
  'backupPlans.sourceChooser.pickTemplateManually': 'Pick a template to configure manually',
  'backupPlans.sourceChooser.sourcePath': 'Source path',
  'backupPlans.sourceChooser.addPath': 'Add path',
  'backupPlans.sourceChooser.browseCurrentSource': 'Browse current source',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
  'backupPlans.sourceChooser.removePath': 'Remove path',
  'backupPlans.sourceChooser.removeSourceGroup': 'Remove source group',
  'backupPlans.sourceChooser.applyPaths': 'Use these paths',
  'backupPlans.sourceChooser.summaryEmpty': 'No source selected yet',
  'backupPlans.sourceChooser.back': 'Back',
  'common.buttons.cancel': 'Cancel',
  'backupPlans.wizard.fileExplorer.sourceTitle': 'Select source paths',
}

const t = (key: string, options?: Record<string, unknown>) => {
  if (key === 'backupPlans.sourceChooser.pathCount') {
    const count = Number(options?.count ?? 0)
    return `${count} ${count === 1 ? 'path' : 'paths'}`
  }
  if (key === 'backupPlans.sourceChooser.scanFailedTitle') {
    return `Couldn't scan ${options?.target ?? 'target'}`
  }
  if (key === 'backupPlans.sourceChooser.nothingFoundTitle') {
    return `No databases found on ${options?.target ?? 'target'}`
  }
  return translations[key] || key
}

interface DialogStoryArgs {
  wizardState: WizardState
  mockOptions: MockOptions
}

function DialogStory({ wizardState, mockOptions }: DialogStoryArgs) {
  useMockedDiscovery(mockOptions)
  const stableState = useMemo(() => wizardState, [wizardState])
  return (
    <Box sx={{ width: 1, height: '100vh', position: 'relative' }}>
      <SourceSelectionDialog
        open
        wizardState={stableState}
        sshConnections={sshConnections}
        scripts={[]}
        loadingScripts={false}
        updateState={() => {}}
        onCreateScript={async () => ({ id: 1 })}
        onClose={() => {}}
        t={t as never}
      />
    </Box>
  )
}

const meta: Meta = {
  title: 'Backup Plans/SourceSelectionDialog',
  parameters: {
    layout: 'fullscreen',
  },
}

export default meta

type Story = StoryObj

export const PathPickerEmpty: Story = {
  render: () => (
    <DialogStory wizardState={emptyWizardState} mockOptions={{ scanStatus: 'detected' }} />
  ),
}

export const PathPickerWithLocalSelections: Story = {
  render: () => (
    <DialogStory wizardState={localPathsState} mockOptions={{ scanStatus: 'detected' }} />
  ),
}

export const DatabaseScanDetected: Story = {
  render: () => (
    <DialogStory wizardState={emptyWizardState} mockOptions={{ scanStatus: 'detected' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Open the Database view from "Scan a database instead". Mocked endpoint returns two detected engines plus all four templates.',
      },
    },
  },
}

export const DatabaseScanNothingFound: Story = {
  render: () => (
    <DialogStory wizardState={emptyWizardState} mockOptions={{ scanStatus: 'nothing-found' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Scan completed successfully but found nothing — info banner explains and templates render below as fallback.',
      },
    },
  },
}

export const DatabaseScanFailed: Story = {
  render: () => (
    <DialogStory wizardState={emptyWizardState} mockOptions={{ scanStatus: 'failed' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          '502 from the scan endpoint. Warning banner with inline Re-scan, plus templates from the legacy GET fallback.',
      },
    },
  },
}

export const DatabaseScanEndpointMissing: Story = {
  render: () => (
    <DialogStory wizardState={emptyWizardState} mockOptions={{ scanStatus: 'endpoint-missing' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'New POST endpoint not deployed yet (404). Info banner, templates render from the legacy GET fallback.',
      },
    },
  },
}
