import { useState } from 'react'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { createInitialState } from '../state'
import { SourceStep } from '../wizard-step/SourceStep'

const apiMocks = vi.hoisted(() => ({
  databases: vi.fn(),
  scanDatabases: vi.fn(),
  filesystemSnapshots: vi.fn(),
}))

vi.mock('../../../services/api', () => ({
  managedAgentsAPI: {
    browseFilesystem: vi.fn(),
  },
  sourceDiscoveryAPI: {
    databases: apiMocks.databases,
    scanDatabases: apiMocks.scanDatabases,
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

vi.mock('../../../components/CodeEditor', () => ({
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

vi.mock('../../../components/ResponsiveDialog', () => ({
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
  }: {
    open: boolean
    onSelect: (paths: string[]) => void
    title?: string
    connectionType?: 'local' | 'ssh' | 'agent'
    initialPath?: string
    sshConfig?: { host: string }
    agentId?: number
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
  'backupPlans.sourceChooser.containerPlanned': 'Planned',
  'backupPlans.sourceChooser.backToTypes': 'Back to source types',
  'backupPlans.sourceChooser.applyPaths': 'Use these paths',
  'backupPlans.sourceChooser.loading': 'Scanning sources...',
  'backupPlans.sourceChooser.noDatabaseTemplates': 'No database templates available',
  'backupPlans.sourceChooser.databaseTemplates': 'Templates',
  'backupPlans.sourceChooser.detectedDatabases': 'Detected databases',
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
  'backupPlans.sourceChooser.applyDatabase': 'Use database source',
  'backupPlans.sourceChooser.addSourceGroup': 'Add source group',
  'backupPlans.sourceChooser.localSource': 'Borg UI server',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.managedAgent': 'Managed agent',
  'backupPlans.sourceChooser.managedAgentDescription': 'Read paths from an enrolled managed agent',
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
  'backupPlans.sourceChooser.showLessPaths': 'Show less',
  'backupPlans.sourceChooser.scanDatabaseInstead': 'Scan a database instead',
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
  'backupPlans.sourceChooser.snapshotRecursive': 'Recursive snapshot',
  'backupPlans.sourceChooser.snapshotToolAvailable': '{{command}} available',
  'backupPlans.sourceChooser.snapshotToolMissing': '{{command}} not found',
  'backupPlans.sourceChooser.snapshotChip': '{{provider}} snapshot',
  'backupPlans.sourceChooser.backToFiles': 'Back to files and folders',
  'backupPlans.sourceChooser.change': 'Change',
  'backupPlans.sourceChooser.edit': 'Edit',
  'backupPlans.wizard.fileExplorer.sourceTitle': 'Select source paths',
}

const t = (key: string, options?: { count?: number }) => {
  if (key === 'backupPlans.sourceChooser.pathCount' && typeof options?.count === 'number') {
    return `${options.count} ${options.count === 1 ? 'path' : 'paths'}`
  }
  if (key === 'backupPlans.sourceChooser.showMorePaths' && typeof options?.count === 'number') {
    return `Show ${options.count} more ${options.count === 1 ? 'path' : 'paths'}`
  }
  return (translations[key] || key)
    .replace('{{command}}', String((options as { command?: string } | undefined)?.command ?? ''))
    .replace('{{provider}}', String((options as { provider?: string } | undefined)?.provider ?? ''))
}

async function clickTextButton(name: string | RegExp) {
  const labels = await screen.findAllByText(name)
  const button = labels.map((label) => label.closest('button')).find(Boolean)
  expect(button).not.toBeNull()
  fireEvent.click(button as HTMLButtonElement)
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

async function selectRemoteMachine(optionName: RegExp) {
  const labels = screen.getAllByText(/^remote machine$/i)
  const card = labels.map((label) => label.closest('button')).find(Boolean)
  expect(card).not.toBeNull()
  fireEvent.click(card as HTMLButtonElement)

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
    status: string
    created_at: string
    updated_at: string
  }>
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
      updateState={(updates) => setWizardState((current) => ({ ...current, ...updates }))}
      openExcludeExplorer={vi.fn()}
      onCreateScript={vi.fn(async () => ({ id: 101 }))}
      t={t as never}
    />
  )
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

  it('opens straight into the path picker with an inline database link', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    expect(screen.getByRole('dialog')).toHaveAttribute('data-max-width', 'md')
    expect(await screen.findByText('Borg UI server')).toBeInTheDocument()
    expect(screen.getByText('Remote machine')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /scan a database instead/i })).toBeInTheDocument()
    expect(screen.queryByText(/docker containers/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/planned/i)).not.toBeInTheDocument()
  })

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
    await screen.findByRole('button', { name: /scan a database instead/i })
    clickExistingTextButton(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app-data' },
    })
    clickExistingTextButton(/add path/i)
    clickExistingTextButton(/use these paths/i)

    fireEvent.click(screen.getByRole('button', { name: /borg ui server/i }))
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

    expect(await screen.findByText('This Borg UI server')).toBeInTheDocument()
    expect(screen.getByText('Remote machine')).toBeInTheDocument()

    clickExistingTextButton(/borg ui server/i)
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

  it('applies btrfs snapshot metadata for a local source group', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    renderSourceStep({ updateState })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('button', { name: /scan a database instead/i })

    clickExistingTextButton(/borg ui server/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })

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
    await screen.findByRole('button', { name: /scan a database instead/i })

    clickExistingTextButton(/borg ui server/i)
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

    fireEvent.click(screen.getByRole('button', { name: /borg ui server/i }))
    fireEvent.click(screen.getByRole('button', { name: /backup-a@server-a.example/i }))
    expect(screen.getByTitle('/srv/app')).toBeInTheDocument()
    expect(screen.getByTitle('/selected/from-browser')).toBeInTheDocument()
    expect(screen.getByText('backup-a@server-a.example')).toBeInTheDocument()
  }, 30000)

  it('browses paths for the selected managed agent with the shared file explorer', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const agentMachines = [
      {
        id: 77,
        name: 'pi',
        agent_id: 'agt_pi',
        hostname: 'pi.local',
        status: 'online',
        created_at: '2026-05-21T00:00:00.000Z',
        updated_at: '2026-05-21T00:00:00.000Z',
      },
    ]
    render(<StatefulSourceStep agentMachines={agentMachines} />)

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await screen.findByRole('button', { name: /scan a database instead/i })

    clickExistingTextButton(/managed agent/i)
    expect(screen.queryByRole('button', { name: /browse current source/i })).not.toBeInTheDocument()
    fireEvent.click(screen.getByTitle('Browse filesystem'))

    const explorer = screen.getByTestId('file-explorer-dialog')
    expect(explorer).toHaveAttribute('data-connection-type', 'agent')
    expect(explorer).toHaveAttribute('data-agent-id', '77')

    clickExistingTextButton(/select browsed path/i)
    clickExistingTextButton(/use these paths/i)

    fireEvent.click(screen.getByRole('button', { name: /pi.local/i }))
    expect(screen.getByTitle('/selected/from-browser')).toBeInTheDocument()
  }, 30000)

  it('applies database templates with code-editor script drafts', async () => {
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
    await clickTextButton(/scan a database instead/i)
    const postgresqlTemplate = await screen.findByText(/^postgresql$/i)
    fireEvent.click(postgresqlTemplate.closest('button') || postgresqlTemplate)

    expect(
      (screen.getByLabelText(/pre-backup script draft/i) as HTMLTextAreaElement).value
    ).toContain('pg_dump')
    expect(
      (screen.getByLabelText(/post-backup script draft/i) as HTMLTextAreaElement).value
    ).toContain('rm -rf')

    fireEvent.click(screen.getByRole('button', { name: /use database source/i }))

    await waitFor(() => {
      expect(onCreateScript).toHaveBeenCalledTimes(2)
      expect(updateState).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceType: 'local',
          sourceDirectories: ['/var/tmp/borg-ui/database-dumps/postgresql'],
          preBackupScriptId: 101,
          postBackupScriptId: 102,
        })
      )
    })
  })
})
