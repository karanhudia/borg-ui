import { useState } from 'react'
import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { createInitialState } from '../state'
import { SourceStep } from '../wizard-step/SourceStep'

const apiMocks = vi.hoisted(() => ({
  databases: vi.fn(),
  scanDatabases: vi.fn(),
  scanContainers: vi.fn(),
  filesystemSnapshots: vi.fn(),
}))

vi.mock('../../../services/api', () => ({
  managedAgentsAPI: {
    browseFilesystem: vi.fn(),
  },
  sourceDiscoveryAPI: {
    databases: apiMocks.databases,
    scanDatabases: apiMocks.scanDatabases,
    scanContainers: apiMocks.scanContainers,
    filesystemSnapshots: apiMocks.filesystemSnapshots,
  },
}))

vi.mock('../../../components/wizard', () => ({
  WizardStepDataSource: ({
    onChange,
  }: {
    onChange: (updates: {
      dataSource: 'local'
      sourceDirs: string[]
      sourceSshConnectionId: string
    }) => void
  }) => (
    <div data-testid="wizard-data-source">
      Path controls
      <button
        type="button"
        onClick={() =>
          onChange({
            dataSource: 'local',
            sourceDirs: ['/srv/app-data'],
            sourceSshConnectionId: '',
          })
        }
      >
        Select app data path
      </button>
    </div>
  ),
}))

vi.mock('../../../components/ExcludePatternInput', () => ({
  default: () => <div data-testid="exclude-patterns">Exclude patterns</div>,
}))

vi.mock('../../../components/shared/CodeEditor', () => ({
  default: ({
    label,
    value,
    onChange,
  }: {
    label?: string
    value: string
    onChange: (value: string) => void
  }) => (
    <label>
      {label}
      <textarea value={value} onChange={(event) => onChange(event.target.value)} />
    </label>
  ),
}))

vi.mock('../../../components/shared/ResponsiveDialog', () => ({
  default: ({
    open,
    children,
    footer,
    maxWidth,
  }: {
    open: boolean
    children: ReactNode
    footer?: ReactNode
    maxWidth?: string
  }) =>
    open ? (
      <div role="dialog" data-max-width={maxWidth}>
        {children}
        {footer}
      </div>
    ) : null,
}))

vi.mock('../../../components/FileExplorerDialog', () => ({
  default: ({
    open,
    onSelect,
    title,
    connectionType,
    initialPath,
    sshConfig,
    agentId,
    agentDefaultPath,
  }: {
    open: boolean
    onSelect: (paths: string[]) => void
    title?: string
    connectionType?: 'local' | 'ssh' | 'agent'
    initialPath?: string
    sshConfig?: { host: string }
    agentId?: number
    agentDefaultPath?: string | null
  }) =>
    open ? (
      <div
        role="dialog"
        aria-label={title || 'File explorer'}
        data-testid="file-explorer-dialog"
        data-connection-type={connectionType}
        data-initial-path={initialPath}
        data-ssh-host={sshConfig?.host || ''}
        data-agent-id={agentId || ''}
        data-agent-default-path={agentDefaultPath || ''}
      >
        <button type="button" onClick={() => onSelect(['/selected/from-browser'])}>
          Select browsed path
        </button>
      </div>
    ) : null,
}))

const discoveryResponse = {
  source_types: [
    {
      id: 'paths',
      label: 'Files and folders',
      description: 'Back up local or remote paths.',
      status: 'enabled',
      disabled: false,
    },
    {
      id: 'database',
      label: 'Database',
      description: 'Scan supported databases.',
      status: 'enabled',
      disabled: false,
    },
    {
      id: 'container',
      label: 'Docker containers',
      description: 'Container scanning is planned.',
      status: 'planned',
      disabled: true,
    },
  ],
  detections: [],
  templates: [
    {
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
          description: 'Remove transient PostgreSQL dump files.',
          content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui\n',
          timeout: 120,
        },
      },
    },
    {
      id: 'mysql',
      engine: 'MySQL',
      display_name: 'MySQL database',
      backup_strategy: 'logical_dump',
      source_directories: ['/var/tmp/borg-ui/database-dumps/mysql'],
      client_commands: ['mysqldump'],
      documentation_url: 'https://dev.mysql.com/doc/refman/8.0/en/mysqldump.html',
      detected: false,
      detection_source: null,
      notes: ['Uses mysqldump.'],
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
    },
  ],
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

