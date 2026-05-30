import { useEffect, useMemo } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'

import api from '../../../services/api'
import { SourceSelectionDialog } from './SourceSelectionDialog'
import type { SSHConnection, WizardState } from '../types'
import type { AgentMachineResponse, SourceDiscoveryDatabase } from '../../../services/api'
import type { Repository } from '../../../types'
import { createInitialState } from '../state'

const sshConnections: SSHConnection[] = [
  {
    id: 11,
    host: 'server-a.example',
    username: 'backup-a',
    port: 22,
    ssh_key_id: 1,
    default_path: '/home/backup-a',
    mount_point: '/mnt/server-a',
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

const agentMachines: AgentMachineResponse[] = [
  {
    id: 31,
    name: 'Build agent',
    agent_id: 'agt_build',
    hostname: 'build-agent.local',
    os: 'linux',
    arch: 'amd64',
    agent_version: '0.1.0',
    borg_versions: [],
    capabilities: ['filesystem.browse'],
    labels: {},
    status: 'online',
    last_seen_at: null,
    last_error: null,
    created_at: '2026-05-20T00:00:00Z',
    updated_at: '2026-05-20T00:00:00Z',
  },
]

const repositories: Repository[] = [
  {
    id: 101,
    name: 'Agent repo',
    path: '/backups/agent-repo',
    executor_type: 'agent',
    execution_target: 'agent',
    agent_machine_id: 31,
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

const sqliteTemplate: SourceDiscoveryDatabase = {
  ...postgresqlTemplate,
  id: 'sqlite',
  engine: 'SQLite',
  display_name: 'SQLite database',
  backup_strategy: 'online_backup',
  source_directories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
  client_commands: ['sqlite3'],
  documentation_url: 'https://www.sqlite.org/backup.html',
  notes: ['Uses the SQLite Online Backup API through sqlite3 .backup.'],
  script_drafts: {
    pre_backup: {
      name: 'Prepare SQLite backup',
      description: 'Create a consistent SQLite backup.',
      content:
        '#!/usr/bin/env bash\nset -euo pipefail\nsqlite3 "$SQLITE_DATABASE_PATH" ".backup /var/tmp/borg-ui/database-dumps/sqlite/database.sqlite3"\n',
      timeout: 300,
    },
    post_backup: {
      name: 'Clean SQLite backup',
      description: 'Remove transient SQLite backup files.',
      content:
        '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui/database-dumps/sqlite\n',
      timeout: 120,
    },
  },
}

const allTemplates = [
  postgresqlTemplate,
  mysqlTemplate,
  mongoTemplate,
  redisTemplate,
  sqliteTemplate,
]

const legacyDiscoveryResponse = {
  source_types: [],
  detections: [],
  templates: allTemplates,
}

const filesystemSnapshotCapabilities = {
  providers: [
    {
      id: 'btrfs',
      label: 'btrfs read-only subvolume snapshot',
      command: 'btrfs',
      available: true,
      requirements: ['The selected path must be a btrfs subvolume visible to the Borg UI server.'],
    },
    {
      id: 'zfs',
      label: 'zfs dataset snapshot',
      command: 'zfs',
      available: false,
      requirements: ['The selected path must live under the configured zfs dataset mountpoint.'],
    },
  ],
  supported_source_types: ['local'],
  unsupported_source_targets: [
    'Remote SSH sources are not supported because snapshot commands must run on the source host.',
    'Managed-agent sources are not supported in this server-side snapshot flow.',
  ],
  default_staging_path: '/var/tmp/borg-ui/snapshots',
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
    mock.onGet('/source-discovery/filesystem-snapshots').reply(200, filesystemSnapshotCapabilities)

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
    mock.onGet(/\/managed-machines\/agents\/31\/filesystem\/browse.*/).reply(200, {
      success: true,
      current_path: '/',
      parent_path: null,
      items: [
        {
          name: 'srv',
          path: '/srv',
          type: 'directory',
          size: 0,
          modified_at: 0,
          hidden: false,
        },
        {
          name: 'data.txt',
          path: '/data.txt',
          type: 'file',
          size: 1024,
          modified_at: 0,
          hidden: false,
        },
      ],
    })

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

const mixedSinglePathState: WizardState = {
  ...createInitialState(),
  sourceType: 'mixed',
  sourceDirectories: [
    '/local/Users/karanhudia/test-backups/restore-speed-test',
    '/home/karanhudia/test-backup-source',
  ],
  sourceLocations: [
    {
      source_type: 'remote',
      source_ssh_connection_id: 11,
      paths: ['/home/karanhudia/test-backup-source'],
    },
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      paths: ['/local/Users/karanhudia/test-backups/restore-speed-test'],
    },
  ],
}

const btrfsSnapshotState: WizardState = {
  ...createInitialState(),
  sourceType: 'local',
  sourceDirectories: ['/srv/app'],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/srv/app'],
      snapshot: {
        provider: 'btrfs',
        staging_path: '/var/tmp/borg-ui/snapshots',
        recursive: false,
      },
    },
  ],
}

const zfsIncompleteSnapshotState: WizardState = {
  ...createInitialState(),
  sourceType: 'local',
  sourceDirectories: ['/srv/app/uploads'],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/srv/app/uploads'],
      snapshot: {
        provider: 'zfs',
        recursive: false,
      },
    },
  ],
}

