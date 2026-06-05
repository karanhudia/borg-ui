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
  documentation_url: 'https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html',
  notes: ['Uses mysqldump with a Borg-managed staging directory.'],
  script_drafts: {
    pre_backup: {
      name: 'Prepare MySQL dump',
      description: 'Create a MySQL dump.',
      content: '#!/usr/bin/env bash\nset -euo pipefail\nmysqldump --all-databases\n',
      timeout: 900,
    },
    post_backup: {
      name: 'Clean MySQL dump',
      description: 'Remove transient MySQL dump files.',
      content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui/mysql\n',
      timeout: 120,
    },
  },
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
  scanned_paths: [
    '/var/lib/postgresql',
    '/var/lib/mysql',
    '/var/lib/mongodb',
    '/var/lib/redis',
    '/srv/app',
  ],
  detections: [
    { ...postgresqlTemplate, detected: true, detection_source: '/var/lib/postgresql' },
    { ...mysqlTemplate, detected: true, detection_source: '/var/lib/mysql' },
    {
      ...sqliteTemplate,
      detected: true,
      detection_source: '/srv/compose/vaultwarden/data/db.sqlite3',
    },
    { ...sqliteTemplate, detected: true, detection_source: '/srv/app/cache.sqlite3' },
  ],
  templates: allTemplates,
  warnings: [],
}

const multipleSqliteScanResponse = {
  ...detectedScanResponse,
  scanned_paths: ['/srv/app'],
  detections: [
    { ...sqliteTemplate, detected: true, detection_source: '/srv/app/state.sqlite' },
    { ...sqliteTemplate, detected: true, detection_source: '/srv/app/cache.sqlite3' },
  ],
}

const singleSqliteScanResponse = {
  ...detectedScanResponse,
  scanned_paths: ['/srv/app'],
  detections: [{ ...sqliteTemplate, detected: true, detection_source: '/srv/app/state.sqlite' }],
}

const multipleTypeScanResponse = {
  ...detectedScanResponse,
  scanned_paths: ['/var/lib/postgresql', '/var/lib/mysql', '/srv/app'],
  detections: [
    { ...postgresqlTemplate, detected: true, detection_source: '/var/lib/postgresql' },
    { ...mysqlTemplate, detected: true, detection_source: '/var/lib/mysql' },
    { ...sqliteTemplate, detected: true, detection_source: '/srv/app/state.sqlite' },
  ],
}

const nothingFoundScanResponse = {
  ...detectedScanResponse,
  detections: [],
}

const detectedContainerScanResponse = {
  scan_target: {
    source_type: 'local',
    source_ssh_connection_id: null,
    label: 'This Borg UI server',
  },
  containers: [
    {
      id: '5ad07b8f01d2',
      name: 'postgres',
      image: 'postgres:17',
      status: 'running',
      state: 'running',
      export_path: '/var/tmp/borg-ui/container-exports/postgres',
      backup_mode: 'export',
      notes: [
        'docker export captures the container filesystem.',
        'Bind mounts and Docker named volumes are not included by docker export.',
      ],
      mounts: [
        {
          type: 'volume',
          name: 'postgres-data',
          source: '/var/lib/docker/volumes/postgres-data/_data',
          destination: '/var/lib/postgresql/data',
          backed_up: false,
          reason: 'Not included in docker export; add this path separately from Files if needed.',
          size_bytes: 1073741824,
          size_status: 'available',
        },
        {
          type: 'bind',
          name: null,
          source: '/srv/postgres/conf',
          destination: '/etc/postgresql/conf.d',
          backed_up: false,
          reason: 'Not included in docker export; add this path separately from Files if needed.',
          size_bytes: null,
          size_status: 'permission_denied',
        },
        {
          type: 'bind',
          name: null,
          source: '/srv/postgres/archive',
          destination: '/var/lib/postgresql/archive',
          backed_up: false,
          reason: 'Not included in docker export; add this path separately from Files if needed.',
          size_bytes: null,
          size_status: 'unavailable',
        },
        {
          type: 'volume',
          name: 'postgres-wal',
          source: '/var/lib/docker/volumes/postgres-wal/_data',
          destination: '/var/lib/postgresql/wal',
          backed_up: false,
          reason: 'Not included in docker export; add this path separately from Files if needed.',
          size_bytes: null,
          size_status: 'timeout',
        },
      ],
    },
  ],
  warnings: [],
}

