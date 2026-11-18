import { useEffect, useState, type ReactNode } from 'react'
import MockAdapter from 'axios-mock-adapter'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { AuthProvider } from '../../hooks/useAuth'
import { RemoteBackendProvider } from '../../services/remoteBackends/context'
import api, { type McpConfig, type McpConnection } from '../../services/api'
import { activityRows } from './storyFixtures'

/** API mocks for the MCP tab and admin section stories. */
export interface McpStoryState {
  config: McpConfig
  connections: McpConnection[]
  role?: 'admin' | 'viewer'
  plan?: 'pro' | 'community'
  /** The connections request fails, to show the retry state. */
  listFails?: boolean
}

function install({ config, connections, role = 'admin', plan = 'pro', listFails }: McpStoryState) {
  const mock = new MockAdapter(api)
  // Proxy auth resolves the user from /auth/me with no stored token, the
  // way the Background work stories do.
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
  mock.onGet('/auth/authorization-model').reply(200, {
    global_roles: [
      { id: 'viewer', rank: 10 },
      { id: 'operator', rank: 20 },
      { id: 'admin', rank: 30 },
    ],
    repository_roles: [],
    global_permission_rules: {},
    repository_action_rules: {},
    assignable_repository_roles_by_global_role: {},
  })
  mock.onGet('/auth/me').reply(200, {
    id: 1,
    username: 'alex',
    full_name: 'Alex Example',
    email: 'alex@example.com',
    is_active: true,
    role,
    deployment_type: 'individual',
    created_at: '2026-06-06T00:00:00.000Z',
    global_permissions: role === 'admin' ? ['settings.system.manage'] : [],
  })
  mock.onGet('/system/info').reply(200, {
    app_version: '2.5.0',
    borg_version: '1.4.0',
    borg2_version: null,
    plan,
    features: {},
    feature_access: { mcp: plan !== 'community' },
  })
  mock.onGet('/settings/mcp/config').reply(200, config)
  mock.onPut('/settings/mcp/config').reply((req) => [200, { ...config, ...JSON.parse(req.data) }])
  mock.onGet('/settings/mcp/connections').reply(listFails ? 500 : 200, listFails ? {} : connections)
  mock.onGet(/\/settings\/mcp\/connections\/\d+\/activity/).reply(200, activityRows(8))
  mock.onPost('/settings/mcp/connections').reply(201, {
    ...connections[0],
    id: 99,
    token: 'borgui_EXAMPLEtokenEXAMPLEtokenEXAMPLEtoken',
  })
  mock.onAny().reply(200, {})
  return mock
}

export function McpStoryProviders({ children, ...state }: McpStoryState & { children: ReactNode }) {
  const [ready, setReady] = useState(false)
  useEffect(() => {
    const mock = install(state)
    setReady(true)
    return () => mock.restore()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])
  if (!ready) return null
  return (
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <RemoteBackendProvider>
        <AuthProvider>{children}</AuthProvider>
      </RemoteBackendProvider>
    </QueryClientProvider>
  )
}