const translations: Record<string, string> = {
  'backupPlans.sourceChooser.title': 'Choose backup source',
  'backupPlans.sourceChooser.where': 'Where are the files?',
  'backupPlans.sourceChooser.localSource': 'Local source',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.remoteMachine': 'Remote machine',
  'backupPlans.sourceChooser.remoteMachineDescription': 'Pull from an SSH connection',
  'backupPlans.sourceChooser.managedAgent': 'Managed agent',
  'backupPlans.sourceChooser.managedAgentDescription': 'Read paths from an enrolled agent',
  'backupPlans.sourceChooser.selectManagedAgent': 'Select a managed agent',
  'backupPlans.sourceChooser.noManagedAgents': 'No managed agents available',
  'backupPlans.sourceChooser.agentFallback': 'Agent #{{id}}',
  'backupPlans.sourceChooser.selectRemoteMachine': 'Select a remote machine',
  'backupPlans.sourceChooser.noRemoteMachines': 'No SSH connections available',
  'backupPlans.sourceChooser.readingFromLocal': 'Reading directly from this server',
  'backupPlans.sourceChooser.snapshotMode': 'Snapshot mode',
  'backupPlans.sourceChooser.snapshotModeNone': 'No filesystem snapshot',
  'backupPlans.sourceChooser.snapshotModeBtrfs': 'btrfs snapshot',
  'backupPlans.sourceChooser.snapshotModeZfs': 'zfs snapshot',
  'backupPlans.sourceChooser.snapshotRequirementsTitle': 'Host requirements',
  'backupPlans.sourceChooser.snapshotLocalOnly':
    'Snapshots are only available for Borg UI server paths.',
  'backupPlans.sourceChooser.snapshotBtrfsStagingPath': 'Snapshot staging path',
  'backupPlans.sourceChooser.snapshotZfsDataset': 'ZFS dataset',
  'backupPlans.sourceChooser.snapshotZfsMountpoint': 'ZFS mountpoint',
  'backupPlans.sourceChooser.snapshotZfsRequired': 'Required for zfs snapshots',
  'backupPlans.sourceChooser.snapshotRecursive': 'Recursive snapshot',
  'backupPlans.sourceChooser.snapshotToolAvailable': '{{command}} available',
  'backupPlans.sourceChooser.snapshotToolMissing': '{{command}} not found',
  'backupPlans.sourceChooser.snapshotChip': '{{provider}} snapshot',
  'backupPlans.sourceChooser.kindFiles': 'Files',
  'backupPlans.sourceChooser.kindDatabase': 'Database',
  'backupPlans.sourceChooser.kindContainer': 'Container',
  'backupPlans.sourceChooser.kindContainerSoonBadge': 'Soon',
  'backupPlans.sourceChooser.advancedCaptureMode': 'Advanced — Capture mode',
  'backupPlans.sourceChooser.captureModeDirect': 'Direct (no snapshot)',
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
  'backupPlans.sourceChooser.selectPaths': 'Select paths',
  'backupPlans.sourceChooser.currentPath': 'Current path',
  'backupPlans.sourceChooser.agentBrowseTitle': 'Browse {{agent}}',
  'backupPlans.sourceChooser.agentBrowseFailed': 'Could not browse this agent',
  'backupPlans.sourceChooser.openPath': 'Open',
  'backupPlans.sourceChooser.parentDirectory': 'Parent directory',
  'backupPlans.sourceChooser.selected': 'Selected',
  'backupPlans.sourceChooser.select': 'Select',
  'backupPlans.sourceChooser.emptyDirectory': 'No visible files in this directory',
  'backupPlans.sourceChooser.loading': 'Loading',
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
  return (translations[key] || key)
    .replace('{{command}}', String(options?.command ?? ''))
    .replace('{{provider}}', String(options?.provider ?? ''))
}