const translations: Record<string, string> = {
  'backupPlans.wizard.fields.planName': 'Plan name',
  'backupPlans.wizard.fields.description': 'Description',
  'backupPlans.sourceChooser.summaryTitle': 'Backup source',
  'backupPlans.sourceChooser.summaryEmpty': 'No source selected yet',
  'backupPlans.sourceChooser.chooseSource': 'Choose source',
  'backupPlans.sourceChooser.title': 'Choose backup source',
  'backupPlans.sourceChooser.databaseTitle': 'Database scan',
  'backupPlans.sourceChooser.filesTitle': 'Files and folders',
  'backupPlans.sourceChooser.backToTypes': 'Back to source types',
  'backupPlans.sourceChooser.back': 'Back',
  'backupPlans.sourceChooser.applyPaths': 'Use these paths',
  'backupPlans.sourceChooser.applyContainers': 'Use these containers',
  'backupPlans.sourceChooser.loading': 'Scanning sources...',
  'backupPlans.sourceChooser.noDatabaseTemplates': 'No database templates available',
  'backupPlans.sourceChooser.databaseTemplates': 'Templates',
  'backupPlans.sourceChooser.detectedDatabases': 'Detected databases',
  'backupPlans.sourceChooser.scriptDrafts': 'Script drafts',
  'backupPlans.sourceChooser.notesLabel': 'Notes',
  'backupPlans.sourceChooser.preScriptDraft': 'Pre-backup script draft',
  'backupPlans.sourceChooser.postScriptDraft': 'Post-backup script draft',
  'backupPlans.sourceChooser.createScripts': 'Create new scripts',
  'backupPlans.sourceChooser.reuseScripts': 'Use existing scripts',
  'backupPlans.sourceChooser.skipScripts': 'Skip script assignment',
  'backupPlans.sourceChooser.preScriptName': 'Pre-backup script name',
  'backupPlans.sourceChooser.postScriptName': 'Post-backup script name',
  'backupPlans.sourceChooser.preExistingScript': 'Existing pre-backup script',
  'backupPlans.sourceChooser.postExistingScript': 'Existing post-backup script',
  'backupPlans.sourceChooser.applyDatabase': 'Add database',
  'backupPlans.sourceChooser.selectedDatabases': 'Selected databases',
  'backupPlans.sourceChooser.databaseScriptsAssigned': 'Source scripts assigned',
  'backupPlans.sourceChooser.databaseScriptsSkipped': 'No source scripts',
  'backupPlans.sourceChooser.showTemplates': 'Show templates',
  'backupPlans.sourceChooser.hideTemplates': 'Hide templates',
  'backupPlans.sourceChooser.captureModeDatabase': 'Database capture mode',
  'backupPlans.sourceChooser.captureModeDump': 'Dump to staging path',
  'backupPlans.sourceChooser.captureModeOriginal': 'Back up original path',
  'backupPlans.sourceChooser.databaseSourceMachine': 'Source machine',
  'backupPlans.sourceChooser.databaseLivePath': 'Live database path',
  'backupPlans.sourceChooser.databaseDumpPath': 'Dump path',
  'backupPlans.sourceChooser.databaseBackupPaths': 'Final Borg paths',
  'backupPlans.sourceChooser.databaseBackupTitle': 'Add database backup',
  'backupPlans.sourceChooser.containerTitle': 'Docker container',
  'backupPlans.sourceChooser.containerBackupTitle': 'Add Docker container backup',
  'backupPlans.sourceChooser.containerName': 'Container name or ID',
  'backupPlans.sourceChooser.containerImage': 'Image (optional)',
  'backupPlans.sourceChooser.containerExportPath': 'Export staging path',
  'backupPlans.sourceChooser.containerExportHint':
    'Borg UI exports the container filesystem to a staging path before Borg reads it. This does not back up the Docker image, bind mounts, or named volumes.',
  'backupPlans.sourceChooser.containerExportsTo': 'Exports to',
  'backupPlans.sourceChooser.addContainerManually': 'Add by name',
  'backupPlans.sourceChooser.addContainerManuallyHelp':
    "If your container isn't listed above, add it here.",
  'backupPlans.sourceChooser.containerSourceMachine': 'Docker host',
  'backupPlans.sourceChooser.containerBackupPath': 'Export staging path',
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
  'backupPlans.sourceChooser.removeDetectedContainer': 'Remove detected container',
  'backupPlans.sourceChooser.containerAdded': 'Added',
  'backupPlans.sourceChooser.noContainersFoundTitle': 'No containers found',
  'backupPlans.sourceChooser.noContainersFoundBody':
    'Check Docker access on this host, or enter a container manually.',
  'backupPlans.sourceChooser.addContainer': 'Add container',
  'backupPlans.sourceChooser.selectedContainers': 'Selected containers',
  'backupPlans.sourceChooser.containerScriptsAssigned': 'Export scripts assigned',
  'backupPlans.sourceChooser.addSourceGroup': 'Add source group',
  'backupPlans.sourceChooser.localSource': 'Borg UI server',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.managedAgent': 'Managed agent',
  'backupPlans.sourceChooser.managedAgentDescription': 'Read paths from an enrolled managed agent',
  'backupPlans.sourceChooser.managedAgentRequiresPro': 'Managed-agent sources require Pro.',
  'backupPlans.sourceChooser.mixedSourceTypesRequiresPro':
    'Mixed source types require Pro. Multiple paths from the same source type are still available.',
  'backupPlans.sourceChooser.selectManagedAgent': 'Select a managed agent',
  'backupPlans.sourceChooser.noManagedAgents': 'No managed agents available',
  'backupPlans.sourceChooser.agentFallback': 'Agent #{{id}}',
  'backupPlans.sourceChooser.selectPaths': 'Select paths',
  'backupPlans.sourceChooser.currentPath': 'Current path',
  'backupPlans.sourceChooser.agentBrowseTitle': 'Browse {{agent}}',
  'backupPlans.sourceChooser.agentBrowseFailed': 'Could not browse this agent',
  'backupPlans.sourceChooser.openPath': 'Open',
  'backupPlans.sourceChooser.parentDirectory': 'Parent directory',
  'backupPlans.sourceChooser.selected': 'Selected',
  'backupPlans.sourceChooser.select': 'Select',
  'backupPlans.sourceChooser.emptyDirectory': 'No visible files in this directory',
  'backupPlans.sourceChooser.sshSource': 'SSH source',
  'backupPlans.sourceChooser.sshSourceDescription': 'Remote machine',
  'backupPlans.sourceChooser.sourcePath': 'Source path',
  'backupPlans.sourceChooser.addPath': 'Add path',
  'backupPlans.sourceChooser.browseCurrentSource': 'Browse current source',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
  'backupPlans.sourceChooser.removePath': 'Remove path',
  'backupPlans.sourceChooser.removeSourceGroup': 'Remove source group',
  'backupPlans.sourceChooser.where': 'Where are the files?',
  'backupPlans.sourceChooser.remoteMachine': 'Remote machine',
  'backupPlans.sourceChooser.remoteMachineDescription': 'Pull from an SSH connection',
  'backupPlans.sourceChooser.selectRemoteMachine': 'Select a remote machine',
  'backupPlans.sourceChooser.noRemoteMachines': 'No SSH connections available',
  'backupPlans.sourceChooser.scanTarget': 'Scan where?',
  'backupPlans.sourceChooser.pathsToScan': 'Paths to scan',
  'backupPlans.sourceChooser.noScanPaths': 'Add at least one path to scan.',
  'backupPlans.sourceChooser.scanning': 'Scanning...',
  'backupPlans.sourceChooser.rescan': 'Re-scan',
  'backupPlans.sourceChooser.scanEndpointMissing':
    "Database scanning isn't available on this server yet. Open templates to configure manually.",
  'backupPlans.sourceChooser.nothingFoundTitle': 'No databases found on {{target}}',
  'backupPlans.sourceChooser.nothingFoundBody':
    'Add another path above, or open templates to set one up manually.',
  'backupPlans.sourceChooser.checkedPaths': 'Checked:',
  'backupPlans.sourceChooser.detectedSection': 'Detected',
  'backupPlans.sourceChooser.detectedBadge': 'Detected',
  'backupPlans.sourceChooser.orPickTemplate': 'Or pick a template',
  'backupPlans.sourceChooser.pickTemplateManually': 'Pick a template to configure manually',
  'backupPlans.sourceChooser.scanForDatabases': 'Scan for databases',
  'backupPlans.sourceChooser.scanForDatabasesHint': 'Find databases running on the source machine.',
  'backupPlans.sourceChooser.scanForDatabasesTitle': 'Scan for databases',
  'backupPlans.sourceChooser.scanForDatabasesSubtitle':
    'Pick a detected database, or close this dialog and choose a template manually.',
  'backupPlans.sourceChooser.closeScanDialog': 'Close',
  'backupPlans.sourceChooser.noQueuedDatabases': 'No databases selected yet.',
  'backupPlans.sourceChooser.showLessPaths': 'Show less',
  'backupPlans.sourceChooser.kindFiles': 'Files',
  'backupPlans.sourceChooser.kindDatabase': 'Database',
  'backupPlans.sourceChooser.kindContainer': 'Container',
  'backupPlans.sourceChooser.kindContainerSoonBadge': 'Soon',
  'backupPlans.sourceChooser.advancedCaptureMode': 'Advanced — Capture mode',
  'backupPlans.sourceChooser.captureModeDirect': 'Direct (no snapshot)',
  'backupPlans.sourceChooser.readingFromLocal': 'Reading directly from this server',
  'backupPlans.sourceChooser.snapshotMode': 'Snapshot mode',
  'backupPlans.sourceChooser.snapshotModeNone': 'No filesystem snapshot',
  'backupPlans.sourceChooser.snapshotModeBtrfs': 'btrfs snapshot',
  'backupPlans.sourceChooser.snapshotModeZfs': 'zfs snapshot',
  'backupPlans.sourceChooser.snapshotRequirementsTitle': 'Host requirements',
  'backupPlans.sourceChooser.snapshotBtrfsStagingPath': 'Snapshot staging path',
  'backupPlans.sourceChooser.snapshotZfsDataset': 'ZFS dataset',
  'backupPlans.sourceChooser.snapshotZfsMountpoint': 'ZFS mountpoint',
  'backupPlans.sourceChooser.snapshotZfsRequired': 'Required for zfs snapshots',
  'backupPlans.sourceChooser.snapshotRecursive': 'Recursive snapshot',
  'backupPlans.sourceChooser.snapshotToolAvailable': '{{command}} available',
  'backupPlans.sourceChooser.snapshotToolMissing': '{{command}} not found',
  'backupPlans.sourceChooser.snapshotChip': '{{provider}} snapshot',
  'backupPlans.sourceChooser.backToFiles': 'Back to files and folders',
  'backupPlans.sourceChooser.change': 'Change',
  'backupPlans.sourceChooser.edit': 'Edit',
  'backupPlans.wizard.fileExplorer.sourceTitle': 'Select source paths',
}

