import type { McpActivityRow, McpConfig, McpConnection } from '../../services/api'

/** Made-up data for stories and tests. No real hosts, paths or tokens. */

const minutesAgo = (m: number) => new Date(Date.now() - m * 60_000).toISOString()

export const mcpConfig: McpConfig = {
  enabled: true,
  max_access_level: 'full',
  endpoint_path: '/mcp',
  available_levels: ['read'],
}

export const connection = (overrides: Partial<McpConnection> = {}): McpConnection => ({
  id: 1,
  name: 'Claude on my laptop',
  prefix: 'borgui_Ab3dE',
  access_level: 'read',
  effective_level: 'read',
  skip_routine_confirmations: false,
  last_client_name: 'claude-code',
  last_client_version: '2.1.0',
  last_used_at: minutesAgo(3),
  created_at: minutesAgo(60 * 24 * 3),
  username: 'alex',
  calls_today: 14,
  ...overrides,
})

export const connections: McpConnection[] = [
  connection(),
  connection({
    id: 2,
    name: 'Cursor at work',
    prefix: 'borgui_Zz9yX',
    access_level: 'full',
    effective_level: 'read',
    last_client_name: 'cursor',
    last_client_version: '1.7.2',
    last_used_at: minutesAgo(60 * 26),
    calls_today: 0,
  }),
  connection({
    id: 3,
    name: 'Desktop',
    prefix: 'borgui_Qq1wE',
    last_client_name: null,
    last_client_version: null,
    last_used_at: null,
    calls_today: 0,
    username: 'sam',
  }),
]

const outcomes: McpActivityRow['outcome'][] = [
  'ok',
  'error',
  'denied_level',
  'denied_rbac',
  'needs_confirmation',
  'confirmed',
]

export const activityRows = (count: number, startId = 500): McpActivityRow[] =>
  Array.from({ length: count }, (_, i) => ({
    id: startId - i,
    tool: ['get_overview', 'list_repositories', 'get_job_log', 'browse_archive'][i % 4],
    effective_level: 'read',
    outcome: outcomes[i % outcomes.length],
    error_key: i % outcomes.length === 1 ? 'backend.errors.repo.notFound' : null,
    target: i % 2 ? 'repository Photos' : null,
    duration_ms: 40 + i * 7,
    created_at: minutesAgo(i * 5),
  }))