interface DialogStoryArgs {
  wizardState: WizardState
  mockOptions: MockOptions
  initialView?: 'paths' | 'database' | 'database-detail'
  initialScanTarget?: { type: 'local' | 'remote'; sshId: number | '' }
  initialCaptureModeExpanded?: boolean
  scrollToText?: string
}

function DialogStory({
  wizardState,
  mockOptions,
  initialView,
  initialScanTarget,
  initialCaptureModeExpanded,
  scrollToText,
}: DialogStoryArgs) {
  useMockedDiscovery(mockOptions)
  const stableState = useMemo(() => wizardState, [wizardState])

  useEffect(() => {
    if (!scrollToText) return undefined

    let timeout: number | undefined
    let attempts = 0

    const scrollToMatch = () => {
      const match = Array.from(
        document.querySelectorAll<HTMLElement>('button, [role="button"], label, [role="combobox"]')
      ).find((element) => element.textContent?.includes(scrollToText))

      if (match) {
        match.scrollIntoView({ block: 'center' })
        return
      }

      attempts += 1
      if (attempts < 60) {
        timeout = window.setTimeout(scrollToMatch, 50)
      }
    }

    timeout = window.setTimeout(scrollToMatch, 50)

    return () => {
      if (timeout) window.clearTimeout(timeout)
    }
  }, [scrollToText])

  return (
    <Box sx={{ width: 1, height: '100vh', position: 'relative' }}>
      <SourceSelectionDialog
        open
        wizardState={stableState}
        sshConnections={sshConnections}
        agentMachines={agentMachines}
        fullRepositories={repositories}
        scripts={[]}
        loadingScripts={false}
        updateState={() => {}}
        onCreateScript={async () => ({ id: 1 })}
        onClose={() => {}}
        t={t as never}
        initialView={initialView}
        initialScanTarget={initialScanTarget}
        initialCaptureModeExpanded={initialCaptureModeExpanded}
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

export const PathPickerCaptureModeExpanded: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialCaptureModeExpanded
      scrollToText="Snapshot mode"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Local file source picker with Advanced capture mode expanded, covering the accordion spacing around snapshot controls.',
      },
    },
  },
}

export const PathPickerWithBtrfsSnapshot: Story = {
  render: () => (
    <DialogStory wizardState={btrfsSnapshotState} mockOptions={{ scanStatus: 'detected' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Local source group with btrfs snapshot staging enabled. The dialog shows host requirements, tool availability, and the staging path.',
      },
    },
  },
}

export const PathPickerWithIncompleteZfsSnapshot: Story = {
  render: () => (
    <DialogStory
      wizardState={zfsIncompleteSnapshotState}
      mockOptions={{ scanStatus: 'detected' }}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Local source group with zfs snapshot mode selected but missing required dataset and mountpoint fields. The dialog shows inline validation and keeps Apply disabled.',
      },
    },
  },
}

export const PathPickerMixedSinglePathGroups: Story = {
  render: () => (
    <DialogStory wizardState={mixedSinglePathState} mockOptions={{ scanStatus: 'detected' }} />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Two source groups, each with a single path — exercises the inline single-line group layout.',
      },
    },
  },
}

export const DatabaseScanDetected: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
      scrollToText="SQLite"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Open the Database view from "Scan a database instead". Mocked endpoint returns two detected engines plus all five templates, including SQLite.',
      },
    },
  },
}

export const DatabaseScanRemoteTarget: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
      initialScanTarget={{ type: 'remote', sshId: 11 }}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database scan view with a remote SSH target selected, showing the shared SSH connection picker row.',
      },
    },
  },
}

export const DatabaseScanNothingFound: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'nothing-found' }}
      initialView="database"
    />
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
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'failed' }}
      initialView="database"
    />
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
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'endpoint-missing' }}
      initialView="database"
    />
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
