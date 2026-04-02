import { beforeEach, describe, expect, it, vi } from 'vitest'
import { screen, renderWithProviders, userEvent, waitFor } from '../../test/test-utils'
import { ThemeProvider } from '../../context/ThemeContext'
import Settings from '../Settings'

const trackSettings = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'test', email: 'test@example.com', is_admin: false },
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings,
    EventAction: {
      VIEW: 'View',
      EDIT: 'Edit',
    },
  }),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    can: () => true,
  }),
}))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn().mockResolvedValue({ data: { settings: {} } }),
    changePassword: vi.fn(),
    getUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    resetUserPassword: vi.fn(),
    updateCurrentUser: vi.fn(),
  },
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useParams: () => ({ tab: 'appearance' }),
  }
})

describe('Settings appearance tab', () => {
  beforeEach(() => {
    trackSettings.mockClear()
    localStorage.clear()
    document.documentElement.classList.remove('dark')

    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn().mockImplementation(() => ({
        matches: false,
        media: '(prefers-color-scheme: dark)',
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    })
  })

  it('renders all theme picker options including auto', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    expect(await screen.findByText('Appearance')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Theme mode: Auto' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Theme mode: Light' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Theme mode: Dark' })).toBeInTheDocument()
    expect(screen.getByText('Following device setting: Light')).toBeInTheDocument()
  })

  it('switches to dark mode from the appearance picker', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('Appearance')
    trackSettings.mockClear()

    await userEvent.click(screen.getByRole('button', { name: 'Theme mode: Dark' }))

    await waitFor(() => {
      expect(screen.getByText('Dark selected')).toBeInTheDocument()
    })

    expect(localStorage.getItem('theme')).toBe('dark')
    expect(document.documentElement.classList.contains('dark')).toBe(true)
    expect(trackSettings).toHaveBeenCalledWith('Edit', {
      section: 'appearance',
      setting: 'theme',
      theme: 'dark',
    })
  })
})
