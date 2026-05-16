import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

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
  WizardStepDataSource: () => <div data-testid="wizard-data-source">Path controls</div>,
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
}

const t = (key: string) => translations[key] || key

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
      openSourceExplorer={vi.fn()}
      openExcludeExplorer={vi.fn()}
      onCreateScript={vi.fn(async () => ({ id: 101 }))}
      t={t as never}
      {...overrides}
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

  it('offers one files route plus database and planned container source types', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    renderSourceStep()

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))

    expect(await screen.findByRole('button', { name: /files and folders/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /database/i })).toBeInTheDocument()
    expect(screen.getByText(/docker containers/i)).toBeInTheDocument()
    expect(screen.getAllByText(/planned/i).length).toBeGreaterThan(0)
    expect(screen.queryByRole('button', { name: /manual path/i })).not.toBeInTheDocument()
  })

  it('applies database templates with code-editor script drafts', async () => {
    apiMocks.databases.mockResolvedValue({ data: discoveryResponse })
    const updateState = vi.fn()
    const onCreateScript = vi
      .fn()
      .mockResolvedValueOnce({ id: 101 })
      .mockResolvedValueOnce({ id: 102 })

    renderSourceStep({ updateState, onCreateScript })

    fireEvent.click(screen.getByRole('button', { name: /choose source/i }))
    fireEvent.click(await screen.findByRole('button', { name: /database/i }))
    const postgresqlTemplate = await screen.findByText(/postgresql database/i)
    fireEvent.click(postgresqlTemplate.closest('button') || postgresqlTemplate)

    expect((screen.getByLabelText(/pre-backup script draft/i) as HTMLTextAreaElement).value)
      .toContain('pg_dump')
    expect((screen.getByLabelText(/post-backup script draft/i) as HTMLTextAreaElement).value)
      .toContain('rm -rf')

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
