import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import type { TFunction } from 'i18next'

import { SourceStep } from '../wizard-step/SourceStep'
import { createInitialState } from '../state'

const apiMocks = vi.hoisted(() => ({
  scanDatabases: vi.fn(),
  createScript: vi.fn(),
}))

vi.mock('../../../components/SourceDirectoriesInput', () => ({
  default: () => <div data-testid="source-directories-input">Source directories input</div>,
}))

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    sourceDiscoveryAPI: {
      scanDatabases: apiMocks.scanDatabases,
    },
    scriptsAPI: {
      ...actual.scriptsAPI,
      create: apiMocks.createScript,
    },
  }
})

const theme = createTheme()

const t = ((key: string, options?: { defaultValue?: string }) => {
  const translations: Record<string, string> = {
    'backupPlans.wizard.fields.planName': 'Plan name',
    'backupPlans.wizard.fields.description': 'Description',
    'backupPlans.wizard.sourceSelection.summaryTitle': 'Backup source',
    'backupPlans.wizard.sourceSelection.chooseSource': 'Choose source',
    'backupPlans.wizard.sourceSelection.changeSource': 'Change source',
    'backupPlans.wizard.sourceSelection.dialogTitle': 'Choose backup source',
    'backupPlans.wizard.sourceSelection.sourceTypes.paths': 'Files and folders',
    'backupPlans.wizard.sourceSelection.sourceTypes.database': 'Database',
    'backupPlans.wizard.sourceSelection.sourceTypes.container': 'Docker containers',
    'backupPlans.wizard.sourceSelection.apply': 'Apply source',
    'backupPlans.wizard.sourceSelection.scriptModeCreate': 'Create new scripts',
  }
  return translations[key] ?? options?.defaultValue ?? key
}) as TFunction

const discoveryResponse = {
  data: {
    source_types: [
      {
        id: 'paths',
        label: 'Files and folders',
        description: 'Choose files or folders.',
        enabled: true,
      },
      {
        id: 'database',
        label: 'Database',
        description: 'Scan supported databases.',
        enabled: true,
      },
      {
        id: 'container',
        label: 'Docker containers',
        description: 'Coming next.',
        enabled: false,
        unavailable_reason: 'Container scanning is planned.',
      },
    ],
    databases: [
      {
        id: 'postgresql-detected',
        engine: 'postgresql',
        engine_label: 'PostgreSQL',
        display_name: 'PostgreSQL on this server',
        status: 'detected',
        confidence: 'high',
        service_name: 'postgresql',
        source_directories: ['/var/lib/postgresql'],
        warnings: ['Review generated scripts before enabling the plan.'],
        pre_backup_script: '#!/usr/bin/env bash\nsystemctl stop postgresql\n',
        post_backup_script: '#!/usr/bin/env bash\nsystemctl start postgresql\n',
        script_name_base: 'PostgreSQL stop-start backup',
        documentation_url: 'https://www.postgresql.org/docs/17/app-pgdump.html',
      },
    ],
    templates: [],
  },
}

function renderSourceStep(overrides: Partial<React.ComponentProps<typeof SourceStep>> = {}) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const props: React.ComponentProps<typeof SourceStep> = {
    wizardState: createInitialState(),
    sshConnections: [],
    scripts: [{ id: 8, name: 'Existing database stop script' }],
    loadingScripts: false,
    updateState: vi.fn(),
    openSourceExplorer: vi.fn(),
    openExcludeExplorer: vi.fn(),
    t,
    ...overrides,
  }

  render(
    <QueryClientProvider client={queryClient}>
      <ThemeProvider theme={theme}>
        <SourceStep {...props} />
      </ThemeProvider>
    </QueryClientProvider>
  )

  return props
}

describe('SourceStep source selection', () => {
  beforeEach(() => {
    apiMocks.scanDatabases.mockReset()
    apiMocks.createScript.mockReset()
    apiMocks.scanDatabases.mockResolvedValue(discoveryResponse)
    apiMocks.createScript
      .mockResolvedValueOnce({ data: { id: 31, name: 'PostgreSQL stop-start backup pre' } })
      .mockResolvedValueOnce({ data: { id: 32, name: 'PostgreSQL stop-start backup post' } })
  })

  it('starts from a source chooser instead of exposing path controls inline', () => {
    renderSourceStep()

    expect(screen.getByRole('button', { name: /choose source/i })).toBeInTheDocument()
    expect(screen.queryByTestId('source-directories-input')).not.toBeInTheDocument()
  })

  it('creates named scripts and applies a scanned database source', async () => {
    const user = userEvent.setup()
    const updateState = vi.fn()
    renderSourceStep({ updateState })

    await user.click(screen.getByRole('button', { name: /choose source/i }))
    await user.click(await screen.findByRole('button', { name: /database/i }))

    expect(await screen.findByText('PostgreSQL on this server')).toBeInTheDocument()
    expect(screen.getByDisplayValue('PostgreSQL stop-start backup pre')).toBeInTheDocument()
    expect(screen.getByDisplayValue('PostgreSQL stop-start backup post')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /apply source/i }))

    await waitFor(() => {
      expect(apiMocks.createScript).toHaveBeenCalledTimes(2)
    })
    expect(apiMocks.createScript).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        name: 'PostgreSQL stop-start backup pre',
        content: expect.stringContaining('systemctl stop postgresql'),
      })
    )
    expect(apiMocks.createScript).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        name: 'PostgreSQL stop-start backup post',
        content: expect.stringContaining('systemctl start postgresql'),
      })
    )
    await waitFor(() => {
      expect(updateState).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceType: 'local',
          sourceSshConnectionId: '',
          sourceDirectories: ['/var/lib/postgresql'],
          preBackupScriptId: 31,
          postBackupScriptId: 32,
        })
      )
    })
  }, 30000)

  it('keeps the existing file and folder source path flow available', async () => {
    const user = userEvent.setup()
    renderSourceStep()

    await user.click(screen.getByRole('button', { name: /choose source/i }))
    await user.click(await screen.findByRole('button', { name: /files and folders/i }))

    expect(await screen.findByTestId('source-directories-input')).toBeInTheDocument()
  })
})