interface MockOptions {
  scanStatus?:
    | 'detected'
    | 'single-sqlite'
    | 'multiple-sqlite'
    | 'multiple-type'
    | 'nothing-found'
    | 'failed'
    | 'endpoint-missing'
  legacyTemplates?: boolean
}

function useMockedDiscovery({ scanStatus = 'detected', legacyTemplates = true }: MockOptions) {
  useEffect(() => {
    const mock = new MockAdapter(api, { onNoMatch: 'passthrough' })

    if (legacyTemplates) {
      mock.onGet('/source-discovery/databases').reply(200, legacyDiscoveryResponse)
    }
    mock.onGet('/source-discovery/filesystem-snapshots').reply(200, filesystemSnapshotCapabilities)
    mock.onPost('/source-discovery/containers/scan').reply(200, detectedContainerScanResponse)

    if (scanStatus === 'detected') {
      mock.onPost('/source-discovery/databases/scan').reply(200, detectedScanResponse)
    } else if (scanStatus === 'single-sqlite') {
      mock.onPost('/source-discovery/databases/scan').reply(200, singleSqliteScanResponse)
    } else if (scanStatus === 'multiple-sqlite') {
      mock.onPost('/source-discovery/databases/scan').reply(200, multipleSqliteScanResponse)
    } else if (scanStatus === 'multiple-type') {
      mock.onPost('/source-discovery/databases/scan').reply(200, multipleTypeScanResponse)
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

const databaseQueuedState: WizardState = {
  ...createInitialState(),
  sourceType: 'local',
  sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
      database: {
        template_id: 'postgresql',
        engine: 'PostgreSQL',
        display_name: 'PostgreSQL database',
        backup_strategy: 'logical_dump',
        detected_source_path: '/var/lib/postgresql',
        detection_label: 'This Borg UI server',
        capture_mode: 'dump',
        dump_path: '/var/tmp/borg-ui/database-dumps/postgresql',
        backup_paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
        script_execution_target: 'source',
        pre_backup_script_id: 101,
        post_backup_script_id: 102,
        pre_backup_script_parameters: {},
        post_backup_script_parameters: {},
        script_execution_order: 1,
      },
    },
  ],
  databaseTemplateId: 'postgresql',
}

const databaseMultiQueuedState: WizardState = {
  ...databaseQueuedState,
  sourceDirectories: [
    '/var/tmp/borg-ui/database-dumps/postgresql',
    '/var/tmp/borg-ui/database-dumps/mysql',
  ],
  sourceLocations: [
    ...(databaseQueuedState.sourceLocations || []),
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
      database: {
        template_id: 'mysql',
        engine: 'MySQL / MariaDB',
        display_name: 'MySQL or MariaDB database',
        backup_strategy: 'logical_dump',
        detected_source_path: '/var/lib/mysql',
        detection_label: 'This Borg UI server',
        capture_mode: 'dump',
        dump_path: '/var/tmp/borg-ui/database-dumps/mysql',
        backup_paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
        script_execution_target: 'source',
        pre_backup_script_id: 103,
        post_backup_script_id: 104,
        pre_backup_script_parameters: {},
        post_backup_script_parameters: {},
        script_execution_order: 2,
      },
    },
  ],
}

const databaseMultiSqliteQueuedState: WizardState = {
  ...createInitialState(),
  sourceType: 'local',
  sourceDirectories: [
    '/var/tmp/borg-ui/database-dumps/sqlite/state',
    '/var/tmp/borg-ui/database-dumps/sqlite/cache',
  ],
  sourceLocations: [
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/sqlite/state'],
      database: {
        template_id: 'sqlite',
        engine: 'SQLite',
        display_name: 'SQLite database',
        backup_strategy: 'online_backup',
        detected_source_path: '/srv/app/state.sqlite',
        detection_label: 'This Borg UI server',
        capture_mode: 'dump',
        dump_path: '/var/tmp/borg-ui/database-dumps/sqlite/state',
        backup_paths: ['/var/tmp/borg-ui/database-dumps/sqlite/state'],
        script_execution_target: 'source',
        pre_backup_script_id: 201,
        post_backup_script_id: 202,
        pre_backup_script_parameters: {
          SQLITE_DATABASE_PATH: '/srv/app/state.sqlite',
        },
        post_backup_script_parameters: {},
        script_execution_order: 1,
      },
    },
    {
      source_type: 'local',
      source_ssh_connection_id: null,
      agent_machine_id: null,
      paths: ['/var/tmp/borg-ui/database-dumps/sqlite/cache'],
      database: {
        template_id: 'sqlite',
        engine: 'SQLite',
        display_name: 'SQLite database',
        backup_strategy: 'online_backup',
        detected_source_path: '/srv/app/cache.sqlite3',
        detection_label: 'This Borg UI server',
        capture_mode: 'dump',
        dump_path: '/var/tmp/borg-ui/database-dumps/sqlite/cache',
        backup_paths: ['/var/tmp/borg-ui/database-dumps/sqlite/cache'],
        script_execution_target: 'source',
        pre_backup_script_id: 201,
        post_backup_script_id: 202,
        pre_backup_script_parameters: {
          SQLITE_DATABASE_PATH: '/srv/app/cache.sqlite3',
        },
        post_backup_script_parameters: {},
        script_execution_order: 2,
      },
    },
  ],
  databaseTemplateId: 'sqlite',
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
  'backupPlans.sourceChooser.managedAgentRequiresPro': 'Managed-agent sources require Pro.',
  'backupPlans.sourceChooser.mixedSourceTypesRequiresPro':
    'Mixed source types require Pro. Multiple paths from the same source type are still available.',
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
  'backupPlans.sourceChooser.captureModeDatabase': 'Database capture mode',
  'backupPlans.sourceChooser.captureModeDump': 'Dump to staging path',
  'backupPlans.sourceChooser.captureModeOriginal': 'Back up original path',
  'backupPlans.sourceChooser.captureModeOriginalWarning':
    'Borg will read the live database files directly. Use this only when the database is stopped or you have another consistency mechanism.',
  'backupPlans.sourceChooser.captureModeOriginalUnavailable':
    'Original path mode requires a detected filesystem path.',
  'backupPlans.sourceChooser.databaseBackupTitle': 'Add database backup',
  'backupPlans.sourceChooser.databaseSourceMachine': 'Source machine',
  'backupPlans.sourceChooser.databaseLivePath': 'Live database path',
  'backupPlans.sourceChooser.databaseDumpPath': 'Dump path',
  'backupPlans.sourceChooser.databaseBackupPaths': 'Final Borg paths',
  'backupPlans.sourceChooser.containerBackupTitle': 'Add Docker container backup',
  'backupPlans.sourceChooser.containerName': 'Container name or ID',
  'backupPlans.sourceChooser.containerImage': 'Image (optional)',
  'backupPlans.sourceChooser.containerExportPath': 'Export staging path',
  'backupPlans.sourceChooser.containerExportHint':
    'Borg UI exports the container filesystem to a staging path before Borg reads it. This does not back up the Docker image, bind mounts, or named volumes.',
  'backupPlans.sourceChooser.containerSourceMachine': 'Docker host',
  'backupPlans.sourceChooser.containerModeExport': 'docker export',
  'backupPlans.sourceChooser.scanContainers': 'Scan containers',
  'backupPlans.sourceChooser.rescanContainers': 'Re-scan containers',
  'backupPlans.sourceChooser.scanContainersHint': 'Find containers on the selected Docker host.',
  'backupPlans.sourceChooser.detectedContainers': 'Detected containers',
  'backupPlans.sourceChooser.containerBackupCoverageTitle': 'What this source backs up',
  'backupPlans.sourceChooser.containerFilesystemIncluded':
    'Included: container filesystem export at {{path}}',
  'backupPlans.sourceChooser.containerMountsNotIncluded': 'Not included: mounted data',
  'backupPlans.sourceChooser.containerMountsNotIncludedHelp':
    'Add these mount paths as Files sources if they contain data you need.',
  'backupPlans.sourceChooser.containerMountNotIncluded': 'Not included in docker export',
  'backupPlans.sourceChooser.containerMountsOptional': 'Optional mounted data',
  'backupPlans.sourceChooser.containerMountsOptionalHelp':
    'Select mounts to add them as Files sources in this plan.',
  'backupPlans.sourceChooser.includeContainerMountAria':
    'Include mounted data {{path}} as a Files source',
  'backupPlans.sourceChooser.containerMountDestination': 'Mounted at {{path}}',
  'backupPlans.sourceChooser.containerMountSizeAvailable': '{{size}}',
  'backupPlans.sourceChooser.containerMountSizeUnavailable': 'Size unavailable',
  'backupPlans.sourceChooser.containerMountSizePermissionDenied': 'Permission denied',
  'backupPlans.sourceChooser.containerMountSizeTimeout': 'Size timed out',
  'backupPlans.sourceChooser.containerImageMetadata':
    'Image {{image}} identifies this container; Borg UI does not back up the image.',
  'backupPlans.sourceChooser.addDetectedContainer': 'Add detected container',
  'backupPlans.sourceChooser.addDetectedContainerShort': 'Add',
  'backupPlans.sourceChooser.containerAdded': 'Added',
  'backupPlans.sourceChooser.noContainersFoundTitle': 'No containers found',
  'backupPlans.sourceChooser.noContainersFoundBody':
    'Check Docker access on this host, or enter a container manually.',
  'backupPlans.sourceChooser.containerScanUnsupportedForAgents':
    'Docker container scanning is available for the Borg UI server and SSH sources. Enter managed-agent containers manually.',
  'backupPlans.sourceChooser.containerScanFailedBody':
    'Docker container scan did not return data. Check Docker access on this host and try again.',
  'backupPlans.sourceChooser.addContainer': 'Add container',
  'backupPlans.sourceChooser.selectedContainers': 'Selected containers',
  'backupPlans.sourceChooser.containerScriptsAssigned': 'Export scripts assigned',
  'backupPlans.sourceChooser.discoveredAtHint':
    'Live data directory. The pre-backup script targets this instance; Borg does not read these files directly.',
  'backupPlans.sourceChooser.borgWillBackUpHint':
    'Dump output staging directory. The pre-backup script writes the dump here; Borg captures it.',
  'backupPlans.sourceChooser.selectedDatabases': 'Selected databases',
  'backupPlans.sourceChooser.databaseScriptsAssigned': 'Source scripts assigned',
  'backupPlans.sourceChooser.databaseScriptsSkipped': 'No source scripts',
  'backupPlans.sourceChooser.showTemplates': 'Show templates',
  'backupPlans.sourceChooser.hideTemplates': 'Hide templates',
  'backupPlans.sourceChooser.scanTarget': 'Scan where?',
  'backupPlans.sourceChooser.pathsToScan': 'Paths to scan',
  'backupPlans.sourceChooser.noScanPaths': 'Add at least one path to scan.',
  'backupPlans.sourceChooser.scanning': 'Scanning…',
  'backupPlans.sourceChooser.rescan': 'Re-scan',
  'backupPlans.sourceChooser.advancedScanOptions': 'Advanced scan options',
  'backupPlans.sourceChooser.scanMaxDepth': 'Max depth',
  'backupPlans.sourceChooser.scanMaxDepthHelp':
    '0 = check the path only. Higher = walk that many levels deep.',
  'backupPlans.sourceChooser.scanTimeout': 'Timeout (seconds)',
  'backupPlans.sourceChooser.scanTimeoutHelp': 'Hard cap on the scan duration.',
  'backupPlans.sourceChooser.scanIgnorePatterns': 'Ignore patterns (one per line)',
  'backupPlans.sourceChooser.scanIgnorePatternsHelp':
    'Directory names to skip during the walk. Wildcards (*) are allowed.',
  'backupPlans.sourceChooser.scanForDatabases': 'Scan for databases',
  'backupPlans.sourceChooser.scanForDatabasesHint': 'Find databases running on the source machine.',
  'backupPlans.sourceChooser.scanForDatabasesTitle': 'Scan for databases',
  'backupPlans.sourceChooser.scanForDatabasesSubtitle':
    'Pick a detected database, or close this dialog and choose a template manually.',
  'backupPlans.sourceChooser.closeScanDialog': 'Close',
  'backupPlans.sourceChooser.noQueuedDatabases': 'No databases selected yet.',
  'backupPlans.sourceChooser.scanFailedBody': 'Check the connection or try again.',
  'backupPlans.sourceChooser.scanEndpointMissing':
    "Database scanning isn't available on this server yet. Open templates to configure manually.",
  'backupPlans.sourceChooser.nothingFoundBody':
    'Add another path above, or open templates to set one up manually.',
  'backupPlans.sourceChooser.checkedPaths': 'Checked:',
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
  'backupPlans.sourceChooser.applyContainers': 'Use these containers',
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
  'backupPlans.sourceChooser.applyDatabase': 'Add database',
  'backupPlans.sourceChooser.scriptDrafts': 'Script drafts',
  'backupPlans.sourceChooser.preScriptDraft': 'Pre-backup script draft',
  'backupPlans.sourceChooser.postScriptDraft': 'Post-backup script draft',
  'backupPlans.sourceChooser.createScripts': 'Create new scripts',
  'backupPlans.sourceChooser.reuseScripts': 'Use existing scripts',
  'backupPlans.sourceChooser.skipScripts': 'Skip script assignment',
  'backupPlans.sourceChooser.preScriptName': 'Pre-backup script name',
  'backupPlans.sourceChooser.postScriptName': 'Post-backup script name',
  'backupPlans.sourceChooser.preExistingScript': 'Existing pre-backup script',
  'backupPlans.sourceChooser.postExistingScript': 'Existing post-backup script',
  'backupPlans.sourceChooser.notesLabel': 'Notes',
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
    .replace('{{path}}', String(options?.path ?? ''))
    .replace('{{size}}', String(options?.size ?? ''))
}

