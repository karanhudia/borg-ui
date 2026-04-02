import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import { ThemeProvider } from '../../context/ThemeContext'
import Settings from '../Settings'
import * as apiModule from '../../services/api'
import { toast } from 'react-hot-toast'

const trackSettings = vi.fn()

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, username: 'admin', email: 'admin@example.com', is_admin: true },
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
    vi.mocked(apiModule.settingsAPI.getSystemSettings).mockResolvedValue({
      data: { settings: {} },
    } as never)
    vi.mocked(apiModule.settingsAPI.getUsers).mockResolvedValue({
      data: { users: [] },
    } as never)
    vi.mocked(apiModule.settingsAPI.changePassword).mockResolvedValue({ data: {} } as never)
  })

  it('changes password and tracks the edit event', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByRole('heading', { name: 'Change Password' })
    const newPasswordInput = screen.getAllByLabelText(/new password/i)[0]
    await user.type(screen.getByLabelText(/current password/i), 'old-password')
    await user.type(newPasswordInput, 'new-password-123')
    await user.type(screen.getByLabelText(/confirm new password/i), 'new-password-123')
    await user.click(screen.getByRole('button', { name: /change password/i }))

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

    await screen.findByRole('heading', { name: 'Change Password' })
    const newPasswordInput = screen.getAllByLabelText(/new password/i)[0]
    await user.type(screen.getByLabelText(/current password/i), 'old-password')
    await user.type(newPasswordInput, 'new-password-123')
    await user.type(screen.getByLabelText(/confirm new password/i), 'different-password')
    await user.click(screen.getByRole('button', { name: /change password/i }))

    expect(apiModule.settingsAPI.changePassword).not.toHaveBeenCalled()
    expect(toast.error).toHaveBeenCalled()
  })
})
