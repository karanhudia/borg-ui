import { fireEvent, render, screen } from '@testing-library/react'
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
  WizardStepDataSource: () => <div data-testid="wizard-data-source">Path controls</div>,
}))

vi.mock('../../../components/ExcludePatternInput', () => ({
  default: () => <div data-testid="exclude-patterns">Exclude patterns</div>,
}))

vi.mock('../../../components/shared/CodeEditor', () => ({
  default: () => <textarea aria-label="code editor" readOnly />,
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

const filesystemSnapshotCapabilities = {
  providers: [],
  supported_source_types: ['local'],
  unsupported_source_targets: [],
  default_staging_path: '/var/tmp/borg-ui/snapshots',
}

const translations: Record<string, string> = {
  'backupPlans.wizard.fields.planName': 'Plan name',
  'backupPlans.wizard.fields.description': 'Description',
  'backupPlans.sourceChooser.summaryTitle': 'Backup source',
  'backupPlans.sourceChooser.summaryEmpty': 'No source selected yet',
  'backupPlans.sourceChooser.chooseSource': 'Choose source',
  'backupPlans.sourceChooser.title': 'Choose backup source',
  'backupPlans.sourceChooser.databaseBackupTitle': 'Add database backup',
  'backupPlans.sourceChooser.containerBackupTitle': 'Add Docker container backup',
  'backupPlans.sourceChooser.kindFiles': 'Files',
  'backupPlans.sourceChooser.kindDatabase': 'Database',
  'backupPlans.sourceChooser.kindContainer': 'Container',
  'backupPlans.sourceChooser.where': 'Where are the files?',
  'backupPlans.sourceChooser.borgUiServer': 'Borg UI server',
  'backupPlans.sourceChooser.localSourceDescription': 'This Borg UI server',
  'backupPlans.sourceChooser.remoteMachine': 'Remote machine',
  'backupPlans.sourceChooser.remoteMachineDescription': 'Pull from an SSH connection',
  'backupPlans.sourceChooser.managedAgent': 'Managed agent',
  'backupPlans.sourceChooser.managedAgentDescription': 'Read paths from an enrolled managed agent',
  'backupPlans.sourceChooser.selectManagedAgent': 'Select a managed agent',
  'backupPlans.sourceChooser.noManagedAgents': 'No managed agents available',
  'backupPlans.sourceChooser.selectRemoteMachine': 'Select a remote machine',
  'backupPlans.sourceChooser.noRemoteMachines': 'No SSH connections available',
  'backupPlans.sourceChooser.sourcePath': 'Source path',
  'backupPlans.sourceChooser.addPath': 'Add path',
  'backupPlans.sourceChooser.applyPaths': 'Use these paths',
  'backupPlans.sourceChooser.selectedSourceGroups': 'Selected source groups',
}

const t = (key: string) => translations[key] || key

describe('SourceStep plan gates', () => {
  beforeEach(() => {
    apiMocks.databases.mockResolvedValue({ data: { templates: [] } })
    apiMocks.filesystemSnapshots.mockResolvedValue({ data: filesystemSnapshotCapabilities })
  })

  afterEach(() => {
    vi.clearAllMocks()
  })

  it('locks database and container source kinds when the plan cannot use them', async () => {
    render(
      <SourceStep
        wizardState={createInitialState()}
        sshConnections={[]}
        agentMachines={[]}
        fullRepositories={[]}
        scripts={[]}
        loadingScripts={false}
        canUseDatabaseDiscovery={false}
        canUseContainerBackups={false}
        updateState={vi.fn()}
        openExcludeExplorer={vi.fn()}
        onCreateScript={vi.fn(async () => ({ id: 101 }))}
        t={t as never}
      />
    )

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    const filesTab = await screen.findByRole('tab', { name: /^files$/i })
    const databaseTab = screen.getByRole('tab', { name: /^database$/i })
    const containerTab = screen.getByRole('tab', { name: /^container$/i })

    expect(filesTab).toHaveAttribute('aria-selected', 'true')
    expect(databaseTab).toHaveAttribute('aria-disabled', 'true')
    expect(containerTab).toHaveAttribute('aria-disabled', 'true')
    expect(apiMocks.databases).not.toHaveBeenCalled()

    fireEvent.click(databaseTab)
    expect(filesTab).toHaveAttribute('aria-selected', 'true')
    expect(screen.queryByRole('heading', { name: /add database backup/i })).not.toBeInTheDocument()

    fireEvent.click(containerTab)
    expect(filesTab).toHaveAttribute('aria-selected', 'true')
    expect(
      screen.queryByRole('heading', { name: /add docker container backup/i })
    ).not.toBeInTheDocument()
  })
})
