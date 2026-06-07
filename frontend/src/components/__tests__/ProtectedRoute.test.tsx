import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderWithProviders, screen, waitFor } from '../../test/test-utils'
import ProtectedRoute from '../ProtectedRoute'

const {
  navigateMock,
  toastErrorMock,
  getTabDisabledReasonMock,
  hasGlobalPermissionMock,
  useAppStateMock,
  useTabEnablementMock,
} = vi.hoisted(() => ({
  navigateMock: vi.fn(),
  toastErrorMock: vi.fn(),
  getTabDisabledReasonMock: vi.fn(),
  hasGlobalPermissionMock: vi.fn(() => true),
  useAppStateMock: vi.fn(),
  useTabEnablementMock: vi.fn(),
}))

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    useNavigate: () => navigateMock,
  }
})

vi.mock('../../context/AppContext', () => ({
  useAppState: () => useAppStateMock(),
  useTabEnablement: () => useTabEnablementMock(),
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: hasGlobalPermissionMock,
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      error: toastErrorMock,
    },
  }
})

describe('ProtectedRoute', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    hasGlobalPermissionMock.mockReturnValue(true)
    useAppStateMock.mockReturnValue({ isLoading: false })
    getTabDisabledReasonMock.mockReturnValue('Please create a repository first')
    useTabEnablementMock.mockReturnValue({
      tabEnablement: {
        dashboard: true,
        sshKeys: true,
        connections: true,
        repositories: true,
        backups: true,
        archives: true,
        restore: true,
        schedule: true,
        settings: true,
      },
      getTabDisabledReason: getTabDisabledReasonMock,
    })
  })

  it('renders children when the tab is enabled', () => {
    renderWithProviders(
      <ProtectedRoute requiredTab="backups">
        <div>Backup Page</div>
      </ProtectedRoute>
    )

    expect(screen.getByText('Backup Page')).toBeInTheDocument()
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('does not redirect while app state is still loading', () => {
    useAppStateMock.mockReturnValue({ isLoading: true })
    useTabEnablementMock.mockReturnValue({
      tabEnablement: {
        dashboard: true,
        sshKeys: true,
        connections: true,
        repositories: true,
        backups: false,
        archives: true,
        restore: true,
        schedule: true,
        settings: true,
      },
      getTabDisabledReason: getTabDisabledReasonMock,
    })

    renderWithProviders(
      <ProtectedRoute requiredTab="backups">
        <div>Backup Page</div>
      </ProtectedRoute>
    )

    expect(screen.queryByText('Backup Page')).not.toBeInTheDocument()
    expect(toastErrorMock).not.toHaveBeenCalled()
    expect(navigateMock).not.toHaveBeenCalled()
  })

  it('shows a toast and redirects to the dashboard when the tab is disabled', async () => {
    useTabEnablementMock.mockReturnValue({
      tabEnablement: {
        dashboard: true,
        sshKeys: true,
        connections: true,
        repositories: true,
        backups: false,
        archives: true,
        restore: true,
        schedule: true,
        settings: true,
      },
      getTabDisabledReason: getTabDisabledReasonMock,
    })

    renderWithProviders(
      <ProtectedRoute requiredTab="backups">
        <div>Backup Page</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('Please create a repository first', {
        duration: 4000,
      })
      expect(navigateMock).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
    expect(screen.queryByText('Backup Page')).not.toBeInTheDocument()
  })

  it('falls back to the translated unavailable message when no disabled reason exists', async () => {
    getTabDisabledReasonMock.mockReturnValue(null)
    useTabEnablementMock.mockReturnValue({
      tabEnablement: {
        dashboard: true,
        sshKeys: true,
        connections: true,
        repositories: true,
        backups: false,
        archives: true,
        restore: true,
        schedule: true,
        settings: true,
      },
      getTabDisabledReason: getTabDisabledReasonMock,
    })

    renderWithProviders(
      <ProtectedRoute requiredTab="backups">
        <div>Backup Page</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('This feature is currently unavailable', {
        duration: 4000,
      })
    })
  })

  it('redirects when the required permission is missing', async () => {
    hasGlobalPermissionMock.mockReturnValue(false)

    renderWithProviders(
      <ProtectedRoute requiredTab="connections" requiredPermission="settings.ssh.manage">
        <div>Remote Clients Page</div>
      </ProtectedRoute>
    )

    await waitFor(() => {
      expect(toastErrorMock).toHaveBeenCalledWith('You do not have permission to open this page', {
        duration: 4000,
      })
      expect(navigateMock).toHaveBeenCalledWith('/dashboard', { replace: true })
    })
    expect(screen.queryByText('Remote Clients Page')).not.toBeInTheDocument()
  })
})
