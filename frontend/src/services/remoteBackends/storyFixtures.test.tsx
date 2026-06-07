import { beforeEach, describe, expect, it } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import { RemoteBackendStoryProvider } from './storyFixtures'
import { useRemoteBackends } from './context'
import { resetRemoteBackendStateForTests } from './storage'

function RemoteBackendStoryProbe() {
  const { activeTarget, clients } = useRemoteBackends()

  return (
    <div>
      <div>active:{activeTarget.name}</div>
      <div>clients:{clients.map((client) => client.name).join(',')}</div>
    </div>
  )
}

describe('RemoteBackendStoryProvider', () => {
  beforeEach(() => {
    resetRemoteBackendStateForTests()
  })

  it('hydrates mixed story clients on initial render', async () => {
    renderWithProviders(
      <RemoteBackendStoryProvider state="mixed">
        <RemoteBackendStoryProbe />
      </RemoteBackendStoryProvider>
    )

    expect(await screen.findByText(/clients:.*Studio NAS/)).toBeInTheDocument()
    expect(screen.getByText(/Workshop Mini PC/)).toBeInTheDocument()
    expect(screen.getByText(/Legacy Server/)).toBeInTheDocument()
  })

  it('selects the active remote story client on initial render', async () => {
    renderWithProviders(
      <RemoteBackendStoryProvider state="activeRemote">
        <RemoteBackendStoryProbe />
      </RemoteBackendStoryProvider>
    )

    expect(await screen.findByText('active:Studio NAS')).toBeInTheDocument()
  })
})
