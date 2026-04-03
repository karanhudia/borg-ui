import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ThemeProvider } from '../../context/ThemeContext'
import {
  fireEvent,
  renderWithProviders,
  screen,
  userEvent,
  waitFor,
  within,
} from '../../test/test-utils'
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
      CREATE: 'Create',
      EDIT: 'Edit',
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

vi.mock('../../components/DataTable', () => ({
  default: ({
    data,
    actions,
  }: {
    data: Array<{ id: number }>
    actions?: Array<{ label: string; onClick: (row: { id: number }) => void }>
  }) => (
    <div>
      {actions?.map((action) => (
        <button key={action.label} onClick={() => action.onClick(data[0])}>
          {action.label}
        </button>
      ))}
    </div>
  ),
}))

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
    useParams: () => ({ tab: 'users' }),
  }
})

describe('Settings users tab', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(apiModule.settingsAPI.getSystemSettings).mockResolvedValue({
      data: { settings: {} },
    } as never)
    vi.mocked(apiModule.settingsAPI.getUsers).mockResolvedValue({
      data: {
        users: [
          {
            id: 2,
            username: 'existing',
            email: 'existing@example.com',
            is_active: true,
            is_admin: false,
            created_at: '2026-01-01T00:00:00Z',
            last_login: null,
          },
        ],
      },
    } as never)
    vi.mocked(apiModule.settingsAPI.createUser).mockResolvedValue({ data: {} } as never)
    vi.mocked(apiModule.settingsAPI.resetUserPassword).mockResolvedValue({ data: {} } as never)
    vi.mocked(apiModule.settingsAPI.deleteUser).mockResolvedValue({ data: {} } as never)
  })

  it('tracks the users tab view on render', async () => {
    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('User Management')

    expect(trackSettings).toHaveBeenCalledWith('View', {
      section: 'settings',
      tab: 'users',
    })
  })

  it('creates, resets password for, and deletes users via settings actions', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('User Management')

    await user.click(screen.getByRole('button', { name: /add user/i }))
    const createDialog = await screen.findByRole('dialog', { name: /create user/i })
    const usernameInput = within(createDialog).getByLabelText(/username/i)
    const emailInput = within(createDialog).getByLabelText(/email/i)
    const passwordInput = within(createDialog).getByLabelText(/password/i)
    await user.type(usernameInput, 'new-user')
    await user.type(emailInput, 'new@example.com')
    await user.type(passwordInput, 'strong-password')
    expect(usernameInput).toHaveValue('new-user')
    expect(emailInput).toHaveValue('new@example.com')
    expect(passwordInput).toHaveValue('strong-password')
    fireEvent.submit(
      within(createDialog)
        .getByRole('button', { name: /^create$/i })
        .closest('form')!
    )

    await waitFor(() => {
      expect(apiModule.settingsAPI.createUser).toHaveBeenCalled()
    })
    expect(vi.mocked(apiModule.settingsAPI.createUser).mock.calls.slice(-1)[0]?.[0]).toMatchObject({
      username: 'new-user',
      email: 'new@example.com',
      password: 'strong-password',
      is_admin: false,
    })
    expect(trackSettings).toHaveBeenCalledWith('Create', {
      section: 'users',
      role: 'user',
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /create user/i })).not.toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /reset password/i }))
    const resetDialog = await screen.findByRole('dialog', { name: /reset password/i })
    const resetPasswordInput = within(resetDialog).getByLabelText(/new password/i)
    await user.type(resetPasswordInput, 'new-reset-password')
    expect(resetPasswordInput).toHaveValue('new-reset-password')
    fireEvent.submit(
      within(resetDialog)
        .getByRole('button', { name: /^reset password$/i })
        .closest('form')!
    )

    await waitFor(() => {
      expect(apiModule.settingsAPI.resetUserPassword).toHaveBeenCalled()
    })
    expect(vi.mocked(apiModule.settingsAPI.resetUserPassword).mock.calls.slice(-1)[0]).toEqual([
      2,
      'new-reset-password',
    ])
    expect(trackSettings).toHaveBeenCalledWith('Edit', {
      section: 'users',
      operation: 'reset_password',
    })
    await waitFor(() => {
      expect(screen.queryByRole('dialog', { name: /reset password/i })).not.toBeInTheDocument()
    })

    await user.click(screen.getByRole('button', { name: /delete user/i }))
    const deleteDialog = await screen.findByRole('dialog', { name: /delete user/i })
    await user.click(within(deleteDialog).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => {
      expect(apiModule.settingsAPI.deleteUser).toHaveBeenCalled()
    })
    expect(vi.mocked(apiModule.settingsAPI.deleteUser).mock.calls.slice(-1)[0]?.[0]).toBe(2)
    expect(trackSettings).toHaveBeenCalledWith('Delete', { section: 'users' })
  })

  it('edits an existing user via the settings actions', async () => {
    const user = userEvent.setup()

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('User Management')

    await user.click(screen.getByRole('button', { name: /edit user/i }))
    const editDialog = await screen.findByRole('dialog', { name: /edit user/i })
    const emailInput = within(editDialog).getByLabelText(/email/i)
    await user.clear(emailInput)
    await user.type(emailInput, 'updated@example.com')
    await user.click(within(editDialog).getByRole('button', { name: /^update$/i }))

    await waitFor(() => {
      expect(apiModule.settingsAPI.updateUser).toHaveBeenCalledWith(
        2,
        expect.objectContaining({
          username: 'existing',
          email: 'updated@example.com',
          is_admin: false,
        })
      )
    })
    expect(trackSettings).toHaveBeenCalledWith('Edit', {
      section: 'users',
      role: 'user',
    })
  })

  it('shows backend errors when creating a user fails', async () => {
    const user = userEvent.setup()
    vi.mocked(apiModule.settingsAPI.createUser).mockRejectedValue({
      response: { data: { detail: 'settings.toasts.failedToCreateUser' } },
    } as never)

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('User Management')

    await user.click(screen.getByRole('button', { name: /add user/i }))
    const createDialog = await screen.findByRole('dialog', { name: /create user/i })
    await user.type(within(createDialog).getByLabelText(/username/i), 'new-user')
    await user.type(within(createDialog).getByLabelText(/email/i), 'new@example.com')
    await user.type(within(createDialog).getByLabelText(/password/i), 'strong-password')
    fireEvent.submit(
      within(createDialog)
        .getByRole('button', { name: /^create$/i })
        .closest('form')!
    )

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Failed to create user')
    })
    expect(trackSettings).not.toHaveBeenCalledWith('Create', {
      section: 'users',
      role: 'user',
    })
    expect(screen.getByRole('dialog', { name: /create user/i })).toBeInTheDocument()
  })

  it('shows backend errors when deleting a user fails', async () => {
    const user = userEvent.setup()
    vi.mocked(apiModule.settingsAPI.deleteUser).mockRejectedValue({
      response: { data: { detail: 'Cannot delete the last admin' } },
    } as never)

    renderWithProviders(
      <ThemeProvider>
        <Settings />
      </ThemeProvider>
    )

    await screen.findByText('User Management')
    await user.click(screen.getByRole('button', { name: /delete user/i }))
    const deleteDialog = await screen.findByRole('dialog', { name: /delete user/i })
    await user.click(within(deleteDialog).getByRole('button', { name: /^delete$/i }))

    await waitFor(() => {
      expect(toast.error).toHaveBeenCalledWith('Cannot delete the last admin')
    })
    expect(trackSettings).not.toHaveBeenCalledWith('Delete', { section: 'users' })
    expect(screen.getByRole('dialog', { name: /delete user/i })).toBeInTheDocument()
  })
})
