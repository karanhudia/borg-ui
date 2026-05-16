import type { Dispatch, SetStateAction } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import i18n from '../../i18n'
import { fireEvent, renderWithProviders, screen, waitFor } from '../../test/test-utils'
import type {
  DeployConnectionPayload,
  SSHConnection,
  TestConnectionPayload,
  UpdateConnectionPayload,
} from '../ssh-connections-single-key/types'
import SSHConnectionsSingleKey from '../SSHConnectionsSingleKey'

interface MockViewProps {
  connections: SSHConnection[]
  connectionForm: DeployConnectionPayload
  setConnectionForm: Dispatch<SetStateAction<DeployConnectionPayload>>
  connectionHostError?: string
  testConnectionForm: TestConnectionPayload
  setTestConnectionForm: Dispatch<SetStateAction<TestConnectionPayload>>
  testConnectionHostError?: string
  editConnectionForm: UpdateConnectionPayload
  setEditConnectionForm: Dispatch<SetStateAction<UpdateConnectionPayload>>
  editConnectionHostError?: string
  handleDeployKey: () => void
  handleTestManualConnection: () => void
  handleEditConnection: (connection: SSHConnection) => void
  handleUpdateConnection: () => void
}

const { mockState } = vi.hoisted(() => ({
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
    },
    connectionsResponse: {
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
    track: vi.fn(),
    EventCategory: { SSH: 'ssh' },
    EventAction: {
      CREATE: 'create',
      EDIT: 'edit',
      TEST: 'test',
      VIEW: 'view',
    },
  }),
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

vi.mock('../../services/api', () => ({
  sshKeysAPI: {
    getSystemKey: vi.fn(() => Promise.resolve(mockState.systemKeyResponse)),
    getSSHConnections: vi.fn(() => Promise.resolve(mockState.connectionsResponse)),
    deploySSHKey: vi.fn(() => Promise.resolve({ data: {} })),
    testSSHConnection: vi.fn(() => Promise.resolve({ data: { success: true } })),
    updateSSHConnection: vi.fn(() => Promise.resolve({ data: {} })),
    testExistingConnection: vi.fn(() => Promise.resolve({ data: { success: true } })),
    refreshConnectionStorage: vi.fn(() => Promise.resolve({ data: {} })),
  },
}))

vi.mock('../ssh-connections-single-key/SSHConnectionsSingleKeyView', () => ({
  SSHConnectionsSingleKeyView: (props: MockViewProps) => (
    <div>
      <label>
        Deploy host
        <input
          value={props.connectionForm.host}
          onChange={(event) =>
            props.setConnectionForm((form) => ({
              ...form,
              host: event.target.value,
            }))
          }
        />
      </label>
      <label>
        Deploy username
        <input
          value={props.connectionForm.username}
          onChange={(event) =>
            props.setConnectionForm((form) => ({
              ...form,
              username: event.target.value,
            }))
          }
        />
      </label>
      <label>
        Deploy password
        <input
          value={props.connectionForm.password}
          onChange={(event) =>
            props.setConnectionForm((form) => ({
              ...form,
              password: event.target.value,
            }))
          }
        />
      </label>
      {props.connectionHostError && <p>{props.connectionHostError}</p>}
      <button onClick={props.handleDeployKey}>deploy</button>

      <label>
        Manual host
        <input
          value={props.testConnectionForm.host}
          onChange={(event) =>
            props.setTestConnectionForm((form) => ({
              ...form,
              host: event.target.value,
            }))
          }
        />
      </label>
      <label>
        Manual username
        <input
          value={props.testConnectionForm.username}
          onChange={(event) =>
            props.setTestConnectionForm((form) => ({
              ...form,
              username: event.target.value,
            }))
          }
        />
      </label>
      {props.testConnectionHostError && <p>{props.testConnectionHostError}</p>}
      <button onClick={props.handleTestManualConnection}>manual test</button>

      <button onClick={() => props.handleEditConnection(props.connections[0])}>open edit</button>
      <label>
        Edit host
        <input
          value={props.editConnectionForm.host}
          onChange={(event) =>
            props.setEditConnectionForm((form) => ({
              ...form,
              host: event.target.value,
            }))
          }
        />
      </label>
      {props.editConnectionHostError && <p>{props.editConnectionHostError}</p>}
      <button onClick={props.handleUpdateConnection}>update</button>
    </div>
  ),
}))

describe('SSHConnectionsSingleKey host validation', () => {
  beforeEach(async () => {
    await i18n.changeLanguage('en')
    vi.clearAllMocks()
    mockState.canManageSsh = true
  })

  it('submits trimmed hosts for deploy, manual test, and edit flows', async () => {
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    fireEvent.change(await screen.findByLabelText(/deploy host/i), {
      target: { value: '  u123456.your-storagebox.de  ' },
    })
    fireEvent.change(screen.getByLabelText(/deploy username/i), {
      target: { value: 'root' },
    })
    fireEvent.change(screen.getByLabelText(/deploy password/i), {
      target: { value: 'secret' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'deploy' }))

    await waitFor(() => {
      expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ host: 'u123456.your-storagebox.de' })
      )
    })

    fireEvent.change(screen.getByLabelText(/manual host/i), {
      target: { value: '  manual.example.com  ' },
    })
    fireEvent.change(screen.getByLabelText(/manual username/i), {
      target: { value: 'backup' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'manual test' }))

    await waitFor(() => {
      expect(sshKeysAPI.testSSHConnection).toHaveBeenCalledWith(
        7,
        expect.objectContaining({ host: 'manual.example.com' })
      )
    })

    fireEvent.click(screen.getByRole('button', { name: 'open edit' }))
    fireEvent.change(screen.getByLabelText(/edit host/i), {
      target: { value: '  edited.example.com  ' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'update' }))

    await waitFor(() => {
      expect(sshKeysAPI.updateSSHConnection).toHaveBeenCalledWith(
        3,
        expect.objectContaining({ host: 'edited.example.com' })
      )
    })
  })

  it('blocks malformed hosts before submit and surfaces validation feedback', async () => {
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    fireEvent.change(await screen.findByLabelText(/deploy host/i), {
      target: { value: 'http://host' },
    })
    fireEvent.change(screen.getByLabelText(/deploy username/i), {
      target: { value: 'root' },
    })
    fireEvent.change(screen.getByLabelText(/deploy password/i), {
      target: { value: 'secret' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'deploy' }))

    expect(await screen.findByText(/bare DNS name or IP address/i)).toBeInTheDocument()
    expect(sshKeysAPI.deploySSHKey).not.toHaveBeenCalled()

    fireEvent.change(screen.getByLabelText(/manual host/i), {
      target: { value: 'host:23' },
    })
    fireEvent.change(screen.getByLabelText(/manual username/i), {
      target: { value: 'backup' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'manual test' }))

    expect(screen.getAllByText(/bare DNS name or IP address/i)).toHaveLength(2)
    expect(sshKeysAPI.testSSHConnection).not.toHaveBeenCalled()

    fireEvent.click(screen.getByRole('button', { name: 'open edit' }))
    fireEvent.change(screen.getByLabelText(/edit host/i), {
      target: { value: '[host](https://host)' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'update' }))

    expect(screen.getAllByText(/bare DNS name or IP address/i)).toHaveLength(3)
    expect(sshKeysAPI.updateSSHConnection).not.toHaveBeenCalled()
  })
})
