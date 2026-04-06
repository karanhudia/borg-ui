import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import AppHeader from '../AppHeader'

const { logoutMock, trackAuthMock, trackNavigationMock } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  trackAuthMock: vi.fn(),
  trackNavigationMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: {
      username: 'admin',
      full_name: 'Admin User',
      email: 'admin@example.com',
      role: 'admin',
      deployment_type: 'individual',
    },
    logout: logoutMock,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackAuth: trackAuthMock,
    trackNavigation: trackNavigationMock,
    EventAction: {
      VIEW: 'View',
      LOGOUT: 'Logout',
    },
  }),
}))

describe('AppHeader', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('tracks user menu views and logout from the user menu', async () => {
    const user = userEvent.setup()

    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(trackNavigationMock).toHaveBeenCalledWith('View', { surface: 'user_menu' })

    await user.click(await screen.findByText('Logout'))

    await waitFor(() => {
      expect(trackAuthMock).toHaveBeenCalledWith('Logout', { surface: 'user_menu' })
      expect(logoutMock).toHaveBeenCalledTimes(1)
    })
  })
})