const t = (key: string, options?: { count?: number; image?: string; size?: string }) => {
  if (key === 'backupPlans.sourceChooser.pathCount' && typeof options?.count === 'number') {
    return `${options.count} ${options.count === 1 ? 'path' : 'paths'}`
  }
  if (key === 'backupPlans.sourceChooser.showMorePaths' && typeof options?.count === 'number') {
    return `Show ${options.count} more ${options.count === 1 ? 'path' : 'paths'}`
  }
  return (translations[key] || key)
    .replace('{{command}}', String((options as { command?: string } | undefined)?.command ?? ''))
    .replace('{{provider}}', String((options as { provider?: string } | undefined)?.provider ?? ''))
    .replace('{{target}}', String((options as { target?: string } | undefined)?.target ?? ''))
    .replace('{{path}}', String((options as { path?: string } | undefined)?.path ?? ''))
    .replace('{{image}}', String(options?.image ?? ''))
    .replace('{{size}}', String(options?.size ?? ''))
}

function clickExistingTextButton(name: string | RegExp) {
  const labels = screen.getAllByText(name)
  const button = labels.map((label) => label.closest('button')).find(Boolean)
  expect(button).not.toBeNull()
  fireEvent.click(button as HTMLButtonElement)
}

function clickExistingSummaryToggle(name: string | RegExp) {
  const buttons = Array.from(document.querySelectorAll<HTMLElement>('[role="button"], button'))
  const button = buttons.find((candidate) => {
    const text = candidate.textContent || ''
    return typeof name === 'string' ? text.includes(name) : name.test(text)
  })
  expect(button).not.toBeNull()
  fireEvent.click(button as HTMLElement)
}

