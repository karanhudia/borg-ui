import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor, within } from '../../test/test-utils'
import { ThemeProvider } from '../../context/ThemeContext'
import Settings from '../Settings'
import * as apiModule from '../../services/api'
import { toast } from 'react-hot-toast'

const trackSettings = vi.fn()
const { useAuthMock } = vi.hoisted(() => ({
  useAuthMock: vi.fn(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => useAuthMock(),
}))

vi.mock('../../hooks/useAuthorization', () => ({
  useAuthorization: () => ({
    roleHasGlobalPermission: (role: string, permission: string) => {
      if (role !== 'admin') return false
      return [
        'settings.users.manage',
        'settings.system.manage',
        'repositories.manage_all',
        'settings.mounts.manage',
      ].includes(permission)
    },
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    trackSettings,
    EventAction: {
      VIEW: 'View',
      EDIT: 'Edit',
      CREATE: 'Create',
      DELETE: 'Delete',
    },
  }),
}))

vi.mock('../../hooks/usePlan', () => ({
  usePlan: () => ({
    can: () => true,
  }),
}))

vi.mock('../../components/NotificationsTab', () => ({ default: () => null }))
vi.mock('../../components/PreferencesTab', () => ({ default: () => null }))
vi.mock('../../components/PackagesTab', () => ({ default: () => null }))
vi.mock('../../components/ExportImportTab', () => ({ default: () => null }))
vi.mock('../../components/LogManagementTab', () => ({ default: () => null }))
vi.mock('../../components/CacheManagementTab', () => ({ default: () => null }))
vi.mock('../../components/MountsManagementTab', () => ({ default: () => null }))
vi.mock('../../components/SystemSettingsTab', () => ({ default: () => null }))
vi.mock('../../components/BetaFeaturesTab', () => ({ default: () => null }))
vi.mock('../../components/MqttSettingsTab', () => ({ default: () => null }))
vi.mock('../Scripts', () => ({ default: () => null }))
vi.mock('../Activity', () => ({ default: () => null }))
vi.mock('../../components/DataTable', () => ({ default: () => null }))

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
    changePassword: vi.fn(),
    getUsers: vi.fn(),
    createUser: vi.fn(),
    updateUser: vi.fn(),
    deleteUser: vi.fn(),
    resetUserPassword: vi.fn(),
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
    useParams: () => ({ tab: 'account' }),
  }
})

describe('Settings account tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    useAuthMock.mockReturnValue({
      user: {
        id: 1,
        username: 'admin',
        full_name: 'Admin User',
        email: 'admin@example.com',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
        deployment_type: 'enterprise',
        enterprise_name: 'NullCode AI',
        global_permissions: [
          'settings.users.manage',
          'settings.system.manage',
          'repositories.manage_all',
        ],
      },
      hasGlobalPermission: (permission: string) =>
        ['settings.users.manage', 'settings.system.manage', 'repositories.manage_all'].includes(
          permission
        ),
      markRecentPasswordConfirmation: vi.fn(),
      refreshUser: vi.fn(),
    })
    vi.mocked(apiModule.settingsAPI.getSystemSettings).mockResolvedValue({
      data: { settings: {} },
    } as never)
    vi.mocked(apiModule.settingsAPI.getUsers).mockResolvedValue({
      data: { users: [] },
    } as never)
    vi.mocked(apiModule.settingsAPI.changePassword).mockResolvedValue({ data: {} } as never)
  })

  it('tracks the account tab view on render', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('tab', { name: 'Personal profile' })

    expect(trackSettings).toHaveBeenCalledWith('View', {
      section: 'settings',
      tab: 'account',
    })
  })

  it('shows the password action at the top when password change is required', async () => {
    useAuthMock.mockReturnValue({
      user: {
        id: 1,
        username: 'admin',
        full_name: 'Admin User',
        email: 'admin@example.com',
        role: 'admin',
        created_at: '2024-01-01T00:00:00Z',
        deployment_type: 'enterprise',
        enterprise_name: 'NullCode AI',
        must_change_password: true,
        global_permissions: [
          'settings.users.manage',
          'settings.system.manage',
          'repositories.manage_all',
        ],
      },
      hasGlobalPermission: (permission: string) =>
        ['settings.users.manage', 'settings.system.manage', 'repositories.manage_all'].includes(
          permission
        ),
      markRecentPasswordConfirmation: vi.fn(),
      refreshUser: vi.fn(),
    })

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('tab', { name: 'Personal profile' })

    const headings = screen.getAllByText('Account password')
    expect(headings[0]).toBeInTheDocument()
    expect(screen.getByText('Password update required')).toBeInTheDocument()
    expect(screen.queryByText('Finish account setup')).not.toBeInTheDocument()
  })

  it('changes password and tracks the edit event', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('tab', { name: 'Personal profile' })
    await user.click(screen.getByRole('button', { name: /account password/i }))
    const dialog = await screen.findByRole('dialog', { name: /change password/i })
    const newPasswordInput = within(dialog).getByLabelText(/new password/i)
    await user.type(within(dialog).getByLabelText(/current password/i), 'old-password')
    await user.type(newPasswordInput, 'new-password-123')
    await user.type(within(dialog).getByLabelText(/confirm password/i), 'new-password-123')
    await user.click(within(dialog).getByRole('button', { name: /update password/i }))

    await waitFor(() => {
      expect(apiModule.settingsAPI.changePassword).toHaveBeenCalledWith({
        current_password: 'old-password',
        new_password: 'new-password-123',
      })
    })
    expect(trackSettings).toHaveBeenCalledWith('Edit', {
      section: 'account',
      operation: 'change_password',
    })
    expect(toast.success).toHaveBeenCalled()
  })

  it('blocks submission when the new passwords do not match', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('tab', { name: 'Personal profile' })
    await user.click(screen.getByRole('button', { name: /account password/i }))
    const dialog = await screen.findByRole('dialog', { name: /change password/i })
    const newPasswordInput = within(dialog).getByLabelText(/new password/i)
    await user.type(within(dialog).getByLabelText(/current password/i), 'old-password')
    await user.type(newPasswordInput, 'new-password-123')
    await user.type(within(dialog).getByLabelText(/confirm password/i), 'different-password')
    await user.click(within(dialog).getByRole('button', { name: /update password/i }))

    expect(apiModule.settingsAPI.changePassword).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalled()
  })

  it('shows translated backend errors when password change fails', async () => {
    const user = userEvent.setup()
    vi.mocked(apiModule.settingsAPI.changePassword).mockRejectedValue({
      response: { data: { detail: 'settings.toasts.failedToChangePassword' } },
    } as never)

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('tab', { name: 'Personal profile' })
    await user.click(screen.getByRole('button', { name: /account password/i }))
    const dialog = await screen.findByRole('dialog', { name: /change password/i })
    const newPasswordInput = within(dialog).getByLabelText(/new password/i)
    await user.type(within(dialog).getByLabelText(/current password/i), 'old-password')
    await user.type(newPasswordInput, 'new-password-123')
    await user.type(within(dialog).getByLabelText(/confirm password/i), 'new-password-123')
    await user.click(within(dialog).getByRole('button', { name: /update password/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to change password')
    })
    expect(trackSettings).not.toHaveBeenCalledWith('Edit', {
      section: 'account',
      operation: 'change_password',
    })
  })
})
