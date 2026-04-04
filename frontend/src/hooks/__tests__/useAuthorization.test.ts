import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import React from 'react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { useAuthorization } from '../useAuthorization'

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
          { id: 'admin', rank: 3, scope: 'repository' },
        ],
        global_permission_rules: {
          'settings.users.manage': 'admin',
          'settings.ssh.manage': 'operator',
        },
        repository_action_rules: {
          view: 'viewer',
          backup: 'operator',
          delete_archive: 'admin',
        },
        assignable_repository_roles_by_global_role: {
          viewer: ['viewer'],
          operator: ['viewer', 'operator'],
          admin: ['viewer', 'operator', 'admin'],
        },
      },
    }),
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

describe('useAuthorization', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('derives repository and global permission checks from the authorization model', async () => {
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'operator' },
      hasGlobalPermission: vi.fn().mockReturnValue(false),
    } as never)

    const { result } = renderHook(() => useAuthorization(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.canRepositoryRoleDo('viewer', 'view')).toBe(true)
    expect(result.current.canRepositoryRoleDo('viewer', 'backup')).toBe(false)
    expect(result.current.canRepositoryRoleDo('operator', 'backup')).toBe(true)
    expect(result.current.canRepositoryRoleDo('operator', 'delete_archive')).toBe(false)

    expect(result.current.roleHasGlobalPermission('viewer', 'settings.ssh.manage')).toBe(false)
    expect(result.current.roleHasGlobalPermission('operator', 'settings.ssh.manage')).toBe(true)
    expect(result.current.roleHasGlobalPermission('operator', 'settings.users.manage')).toBe(false)
    expect(result.current.roleHasGlobalPermission('admin', 'settings.users.manage')).toBe(true)
  })

  it('exposes assignable repository roles and auth passthrough state', async () => {
    const hasGlobalPermission = vi.fn((permission: string) => permission === 'settings.ssh.manage')
    const { useAuth } = await import('../useAuth')
    vi.mocked(useAuth).mockReturnValue({
      user: { role: 'admin' },
      hasGlobalPermission,
    } as never)

    const { result } = renderHook(() => useAuthorization(), { wrapper: makeWrapper() })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.currentGlobalRole).toBe('admin')
    expect(result.current.assignableRepositoryRolesFor('operator')).toEqual(['viewer', 'operator'])
    expect(result.current.assignableRepositoryRolesFor('admin')).toEqual([
      'viewer',
      'operator',
      'admin',
    ])
    expect(result.current.assignableRepositoryRolesFor(null)).toEqual([])
    expect(result.current.hasGlobalPermission('settings.ssh.manage')).toBe(true)
    expect(hasGlobalPermission).toHaveBeenCalledWith('settings.ssh.manage')
  })
})
