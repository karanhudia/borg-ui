import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import AppHeader from '../AppHeader'

const { logoutMock, trackAuthMock, trackNavigationMock, navigateMock } = vi.hoisted(() => ({
  logoutMock: vi.fn(),
  trackAuthMock: vi.fn(),
  trackNavigationMock: vi.fn(),
  navigateMock: vi.fn(),
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
    trackPlan: vi.fn(),
    EventAction: {
      VIEW: 'View',
      LOGOUT: 'Logout',
    },
  }),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    plan: 'pro',
    features: {},
    entitlement: undefined,
    isLoading: false,
  }),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return { ...actual, useNavigate: () => navigateMock }
})

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

  it('shows user name and role badge in the hero header when menu opens', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(await screen.findAllByText('Admin User')).toHaveLength(2) // trigger + hero
    expect(await screen.findByText('Individual')).toBeInTheDocument()
    expect(await screen.findByText('Admin')).toBeInTheDocument()
  })

  it('shows the plan card when menu opens', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(await screen.findByText('Pro Plan')).toBeInTheDocument()
    expect(await screen.findByText('All Pro features unlocked')).toBeInTheDocument()
  })

  it('shows all three settings navigation links when menu opens', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(await screen.findByText('Account & Security')).toBeInTheDocument()
    expect(await screen.findByText('Appearance')).toBeInTheDocument()
    expect(await screen.findByText('Notifications')).toBeInTheDocument()
  })

  it('navigates to account settings when Account & Security link is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(await screen.findByText('Account & Security'))

    expect(navigateMock).toHaveBeenCalledWith('/settings/account')
  })

  it('navigates to appearance settings when Appearance link is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(await screen.findByText('Appearance'))

    expect(navigateMock).toHaveBeenCalledWith('/settings/appearance')
  })

  it('navigates to notifications settings when Notifications link is clicked', async () => {
    const user = userEvent.setup()
    renderWithProviders(<AppHeader onToggleMobileMenu={vi.fn()} />)

    await user.click(screen.getByRole('button', { name: /user menu/i }))
    await user.click(await screen.findByText('Notifications'))

    expect(navigateMock).toHaveBeenCalledWith('/settings/notifications')
  })
})
