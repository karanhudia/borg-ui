import { useEffect, useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter } from 'react-router-dom'
import { Box } from '@mui/material'
import BackgroundWorkTab from './BackgroundWorkTab'
import { AuthProvider } from '../hooks/useAuth'
import { RemoteBackendProvider } from '../services/remoteBackends/context'
import api from '../services/api'
import { busyQueue, emptyQueue, hubDetail, hubResponse } from './background-work/storyFixtures'
import type { QueueResponse } from '../types/operations'

const adminUser = {
  id: 1,
  username: 'admin',
  full_name: 'Admin User',
  email: 'admin@example.com',
  is_active: true,
  role: 'admin',
  deployment_type: 'individual' as const,
  created_at: '2026-06-06T00:00:00.000Z',
  global_permissions: ['settings.system.manage'],
}

const authorizationModel = {
  global_roles: [
    { id: 'viewer', rank: 10 },
    { id: 'operator', rank: 20 },
    { id: 'admin', rank: 30 },
  ],
  repository_roles: [],
  global_permission_rules: {},
  repository_action_rules: {},
  assignable_repository_roles_by_global_role: {},
}

function installApiMocks(queue: QueueResponse): MockAdapter {
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
  mock.onGet('/auth/authorization-model').reply(200, authorizationModel)
  mock.onGet('/operations/queue').reply(200, queue)
  mock.onGet('/operations/repositories').reply(200, hubResponse)
  mock.onGet(/\/operations\/repositories\/\d+/).reply(200, hubDetail)
  mock.onGet('/system/info').reply(200, {
    app_version: '2.3.0',
    borg_version: '1.4.0',
    borg2_version: null,
    plan: 'pro',
    features: {},
    feature_access: { archive_history: true },
  })
  mock.onGet('/repositories/').reply(200, {
    repositories: hubResponse.repositories.map((r) => ({
      id: r.repository_id,
      name: r.repository_name,
    })),
  })
  mock.onAny().reply(200, {})
  return mock
}

function StoryProviders({ children, queue }: { children: ReactNode; queue: QueueResponse }) {
  const [isReady, setIsReady] = useState(false)

  useEffect(() => {
    const mock = installApiMocks(queue)
    setIsReady(true)
    return () => {
      mock.restore()
    }
  }, [queue])

  if (!isReady) return null

  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <MemoryRouter>
        <RemoteBackendProvider>
          <AuthProvider>{children}</AuthProvider>
        </RemoteBackendProvider>
      </MemoryRouter>
    </QueryClientProvider>
  )
}

function renderTab(queue: QueueResponse) {
  return (
    <StoryProviders queue={queue}>
      <Box sx={{ p: 3 }}>
        <BackgroundWorkTab />
      </Box>
    </StoryProviders>
  )
}

const meta = {
  title: 'Settings/BackgroundWorkTab',
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof BackgroundWorkTab>

export default meta

type Story = StoryObj<typeof meta>

export const Busy: Story = {
  render: () => renderTab(busyQueue),
}

export const Idle: Story = {
  render: () => renderTab(emptyQueue),
}

export const Paused: Story = {
  render: () => renderTab({ ...emptyQueue, paused: true }),
}
