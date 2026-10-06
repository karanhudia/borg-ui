import { beforeEach, describe, expect, it, vi } from 'vitest'

import { renderWithProviders, screen, waitFor } from '../../../test/test-utils'
import AppTemplateFolderPanel from '../AppTemplateFolderPanel'
import { immichFound, immichStats, immichTemplate } from '../appTemplates.fixtures'

const apiMocks = vi.hoisted(() => ({ detectApps: vi.fn(), inspectApp: vi.fn() }))

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    sourceDiscoveryAPI: {
      ...actual.sourceDiscoveryAPI,
      detectApps: apiMocks.detectApps,
      inspectApp: apiMocks.inspectApp,
    },
  }
})

function renderPanel(root: string) {
  const onContainerChange = vi.fn()
  renderWithProviders(
    <AppTemplateFolderPanel
      template={immichTemplate}
      target={{ source_type: 'local', source_ssh_connection_id: null }}
      root={root}
      rootIncluded
      onRootIncludedChange={() => {}}
      extraPaths={[]}
      onPathsChange={() => {}}
      onContainerChange={onContainerChange}
      excludes={[]}
      onExcludesChange={() => {}}
    />
  )
  return onContainerChange
}

describe('AppTemplateFolderPanel container', () => {
  beforeEach(() => {
    apiMocks.detectApps.mockResolvedValue({
      data: { scan_target: {}, detections: [immichFound], warnings: [] },
    })
    apiMocks.inspectApp.mockResolvedValue({
      data: { root_status: 'ok', user: 'backup', folders: immichStats, warnings: [] },
    })
  })

  it('reports the detected container for the folder it was found at', async () => {
    const onContainerChange = renderPanel(`${immichFound.path}/`)
    await waitFor(() => expect(onContainerChange).toHaveBeenLastCalledWith('immich_server'))
  })

  it('reports no container for a folder the user picked elsewhere', async () => {
    const onContainerChange = renderPanel('/srv/somewhere-else')
    // Detection has landed once its "Found Immich (container …)" card shows.
    expect(await screen.findByText(/immich_server/)).toBeInTheDocument()
    expect(onContainerChange).not.toHaveBeenCalledWith('immich_server')
  })
})
