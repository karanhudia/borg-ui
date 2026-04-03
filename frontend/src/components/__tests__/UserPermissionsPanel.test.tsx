import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders, userEvent } from '../../test/test-utils'
import UserPermissionsPanel from '../UserPermissionsPanel'

const { refreshUserMock, trackSettingsMock } = vi.hoisted(() => ({
  refreshUserMock: vi.fn(),
  trackSettingsMock: vi.fn(),
}))

vi.mock('../../services/api', () => ({
  permissionsAPI: {
    getMyPermissions: vi.fn().mockResolvedValue({ data: [] }),
    getMyPermissionScope: vi.fn().mockResolvedValue({ data: { all_repositories_role: null } }),
    getUserPermissions: vi.fn().mockResolvedValue({ data: [] }),
    getUserPermissionScope: vi.fn().mockResolvedValue({ data: { all_repositories_role: null } }),
    assign: vi.fn().mockResolvedValue({}),
    remove: vi.fn().mockResolvedValue({}),
    update: vi.fn().mockResolvedValue({}),
    updateScope: vi.fn().mockResolvedValue({}),
  },
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      id: 1,
      role: 'operator',
      global_permissions: [],
      all_repositories_role: null,
    },
    refreshUser: refreshUserMock,
  }),
}))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    assignableRepositoryRolesFor: (role: string) =>
      role === 'viewer' ? ['viewer'] : ['viewer', 'operator'],
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings: trackSettingsMock,
    EventAction: {
      EDIT: 'Edit',
      DELETE: 'Delete',
    },
  }),
}))

describe('UserPermissionsPanel', () => {
  beforeEach(async () => {
    vi.clearAllMocks()
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissions).mockResolvedValue({ data: [] } as never)
    vi.mocked(permissionsAPI.getMyPermissionScope).mockResolvedValue({
      data: { all_repositories_role: null },
    } as never)
    vi.mocked(permissionsAPI.getUserPermissions).mockResolvedValue({ data: [] } as never)
    vi.mocked(permissionsAPI.getUserPermissionScope).mockResolvedValue({
      data: { all_repositories_role: null },
    } as never)
  })

  it('shows empty state when no permissions exist in read-only mode', async () => {
    renderWithProviders(<UserPermissionsPanel />)

    await waitFor(() => {
      expect(screen.getByText(/no repository permissions assigned yet/i)).toBeInTheDocument()
    })
  })

  it('shows only the wildcard summary in read-only mode when automatic access exists', async () => {
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissionScope).mockResolvedValue({
      data: { all_repositories_role: 'operator' },
    } as never)
    vi.mocked(permissionsAPI.getMyPermissions).mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 1,
          repository_id: 10,
          repository_name: 'prod-backups',
          role: 'viewer',
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    } as never)

    renderWithProviders(<UserPermissionsPanel />)

    await waitFor(() => {
      expect(
        screen.getByText(/this account currently has automatic access to all repositories/i)
      ).toBeInTheDocument()
    })
    expect(screen.queryByText('prod-backups')).not.toBeInTheDocument()
  })

  it('shows assign controls in selected mode for admins', async () => {
    renderWithProviders(
      <UserPermissionsPanel
        userId={2}
        canManageAssignments={true}
        repositories={[{ id: 1, name: 'prod-backups' }]}
      />
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /assign/i })).toBeInTheDocument()
    })
  })

  it('refreshes auth when updating the current user repository scope', async () => {
    const user = userEvent.setup()
    const { permissionsAPI } = await import('../../services/api')

    renderWithProviders(
      <UserPermissionsPanel
        userId={1}
        canManageAssignments={true}
        repositories={[{ id: 1, name: 'prod-backups' }]}
        targetUserRole="operator"
      />
    )

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /save changes/i })).toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /all repositories/i }))
    await user.click(screen.getByRole('button', { name: /save changes/i }))

    await waitFor(() => {
      expect(permissionsAPI.updateScope).toHaveBeenCalledWith(1, 'operator')
    })
    await waitFor(() => {
      expect(refreshUserMock).toHaveBeenCalledTimes(1)
    })
  })
})
