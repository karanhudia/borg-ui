import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import SSHConnectionsSingleKey from '../SSHConnectionsSingleKey'

const { track, toastSuccess, toastError, mockState } = vi.hoisted(() => ({
  track: vi.fn(),
  toastSuccess: vi.fn(),
  toastError: vi.fn(),
  mockState: {
    canManageSsh: true,
    systemKeyResponse: {
      data: {
        exists: true,
        ssh_key: {
          id: 7,
          key_type: 'ed25519',
          fingerprint: 'SHA256:abc',
          public_key: 'ssh-ed25519 AAAA test@example',
        },
      },
    } as {
      data: {
        exists: boolean
        ssh_key?: {
          id: number
          key_type: string
          fingerprint: string
          public_key: string
        }
      }
    },
    connectionsResponse: {
      data: {
        connections: [] as Array<Record<string, unknown>>,
      },
    } as {
      data: {
        connections: Array<Record<string, unknown>>
      }
    },
  },
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    user: { id: 1, role: 'admin' },
    hasGlobalPermission: (permission: string) =>
      permission === 'settings.ssh.manage' ? mockState.canManageSsh : false,
  }),
}))

vi.mock('../../hooks/useAnalytics', () => ({
  useAnalytics: () => ({
    track,
    EventCategory: { SSH: 'ssh' },
    EventAction: {
      CREATE: 'create',
      UPLOAD: 'upload',
      TEST: 'test',
      EDIT: 'edit',
      DELETE: 'delete',
      VIEW: 'view',
      START: 'start',
    },
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual<typeof import('react-hot-toast')>('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: toastSuccess,
      error: toastError,
    },
  }
})

vi.mock('react-router-dom', async () => {
  const actual = await vi.importActual<typeof import('react-router-dom')>('react-router-dom')
  return {
    ...actual,
    Navigate: ({ to }: { to: string }) => <div data-testid="navigate">redirect:{to}</div>,
  }
})

vi.mock('../../components/RemoteMachineCard', () => ({
  default: ({
    machine,
    onEdit,
    onDelete,
    onTestConnection,
    onDeployKey,
  }: {
    machine: { host: string }
    onEdit: (machine: { host: string }) => void
    onDelete: (machine: { host: string }) => void
    onTestConnection: (machine: { host: string }) => void
    onDeployKey: (machine: { host: string }) => void
  }) => (
    <div>
      <span>{machine.host}</span>
      <button onClick={() => onEdit(machine)}>edit {machine.host}</button>
      <button onClick={() => onDelete(machine)}>delete {machine.host}</button>
      <button onClick={() => onTestConnection(machine)}>test {machine.host}</button>
      <button onClick={() => onDeployKey(machine)}>deploy {machine.host}</button>
    </div>
  ),
}))

vi.mock('../../services/api', () => ({
  sshKeysAPI: {
    getSystemKey: vi.fn(() => Promise.resolve(mockState.systemKeyResponse)),
    getSSHConnections: vi.fn(() => Promise.resolve(mockState.connectionsResponse)),
    generateSSHKey: vi.fn(() => Promise.resolve({ data: {} })),
    importSSHKey: vi.fn(() => Promise.resolve({ data: {} })),
    deploySSHKey: vi.fn(() => Promise.resolve({ data: {} })),
    testSSHConnection: vi.fn(() => Promise.resolve({ data: { success: true } })),
    updateSSHConnection: vi.fn(() => Promise.resolve({ data: {} })),
    testExistingConnection: vi.fn(() => Promise.resolve({ data: { success: true } })),
    deleteSSHConnection: vi.fn(() => Promise.resolve({ data: {} })),
    refreshConnectionStorage: vi.fn(() => Promise.resolve({ data: {} })),
    deleteSSHKey: vi.fn(() => Promise.resolve({ data: {} })),
    redeployKeyToConnection: vi.fn(() => Promise.resolve({ data: { success: true } })),
  },
}))

describe('SSHConnectionsSingleKey', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    vi.clearAllMocks()
    mockState.canManageSsh = true
    mockState.systemKeyResponse = {
      data: {
        exists: true,
        ssh_key: {
          id: 7,
          key_type: 'ed25519',
          fingerprint: 'SHA256:abc',
          public_key: 'ssh-ed25519 AAAA test@example',
        },
      },
    }
    mockState.connectionsResponse = {
      data: {
        connections: [
          {
            id: 3,
            ssh_key_id: 7,
            ssh_key_name: 'System SSH Key',
            host: 'backup-host',
            username: 'borg',
            port: 2222,
            use_sftp_mode: true,
            use_sudo: false,
            default_path: '/srv',
            ssh_path_prefix: '/prefix',
            mount_point: 'backup-box',
            status: 'connected',
            created_at: '2026-01-01T00:00:00Z',
            storage: {
              total: 1,
              total_formatted: '1 TB',
              used: 1,
              used_formatted: '100 GB',
              available: 1,
              available_formatted: '900 GB',
              percent_used: 10,
            },
          },
        ],
      },
    }
  })

  it('redirects when the user lacks SSH management permission', async () => {
    mockState.canManageSsh = false

    renderWithProviders(<SSHConnectionsSingleKey />)

    expect(await screen.findByTestId('navigate')).toHaveTextContent('redirect:/dashboard')
  })

  it('generates a system SSH key with the selected algorithm', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')
    mockState.systemKeyResponse = { data: { exists: false } }
    mockState.connectionsResponse = { data: { connections: [] } }

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    await user.click(screen.getByRole('button', { name: /generate system ssh key/i }))
    await user.click(screen.getByRole('combobox'))
    await user.click(screen.getByRole('option', { name: 'RSA' }))
    await user.click(screen.getByRole('button', { name: /^generate key$/i }))

    await waitFor(() => {
      expect(sshKeysAPI.generateSSHKey).toHaveBeenCalledWith({
        name: 'System SSH Key',
        key_type: 'rsa',
        description: 'System SSH key for all remote connections',
      })
    })
  })

  it('deploys the system key with the expected connection payload', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    await user.click(
      screen.getByRole('button', {
        name: /automatically deploy ssh key using password authentication/i,
      })
    )
    await user.type(screen.getByLabelText(/^host$/i), 'nas.local')
    await user.type(screen.getByLabelText(/^username$/i), 'root')
    await user.clear(screen.getByLabelText(/^port$/i))
    await user.type(screen.getByLabelText(/^port$/i), '2200')
    await user.type(screen.getByLabelText(/^password$/i), 'secret')
    await user.type(screen.getByLabelText(/default path/i), '/backups')
    await user.type(screen.getByLabelText(/mount point/i), 'nas')
    await user.click(screen.getByRole('button', { name: /^deploy key$/i }))

    await waitFor(() => {
      expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(7, {
        host: 'nas.local',
        username: 'root',
        port: 2200,
        password: 'secret',
        use_sftp_mode: true,
        default_path: '/backups',
        ssh_path_prefix: '',
        mount_point: 'nas',
      })
    })
  })

  it('tests and adds a manual connection with the expected payload', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    await user.click(
      screen.getByRole('button', {
        name: /add a connection for a manually deployed ssh key/i,
      })
    )
    await user.type(screen.getByLabelText(/^host$/i), 'manual.example.com')
    await user.type(screen.getByLabelText(/^username$/i), 'backup')
    await user.clear(screen.getByLabelText(/^port$/i))
    await user.type(screen.getByLabelText(/^port$/i), '44')
    await user.click(screen.getByRole('button', { name: /test & add connection/i }))

    await waitFor(() => {
      expect(sshKeysAPI.testSSHConnection).toHaveBeenCalledWith(7, {
        host: 'manual.example.com',
        username: 'backup',
        port: 44,
      })
    })
  })

  it('localizes the remote connections empty state', async () => {
    await i18n.changeLanguage('de')
    mockState.systemKeyResponse = { data: { exists: false } }
    mockState.connectionsResponse = { data: { connections: [] } }

    renderWithProviders(<SSHConnectionsSingleKey />)

    expect(await screen.findByText('Remote-Maschinen')).toBeInTheDocument()
    expect(screen.getByText('Remote-Verbindungen')).toBeInTheDocument()
    expect(screen.getByText('Noch keine Remote-Maschinen')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Erzeuge oder importiere zuerst einen SSH-Schlüssel und stelle ihn dann auf Remote-Servern bereit.'
      )
    ).toBeInTheDocument()
  })

  it('updates an existing connection and automatically retests it', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('backup-host')
    await user.click(screen.getByRole('button', { name: /edit backup-host/i }))
    const hostInputs = screen.getAllByLabelText(/^host$/i)
    await user.clear(hostInputs[0])
    await user.type(hostInputs[0], 'updated-host')
    const mountInputs = screen.getAllByLabelText(/mount point/i)
    await user.clear(mountInputs[0])
    await user.type(mountInputs[0], 'branch-office')
    await user.click(screen.getByRole('button', { name: /update connection/i }))

    await waitFor(() => {
      expect(sshKeysAPI.updateSSHConnection).toHaveBeenCalledWith(3, {
        host: 'updated-host',
        username: 'borg',
        port: 2222,
        use_sftp_mode: true,
        use_sudo: false,
        default_path: '/srv',
        ssh_path_prefix: '/prefix',
        mount_point: 'branch-office',
      })
    })
    await waitFor(() => {
      expect(sshKeysAPI.testExistingConnection).toHaveBeenCalledWith(3)
    })
  })
})
