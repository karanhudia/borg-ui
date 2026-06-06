import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { Box } from '@mui/material'
import { BrowserRouter } from 'react-router-dom'
import AppSidebar from './AppSidebar'
import { AppProvider } from '../context/AppContext'
import { AuthProvider } from '../hooks/useAuth'
import api from '../services/api'
import { RemoteBackendProvider } from '../services/remoteBackends/context'
import {
  communitySystemInfo,
  proSystemInfo,
} from '../services/remoteBackends/planStoryFixtures'
import type { SystemInfo } from '../hooks/useSystemInfo'

const adminUser = {
  id: 1,
  username: 'admin',
  full_name: 'Admin User',
  email: 'admin@example.com',
  is_active: true,
  role: 'admin',
  deployment_type: 'individual' as const,
  created_at: '2026-06-06T00:00:00.000Z',
  global_permissions: [
    'settings.users.manage',
    'settings.system.manage',
    'settings.mqtt.manage',
    'settings.packages.manage',
    'settings.scripts.manage',
    'settings.export_import.manage',
    'settings.beta.manage',
    'settings.mounts.manage',
    'settings.ssh.manage',
  ],
}

function installApiMocks(systemInfo: SystemInfo): MockAdapter {
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
  mock.onGet('/auth/me').reply(200, adminUser)
  mock.onGet('/system/info').reply(200, systemInfo)
  mock.onGet('/settings/system').reply(200, { settings: {} })
  mock.onGet('/backup-plans/').reply(200, { backup_plans: [] })
  mock.onGet('/repositories/').reply(200, { repositories: [{ id: 1, name: 'Main repo' }] })
  mock.onGet('/ssh-keys').reply(200, { ssh_keys: [{ id: 1, name: 'System key' }] })
  mock.onAny().reply(200, {})
  return mock
}

function SidebarStoryProviders({
  children,
  systemInfo,
}: {
  children: ReactNode
  systemInfo: SystemInfo
}) {
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const mock = installApiMocks(systemInfo)
    setIsReady(true)

    return () => {
      mock.restore()
    }
  }, [systemInfo])

  if (!isReady) return null

  return (
    <BrowserRouter>
      <RemoteBackendProvider>
        <AuthProvider>
          <AppProvider>{children}</AppProvider>
        </AuthProvider>
      </RemoteBackendProvider>
    </BrowserRouter>
  )
}

function renderSidebar(systemInfo: SystemInfo) {
  return (
    <SidebarStoryProviders systemInfo={systemInfo}>
      <Box sx={{ width: 260, height: 720, bgcolor: 'background.default' }}>
        <AppSidebar mobileOpen={false} onClose={() => {}} />
      </Box>
    </SidebarStoryProviders>
  )
}

const meta = {
  title: 'Components/AppSidebar',
  component: AppSidebar,
  args: {
    mobileOpen: false,
    onClose: () => {},
  },
  parameters: {
    layout: 'fullscreen',
    systemInfo: proSystemInfo,
  },
} satisfies Meta<typeof AppSidebar>

export default meta

type Story = StoryObj<typeof meta>

export const WithRemoteClients: Story = {
  render: () => renderSidebar(proSystemInfo),
}

export const WithoutRemoteClients: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => renderSidebar(communitySystemInfo),
}
