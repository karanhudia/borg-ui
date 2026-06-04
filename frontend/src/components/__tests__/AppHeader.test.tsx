import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider as MuiThemeProvider } from '@mui/material/styles'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import { darkTheme, theme } from '../../theme'
import AppHeader from '../AppHeader'
import { getProfileMenuContrastPairs } from '../profileMenuColors'

type Rgb = [number, number, number]

function hexToRgb(color: string): Rgb {
  const match = color.match(/^#([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i)

  if (!match) {
    throw new Error(`Expected a hex color, received ${color}`)
  }

  return [
    Number.parseInt(match[1], 16),
    Number.parseInt(match[2], 16),
    Number.parseInt(match[3], 16),
  ]
}

function linearizeChannel(channel: number) {
  const value = channel / 255
  return value <= 0.03928 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4
}

function relativeLuminance([red, green, blue]: Rgb) {
  return (
    0.2126 * linearizeChannel(red) +
    0.7152 * linearizeChannel(green) +
    0.0722 * linearizeChannel(blue)
  )
}

function contrastRatio(foreground: string, background: string) {
  const foregroundLuminance = relativeLuminance(hexToRgb(foreground))
  const backgroundLuminance = relativeLuminance(hexToRgb(background))
  const lighter = Math.max(foregroundLuminance, backgroundLuminance)
  const darker = Math.min(foregroundLuminance, backgroundLuminance)

  return (lighter + 0.05) / (darker + 0.05)
}

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

  it('keeps profile menu text colors above WCAG AA contrast in light and dark themes', () => {
    const minimumNormalTextContrast = 4.5

    for (const muiTheme of [theme, darkTheme]) {
      for (const pair of getProfileMenuContrastPairs(muiTheme)) {
        expect(contrastRatio(pair.foreground, pair.background), pair.name).toBeGreaterThanOrEqual(
          minimumNormalTextContrast
        )
      }
    }
  })

  it.each([
    ['light', theme],
    ['dark', darkTheme],
  ])('opens the profile menu in %s theme', async (_mode, muiTheme) => {
    const user = userEvent.setup()

    renderWithProviders(
      <MuiThemeProvider theme={muiTheme}>
        <AppHeader onToggleMobileMenu={vi.fn()} />
      </MuiThemeProvider>
    )

    await user.click(screen.getByRole('button', { name: /user menu/i }))

    expect(await screen.findByText('Pro Plan')).toBeInTheDocument()
    expect(await screen.findByText('Account & Security')).toBeInTheDocument()
    expect(await screen.findByText('Appearance')).toBeInTheDocument()
    expect(await screen.findByText('Logout')).toBeInTheDocument()
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
