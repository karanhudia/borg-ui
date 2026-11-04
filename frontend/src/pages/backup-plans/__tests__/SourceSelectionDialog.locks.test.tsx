import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { ReactNode } from 'react'

import { renderWithProviders, screen, userEvent } from '../../../test/test-utils'
import { createInitialState } from '../state'
import { SourceSelectionDialog } from '../wizard-step/SourceSelectionDialog'
import { closeUpgradeDialog, upgradeDialogStore } from '../../../utils/upgradeDialog'

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

const { trackEventMock } = vi.hoisted(() => ({ trackEventMock: vi.fn() }))

vi.mock('../../../utils/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../../utils/analytics')>()),
  trackEvent: trackEventMock,
}))

describe('SourceSelectionDialog locked source tabs', () => {
  beforeEach(() => {
    trackEventMock.mockClear()
    closeUpgradeDialog()
    apiMocks.appTemplates.mockResolvedValue({ data: { templates: [] } })
    apiMocks.detectApps.mockResolvedValue({ data: { detections: [], warnings: [] } })
    apiMocks.filesystemSnapshots.mockResolvedValue({
      data: { providers: [], supported_source_types: [], unsupported_source_targets: [] },
    })
  })

  it('answers a click on a locked tab with the upgrade card, not a dead end', async () => {
    renderWithProviders(
      <SourceSelectionDialog
        open
        wizardState={createInitialState()}
        sshConnections={[]}
        agentMachines={[]}
        fullRepositories={[]}
        scripts={[]}
        loadingScripts={false}
        onClose={() => {}}
        updateState={vi.fn()}
        onCreateScript={vi.fn()}
        t={((key: string) => key) as never}
        canUseDatabaseDiscovery={false}
        canUseContainerBackups={false}
      />
    )

    await userEvent.click(screen.getByRole('tab', { name: /kindContainer/ }))

    expect(screen.getByRole('tab', { name: /kindContainer/ })).toHaveAttribute(
      'aria-selected',
      'false'
    )
    expect(trackEventMock).toHaveBeenCalledWith(
      'Plan',
      'FeatureBlocked',
      expect.objectContaining({
        feature: 'container_backups',
        surface: 'source_selection_dialog',
        operation: 'locked_click',
        control: 'source_kind_pivot',
      })
    )
    expect(upgradeDialogStore.get()).toMatchObject({ feature: 'container_backups' })
  })
})