interface DialogStoryArgs {
  wizardState: WizardState
  mockOptions: MockOptions
  initialView?: 'paths' | 'database' | 'database-detail' | 'container'
  initialScanTarget?: { type: 'local' | 'remote'; sshId: number | '' }
  initialCaptureModeExpanded?: boolean
  initialSelectedDatabase?: SourceDiscoveryDatabase
  initialScanDialogOpen?: boolean
  canUseManagedAgents?: boolean
  canUseMixedSourceTypes?: boolean
  scrollToText?: string
  autoClickText?: string
}

function DialogStory({
  wizardState,
  mockOptions,
  initialView,
  initialScanTarget,
  initialCaptureModeExpanded,
  initialSelectedDatabase,
  initialScanDialogOpen,
  canUseManagedAgents = true,
  canUseMixedSourceTypes = true,
  scrollToText,
  autoClickText,
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

  useEffect(() => {
    if (!autoClickText) return undefined

    let timeout: number | undefined
    let attempts = 0

    const clickMatch = () => {
      const match = Array.from(document.querySelectorAll<HTMLButtonElement>('button')).find(
        (element) => element.textContent?.includes(autoClickText)
      )

      if (match) {
        match.click()
        return
      }

      attempts += 1
      if (attempts < 60) {
        timeout = window.setTimeout(clickMatch, 50)
      }
    }

    timeout = window.setTimeout(clickMatch, 50)

    return () => {
      if (timeout) window.clearTimeout(timeout)
    }
  }, [autoClickText])

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
        initialSelectedDatabase={initialSelectedDatabase}
        initialScanDialogOpen={initialScanDialogOpen}
        canUseManagedAgents={canUseManagedAgents}
        canUseMixedSourceTypes={canUseMixedSourceTypes}
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

export const ContainerPickerEmpty: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="container"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Docker container source picker with host selection, generated export staging path, and queued source scripts.',
      },
    },
  },
}

