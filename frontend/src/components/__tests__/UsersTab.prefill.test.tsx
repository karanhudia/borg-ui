import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor, within } from '@testing-library/react'
import { renderWithProviders } from '../../test/test-utils'
import UsersTab from '../UsersTab'

const plan = vi.hoisted(() => ({ multiUser: true }))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({ hasGlobalPermission: () => true, user: { id: 1, role: 'admin' } }),
}))
vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({ roleHasGlobalPermission: () => true }),
}))
vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({ trackSettings: vi.fn(), EventAction: {} }),
}))
vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({ can: () => plan.multiUser }),
}))
vi.mock('../../services/api', () => ({
  settingsAPI: {
    getUsers: vi.fn().mockResolvedValue({ data: { users: [] } }),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    resetUserPassword: vi.fn(),
  },
  repositoriesAPI: { getRepositories: vi.fn().mockResolvedValue({ data: { repositories: [] } }) },
}))

describe('UsersTab hand-off link', () => {
  it('opens the add-user dialog prefilled from ?new=1', async () => {
    plan.multiUser = true
    renderWithProviders(<UsersTab />, {
      initialRoute:
        '/settings/users?new=1&username=robin&email=robin%40example.invalid&full_name=Robin&role=operator',
    })
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/^Username/i)).toHaveValue('robin')
    expect(within(dialog).getByLabelText(/^Email/i)).toHaveValue('robin@example.invalid')
    expect(within(dialog).getByLabelText(/^Full name/i)).toHaveValue('Robin')
    await waitFor(() => expect(window.location.search).toBe(''))
  })

  it('ignores a role it does not know', async () => {
    plan.multiUser = true
    renderWithProviders(<UsersTab />, {
      initialRoute: '/settings/users?new=1&username=robin&role=superuser',
    })
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).getByLabelText(/^Username/i)).toHaveValue('robin')
    expect(within(dialog).queryByText(/superuser/i)).not.toBeInTheDocument()
  })

  it('opens nothing when the plan has no multi-user', async () => {
    plan.multiUser = false
    renderWithProviders(<UsersTab />, { initialRoute: '/settings/users?new=1&username=robin' })
    await new Promise((resolve) => setTimeout(resolve, 50))
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })
})
