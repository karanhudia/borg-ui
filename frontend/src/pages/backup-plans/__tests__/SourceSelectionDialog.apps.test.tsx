import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { renderWithProviders, screen, userEvent, waitFor } from '../../../test/test-utils'
import {
  immichFound,
  immichStats,
  immichTemplate,
} from '../../../components/app-templates/appTemplates.fixtures'
import { createInitialState } from '../state'
import { SourceSelectionDialog } from '../wizard-step/SourceSelectionDialog'
import type { WizardState } from '../types'

const apiMocks = vi.hoisted(() => ({
  appTemplates: vi.fn(),
  detectApps: vi.fn(),
  inspectApp: vi.fn(),
  filesystemSnapshots: vi.fn(),
}))

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    sourceDiscoveryAPI: {
      ...actual.sourceDiscoveryAPI,
      appTemplates: apiMocks.appTemplates,
      detectApps: apiMocks.detectApps,
      inspectApp: apiMocks.inspectApp,
      filesystemSnapshots: apiMocks.filesystemSnapshots,
    },
  }
})

vi.mock('../../../components/shared/ResponsiveDialog', () => ({
  default: ({
    open,
    children,
    footer,
  }: {
    open: boolean
    children: ReactNode
    footer?: ReactNode
  }) =>
    open ? (
      <div role="dialog">
        {children}
        {footer}
      </div>
    ) : null,
}))

function renderDialog(wizardState: WizardState) {
  const updateState = vi.fn()
  const onCreateScript = vi.fn().mockResolvedValue({ id: 31 })
  renderWithProviders(
    <SourceSelectionDialog
      open
      wizardState={wizardState}
      sshConnections={[]}
      agentMachines={[]}
      fullRepositories={[]}
      scripts={[]}
      loadingScripts={false}
      onClose={() => {}}
      updateState={updateState}
      onCreateScript={onCreateScript}
      t={
        ((key: string, options?: Record<string, unknown>) =>
          options?.app ? `${key}:${options.app}` : key) as never
      }
      initialView={'app' as never}
    />
  )
  return { updateState, onCreateScript }
}

describe('SourceSelectionDialog Apps tab', () => {
  beforeEach(() => {
    apiMocks.appTemplates.mockResolvedValue({ data: { templates: [immichTemplate] } })
    apiMocks.detectApps.mockResolvedValue({
      data: { detections: [immichFound], warnings: [] },
    })
    apiMocks.inspectApp.mockResolvedValue({
      data: { root_status: 'ok', user: 'root', folders: immichStats, warnings: [] },
    })
    apiMocks.filesystemSnapshots.mockResolvedValue({
      data: { providers: [], supported_source_types: [], unsupported_source_targets: [] },
    })
  })

  it('adds Immich as an app source with its excludes and its check', async () => {
    const user = userEvent.setup()
    const { updateState, onCreateScript } = renderDialog({
      ...createInitialState(),
      excludePatterns: ['*.tmp'],
    })

    await user.click(await screen.findByRole('combobox', { name: 'App' }))
    await user.click(screen.getByRole('option', { name: /Immich/ }))
    await user.click(await screen.findByRole('button', { name: 'appTemplates.tab.add:Immich' }))
    await user.click(screen.getByRole('button', { name: 'backupPlans.sourceChooser.applyPaths' }))

    await waitFor(() => expect(updateState).toHaveBeenCalled())
    expect(onCreateScript).toHaveBeenCalledWith(
      expect.objectContaining({ content: "APP_ROOT='/local/srv/immich'\n" })
    )
    const patch = updateState.mock.calls[0][0]
    expect(patch.sourceLocations).toEqual([
      expect.objectContaining({
        source_type: 'local',
        paths: ['/local/srv/immich', '/local/srv/photos'],
        app: expect.objectContaining({
          template_id: 'immich',
          root: '/local/srv/immich',
          exclude_patterns: ['/local/srv/immich/thumbs', '/local/srv/immich/encoded-video'],
          pre_backup_script_id: 31,
          script_execution_target: 'source',
        }),
      }),
    ])
    expect(patch.excludePatterns).toEqual([
      '*.tmp',
      '/local/srv/immich/thumbs',
      '/local/srv/immich/encoded-video',
    ])
  })

  it('takes an app’s excludes away with it when the app is removed', async () => {
    const user = userEvent.setup()
    const { updateState } = renderDialog({
      ...createInitialState(),
      excludePatterns: ['*.tmp', '/srv/immich/thumbs'],
      sourceLocations: [
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/srv/immich'],
          app: {
            template_id: 'immich',
            display_name: 'Immich',
            root: '/srv/immich',
            exclude_patterns: ['/srv/immich/thumbs'],
            script_execution_target: 'source',
          },
        },
        {
          source_type: 'local',
          source_ssh_connection_id: null,
          agent_machine_id: null,
          paths: ['/home'],
        },
      ],
    })

    await user.click(await screen.findByRole('button', { name: 'appTemplates.tab.remove:Immich' }))
    await user.click(screen.getByRole('button', { name: 'backupPlans.sourceChooser.applyPaths' }))

    await waitFor(() => expect(updateState).toHaveBeenCalled())
    const patch = updateState.mock.calls[0][0]
    expect(patch.sourceLocations).toEqual([expect.objectContaining({ paths: ['/home'] })])
    expect(patch.excludePatterns).toEqual(['*.tmp'])
  })
})