export const ContainerPickerDetected: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="container"
      autoClickText="Scan containers"
      scrollToText="Mounts not included"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Docker container source picker after a scan returns a detected container, including the exact export path and optional mounted data selection for Files backup.',
      },
    },
  },
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

export const CommunityMixedSourcesLocked: Story = {
  render: () => (
    <DialogStory
      wizardState={mixedSinglePathState}
      mockOptions={{ scanStatus: 'detected' }}
      canUseManagedAgents={false}
      canUseMixedSourceTypes={false}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Community plan lock state: managed-agent source is disabled and mixed local + SSH source groups cannot be applied.',
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
      initialScanDialogOpen
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Scan sub-dialog open over the Database tab. Mocked endpoint returns detected engines including multiple SQLite files; the dialog shows the scan target picker, paths, detected tiles, and truncated detected paths that reveal the full path on hover.',
      },
    },
  },
}

export const DatabaseScanMultipleSqliteDetected: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'multiple-sqlite' }}
      initialView="database"
      initialScanDialogOpen
      scrollToText="/srv/app/state.sqlite"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Scan sub-dialog with multiple same-type SQLite detections visible in the results grid.',
      },
    },
  },
}

export const DatabaseScanSingleSqliteDetected: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'single-sqlite' }}
      initialView="database"
      initialScanDialogOpen
      scrollToText="/srv/app/state.sqlite"
    />
  ),
  parameters: {
    docs: {
      description: {
        story: 'Scan sub-dialog with one SQLite detection visible in the results grid.',
      },
    },
  },
}

