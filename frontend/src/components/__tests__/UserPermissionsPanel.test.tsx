import { describe, it, expect, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import UserPermissionsPanel from '../UserPermissionsPanel'

vi.mock('../../services/api', () => ({
  permissionsAPI: {
    getMyPermissions: vi.fn().mockResolvedValue({ data: [] }),
    getMyPermissionScope: vi.fn().mockResolvedValue({ data: { all_repositories_role: null } }),
    getUserPermissions: vi.fn().mockResolvedValue({ data: [] }),
    getUserPermissionScope: vi.fn().mockResolvedValue({ data: { all_repositories_role: null } }),
    assign: vi.fn(),
    remove: vi.fn(),
    update: vi.fn(),
    updateScope: vi.fn(),
  },
}))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    assignableRepositoryRolesFor: (role: string) =>
      role === 'viewer' ? ['viewer'] : ['viewer', 'operator'],
  }),
}))

describe('UserPermissionsPanel', () => {
  it('shows empty state when no permissions (read-only mode)', async () => {
    renderWithProviders(<UserPermissionsPanel />)
    await waitFor(() => {
      expect(screen.getByText(/no repository permissions assigned/i)).toBeInTheDocument()
    })
  })

  it('shows automatic access chip in read-only mode when wildcard role exists', async () => {
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getMyPermissionScope).mockResolvedValue({
      data: { all_repositories_role: 'operator' },
    } as never)

    renderWithProviders(<UserPermissionsPanel />)
    await waitFor(() => {
      expect(screen.getByText(/automatic operator access/i)).toBeInTheDocument()
    })
  })

  it('does not show Add controls in read-only mode', async () => {
    renderWithProviders(<UserPermissionsPanel canManageAssignments={false} />)
    await waitFor(() =>
      expect(screen.queryByRole('button', { name: /add/i })).not.toBeInTheDocument()
    )
  })

  it('shows Add controls in admin mode when repositories are available', async () => {
    renderWithProviders(
      <UserPermissionsPanel
        userId={1}
        canManageAssignments={true}
        repositories={[{ id: 1, name: 'prod-backups' }]}
      />
    )
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /add|assign/i })).toBeInTheDocument()
    })
  })

  it('renders permission rows with role chips', async () => {
    const { permissionsAPI } = await import('../../services/api')
    vi.mocked(permissionsAPI.getUserPermissions).mockResolvedValue({
      data: [
        {
          id: 1,
          user_id: 2,
          repository_id: 3,
          repository_name: 'prod-backups',
          role: 'operator',
          created_at: '2024-01-01T00:00:00Z',
        },
      ],
    } as never)

    renderWithProviders(
      <UserPermissionsPanel userId={2} canManageAssignments={true} repositories={[]} />
    )
    await waitFor(() => {
      expect(screen.getByText('prod-backups')).toBeInTheDocument()
      expect(screen.getByText('Operator')).toBeInTheDocument()
    })
  })
})
