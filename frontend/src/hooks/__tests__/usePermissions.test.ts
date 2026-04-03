import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import React from 'react'
import { usePermissions } from '../usePermissions'

vi.mock('../../services/api', () => ({
  authAPI: {
    getAuthorizationModel: vi.fn().mockResolvedValue({
      data: {
        global_roles: [
          { id: 'viewer', rank: 1, scope: 'global' },
          { id: 'operator', rank: 2, scope: 'global' },
          { id: 'admin', rank: 3, scope: 'global' },
        ],
        repository_roles: [
          { id: 'viewer', rank: 1, scope: 'repository' },
          { id: 'operator', rank: 2, scope: 'repository' },
        ],
        global_permission_rules: {
          'repositories.manage_all': 'admin',
        },
        repository_action_rules: {
          view: 'viewer',
          restore: 'viewer',
          backup: 'operator',
          maintenance: 'operator',
          delete_archive: 'operator',
        },
        assignable_repository_roles_by_global_role: {
          viewer: ['viewer'],
          operator: ['viewer', 'operator'],
          admin: ['viewer', 'operator'],
        },
      },
    }),
  },
  permissionsAPI: {
    getMyPermissions: vi.fn(),
    getMyPermissionScope: vi.fn(),
  },
}))

vi.mock('../useAuth', () => ({
  useAuth: vi.fn(),
}))

function makeWrapper() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return ({ children }: { children: React.ReactNode }) =>
    React.createElement(QueryClientProvider, { client }, children)
}

describe('usePermissions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('returns canDo=true for everything when user is admin', async () => {
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'admin', global_permissions: ['repositories.manage_all'] },
      hasGlobalPermission: (permission: string) => permission === 'repositories.manage_all',
    } as never)

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() })
    expect(result.current.canDo(1, 'backup')).toBe(true)
    expect(result.current.canDo(99, 'maintenance')).toBe(true)
    expect(result.current.isLoading).toBe(false)
  })

  it('fetches permissions for non-admin and populates canDo', async () => {
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'operator', global_permissions: [] },
      hasGlobalPermission: () => false,
    } as never)
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissions).mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 2,
          repository_id: 10,
          repository_name: 'prod',
          role: 'operator',
          created_at: '',
        },
      ],
    } as never)

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.canDo(10, 'backup')).toBe(true)
    expect(result.current.canDo(10, 'view')).toBe(true)
    expect(result.current.canDo(99, 'view')).toBe(false) // repo 99 has no permission
  })

  it('viewer cannot do operator-level actions', async () => {
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'viewer', global_permissions: [] },
      hasGlobalPermission: () => false,
    } as never)
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissions).mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 3,
          repository_id: 5,
          repository_name: 'docs',
          role: 'viewer',
          created_at: '',
        },
      ],
    } as never)

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.canDo(5, 'view')).toBe(true)
    expect(result.current.canDo(5, 'restore')).toBe(true)
    expect(result.current.canDo(5, 'backup')).toBe(false)
    expect(result.current.canDo(5, 'maintenance')).toBe(false)
    expect(result.current.canDo(5, 'delete_archive')).toBe(false)
  })

  it('wildcard repository role grants access to future repositories', async () => {
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'viewer', global_permissions: [], all_repositories_role: 'viewer' },
      hasGlobalPermission: () => false,
    } as never)
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissions).mockResolvedValue({ data: [] } as never)

    const { result } = renderHook(() => usePermissions(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.canAccess(77)).toBe(true)
    expect(result.current.canDo(77, 'view')).toBe(true)
    expect(result.current.canDo(77, 'backup')).toBe(false)
  })
})
