import { useState } from 'react'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { createInitialState } from '../state'
import { SourceStep } from '../wizard-step/SourceStep'

const apiMocks = vi.hoisted(() => ({
  databases: vi.fn(),
}))

vi.mock('../../../services/api', () => ({
  sourceDiscoveryAPI: {
    databases: apiMocks.databases,
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
  }: {
    open: boolean
    onSelect: (paths: string[]) => void
    title?: string
    connectionType?: 'local' | 'ssh'
    initialPath?: string
    sshConfig?: { host: string }
  }) =>
    open ? (
      <div
        role="dialog"
        aria-label={title || 'File explorer'}
        data-testid="file-explorer-dialog"
        data-connection-type={connectionType}
        data-initial-path={initialPath}
        data-ssh-host={sshConfig?.host || ''}
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
  'backupPlans.sourceChooser.localSource': 'Local source',
  'backupPlans.sourceChooser.sshSource': 'SSH source',
  'backupPlans.sourceChooser.sourcePath': 'Source path',
  'backupPlans.sourceChooser.addPath': 'Add path',
  'backupPlans.sourceChooser.browseCurrentSource': 'Browse current source',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
  'backupPlans.sourceChooser.removePath': 'Remove path',
  'backupPlans.sourceChooser.removeSourceGroup': 'Remove source group',
  'backupPlans.wizard.fileExplorer.sourceTitle': 'Select source paths',
}

const t = (key: string) => translations[key] || key

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

function renderSourceStep(overrides = {}) {
  return render(
    <SourceStep
      wizardState={createInitialState()}
      sshConnections={[]}
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
}) {
  const [wizardState, setWizardState] = useState(initialState)

  return (
    <SourceStep
      wizardState={wizardState}
      sshConnections={sshConnections}
      scripts={[]}
      loadingScripts={false}
      updateState={(updates) => setWizardState((current) => ({ ...current, ...updates }))}
      openExcludeExplorer={vi.fn()}
      onCreateScript={vi.fn(async () => ({ id: 101 }))}
      t={t as never}
    />
  )
}

describe('SourceStep', () => {
  afterEach(() => {
    vi.clearAllMocks()
  })

  it('shows a compact source chooser before rendering path controls inline', () => {
    renderSourceStep()

    expect(screen.getByRole('button', { name: /choose source/i })).toBeInTheDocument()
    expect(screen.queryByTestId('wizard-data-source')).not.toBeInTheDocument()
  })

  it('offers one files route and database scanning without showing planned containers', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    expect(screen.getByRole('dialog')).toHaveAttribute('data-max-width', 'sm')
    expect(await screen.findByText('Files and folders')).toBeInTheDocument()
    expect(screen.getByText('Database')).toBeInTheDocument()
    expect(screen.queryByText(/docker containers/i)).not.toBeInTheDocument()
    expect(screen.queryByText(/planned/i)).not.toBeInTheDocument()
    expect(screen.queryByRole('button', { name: /manual path/i })).not.toBeInTheDocument()
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

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await clickTextButton(/files and folders/i)
    clickExistingTextButton(/local source/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app-data' },
    })
    clickExistingTextButton(/add path/i)
    clickExistingTextButton(/use these paths/i)

    expect(screen.getByText('/srv/app-data')).toBeInTheDocument()
    expect(screen.getByText('Files and folders')).toBeInTheDocument()
    expect(screen.queryByText('Database scan')).not.toBeInTheDocument()
  })

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
    await clickTextButton(/files and folders/i)

    clickExistingTextButton(/local source/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })
    clickExistingTextButton(/add path/i)

    clickExistingTextButton(/backup-a@server-a.example/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/home/app/data' },
    })
    clickExistingTextButton(/add path/i)

    clickExistingTextButton(/backup-b@server-b.example/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/var/lib/service' },
    })
    clickExistingTextButton(/add path/i)

    clickExistingTextButton(/use these paths/i)

    expect(screen.getByText('/srv/app')).toBeInTheDocument()
    expect(screen.getByText('/home/app/data')).toBeInTheDocument()
    expect(screen.getByText('/var/lib/service')).toBeInTheDocument()
    expect(screen.getByText('backup-a@server-a.example')).toBeInTheDocument()
    expect(screen.getByText('backup-b@server-b.example')).toBeInTheDocument()
  })

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
    await clickTextButton(/files and folders/i)

    clickExistingTextButton(/local source/i)
    fireEvent.change(screen.getByLabelText(/source path/i), {
      target: { value: '/srv/app' },
    })
    clickExistingTextButton(/add path/i)

    clickExistingTextButton(/backup-a@server-a.example/i)
    clickExistingTextButton(/browse current source/i)

    const explorer = screen.getByTestId('file-explorer-dialog')
    expect(explorer).toHaveAttribute('data-connection-type', 'ssh')
    expect(explorer).toHaveAttribute('data-initial-path', '/home/backup-a')
    expect(explorer).toHaveAttribute('data-ssh-host', 'server-a.example')

    clickExistingTextButton(/select browsed path/i)
    clickExistingTextButton(/use these paths/i)

    expect(screen.getByText('/srv/app')).toBeInTheDocument()
    expect(screen.getByText('/selected/from-browser')).toBeInTheDocument()
    expect(screen.getByText('backup-a@server-a.example')).toBeInTheDocument()
  }, 30000)

  it('applies database templates with code-editor script drafts', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 101 })
      .mockResolvedValueOnce({ id: 102 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    await clickTextButton(/database/i)
    const postgresqlTemplate = await screen.findByText(/postgresql database/i)
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
