import { useState } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, waitFor as rtlWaitFor, within } from '@testing-library/react'
import i18n from '../../i18n'
import { renderWithProviders, screen, userEvent, waitFor } from '../../test/test-utils'
import SSHConnectionsSingleKey from '../SSHConnectionsSingleKey'
import { remoteMachineSetupPresets } from '../ssh-connections-single-key/connectionPresets'
import { createConnectionForm } from '../ssh-connections-single-key/formDefaults'
import { ConnectionDiagnosticsDialog } from '../ssh-connections-single-key/dialogs/ConnectionDiagnosticsDialog'
import { DeployKeyDialog } from '../ssh-connections-single-key/dialogs/DeployKeyDialog'
import type { DeployConnectionPayload } from '../ssh-connections-single-key/types'

const remoteMachineSetupPresetBrandColors = {
  custom: '#64748B',
  linux: '#FCC624',
  borgbase: '#00DD00',
  hetzner: '#D50C2D',
  nas: '#B5B5B6',
} as const

function DeployDialogHarness({
  initialForm,
  onDeploy,
}: {
  initialForm: DeployConnectionPayload
  onDeploy?: (form: DeployConnectionPayload) => void
}) {
  const [open, setOpen] = useState(true)
  const [connectionForm, setConnectionForm] = useState(initialForm)
  const [hostError, setHostError] = useState<string>()

  return (
    <DeployKeyDialog
      t={i18n.t.bind(i18n)}
      open={open}
      setOpen={setOpen}
      connectionForm={connectionForm}
      setConnectionForm={setConnectionForm}
      hostError={hostError}
      setHostError={setHostError}
      pending={false}
      onDeploy={() => onDeploy?.(connectionForm)}
    />
  )
}

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
    onRunDiagnostics,
  }: {
    machine: { host: string }
    onEdit: (machine: { host: string }) => void
    onDelete: (machine: { host: string }) => void
    onTestConnection: (machine: { host: string }) => void
    onDeployKey: (machine: { host: string }) => void
    onRunDiagnostics?: (machine: { host: string }) => void
  }) => (
    <div>
      <span>{machine.host}</span>
      <button onClick={() => onEdit(machine)}>edit {machine.host}</button>
      <button onClick={() => onDelete(machine)}>delete {machine.host}</button>
      <button onClick={() => onTestConnection(machine)}>test {machine.host}</button>
      <button onClick={() => onDeployKey(machine)}>deploy {machine.host}</button>
      <button onClick={() => onRunDiagnostics?.(machine)}>run diagnostics {machine.host}</button>
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
    runConnectionDiagnostics: vi.fn(() =>
      Promise.resolve({
        data: {
          connection: {
            id: 3,
            host: 'backup-host',
            username: 'borg',
            port: 2222,
            status: 'connected',
            last_test: null,
            last_success: null,
            error_message: null,
          },
          session: { status: 'success', elapsed_ms: 12, output: '/srv' },
          latency: { status: 'success', elapsed_ms: 12 },
          tcp: null,
          throughput: {
            status: 'success',
            direction: 'download',
            probe_size_bytes: 262144,
            bytes_transferred: 262144,
            elapsed_ms: 31,
            mbps: 8.06,
          },
        },
      })
    ),
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

  it('does not show the remote machines summary stats band', async () => {
    renderWithProviders(<SSHConnectionsSingleKey />)

    expect(await screen.findByText('Remote Machines')).toBeInTheDocument()
    expect(screen.queryByText('Total Connections')).not.toBeInTheDocument()
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
  }, 30000)

  it('deploys the system key with the expected connection payload', async () => {
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    fireEvent.click(
      screen.getByRole('button', {
        name: /automatically deploy ssh key using password authentication/i,
      })
    )
    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })
    fireEvent.change(within(dialog).getByLabelText(/^host$/i), {
      target: { value: 'nas.local' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^username$/i), {
      target: { value: 'root' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^port$/i), {
      target: { value: '2200' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^password$/i), {
      target: { value: 'secret' },
    })
    fireEvent.change(within(dialog).getByLabelText(/default path/i), {
      target: { value: '/backups' },
    })
    fireEvent.change(within(dialog).getByLabelText(/mount point/i), {
      target: { value: 'nas' },
    })
    const deployButton = within(dialog).getByRole('button', { name: /^deploy key$/i })
    await rtlWaitFor(() => expect(deployButton).not.toBeDisabled())
    fireEvent.click(deployButton)

    await rtlWaitFor(() => expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledTimes(1))
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
  }, 30000)

  it('renders and deploys the Hetzner Storage Box preset with provider-specific defaults', async () => {
    const onDeploy = vi.fn()
    renderWithProviders(
      <DeployDialogHarness
        initialForm={{
          ...createConnectionForm(),
          port: 23,
          use_sftp_mode: true,
          default_path: '/home',
          ssh_path_prefix: '',
          mount_point: 'hetzner-storage-box',
        }}
        onDeploy={onDeploy}
      />
    )
    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })

    expect(within(dialog).getByRole('combobox', { name: /setup preset/i })).toHaveTextContent(
      /hetzner storage box/i
    )
    expect(within(dialog).getByRole('textbox', { name: /^host$/i })).toHaveAttribute(
      'placeholder',
      'u123456.your-storagebox.de'
    )
    expect(within(dialog).getByRole('textbox', { name: /^username$/i })).toHaveAttribute(
      'placeholder',
      'u123456'
    )
    expect(within(dialog).getByLabelText(/^port$/i)).toHaveValue(23)
    expect(within(dialog).getByRole('checkbox', { name: /use sftp mode/i })).toBeChecked()
    expect(within(dialog).getByRole('textbox', { name: /^default path/i })).toHaveValue('/home')
    expect(within(dialog).getByLabelText(/mount point/i)).toHaveValue('hetzner-storage-box')

    fireEvent.change(within(dialog).getByRole('textbox', { name: /^host$/i }), {
      target: { value: 'u123456.your-storagebox.de' },
    })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /^username$/i }), {
      target: { value: 'u123456' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^password$/i), {
      target: { value: 'secret' },
    })

    const deployButton = within(dialog).getByRole('button', { name: /^deploy key$/i })
    await rtlWaitFor(() => expect(deployButton).not.toBeDisabled())
    fireEvent.click(deployButton)

    await rtlWaitFor(() => expect(onDeploy).toHaveBeenCalledTimes(1))
    expect(onDeploy).toHaveBeenCalledWith({
      host: 'u123456.your-storagebox.de',
      username: 'u123456',
      port: 23,
      password: 'secret',
      use_sftp_mode: true,
      default_path: '/home',
      ssh_path_prefix: '',
      mount_point: 'hetzner-storage-box',
    })
  }, 30000)

  it('keeps manual edits when starting from the NAS preset defaults', async () => {
    const onDeploy = vi.fn()
    renderWithProviders(
      <DeployDialogHarness
        initialForm={{
          ...createConnectionForm(),
          port: 22,
          use_sftp_mode: false,
          default_path: '/backups',
          ssh_path_prefix: '/volume1',
          mount_point: 'nas',
        }}
        onDeploy={onDeploy}
      />
    )
    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })

    expect(within(dialog).getByRole('combobox', { name: /setup preset/i })).toHaveTextContent(
      /^nas/i
    )
    expect(within(dialog).getByRole('textbox', { name: /^host$/i })).toHaveAttribute(
      'placeholder',
      'diskstation.local'
    )
    fireEvent.change(within(dialog).getByRole('textbox', { name: /^default path/i }), {
      target: { value: '/backups/repo' },
    })
    expect(within(dialog).getByRole('textbox', { name: /^default path/i })).toHaveValue(
      '/backups/repo'
    )
    expect(within(dialog).getByRole('textbox', { name: /^ssh path prefix/i })).toHaveValue(
      '/volume1'
    )
    expect(within(dialog).getByRole('textbox', { name: /^mount point/i })).toHaveValue('nas')

    fireEvent.change(within(dialog).getByRole('textbox', { name: /^host$/i }), {
      target: { value: 'diskstation.local' },
    })
    fireEvent.change(within(dialog).getByRole('textbox', { name: /^username$/i }), {
      target: { value: 'backup' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^password$/i), {
      target: { value: 'secret' },
    })

    const deployButton = within(dialog).getByRole('button', { name: /^deploy key$/i })
    await rtlWaitFor(() => expect(deployButton).not.toBeDisabled())
    fireEvent.click(deployButton)

    await rtlWaitFor(() => expect(onDeploy).toHaveBeenCalledTimes(1))
    expect(onDeploy).toHaveBeenCalledWith({
      host: 'diskstation.local',
      username: 'backup',
      port: 22,
      password: 'secret',
      use_sftp_mode: false,
      default_path: '/backups/repo',
      ssh_path_prefix: '/volume1',
      mount_point: 'nas',
    })
  }, 30000)

  it('renders Custom setup with standard deploy defaults', async () => {
    renderWithProviders(<DeployDialogHarness initialForm={createConnectionForm()} />)

    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })

    expect(within(dialog).getByRole('combobox', { name: /setup preset/i })).toHaveTextContent(
      /custom setup/i
    )
    expect(within(dialog).getByLabelText(/^port$/i)).toHaveValue(22)
    expect(within(dialog).getByRole('checkbox', { name: /use sftp mode/i })).toBeChecked()
    expect(within(dialog).getByRole('textbox', { name: /^default path/i })).toHaveValue('')
    expect(within(dialog).getByLabelText(/mount point/i)).toHaveValue('')
  }, 30000)

  it('selects the matching setup preset for corrected Hetzner and reset defaults', async () => {
    const { unmount } = renderWithProviders(
      <DeployDialogHarness
        initialForm={{
          ...createConnectionForm(),
          port: 23,
          use_sftp_mode: true,
          default_path: '/home',
          ssh_path_prefix: '',
          mount_point: 'hetzner-storage-box',
        }}
      />
    )

    const hetznerDialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })
    expect(
      within(hetznerDialog).getByRole('combobox', { name: /setup preset/i })
    ).toHaveTextContent(/hetzner storage box/i)

    unmount()
    renderWithProviders(<DeployDialogHarness initialForm={createConnectionForm()} />)

    const customDialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })
    expect(within(customDialog).getByRole('combobox', { name: /setup preset/i })).toHaveTextContent(
      /custom setup/i
    )
    expect(within(customDialog).getByLabelText(/^port$/i)).toHaveValue(22)
  }, 30000)

  it('renders deploy preset icons with their configured colors', async () => {
    const selectedPreset = remoteMachineSetupPresets.find((preset) => preset.id === 'hetzner')
    expect(selectedPreset).toBeDefined()

    renderWithProviders(
      <DeployDialogHarness
        initialForm={{
          ...createConnectionForm(),
          port: 23,
          use_sftp_mode: true,
          default_path: '/home',
          ssh_path_prefix: '',
          mount_point: 'hetzner-storage-box',
        }}
      />
    )

    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })
    const selectedIcon = within(dialog).getByTestId('remote-machine-preset-icon-hetzner')
    expect(selectedIcon).toHaveStyle({
      color: remoteMachineSetupPresetBrandColors.hetzner,
    })

    fireEvent.mouseDown(within(dialog).getByRole('combobox', { name: /setup preset/i }))
    const listbox = await screen.findByRole('listbox')

    remoteMachineSetupPresets.forEach((preset) => {
      expect(within(listbox).getByTestId(`remote-machine-preset-icon-${preset.id}`)).toHaveStyle({
        color: remoteMachineSetupPresetBrandColors[preset.id],
      })
    })
  }, 30000)

  it('renders the deploy preset dialog at a compact desktop width', async () => {
    renderWithProviders(<DeployDialogHarness initialForm={createConnectionForm()} />)

    const dialog = await screen.findByRole('dialog', { name: /deploy ssh key to server/i })

    expect(dialog).toHaveClass('MuiDialog-paperWidthSm')
  })

  it('tests and adds a manual connection with the expected payload', async () => {
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('Remote Machines')
    fireEvent.click(
      screen.getByRole('button', {
        name: /add a connection for a manually deployed ssh key/i,
      })
    )
    const dialog = await screen.findByRole('dialog', { name: /add manual connection/i })
    fireEvent.change(within(dialog).getByLabelText(/^host$/i), {
      target: { value: 'manual.example.com' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^username$/i), {
      target: { value: 'backup' },
    })
    fireEvent.change(within(dialog).getByLabelText(/^port$/i), {
      target: { value: '44' },
    })
    fireEvent.click(within(dialog).getByRole('button', { name: /test & add connection/i }))

    await waitFor(() => {
      expect(sshKeysAPI.testSSHConnection).toHaveBeenCalledWith(7, {
        host: 'manual.example.com',
        username: 'backup',
        port: 44,
      })
    })
  })

  it('opens remote machine diagnostics from a connection card and runs a session check', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('backup-host')
    await user.click(screen.getByRole('button', { name: /run diagnostics backup-host/i }))
    const dialog = await screen.findByRole('dialog', { name: /remote machine diagnostics/i })

    await user.click(within(dialog).getByRole('button', { name: /run check/i }))

    await waitFor(() => {
      expect(sshKeysAPI.runConnectionDiagnostics).toHaveBeenCalledWith(3, {
        timeout_seconds: 5,
        speed_probe_bytes: 262144,
      })
    })
    expect(await within(dialog).findByText(/SSH session healthy/i)).toBeInTheDocument()
    expect(within(dialog).getAllByText(/12 ms/i)).toHaveLength(2)
    expect(within(dialog).getByText(/8.06 MB\/s/i)).toBeInTheDocument()
  }, 30000)

  it('validates remote diagnostics target inputs before running', async () => {
    const user = userEvent.setup()
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('backup-host')
    await user.click(screen.getByRole('button', { name: /run diagnostics backup-host/i }))
    const dialog = await screen.findByRole('dialog', { name: /remote machine diagnostics/i })

    expect(within(dialog).queryByLabelText(/service host/i)).not.toBeInTheDocument()

    await user.click(
      within(dialog).getByRole('button', { name: /advanced: test another service/i })
    )
    await user.type(within(dialog).getByLabelText(/service host/i), 'postgres.internal')

    expect(within(dialog).getByText(/Enter a TCP port between 1 and 65535/i)).toBeInTheDocument()
    expect(within(dialog).getByRole('button', { name: /run check/i })).toBeDisabled()
    expect(sshKeysAPI.runConnectionDiagnostics).not.toHaveBeenCalled()
  }, 30000)

  it('renders remote diagnostics partial TCP failure details', () => {
    renderWithProviders(
      <ConnectionDiagnosticsDialog
        open
        connection={{
          id: 3,
          ssh_key_id: 7,
          ssh_key_name: 'System SSH Key',
          host: 'backup-host',
          username: 'borg',
          port: 2222,
          use_sftp_mode: true,
          use_sudo: false,
          status: 'connected',
          created_at: '2026-01-01T00:00:00Z',
        }}
        initialResult={{
          connection: {
            id: 3,
            host: 'backup-host',
            username: 'borg',
            port: 2222,
            status: 'connected',
            last_test: null,
            last_success: null,
            error_message: null,
          },
          session: { status: 'success', elapsed_ms: 10, output: '/srv' },
          latency: { status: 'success', elapsed_ms: 10 },
          tcp: {
            target: { host: 'postgres.internal', port: 5432, timeout_seconds: 3 },
            status: 'failed',
            elapsed_ms: 4,
            error: 'connection_refused',
            message: 'Connection refused',
          },
          throughput: {
            status: 'success',
            direction: 'download',
            probe_size_bytes: 262144,
            bytes_transferred: 262144,
            elapsed_ms: 64,
            mbps: 3.91,
          },
        }}
        onClose={vi.fn()}
        onRunDiagnostics={vi.fn()}
      />
    )

    expect(screen.getByText(/SSH session healthy/i)).toBeInTheDocument()
    expect(screen.getByText(/TCP failed/i)).toBeInTheDocument()
    expect(screen.getByText(/postgres.internal:5432/i)).toBeInTheDocument()
    expect(screen.getByText(/connection_refused/i)).toBeInTheDocument()
    expect(screen.getByText(/Connection refused/i)).toBeInTheDocument()
    expect(screen.getByText(/3.91 MB\/s/i)).toBeInTheDocument()
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
    const { sshKeysAPI } = await import('../../services/api')

    renderWithProviders(<SSHConnectionsSingleKey />)

    await screen.findByText('backup-host')
    fireEvent.click(screen.getByRole('button', { name: /edit backup-host/i }))
    const dialog = await screen.findByRole('dialog', { name: /edit ssh connection/i })
    const hostInput = within(dialog).getByLabelText(/^host$/i)
    fireEvent.change(hostInput, {
      target: { value: 'updated-host' },
    })
    await rtlWaitFor(() => expect(hostInput).toHaveValue('updated-host'))
    const mountInput = within(dialog).getByLabelText(/mount point/i)
    fireEvent.change(mountInput, {
      target: { value: 'branch-office' },
    })
    await rtlWaitFor(() => expect(mountInput).toHaveValue('branch-office'))
    const updateButton = within(dialog).getByRole('button', { name: /update connection/i })
    await rtlWaitFor(() => expect(updateButton).not.toBeDisabled())
    fireEvent.click(updateButton)

    await rtlWaitFor(() => expect(sshKeysAPI.updateSSHConnection).toHaveBeenCalledTimes(1))
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
    await rtlWaitFor(() => expect(sshKeysAPI.testExistingConnection).toHaveBeenCalledWith(3))
  }, 30000)
})
