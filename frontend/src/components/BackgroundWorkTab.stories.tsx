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
import type { OperationItem } from '../types/operations'

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

const op = (overrides: Partial<OperationItem>): OperationItem => ({
  activity_key: null,
  id: 1,
  type: 'operation',
  kind: 'stats',
  category: 'index',
  status: 'queued',
  trigger: 'reconcile',
  priority: 20,
  run_id: 'r1',
  depends_on_id: null,
  repository_id: 1,
  repository: 'nas',
  repository_path: '/mnt/nas',
  started_at: null,
  completed_at: null,
  created_at: '2026-09-04T00:00:00Z',
  error_message: null,
  skip_reason: null,
  log_file_path: null,
  triggered_by: 'reconcile',
  schedule_id: null,
  schedule_name: null,
  backup_plan_id: null,
  backup_plan_run_id: null,
  backup_plan_name: null,
  archive_name: null,
  package_name: null,
  has_logs: false,
  progress_percent: null,
  progress_current: null,
  progress_total: null,
  progress_message: null,
  execution_mode: null,
  params: null,
  result: null,
  followups: [],
  ...overrides,
})

const busyQueue = {
  repositories: [
    {
      repository_id: 1,
      repository_name: 'offsite',
      lane_busy: false,
      operations: [
        op({ id: 1, kind: 'import_connect', category: 'import', repository: 'offsite' }),
      ],
    },
    {
      repository_id: 2,
      repository_name: 'nas',
      lane_busy: true,
      operations: [
        op({
          id: 2,
          kind: 'stats',
          status: 'running',
          repository: 'nas',
          repository_id: 2,
          started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
        }),
        op({
          id: 3,
          kind: 'backup',
          category: 'backup',
          status: 'running',
          repository: 'nas',
          repository_id: 2,
          backup_plan_name: 'nightly',
          started_at: new Date(Date.now() - 41 * 60 * 1000).toISOString(),
        }),
      ],
    },
    {
      repository_id: 3,
      repository_name: 'photos',
      lane_busy: false,
      operations: [
        op({
          id: 4,
          kind: 'history_index',
          status: 'running',
          repository: 'photos',
          repository_id: 3,
          progress_percent: 37,
          progress_current: 14,
          progress_total: 38,
          started_at: new Date(Date.now() - 6 * 60 * 1000).toISOString(),
        }),
      ],
    },
    {
      repository_id: 4,
      repository_name: 'laptop',
      lane_busy: false,
      operations: [
        op({ id: 5, status: 'completed', repository: 'laptop', repository_id: 4 }),
        op({
          id: 6,
          kind: 'archive_sync',
          status: 'failed',
          repository: 'docs',
          repository_id: 4,
          error_message: 'borg list timed out',
        }),
      ],
    },
  ],
  limits: { index_workers: 2, index_running: 1 },
  paused: false,
}

const emptyQueue = {
  repositories: [],
  limits: { index_workers: 2, index_running: 0 },
  paused: false,
}

function installApiMocks(queue: unknown): MockAdapter {
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
  mock.onAny().reply(200, {})
  return mock
}

function StoryProviders({ children, queue }: { children: ReactNode; queue: unknown }) {
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

function renderTab(queue: unknown) {
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

export const Default: Story = {
  render: () => renderTab(busyQueue),
}

export const Empty: Story = {
  render: () => renderTab(emptyQueue),
}
