import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { Box } from '@mui/material'
import AppSidebar from './AppSidebar'
import { QuickStartContext } from './quick-start/quickStartContext'
import { AppProvider } from '../context/AppContext'
import { AuthProvider } from '../hooks/useAuth'
import api from '../services/api'
import { RemoteBackendProvider } from '../services/remoteBackends/context'
import { communitySystemInfo, proSystemInfo } from '../services/remoteBackends/planStoryFixtures'
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
    'settings.notifications.manage',
  ],
}

// Viewers have no admin-only settings, so Notifications stays out of the nav.
const viewerUser = {
  ...adminUser,
  id: 2,
  username: 'viewer',
  full_name: 'Viewer User',
  email: 'viewer@example.com',
  role: 'viewer',
  global_permissions: [],
}

type StoryUser = typeof adminUser | typeof viewerUser

function installApiMocks(systemInfo: SystemInfo, user: StoryUser): MockAdapter {
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
  mock.onGet('/auth/me').reply(200, user)
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
  user,
}: {
  children: ReactNode
  systemInfo: SystemInfo
  user: StoryUser
}) {
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const mock = installApiMocks(systemInfo, user)
    setIsReady(true)

    return () => {
      mock.restore()
    }
  }, [systemInfo, user])

  if (!isReady) return null

  return (
    <RemoteBackendProvider>
      <AuthProvider>
        <AppProvider>{children}</AppProvider>
      </AuthProvider>
    </RemoteBackendProvider>
  )
}

function renderSidebar(systemInfo: SystemInfo, user: StoryUser = adminUser) {
  return (
    <SidebarStoryProviders systemInfo={systemInfo} user={user}>
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
    // The sidebar highlights the active nav item from useLocation, so pin the
    // story to a real route instead of the router's default '/'.
    router: { initialEntries: ['/dashboard'] },
  },
} satisfies Meta<typeof AppSidebar>

export default meta

type Story = StoryObj<typeof meta>

export const WithRemoteClients: Story = {
  render: () => renderSidebar(proSystemInfo),
}

export const CommunityPlan: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => renderSidebar(communitySystemInfo),
}

export const ViewerSettings: Story = {
  parameters: {
    router: { initialEntries: ['/settings/account'] },
  },
  render: () => renderSidebar(proSystemInfo, viewerUser),
}

// A user who can create repositories gets the Quick Start "New backup" button.
export const WithQuickStart: Story = {
  render: () => (
    <QuickStartContext.Provider value={{ openQuickStart: () => {} }}>
      {renderSidebar(proSystemInfo)}
    </QuickStartContext.Provider>
  ),
}
