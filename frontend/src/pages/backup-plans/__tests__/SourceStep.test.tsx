import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { ThemeProvider, createTheme } from '@mui/material/styles'
import { describe, expect, it, vi } from 'vitest'
import type { TFunction } from 'i18next'

import { sourceDiscoveryAPI } from '../../../services/api'
import { SourceStep } from '../wizard-step/SourceStep'
import type { WizardState } from '../types'

vi.mock('../../../components/SourceDirectoriesInput', () => ({
  default: () => <div data-testid="source-directories-input">Path source input</div>,
}))

vi.mock('../../../components/ExcludePatternInput', () => ({
  default: () => <div data-testid="exclude-pattern-input">Exclude input</div>,
}))

vi.mock('../../../components/ResponsiveDialog', () => ({
  default: ({
    open,
    children,
    footer,
  }: {
    open: boolean
    children: React.ReactNode
    footer?: React.ReactNode
  }) =>
    open ? (
      <div role="dialog">
        {children}
        {footer}
      </div>
    ) : null,
}))

const theme = createTheme()

const t = ((key: string, options?: { defaultValue?: string }) => {
  const translations: Record<string, string> = {
    'backupPlans.wizard.fields.planName': 'Plan name',
    'backupPlans.wizard.fields.description': 'Description',
    'backupPlans.wizard.sourceDiscovery.title': 'Source discovery',
    'backupPlans.wizard.sourceDiscovery.description':
      'Scan supported structured sources and generate plan scripts.',
    'backupPlans.wizard.sourceDiscovery.databases.title': 'Databases',
    'backupPlans.wizard.sourceDiscovery.databases.description':
      'Find database stores on this Borg UI server.',
    'backupPlans.wizard.sourceDiscovery.databases.action': 'Scan databases',
    'backupPlans.wizard.sourceDiscovery.containers.title': 'Containers',
    'backupPlans.wizard.sourceDiscovery.containers.description':
      'Docker container scanning will be available later.',
    'backupPlans.wizard.sourceDiscovery.containers.badge': 'Planned',
    'backupPlans.wizard.sourceDiscovery.applied': 'Database source added',
    'backupPlans.wizard.sourceDiscovery.applyFailed': 'Failed to apply database source',
  }
  return translations[key] ?? options?.defaultValue ?? key
}) as TFunction

const defaultWizardState: WizardState = {
  name: 'Nightly databases',
  description: '',
  enabled: true,
  sourceType: 'local',
  sourceSshConnectionId: '',
  sourceDirectories: [],
  excludePatterns: [],
  repositoryIds: [],
  compression: 'lz4',
  archiveNameTemplate: '{plan_name}-{repo_name}-{now}',
  customFlags: '',
  uploadRatelimitMb: '',
  repositoryRunMode: 'series',
  maxParallelRepositories: 1,
  failureBehavior: 'continue',
  scheduleEnabled: false,
  cronExpression: '0 21 * * *',
  timezone: 'UTC',
  preBackupScriptId: null,
  postBackupScriptId: null,
  preBackupScriptParameters: {},
  postBackupScriptParameters: {},
  runRepositoryScripts: true,
  runPruneAfter: false,
  runCompactAfter: false,
  runCheckAfter: false,
  checkMaxDuration: 3600,
  pruneKeepHourly: 0,
  pruneKeepDaily: 7,
  pruneKeepWeekly: 4,
  pruneKeepMonthly: 6,
  pruneKeepQuarterly: 0,
  pruneKeepYearly: 1,
}

function renderSourceStep(overrides: Partial<React.ComponentProps<typeof SourceStep>> = {}) {
  return render(
    <ThemeProvider theme={theme}>
      <SourceStep
        wizardState={defaultWizardState}
        sshConnections={[]}
        updateState={vi.fn()}
        openSourceExplorer={vi.fn()}
        openExcludeExplorer={vi.fn()}
        onApplyDatabaseDiscovery={vi.fn()}
        t={t}
        {...overrides}
      />
    </ThemeProvider>
  )
}

describe('SourceStep', () => {
  it('keeps path setup available while offering database and planned container discovery', () => {
    renderSourceStep()

    expect(screen.getByTestId('source-directories-input')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /scan databases/i })).toBeInTheDocument()
    expect(screen.getByText('Containers')).toBeInTheDocument()
    expect(screen.getByText('Planned')).toBeInTheDocument()
  })

  it('applies a detected database source with editable generated scripts', async () => {
    const onApplyDatabaseDiscovery = vi.fn().mockResolvedValue(undefined)
    vi.spyOn(sourceDiscoveryAPI, 'scanDatabases').mockResolvedValue({
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
      data: {
        scanned_at: '2026-05-16T11:00:00Z',
        source_types: [],
        templates: [],
        databases: [
          {
            id: 'postgresql-process-var-lib-postgresql-16-main',
            engine: 'postgresql',
            engine_label: 'PostgreSQL',
            name: 'PostgreSQL cluster',
            status: 'running',
            source_directories: ['/var/lib/postgresql/16/main'],
            service_name: 'postgresql',
            discovery_source: 'process',
            confidence: 'high',
            notes: ['Stop PostgreSQL before the Borg snapshot and start it afterwards.'],
            pre_backup_script: {
              name: 'Stop PostgreSQL before backup',
              description: 'Stop PostgreSQL for a filesystem-consistent backup.',
              content: '#!/bin/sh\nsystemctl stop postgresql\n',
              timeout: 120,
              run_on: 'always',
            },
            post_backup_script: {
              name: 'Start PostgreSQL after backup',
              description: 'Start PostgreSQL after the Borg snapshot.',
              content: '#!/bin/sh\nsystemctl start postgresql\n',
              timeout: 120,
              run_on: 'always',
            },
          },
        ],
      },
    } as unknown as Awaited<ReturnType<typeof sourceDiscoveryAPI.scanDatabases>>)

    renderSourceStep({ onApplyDatabaseDiscovery })

    fireEvent.click(screen.getByRole('button', { name: /scan databases/i }))
    fireEvent.click(await screen.findByText('PostgreSQL cluster'))
    fireEvent.change(screen.getByLabelText(/pre-backup script/i), {
      target: { value: '#!/bin/sh\nservice postgresql stop' },
    })
    fireEvent.click(screen.getByRole('button', { name: /use database source/i }))

    await waitFor(() => {
      expect(onApplyDatabaseDiscovery).toHaveBeenCalledWith(
        expect.objectContaining({
          sourceDirectories: ['/var/lib/postgresql/16/main'],
          preBackupScript: expect.objectContaining({
            content: expect.stringContaining('service postgresql stop'),
          }),
          postBackupScript: expect.objectContaining({
            content: expect.stringContaining('systemctl start postgresql'),
          }),
        })
      )
    })
  })
})