export const DatabaseScanMultipleTypesDetected: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'multiple-type' }}
      initialView="database"
      initialScanDialogOpen
      scrollToText="MySQL / MariaDB"
    />
  ),
  parameters: {
    docs: {
      description: {
        story: 'Scan sub-dialog with multiple database engine types visible in the results grid.',
      },
    },
  },
}

export const DatabaseQueuedSelection: Story = {
  render: () => (
    <DialogStory
      wizardState={databaseQueuedState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database tab with an already queued PostgreSQL selection. The tab badge and selected database summary persist when the dialog is reopened.',
      },
    },
  },
}

export const DatabaseQueuedSelectionWithScanOpen: Story = {
  render: () => (
    <DialogStory
      wizardState={databaseQueuedState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
      initialScanDialogOpen
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database tab reopened with an existing queued database while the scan sub-dialog is open. New detections can be added without the saved template overwriting the active choice.',
      },
    },
  },
}

export const DatabaseQueuedMultipleSelection: Story = {
  render: () => (
    <DialogStory
      wizardState={databaseMultiQueuedState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database tab with PostgreSQL and MySQL queued together. The badge and selected database list show multiple selections without collapsing them into one.',
      },
    },
  },
}

export const DatabaseQueuedMultipleSqliteSelection: Story = {
  render: () => (
    <DialogStory
      wizardState={databaseMultiSqliteQueuedState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database"
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database tab with two detected SQLite files queued together. Each selected database keeps its own staging path under the SQLite dump directory.',
      },
    },
  },
}