async function selectSourceKind(optionName: RegExp) {
  const trigger = screen.getByRole('combobox', { name: /where are the files/i })
  fireEvent.mouseDown(trigger)
  const listbox = await screen.findByRole('listbox')
  const option = within(listbox).getByRole('option', { name: optionName })
  fireEvent.click(option)
  await waitFor(() => {
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
}

async function selectRemoteMachine(optionName: RegExp) {
  await selectSourceKind(/remote machine/i)

  const trigger = screen.getByRole('combobox', { name: /select a remote machine/i })
  fireEvent.mouseDown(trigger)
  const listbox = await screen.findByRole('listbox')
  const option = within(listbox).getByText(optionName)
  fireEvent.click(option)
  await waitFor(() => {
    expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
  })
}

function renderSourceStep(overrides = {}) {
  return render(
    <SourceStep
      wizardState={createInitialState()}
      sshConnections={[]}
      agentMachines={[]}
      fullRepositories={[]}
      scripts={[
        {
          id: 7,
          name: 'Existing database preparation script with a very long descriptive name',
          parameters: null,
        },
      ]}
      loadingScripts={false}
      updateState={vi.fn()}
      openExcludeExplorer={vi.fn()}
      onCreateScript={vi.fn(async () => ({ id: 101 }))}
      t={t as never}
      {...overrides}
    />
  )
}

function StatefulSourceStep({
  initialState = createInitialState(),
  sshConnections = [],
  agentMachines = [],
  canUseManagedAgents = true,
  canUseMixedSourceTypes = true,
}: {
  initialState?: ReturnType<typeof createInitialState>
  sshConnections?: Array<{
    id: number
    host: string
    username: string
    port: number
    ssh_key_id: number
    default_path?: string
    mount_point?: string
    status: string
  }>
  agentMachines?: Array<{
    id: number
    name: string
    agent_id: string
    hostname?: string | null
    default_path?: string | null
    status: string
    created_at: string
    updated_at: string
  }>
  canUseManagedAgents?: boolean
  canUseMixedSourceTypes?: boolean
}) {
  const [wizardState, setWizardState] = useState(initialState)

  return (
    <SourceStep
      wizardState={wizardState}
      sshConnections={sshConnections}
      agentMachines={agentMachines}
      fullRepositories={[]}
      scripts={[]}
      loadingScripts={false}
      canUseManagedAgents={canUseManagedAgents}
      canUseMixedSourceTypes={canUseMixedSourceTypes}
      updateState={(updates) => setWizardState((current) => ({ ...current, ...updates }))}
      openExcludeExplorer={vi.fn()}
      onCreateScript={vi.fn(async () => ({ id: 101 }))}
      t={t as never}
    />
  )
}

const discoveryResponseWithEnabledContainer = {
  ...discoveryResponse,
  source_types: discoveryResponse.source_types.map((sourceType) =>
    sourceType.id === 'container'
      ? {
          ...sourceType,
          description: 'Back up a Docker container filesystem.',
          status: 'enabled',
          disabled: false,
        }
      : sourceType
  ),
}

const emptyScanResponse = {
  scan_target: {
    source_type: 'local' as const,
    source_ssh_connection_id: null,
    label: 'This Borg UI server',
  },
  scanned_paths: [] as string[],
  detections: [] as never[],
  templates: [] as never[],
  warnings: [] as never[],
}

function sqliteScanDetection(path: string, overrides: Record<string, unknown> = {}) {
  return {
    id: 'sqlite',
    engine: 'SQLite',
    display_name: 'SQLite database',
    backup_strategy: 'online_backup',
    source_directories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
    client_commands: ['sqlite3'],
    documentation_url: 'https://www.sqlite.org/backup.html',
    detected: true,
    detection_source: path,
    notes: ['Uses sqlite3 .backup.'],
    script_drafts: {
      pre_backup: {
        name: 'Prepare SQLite backup',
        description: 'Create a SQLite backup.',
        content: '#!/usr/bin/env bash\nset -euo pipefail\nsqlite3 "$SQLITE_DATABASE_PATH"\n',
        timeout: 300,
      },
      post_backup: {
        name: 'Clean SQLite backup',
        description: 'Remove transient SQLite backup files.',
        content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf "$BORG_UI_DB_DUMP_DIR"\n',
        timeout: 120,
      },
    },
    ...overrides,
  }
}

describe('SourceStep', () => {
  beforeEach(() => {
    apiMocks.scanDatabases.mockResolvedValue({ data: emptyScanResponse })
    apiMocks.filesystemSnapshots.mockResolvedValue({ data: filesystemSnapshotCapabilities })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows a compact source chooser before rendering path controls inline', () => {
    renderSourceStep()

    expect(screen.getByRole('button', { name: /choose source/i })).toBeInTheDocument()
    expect(screen.queryByTestId('wizard-data-source')).not.toBeInTheDocument()
  })

  it('shows the live database path in the selected source summary', () => {
    renderSourceStep({
      wizardState: {
        ...createInitialState(),
        name: 'PostgreSQL nightly',
        sourceType: 'local',
        sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
        sourceLocations: [
          {
            source_type: 'local',
            source_ssh_connection_id: null,
            paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
            database: {
              template_id: 'postgresql',
              engine: 'PostgreSQL',
              display_name: 'PostgreSQL database',
              backup_strategy: 'logical_dump',
              detected_source_path: '/var/lib/postgresql',
              detection_label: 'Borg UI server',
              capture_mode: 'dump',
              dump_path: '/var/tmp/borg-ui/database-dumps/postgresql',
              backup_paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
              script_execution_target: 'source',
            },
          },
        ],
      },
    })

    expect(screen.getByText('/var/lib/postgresql')).toBeInTheDocument()
    expect(screen.getByText('PostgreSQL database')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { expanded: false }))

    expect(screen.getAllByText('Live database path').length).toBeGreaterThan(0)
    expect(screen.getByText('Final Borg paths')).toBeInTheDocument()
    expect(screen.getByText('/var/tmp/borg-ui/database-dumps/postgresql')).toBeInTheDocument()
  })

  it('opens straight into the path picker with the source-kind pivot', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponseWithEnabledContainer })
    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    expect(screen.getByRole('dialog')).toHaveAttribute('data-max-width', 'md')
    expect(
      await screen.findByRole('combobox', { name: /where are the files/i })
    ).toBeInTheDocument()
    // Files / Database / Container pivot replaces the old "Scan database instead" link.
    expect(screen.getByRole('tab', { name: /^files$/i })).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tab', { name: /^database$/i })).toBeInTheDocument()
    const containerTab = screen.getByRole('tab', { name: /container/i })
    expect(containerTab).not.toHaveAttribute('aria-disabled', 'true')
    expect(containerTab).not.toHaveTextContent(/soon/i)
    expect(screen.queryByText(/planned/i)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('button', { name: /scan a database instead/i })
    ).not.toBeInTheDocument()
  }, 45000)

  it('scans Docker containers and lets mounted data be added as Files sources', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponseWithEnabledContainer })
    apiMocks.scanContainers.mockResolvedValue({
      data: {
        scan_target: {
          source_type: 'local',
          source_ssh_connection_id: null,
          label: 'This Borg UI server',
        },
        containers: [
          {
            id: '5ad07b8f01d2',
            name: 'portainer',
            image: 'portainer/portainer-ce:latest',
            status: 'running',
            state: 'running',
            export_path: '/var/tmp/borg-ui/container-exports/portainer',
            backup_mode: 'export',
            notes: [
              'docker export captures the container filesystem.',
              'Bind mounts and Docker named volumes are not included by docker export.',
            ],
            mounts: [
              {
                type: 'volume',
                name: 'portainer_data',
                source: '/var/lib/docker/volumes/portainer_data/_data',
                destination: '/data',
                backed_up: false,
                reason:
                  'Not included in docker export; add this path separately from Files if needed.',
                size_bytes: 1073741824,
                size_status: 'available',
              },
              {
                type: 'bind',
                name: null,
                source: '/srv/portainer/config',
                destination: '/config',
                backed_up: false,
                reason:
                  'Not included in docker export; add this path separately from Files if needed.',
                size_bytes: null,
                size_status: 'unavailable',
              },
              {
                type: 'bind',
                name: null,
                source: '/srv/portainer/private',
                destination: '/private',
                backed_up: false,
                reason:
                  'Not included in docker export; add this path separately from Files if needed.',
                size_bytes: null,
                size_status: 'permission_denied',
              },
              {
                type: 'bind',
                name: null,
                source: '/srv/portainer/slow',
                destination: '/slow',
                backed_up: false,
                reason:
                  'Not included in docker export; add this path separately from Files if needed.',
                size_bytes: null,
                size_status: 'timeout',
              },
            ],
          },
        ],
        warnings: [],
      },
    })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 401 })
      .mockResolvedValueOnce({ id: 402 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const containerTab = await screen.findByRole('tab', { name: /container/i })
    fireEvent.click(containerTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan containers/i }))

    await waitFor(() => {
      expect(apiMocks.scanContainers).toHaveBeenCalledWith({
        source_type: 'local',
        source_ssh_connection_id: null,
        include_stopped: true,
      })
    })
    expect(await screen.findByText('Detected containers')).toBeInTheDocument()
    expect(screen.getByTestId('container-scan-results')).toHaveStyle({
      maxHeight: '360px',
      overflowY: 'auto',
    })
    expect(screen.getByText('portainer')).toBeInTheDocument()
    expect(screen.queryByText('portainer/portainer-ce:latest')).not.toBeInTheDocument()
    expect(screen.queryByText('running')).not.toBeInTheDocument()
    expect(screen.queryByText('docker export')).not.toBeInTheDocument()
    expect(
      screen.getByLabelText(
        'Borg UI exports the container filesystem to a staging path before Borg reads it. This does not back up the Docker image, bind mounts, or named volumes.'
      )
    ).toBeInTheDocument()
    expect(
      screen.queryByText(
        'Image portainer/portainer-ce:latest identifies this container; Borg UI does not back up the image.'
      )
    ).not.toBeInTheDocument()
    expect(screen.queryByText('What this source backs up')).not.toBeInTheDocument()
    expect(screen.queryByText('Not included: mounted data')).not.toBeInTheDocument()
    expect(screen.getByText('Optional mounted data')).toBeInTheDocument()
    expect(
      screen.getByText('Add these mount paths as Files sources if they contain data you need.')
    ).toBeInTheDocument()
    expect(screen.getByText('→ /data')).toBeInTheDocument()
    expect(screen.getByText('/var/lib/docker/volumes/portainer_data/_data')).toBeInTheDocument()
    expect(screen.getByText('1.00 GB')).toBeInTheDocument()
    expect(screen.getByText('/srv/portainer/config')).toBeInTheDocument()
    expect(screen.getByText('Size unavailable')).toBeInTheDocument()
    expect(screen.getByText('/srv/portainer/private')).toBeInTheDocument()
    expect(screen.getByText('Permission denied')).toBeInTheDocument()
    expect(screen.getByText('/srv/portainer/slow')).toBeInTheDocument()
    expect(screen.getByText('Size timed out')).toBeInTheDocument()
    expect(
      screen.queryByText('Select mounts to add them as Files sources in this plan.')
    ).not.toBeInTheDocument()

    // Ticking the mount checkbox auto-queues the container with the mount path
    // attached as a Files-style source on the same location group.
    fireEvent.click(
      screen.getByRole('checkbox', {
        name: /include mounted data \/var\/lib\/docker\/volumes\/portainer_data\/_data as a files source/i,
      })
    )

    expect(
      await screen.findByRole('button', { name: /remove detected container/i })
    ).toBeInTheDocument()
    expect(screen.getByText('Selected containers')).toBeInTheDocument()
    expect(screen.getAllByText('/var/tmp/borg-ui/container-exports/portainer').length).toBe(2)

    clickExistingTextButton(/use these containers/i)

    await waitFor(() => {
      expect(onCreateScript).toHaveBeenCalledTimes(2)
      expect(updateState).toHaveBeenCalledTimes(1)
    })
    const updatePayload = updateState.mock.calls[0][0]
    expect(updatePayload.sourceDirectories).toEqual([
      '/var/tmp/borg-ui/container-exports/portainer',
      '/var/lib/docker/volumes/portainer_data/_data',
    ])
    const containerLocation = updatePayload.sourceLocations.find(
      (location: { container?: { container_name?: string } }) =>
        location.container?.container_name === 'portainer'
    )
    expect(containerLocation).toEqual(
      expect.objectContaining({
        source_type: 'local',
        // Mount paths live INSIDE the container location alongside the export
        // path; they no longer leak into a separate Files-only source.
        paths: [
          '/var/tmp/borg-ui/container-exports/portainer',
          '/var/lib/docker/volumes/portainer_data/_data',
        ],
        container: expect.objectContaining({
          container_name: 'portainer',
          display_name: 'portainer',
          image: 'portainer/portainer-ce:latest',
          export_path: '/var/tmp/borg-ui/container-exports/portainer',
          pre_backup_script_id: 401,
          post_backup_script_id: 402,
        }),
      })
    )
    const filesOnlyMountLocation = updatePayload.sourceLocations.find(
      (location: { paths: string[]; container?: unknown; database?: unknown }) =>
        !location.container &&
        !location.database &&
        location.paths.includes('/var/lib/docker/volumes/portainer_data/_data')
    )
    expect(filesOnlyMountLocation).toBeUndefined()
  }, 45000)

  it('keeps a files and folders summary after selecting paths on a scripted plan', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const initialState = {
      ...createInitialState(),
      sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
      preBackupScriptId: 101,
      postBackupScriptId: 102,
    }
    render(<StatefulSourceStep initialState={initialState} />)

    expect(screen.getByText('Database scan')).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /^edit$/i }))
    await screen.findByRole('tab', { name: /^database$/i })
    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app-data' },
    })
    const addPathButton = screen.getByRole('button', { name: /add path/i })
    await waitFor(() => expect(addPathButton).toBeEnabled())
    fireEvent.click(addPathButton)
    const usePathsButton = screen.getByRole('button', { name: /use these paths/i })
    await waitFor(() => expect(usePathsButton).toBeEnabled())
    fireEvent.click(usePathsButton)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    clickExistingSummaryToggle(/borg ui server/i)
    expect(screen.getByTitle('/srv/app-data')).toBeInTheDocument()
    expect(screen.getByText('Files and folders')).toBeInTheDocument()
    expect(screen.queryByText('Database scan')).not.toBeInTheDocument()
  }, 45000)

  it('adds local and multiple SSH source groups from the source modal', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const sshConnections = [
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
        default_path: '/',
        status: 'connected',
      },
    ]
    render(<StatefulSourceStep sshConnections={sshConnections} />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    expect(
      await screen.findByRole('combobox', { name: /where are the files/i })
    ).toBeInTheDocument()
    expect(screen.getByText('This Borg UI server')).toBeInTheDocument()

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })
    clickExistingTextButton(/add path/i)

    await selectRemoteMachine(/backup-a@server-a.example/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/home/app/data' },
    })
    clickExistingTextButton(/add path/i)

    await selectRemoteMachine(/backup-b@server-b.example/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/var/lib/service' },
    })
    clickExistingTextButton(/add path/i)

    const applyButton = screen.getByRole('button', { name: /use these paths/i })
    fireEvent.click(applyButton)
    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })

    clickExistingSummaryToggle(/borg ui server/i)
    clickExistingSummaryToggle(/backup-a@server-a.example/i)
    clickExistingSummaryToggle(/backup-b@server-b.example/i)
    expect(screen.getByTitle('/srv/app')).toBeInTheDocument()
    expect(screen.getByTitle('/home/app/data')).toBeInTheDocument()
    expect(screen.getByTitle('/var/lib/service')).toBeInTheDocument()
    expect(screen.getByText('backup-a@server-a.example')).toBeInTheDocument()
    expect(screen.getByText('backup-b@server-b.example')).toBeInTheDocument()
    expect(screen.getAllByText('1 path')).toHaveLength(3)
  }, 45000)

  it('locks managed-agent sources when the plan cannot use managed agents', async () => {
    const user = userEvent.setup()
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const agentMachines = [
      {
        id: 77,
        name: 'pi',
        agent_id: 'agt_pi',
        hostname: 'pi.local',
        default_path: '/home/pi',
        status: 'online',
        created_at: '2026-05-21T00:00:00.000Z',
        updated_at: '2026-05-21T00:00:00.000Z',
      },
    ]
    render(<StatefulSourceStep agentMachines={agentMachines} canUseManagedAgents={false} />)

    await user.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await user.click(screen.getByRole('combobox', { name: /where are the files/i }))
    const listbox = await screen.findByRole('listbox')
    const agentOption = within(listbox).getByRole('option', { name: /managed agent/i })

    expect(agentOption).toHaveAttribute('aria-disabled', 'true')
    expect(agentOption).toHaveTextContent('Managed-agent sources require Pro.')

    await user.keyboard('{Escape}')
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })
  })

  it('blocks applying mixed source types when the plan cannot use mixed sources', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    const sshConnections = [
      {
        id: 11,
        host: 'server-a.example',
        username: 'backup-a',
        port: 22,
        ssh_key_id: 1,
        default_path: '/home/backup-a',
        status: 'connected',
      },
    ]
    renderSourceStep({
      sshConnections,
      updateState,
      canUseMixedSourceTypes: false,
    })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })
    clickExistingTextButton(/add path/i)

    await selectRemoteMachine(/backup-a@server-a.example/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/home/app/data' },
    })
    clickExistingTextButton(/add path/i)

    expect(screen.getByText(/Mixed source types require Pro/i)).toBeInTheDocument()
    const applyButton = screen.getByRole('button', { name: /use these paths/i })
    expect(applyButton).toBeDisabled()
    fireEvent.click(applyButton)
    expect(updateState).not.toHaveBeenCalled()
  }, 45000)

  it('applies btrfs snapshot metadata for a local source group', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    renderSourceStep({ updateState })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })

    // Snapshot config lives inside the collapsed "Advanced — Capture mode" accordion.
    const advancedCaptureToggle = screen.getByRole('button', {
      name: /advanced.*capture mode/i,
    })
    fireEvent.click(advancedCaptureToggle)
    const advancedCapturePanel = advancedCaptureToggle.closest('.MuiAccordion-root')
    expect(advancedCapturePanel).not.toBeNull()
    expect(window.getComputedStyle(advancedCapturePanel as Element).marginTop).toBe('16px')
    const advancedCaptureDetails = advancedCapturePanel?.querySelector('.MuiAccordionDetails-root')
    expect(advancedCaptureDetails).not.toBeNull()
    expect(window.getComputedStyle(advancedCaptureDetails as Element).paddingTop).toBe('16px')
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /snapshot mode/i }))
    const listbox = await screen.findByRole('listbox')
    fireEvent.click(within(listbox).getByText(/btrfs snapshot/i))
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    expect(screen.getByText(/host requirements/i)).toBeInTheDocument()
    expect(screen.getByText(/btrfs available/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/snapshot staging path/i)).toHaveValue(
      '/var/tmp/borg-ui/snapshots'
    )

    clickExistingTextButton(/add path/i)
    clickExistingTextButton(/use these paths/i)

    await waitFor(() => {
      expect(updateState).toHaveBeenCalledWith(
        expect.objectContaining({
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
        })
      )
    })
  }, 30000)

  it('requires zfs dataset and mountpoint before applying snapshot paths', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    renderSourceStep({ updateState })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app/uploads' },
    })

    fireEvent.click(screen.getByRole('button', { name: /advanced.*capture mode/i }))
    fireEvent.mouseDown(screen.getByRole('combobox', { name: /snapshot mode/i }))
    const listbox = await screen.findByRole('listbox')
    fireEvent.click(within(listbox).getByText(/zfs snapshot/i))
    const datasetInput = await screen.findByLabelText(/zfs dataset/i)
    const mountpointInput = screen.getByLabelText(/zfs mountpoint/i)

    clickExistingTextButton(/add path/i)
    const applyButton = screen.getByRole('button', { name: /use these paths/i })
    expect(applyButton).toBeDisabled()
    expect(screen.getAllByText(/required for zfs snapshots/i)).toHaveLength(2)

    fireEvent.change(datasetInput, {
      target: { value: 'tank/app' },
    })
    expect(applyButton).toBeDisabled()

    fireEvent.change(mountpointInput, {
      target: { value: '/srv/app' },
    })
    expect(applyButton).toBeEnabled()
    fireEvent.click(applyButton)

    await waitFor(() => {
      expect(updateState).toHaveBeenCalledTimes(1)
    })
    expect(updateState.mock.calls[0][0].sourceLocations).toEqual([
      {
        source_type: 'local',
        source_ssh_connection_id: null,
        agent_machine_id: null,
        paths: ['/srv/app/uploads'],
        snapshot: {
          provider: 'zfs',
          dataset: 'tank/app',
          mountpoint: '/srv/app',
          recursive: false,
        },
      },
    ])
  }, 60000)

  it('keeps an existing zfs snapshot from being dropped while switching sources', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    const sshConnections = [
      {
        id: 11,
        host: 'server-a.example',
        username: 'backup-a',
        port: 22,
        ssh_key_id: 1,
        default_path: '/home/backup-a',
        status: 'connected',
      },
    ]
    const initialState = {
      ...createInitialState(),
      sourceDirectories: ['/srv/app/uploads', '/home/app/data'],
      sourceLocations: [
        {
          source_type: 'local' as const,
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/srv/app/uploads'],
          snapshot: {
            provider: 'zfs' as const,
            dataset: 'tank/app',
            mountpoint: '/srv/app',
            recursive: false,
          },
        },
        {
          source_type: 'remote' as const,
          source_ssh_connection_id: 11,
          agent_machine_id: null,
          paths: ['/home/app/data'],
        },
      ],
    }
    renderSourceStep({
      wizardState: initialState,
      sshConnections,
      updateState,
    })

    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    expect(screen.getByLabelText(/zfs dataset/i)).toHaveValue('tank/app')
    fireEvent.change(screen.getByLabelText(/zfs dataset/i), {
      target: { value: '' },
    })

    await selectRemoteMachine(/backup-a@server-a.example/i)
    expect(screen.getByRole('button', { name: /use these paths/i })).toBeDisabled()

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/zfs dataset/i), {
      target: { value: 'tank/app' },
    })
    const applyButton = screen.getByRole('button', { name: /use these paths/i })
    expect(applyButton).toBeEnabled()
    fireEvent.click(applyButton)

    await waitFor(() => {
      expect(updateState).toHaveBeenCalledTimes(1)
    })
    expect(updateState.mock.calls[0][0].sourceLocations).toEqual([
      {
        source_type: 'local',
        source_ssh_connection_id: null,
        agent_machine_id: null,
        paths: ['/srv/app/uploads'],
        snapshot: {
          provider: 'zfs',
          dataset: 'tank/app',
          mountpoint: '/srv/app',
          recursive: false,
        },
      },
      {
        source_type: 'remote',
        source_ssh_connection_id: 11,
        agent_machine_id: null,
        paths: ['/home/app/data'],
      },
    ])
  }, 60000)

  it('browses paths for the selected SSH source without replacing other groups', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const sshConnections = [
      {
        id: 11,
        host: 'server-a.example',
        username: 'backup-a',
        port: 22,
        ssh_key_id: 1,
        default_path: '/home/backup-a',
        status: 'connected',
      },
    ]
    render(<StatefulSourceStep sshConnections={sshConnections} />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await selectSourceKind(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })
    clickExistingTextButton(/add path/i)

    await selectRemoteMachine(/backup-a@server-a.example/i)
    expect(screen.queryByRole('button', { name: /browse current source/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Browse filesystem'))

    const explorer = screen.getByTestId('file-explorer-dialog')
    expect(explorer).toHaveAttribute('data-connection-type', 'ssh')
    expect(explorer).toHaveAttribute('data-initial-path', '/home/backup-a')
    expect(explorer).toHaveAttribute('data-ssh-host', 'server-a.example')

    clickExistingTextButton(/select browsed path/i)
    clickExistingTextButton(/use these paths/i)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    clickExistingSummaryToggle(/borg ui server/i)
    clickExistingSummaryToggle(/backup-a@server-a.example/i)
    expect(screen.getByTitle('/srv/app')).toBeInTheDocument()
    expect(screen.getByTitle('/selected/from-browser')).toBeInTheDocument()
    expect(screen.getByText('backup-a@server-a.example')).toBeInTheDocument()
  }, 60000)

  it('browses paths for the selected managed agent with the shared file explorer', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const agentMachines = [
      {
        id: 77,
        name: 'pi',
        agent_id: 'agt_pi',
        hostname: 'pi.local',
        default_path: '/home/pi',
        status: 'online',
        created_at: '2026-05-21T00:00:00.000Z',
        updated_at: '2026-05-21T00:00:00.000Z',
      },
    ]
    render(<StatefulSourceStep agentMachines={agentMachines} />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('tab', { name: /^database$/i })

    await selectSourceKind(/managed agent/i)
    expect(screen.queryByRole('button', { name: /browse current source/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Browse filesystem'))

    const explorer = screen.getByTestId('file-explorer-dialog')
    expect(explorer).toHaveAttribute('data-connection-type', 'agent')
    expect(explorer).toHaveAttribute('data-agent-id', '77')
    expect(explorer).toHaveAttribute('data-agent-default-path', '/home/pi')

    clickExistingTextButton(/select browsed path/i)
    clickExistingTextButton(/use these paths/i)

    await waitFor(() => {
      expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
    })
    clickExistingSummaryToggle(/pi.local/i)
    expect(screen.getByTitle('/selected/from-browser')).toBeInTheDocument()
  }, 30000)

  it('uses the shared SSH connection picker for database scan targets', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const sshConnections = [
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
    ]
    render(<StatefulSourceStep sshConnections={sshConnections} />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const scanDialogs = screen
      .getAllByRole('dialog')
      .filter((dialog) => within(dialog).queryByRole('heading', { name: /scan for databases/i }))
    expect(scanDialogs.length).toBeGreaterThan(0)
    const scanDialog = scanDialogs[scanDialogs.length - 1]!
    fireEvent.mouseDown(within(scanDialog).getByRole('combobox', { name: /scan where/i }))
    let listbox = await screen.findByRole('listbox')
    fireEvent.click(within(listbox).getByRole('option', { name: /remote machine/i }))
    await waitFor(() => {
      expect(screen.queryByRole('listbox')).not.toBeInTheDocument()
    })

    fireEvent.mouseDown(
      within(scanDialog).getByRole('combobox', { name: /select a remote machine/i })
    )
    listbox = await screen.findByRole('listbox')
    expect(within(listbox).getByText('backup-a@server-a.example')).toBeInTheDocument()
    expect(within(listbox).getByText(/Port 22.*\/mnt\/server-a/i)).toBeInTheDocument()
  }, 30000)

  it('uses the shared path selector for database scan paths', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    render(<StatefulSourceStep />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const sourcePathInput = screen.getByLabelText(/source path/i)
    fireEvent.click(screen.getByTitle('Browse filesystem'))

    const explorer = screen.getByTestId('file-explorer-dialog')
    expect(explorer).toHaveAttribute('data-connection-type', 'local')
    expect(explorer).toHaveAttribute('data-initial-path', '/')

    clickExistingTextButton(/select browsed path/i)

    const selectedPath = screen.getByText('/selected/from-browser')
    const sourcePathControl = sourcePathInput.closest('.MuiFormControl-root') || sourcePathInput
    expect(
      sourcePathControl.compareDocumentPosition(selectedPath) & Node.DOCUMENT_POSITION_FOLLOWING
    ).toBeTruthy()
  })

  it('does not promote broad root database scans by default', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    render(<StatefulSourceStep />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const scanDialogs = screen
      .getAllByRole('dialog')
      .filter((dialog) => within(dialog).queryByRole('heading', { name: /scan for databases/i }))
    expect(scanDialogs.length).toBeGreaterThan(0)
    const scanDialog = scanDialogs[scanDialogs.length - 1]!

    expect(within(scanDialog).getByText('/var/lib/postgresql')).toBeInTheDocument()
    expect(within(scanDialog).getByText('/var/lib/mysql')).toBeInTheDocument()
    expect(within(scanDialog).queryByText('/')).not.toBeInTheDocument()
    expect(
      within(scanDialog).queryByRole('button', { name: /addRootScanPath|add \//i })
    ).not.toBeInTheDocument()
    expect(
      within(scanDialog).queryByText(/rootScanSuggestion|add root|scan broadly/i)
    ).not.toBeInTheDocument()

    await waitFor(() => {
      expect(apiMocks.scanDatabases).toHaveBeenCalled()
    })
    expect(apiMocks.scanDatabases.mock.calls[0]?.[0].paths).toEqual([
      '/var/lib/postgresql',
      '/var/lib/mysql',
      '/var/lib/mongodb',
      '/var/lib/redis',
    ])
    expect(apiMocks.scanDatabases.mock.calls[0]?.[0].ignore_patterns).toEqual(
      expect.arrayContaining(['usr', 'bin', 'sbin', 'tmp'])
    )
    expect(
      await within(scanDialog).findByText(
        'Add another path above, or open templates to set one up manually.'
      )
    ).toBeInTheDocument()
  })

  it('shows every detected database instance from a scan', async () => {
    const user = userEvent.setup()
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        scan_target: {
          source_type: 'local',
          source_ssh_connection_id: null,
          label: 'This Borg UI server',
        },
        scanned_paths: ['/srv'],
        detections: [
          {
            id: 'sqlite',
            engine: 'SQLite',
            display_name: 'SQLite database',
            backup_strategy: 'online_backup',
            source_directories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
            client_commands: ['sqlite3'],
            documentation_url: 'https://www.sqlite.org/backup.html',
            detected: true,
            detection_source: '/srv/app/state.sqlite',
            notes: ['Uses sqlite3 .backup.'],
            script_drafts: {
              pre_backup: {
                name: 'Prepare SQLite backup',
                description: 'Create a SQLite backup.',
                content:
                  '#!/usr/bin/env bash\nset -euo pipefail\nsqlite3 "$SQLITE_DATABASE_PATH"\n',
                timeout: 300,
              },
              post_backup: {
                name: 'Clean SQLite backup',
                description: 'Remove transient SQLite backup files.',
                content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui/sqlite\n',
                timeout: 120,
              },
            },
          },
          {
            id: 'sqlite',
            engine: 'SQLite',
            display_name: 'SQLite database',
            backup_strategy: 'online_backup',
            source_directories: ['/var/tmp/borg-ui/database-dumps/sqlite'],
            client_commands: ['sqlite3'],
            documentation_url: 'https://www.sqlite.org/backup.html',
            detected: true,
            detection_source: '/srv/app/cache.sqlite3',
            notes: ['Uses sqlite3 .backup.'],
            script_drafts: {
              pre_backup: {
                name: 'Prepare SQLite backup',
                description: 'Create a SQLite backup.',
                content:
                  '#!/usr/bin/env bash\nset -euo pipefail\nsqlite3 "$SQLITE_DATABASE_PATH"\n',
                timeout: 300,
              },
              post_backup: {
                name: 'Clean SQLite backup',
                description: 'Remove transient SQLite backup files.',
                content: '#!/usr/bin/env bash\nset -euo pipefail\nrm -rf /var/tmp/borg-ui/sqlite\n',
                timeout: 120,
              },
            },
          },
        ],
        templates: discoveryResponse.templates,
        warnings: [],
      },
    })

    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const stateSqlitePath = await screen.findByText('/srv/app/state.sqlite')
    expect(screen.getByText('/srv/app/cache.sqlite3')).toBeInTheDocument()
    expect(screen.queryByRole('tooltip')).not.toBeInTheDocument()

    await user.hover(stateSqlitePath)

    const tooltip = await screen.findByRole('tooltip')
    expect(within(tooltip).getByText('/srv/app/state.sqlite')).toBeInTheDocument()
  })

  it('keeps a detected SQLite filesystem path visible in the detail view', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        scan_target: {
          source_type: 'local',
          source_ssh_connection_id: null,
          label: 'This Borg UI server',
        },
        scanned_paths: ['/srv'],
        detections: [sqliteScanDetection('/srv/app/state.sqlite', { detected: false })],
        templates: discoveryResponse.templates,
        warnings: [],
      },
    })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 401 })
      .mockResolvedValueOnce({ id: 402 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const stateSqlite = await screen.findByText('/srv/app/state.sqlite')
    fireEvent.click(stateSqlite.closest('button') || stateSqlite)

    expect(await screen.findByRole('heading', { name: /sqlite database/i })).toBeInTheDocument()
    expect(screen.getByText('Live database path')).toBeInTheDocument()
    expect(screen.getByText('/srv/app/state.sqlite')).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('/var/tmp/borg-ui/database-dumps/sqlite/state')
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add database/i }))
    await waitFor(() => {
      expect(
        screen.getByText(/\/var\/tmp\/borg-ui\/database-dumps\/sqlite\/state/)
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /use these paths/i }))

    await waitFor(() => {
      expect(updateState).toHaveBeenCalled()
    })
    const updatePayload = updateState.mock.calls[0][0]
    expect(updatePayload.sourceDirectories).toEqual([
      '/var/tmp/borg-ui/database-dumps/sqlite/state',
    ])
    expect(updatePayload.sourceLocations[0].database.detected_source_path).toBe(
      '/srv/app/state.sqlite'
    )
    expect(
      updatePayload.sourceLocations[0].database.pre_backup_script_parameters.SQLITE_DATABASE_PATH
    ).toBe('/srv/app/state.sqlite')
  })

  it('uses separate staging paths for multiple detected SQLite databases', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        scan_target: {
          source_type: 'local',
          source_ssh_connection_id: null,
          label: 'This Borg UI server',
        },
        scanned_paths: ['/srv'],
        detections: [
          sqliteScanDetection('/srv/app/state.sqlite'),
          sqliteScanDetection('/srv/app/cache.sqlite3'),
        ],
        templates: discoveryResponse.templates,
        warnings: [],
      },
    })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 301 })
      .mockResolvedValueOnce({ id: 302 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const stateSqlite = await screen.findByText('/srv/app/state.sqlite')
    fireEvent.click(stateSqlite.closest('button') || stateSqlite)
    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/\/var\/tmp\/borg-ui\/database-dumps\/sqlite\/state/)
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /scan for databases/i }))
    const cacheSqlite = await screen.findByText('/srv/app/cache.sqlite3')
    fireEvent.click(cacheSqlite.closest('button') || cacheSqlite)
    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/\/var\/tmp\/borg-ui\/database-dumps\/sqlite\/cache/)
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /use these paths/i }))

    await waitFor(() => {
      expect(onCreateScript).toHaveBeenCalledTimes(2)
      expect(updateState).toHaveBeenCalled()
    })
    const updatePayload = updateState.mock.calls[0][0]
    expect(updatePayload.sourceDirectories).toEqual([
      '/var/tmp/borg-ui/database-dumps/sqlite/state',
      '/var/tmp/borg-ui/database-dumps/sqlite/cache',
    ])
    expect(
      updatePayload.sourceLocations.map(
        (location: { database: { dump_path: string } }) => location.database.dump_path
      )
    ).toEqual([
      '/var/tmp/borg-ui/database-dumps/sqlite/state',
      '/var/tmp/borg-ui/database-dumps/sqlite/cache',
    ])
    expect(
      updatePayload.sourceLocations.map(
        (location: { database: { pre_backup_script_parameters: Record<string, string> } }) =>
          location.database.pre_backup_script_parameters.SQLITE_DATABASE_PATH
      )
    ).toEqual(['/srv/app/state.sqlite', '/srv/app/cache.sqlite3'])
  })

  it('does not let existing template hydration overwrite a detected database choice', async () => {
    let resolveDatabases: ((value: { data: typeof discoveryResponse }) => void) | undefined
    apiMocks.databases.mockReturnValue(
      new Promise((resolve) => {
        resolveDatabases = resolve
      })
    )
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        scan_target: {
          source_type: 'local',
          source_ssh_connection_id: null,
          label: 'This Borg UI server',
        },
        scanned_paths: ['/srv'],
        detections: [sqliteScanDetection('/srv/app/index.db')],
        templates: discoveryResponse.templates,
        warnings: [],
      },
    })
    const existingMysqlState = {
      ...createInitialState(),
      sourceType: 'local',
      sourceDirectories: ['/var/tmp/borg-ui/database-dumps/mysql'],
      sourceLocations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
          database: {
            template_id: 'mysql',
            engine: 'MySQL',
            display_name: 'MySQL database',
            backup_strategy: 'logical_dump',
            detected_source_path: '/var/lib/mysql',
            detection_label: 'This Borg UI server',
            capture_mode: 'dump',
            dump_path: '/var/tmp/borg-ui/database-dumps/mysql',
            backup_paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
            script_execution_target: 'source',
          },
        },
      ],
      databaseTemplateId: 'mysql',
    }

    const updateState = vi.fn()
    renderSourceStep({ wizardState: existingMysqlState, updateState })

    fireEvent.click(screen.getByRole('button', { name: /edit/i }))
    fireEvent.click(await screen.findByRole('button', { name: /scan for databases/i }))

    const detectedSqlite = await screen.findByText('/srv/app/index.db')
    fireEvent.click(detectedSqlite.closest('button') || detectedSqlite)

    expect(await screen.findByRole('heading', { name: /^sqlite database$/i })).toBeInTheDocument()
    expect(
      screen.getByDisplayValue('/var/tmp/borg-ui/database-dumps/sqlite/index')
    ).toBeInTheDocument()

    await act(async () => {
      resolveDatabases?.({ data: discoveryResponse })
    })

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /^sqlite database$/i })).toBeInTheDocument()
    })
    expect(
      screen.getByDisplayValue('/var/tmp/borg-ui/database-dumps/sqlite/index')
    ).toBeInTheDocument()

    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(
        screen.getByText(/\/var\/tmp\/borg-ui\/database-dumps\/sqlite\/index/)
      ).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /use these paths/i }))

    await waitFor(() => {
      expect(updateState).toHaveBeenCalled()
    })
    const updatePayload = updateState.mock.calls[0][0]
    expect(
      updatePayload.sourceLocations.map(
        (location: { database: { template_id: string } }) => location.database.template_id
      )
    ).toEqual(['mysql', 'sqlite'])
    expect(
      updatePayload.sourceLocations.map(
        (location: { database: { display_name: string } }) => location.database.display_name
      )
    ).toEqual(['MySQL database', 'SQLite database'])
    expect(updatePayload.sourceDirectories).toEqual([
      '/var/tmp/borg-ui/database-dumps/mysql',
      '/var/tmp/borg-ui/database-dumps/sqlite/index',
    ])
  })

  it('queues database templates in the database tab without closing the modal', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        ...emptyScanResponse,
        templates: discoveryResponse.templates,
      },
    })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 101 })
      .mockResolvedValueOnce({ id: 102 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    const postgresqlTemplate = await screen.findByText(/^postgresql$/i)
    fireEvent.click(postgresqlTemplate.closest('button') || postgresqlTemplate)

    expect(screen.getAllByText(/^PostgreSQL database$/i)).toHaveLength(1)
    expect(screen.queryByRole('button', { name: /^back$/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /cancel/i })).toBeInTheDocument()

    expect(
      (screen.getByLabelText(/pre-backup script draft/i) as HTMLTextAreaElement).value
    ).toContain('pg_dump')
    expect(
      (screen.getByLabelText(/post-backup script draft/i) as HTMLTextAreaElement).value
    ).toContain('rm -rf')

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /^database$/i })).toHaveAttribute(
        'aria-selected',
        'true'
      )
      expect(screen.queryByLabelText(/pre-backup script draft/i)).not.toBeInTheDocument()
      expect(updateState).not.toHaveBeenCalled()
    })

    fireEvent.click(await screen.findByText(/^postgresql$/i))
    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(screen.getByRole('dialog')).toBeInTheDocument()
      expect(screen.getByRole('tab', { name: /database.*1/i })).toHaveAttribute(
        'aria-selected',
        'true'
      )
      expect(screen.getByText(/selected databases/i)).toBeInTheDocument()
      expect(onCreateScript).not.toHaveBeenCalled()
      expect(updateState).not.toHaveBeenCalled()
    })

    fireEvent.click(screen.getByRole('button', { name: /use these paths/i }))

    await waitFor(() => {
      expect(onCreateScript).toHaveBeenCalledTimes(2)
      expect(updateState).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceType: 'local',
          sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
          databaseTemplateId: 'postgresql',
          sourceLocations: [
            expect.objectContaining({
              source_type: 'local',
              paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
              database: expect.objectContaining({
                template_id: 'postgresql',
                capture_mode: 'dump',
                dump_path: '/var/tmp/borg-ui/database-dumps/postgresql',
                backup_paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
                script_execution_target: 'source',
                pre_backup_script_id: 101,
                post_backup_script_id: 102,
                pre_backup_script_parameters: {},
                post_backup_script_parameters: {},
                script_execution_order: 1,
              }),
            }),
          ],
        })
      )
      const updatePayload = updateState.mock.calls[0][0]
      expect(updatePayload.preBackupScriptId).toBeUndefined()
      expect(updatePayload.postBackupScriptId).toBeUndefined()
    })
  }, 45000)

  it('shows a template-specific database title with notes instead of metadata chips', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })

    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)
    const mysqlTemplate = await screen.findByText(/^MySQL$/i)
    fireEvent.click(mysqlTemplate.closest('button') || mysqlTemplate)

    expect(screen.getByRole('heading', { name: /^MySQL database$/i })).toBeInTheDocument()
    expect(screen.getByText('Uses mysqldump.')).toBeInTheDocument()
    expect(screen.queryByText('MySQL')).not.toBeInTheDocument()
    expect(screen.queryByText('logical dump')).not.toBeInTheDocument()
  })

  it('shows the templates grid inline on the Database tab without a Show templates toggle', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })

    render(<StatefulSourceStep />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)

    expect(await screen.findByText(/pick a template to configure manually/i)).toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /show templates/i })).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /hide templates/i })).not.toBeInTheDocument()
    expect(screen.getByRole('button', { name: /scan for databases/i })).toBeInTheDocument()
  })

  it('queues multiple database templates instead of replacing the previous database', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    apiMocks.scanDatabases.mockResolvedValue({
      data: {
        ...emptyScanResponse,
        templates: discoveryResponse.templates,
      },
    })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 201 })
      .mockResolvedValueOnce({ id: 202 })
      .mockResolvedValueOnce({ id: 203 })
      .mockResolvedValueOnce({ id: 204 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    const databaseTab = await screen.findByRole('tab', { name: /^database$/i })
    fireEvent.click(databaseTab)

    const postgresqlTemplate = await screen.findByText(/^postgresql$/i)
    fireEvent.click(postgresqlTemplate.closest('button') || postgresqlTemplate)
    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /database.*1/i })).toHaveAttribute(
        'aria-selected',
        'true'
      )
      expect(screen.getByText('PostgreSQL database')).toBeInTheDocument()
    })

    const mysqlTemplate = await screen.findByText(/^mysql$/i)
    fireEvent.click(mysqlTemplate.closest('button') || mysqlTemplate)
    fireEvent.click(screen.getByRole('button', { name: /add database/i }))

    await waitFor(() => {
      expect(screen.getByRole('tab', { name: /database.*2/i })).toHaveAttribute(
        'aria-selected',
        'true'
      )
      expect(screen.getByText('PostgreSQL database')).toBeInTheDocument()
      expect(screen.getByText('MySQL database')).toBeInTheDocument()
    })

    fireEvent.click(screen.getByRole('button', { name: /use these paths/i }))

    await waitFor(() => {
      expect(onCreateScript).toHaveBeenCalledTimes(4)
      expect(onCreateScript.mock.calls[0][0].content).toContain('pg_dump')
      expect(onCreateScript.mock.calls[2][0].content).toContain('mysqldump')
      expect(onCreateScript.mock.calls[0][0].content).not.toContain('export BORG_UI_DB_DUMP_DIR=')
      expect(updateState).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceDirectories: [
            '/var/tmp/borg-ui/database-dumps/postgresql',
            '/var/tmp/borg-ui/database-dumps/mysql',
          ],
          sourceLocations: [
            expect.objectContaining({
              paths: ['/var/tmp/borg-ui/database-dumps/postgresql'],
              database: expect.objectContaining({
                template_id: 'postgresql',
                pre_backup_script_id: 201,
                post_backup_script_id: 202,
                script_execution_order: 1,
              }),
            }),
            expect.objectContaining({
              paths: ['/var/tmp/borg-ui/database-dumps/mysql'],
              database: expect.objectContaining({
                template_id: 'mysql',
                pre_backup_script_id: 203,
                post_backup_script_id: 204,
                script_execution_order: 2,
              }),
            }),
          ],
        })
      )
      const updatePayload = updateState.mock.calls[0][0]
      expect(updatePayload.preBackupScriptId).toBeUndefined()
      expect(updatePayload.postBackupScriptId).toBeUndefined()
    })
  }, 45000)
})
