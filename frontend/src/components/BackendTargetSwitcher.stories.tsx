import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { Box } from '@mui/material'
import { BrowserRouter } from 'react-router-dom'
import BackendTargetSwitcher from './BackendTargetSwitcher'
import { AuthProvider } from '../hooks/useAuth'
import api from '../services/api'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'
import { communitySystemInfo, proSystemInfo } from '../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/BackendTargetSwitcher',
  component: BackendTargetSwitcher,
  parameters: {
    layout: 'centered',
    systemInfo: proSystemInfo,
  },
} satisfies Meta<typeof BackendTargetSwitcher>

export default meta

type Story = StoryObj<typeof meta>

function installAuthMocks(canManageRemoteClients: boolean): MockAdapter {
  const mock = new MockAdapter(api)
  mock.onGet('/auth/config').reply(200, {
    proxy_auth_enabled: true,
    insecure_no_auth_enabled: false,
    authentication_required: true,
    oidc_enabled: false,
    oidc_provider_name: null,
    oidc_disable_local_auth: false,
    proxy_auth_header: 'x-auth-user',
    proxy_auth_health: { enabled: true, warnings: [] },
  })
  mock.onGet('/auth/me').reply(200, {
    id: canManageRemoteClients ? 1 : 2,
    username: canManageRemoteClients ? 'admin' : 'operator',
    full_name: canManageRemoteClients ? 'Admin User' : 'Operator User',
    email: canManageRemoteClients ? 'admin@example.com' : 'operator@example.com',
    is_active: true,
    role: canManageRemoteClients ? 'admin' : 'operator',
    deployment_type: 'individual',
    created_at: '2026-06-06T00:00:00.000Z',
    global_permissions: canManageRemoteClients ? ['settings.ssh.manage'] : [],
  })
  return mock
}

function SwitcherStoryProviders({
  children,
  state,
  canManageRemoteClients,
}: {
  children: ReactNode
  state: 'mixed' | 'activeRemote'
  canManageRemoteClients: boolean
}) {
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const mock = installAuthMocks(canManageRemoteClients)
    setIsReady(true)
    return () => {
      mock.restore()
    }
  }, [canManageRemoteClients])

  if (!isReady) return null

  return (
    <BrowserRouter>
      <RemoteBackendStoryProvider state={state}>
        <AuthProvider>{children}</AuthProvider>
      </RemoteBackendStoryProvider>
    </BrowserRouter>
  )
}

function renderSwitcher(
  state: 'mixed' | 'activeRemote',
  props = {},
  options: { canManageRemoteClients?: boolean } = {}
) {
  return (
    <SwitcherStoryProviders
      state={state}
      canManageRemoteClients={options.canManageRemoteClients ?? true}
    >
      <Box sx={{ width: 280 }}>
        <BackendTargetSwitcher {...props} />
      </Box>
    </SwitcherStoryProviders>
  )
}

export const LocalSelected: Story = {
  render: () => renderSwitcher('mixed'),
}

export const RemoteSelected: Story = {
  render: () => renderSwitcher('activeRemote'),
}

export const Compact: Story = {
  args: {
    compact: true,
  },
  render: (args) => renderSwitcher('activeRemote', args),
}

export const LockedCommunity: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => renderSwitcher('mixed'),
  play: async ({ canvasElement }) => {
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    canvasElement.querySelector('button')?.click()
  },
}

export const LockedNonAdmin: Story = {
  render: () => renderSwitcher('mixed', {}, { canManageRemoteClients: false }),
  play: async ({ canvasElement }) => {
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    canvasElement.querySelector('button')?.click()
  },
}