export const DatabaseTemplateDetail: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'detected' }}
      initialView="database-detail"
      initialSelectedDatabase={mysqlTemplate}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Database template detail view after selecting MySQL. The header uses the template-specific title, while the body keeps useful notes visible without engine or backup-strategy metadata chips.',
      },
    },
  },
}

export const DatabaseDetectedSqliteDetail: Story = {
  render: () => (
    <DialogStory
      wizardState={emptyWizardState}
      mockOptions={{ scanStatus: 'single-sqlite' }}
      initialView="database-detail"
      initialCaptureModeExpanded
      initialSelectedDatabase={{
        ...sqliteTemplate,
        detected: true,
        detection_source: '/srv/app/state.sqlite',
      }}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Detected SQLite detail view after selecting a scan result. The live database path remains visible while the final Borg path uses a separate staging directory.',
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
      initialScanDialogOpen
      initialScanTarget={{ type: 'remote', sshId: 11 }}
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Scan sub-dialog open with a remote SSH target selected, showing the shared SSH connection picker row.',
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
      initialScanDialogOpen
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'Scan completed successfully but found nothing. The empty-state banner inside the sub-dialog explains next actions; templates remain visible on the parent Database tab when the user closes the sub-dialog.',
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
      initialScanDialogOpen
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          '502 from the scan endpoint. The warning banner with inline Re-scan lives inside the sub-dialog; templates remain accessible on the parent tab.',
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
      initialScanDialogOpen
    />
  ),
  parameters: {
    docs: {
      description: {
        story:
          'New POST endpoint not deployed yet (404). Info banner, with templates available from the legacy GET fallback after the user opens them.',
      },
    },
  },
}
