import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, screen, waitFor } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import ManagedAgents, {
  AgentList,
  AgentSetupGuide,
  AgentSetupHelpContent,
  JobsTable,
  TokensTable,
} from '../ManagedAgents'
import { renderWithProviders, userEvent } from '../../test/test-utils'
import {
  AgentJobResponse,
  AgentMachineResponse,
  managedAgentsAPI,
  settingsAPI,
} from '../../services/api'
import type { AxiosResponse } from 'axios'

vi.mock('../../services/api', () => ({
  settingsAPI: {
    getSystemSettings: vi.fn(),
  },
  managedAgentsAPI: {
    listAgents: vi.fn(),
    listEnrollmentTokens: vi.fn(),
    listJobs: vi.fn(),
    listJobLogs: vi.fn(),
    createEnrollmentToken: vi.fn(),
    revokeEnrollmentToken: vi.fn(),
    revokeAgent: vi.fn(),
    createBackupJob: vi.fn(),
    cancelJob: vi.fn(),
  },
}))

vi.mock('../../hooks/useAuth', () => ({
  useAuth: () => ({
    hasGlobalPermission: (permission: string) => permission === 'settings.ssh.manage',
  }),
}))

vi.mock('react-hot-toast', async () => {
  const actual = await vi.importActual('react-hot-toast')
  return {
    ...actual,
    toast: {
      success: vi.fn(),
      error: vi.fn(),
    },
  }
})

describe('ManagedAgents', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(settingsAPI.getSystemSettings).mockResolvedValue({
      data: { settings: { managed_agents_beta_enabled: true } },
    } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listEnrollmentTokens).mockResolvedValue({
      data: [],
    } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listJobs).mockResolvedValue({ data: [] } as AxiosResponse)
  })

  it('shows concrete remote setup instructions before any agents are enrolled', async () => {
    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    expect(await screen.findByText('Set up an agent on a remote machine')).toBeInTheDocument()
    expect(
      screen.getByText(
        'Create an enrollment token above, install the agent on the client, then register it with this Borg UI server.'
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText(/borg-ui-agent register --server .* --token <enrollment-token>/)
    ).toBeInTheDocument()
  })

  it('opens from the shared system settings cache without redirecting to dashboard', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(['systemSettings'], {
      settings: { managed_agents_beta_enabled: true },
    })

    renderWithProviders(<ManagedAgents />, {
      initialRoute: '/managed-agents',
      queryClient,
    })

    expect(await screen.findByText('Managed Agents')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/managed-agents')
    expect(managedAgentsAPI.listAgents).toHaveBeenCalled()
  })

  it('keeps setup help detailed without duplicating token creation inside the guide', async () => {
    const user = userEvent.setup()
    const onCopy = vi.fn()
    renderWithProviders(
      <AgentSetupGuide
        command="borg-ui-agent register --server http://localhost:7879 --token <enrollment-token> --name <machine-name>"
        onCopy={onCopy}
      />
    )

    expect(
      screen.queryByRole('button', { name: /create enrollment token/i })
    ).not.toBeInTheDocument()
    expect(screen.getByLabelText('Copy setup command')).toBeInTheDocument()
    expect(screen.getByText(/Clone Borg UI on the client machine/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy setup command'))
    expect(onCopy).toHaveBeenCalledWith(
      'borg-ui-agent register --server http://localhost:7879 --token <enrollment-token> --name <machine-name>'
    )

    await user.click(screen.getByRole('button', { name: /setup help/i }))

    expect(screen.getByText(/localhost:7879 is only correct when the agent/i)).toBeInTheDocument()
    expect(screen.getByText(/Use systemd on Linux or launchd on macOS/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy install commands'))
    await user.click(screen.getAllByLabelText('Copy setup command')[1])
    await user.click(screen.getByLabelText('Copy run command'))
    await user.click(screen.getByLabelText('Copy systemd commands'))

    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('git clone'))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('borg-ui-agent run'))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('systemctl enable --now'))
  })

  it('renders setup help details as a standalone story surface', async () => {
    const user = userEvent.setup()
    const onCopy = vi.fn()

    renderWithProviders(
      <AgentSetupHelpContent
        command="borg-ui-agent register --server http://localhost:7879 --token <enrollment-token> --name <machine-name>"
        onCopy={onCopy}
      />
    )

    expect(screen.getByText(/Run this on the machine that owns the files/i)).toBeInTheDocument()
    expect(screen.getByText(/localhost:7879 is only correct when the agent/i)).toBeInTheDocument()
    expect(screen.getByText(/Use systemd on Linux or launchd on macOS/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy install commands'))

    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('git clone'))
  })

  it('creates enrollment tokens from the top-level dialog', async () => {
    const user = userEvent.setup()
    vi.mocked(managedAgentsAPI.createEnrollmentToken).mockResolvedValue({
      data: { token: 'agent-token-secret' },
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await user.click(await screen.findByRole('button', { name: /create enrollment token/i }))
    const dialog = await screen.findByRole('dialog', { name: /create enrollment token/i })
    await user.clear(screen.getByLabelText('Name'))
    await user.type(screen.getByLabelText('Name'), 'Client laptop')
    await user.clear(screen.getByLabelText('Expires In Minutes'))
    await user.type(screen.getByLabelText('Expires In Minutes'), '120')
    await user.click(screen.getByRole('button', { name: /^Create$/ }))

    expect(vi.mocked(managedAgentsAPI.createEnrollmentToken).mock.calls[0][0]).toEqual({
      name: 'Client laptop',
      expires_in_minutes: 120,
    })
    expect(await screen.findByText('agent-token-secret')).toBeInTheDocument()
    expect(dialog).toHaveTextContent(
      /borg-ui-agent register --server http:\/\/localhost:\d+ --token agent-token-secret --name <machine-name>/
    )
  })

  it('queues a backup job with trimmed paths, flags, and secrets', async () => {
    const user = userEvent.setup()
    const agent = {
      id: 42,
      agent_id: 'agent-client-42',
      name: 'client',
      hostname: 'client-02',
      status: 'online',
      borg_versions: [{ path: '/usr/bin/borg', version: 'borg 1.4.4' }],
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [agent] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.createBackupJob).mockResolvedValue({ data: {} } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    expect(await screen.findByText('client-02')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Backup' }))

    expect(await screen.findByRole('dialog', { name: /queue agent backup/i })).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Repository Path'), {
      target: { value: '  /srv/borg/repo  ' },
    })
    fireEvent.change(screen.getByLabelText('Source Paths'), {
      target: { value: ' /home/alice \n\n /etc ' },
    })
    fireEvent.change(screen.getByLabelText('Exclude Patterns'), {
      target: { value: ' *.tmp \n cache ' },
    })
    fireEvent.change(screen.getByLabelText('Custom Flags'), {
      target: { value: ' --stats \n --one-file-system ' },
    })
    fireEvent.change(screen.getByLabelText('Remote Borg Path'), {
      target: { value: ' /usr/local/bin/borg ' },
    })
    fireEvent.change(screen.getByLabelText('Repository Passphrase'), {
      target: { value: ' secret-pass ' },
    })

    await user.click(screen.getByRole('button', { name: /queue backup/i }))

    await waitFor(() => {
      expect(managedAgentsAPI.createBackupJob).toHaveBeenCalledWith(42, {
        repository_path: '/srv/borg/repo',
        archive_name: 'client-{now}',
        source_paths: ['/home/alice', '/etc'],
        borg_version: 1,
        compression: 'lz4',
        exclude_patterns: ['*.tmp', 'cache'],
        custom_flags: ['--stats', '--one-file-system'],
        remote_path: '/usr/local/bin/borg',
        secrets: {
          BORG_PASSPHRASE: { value: 'secret-pass' },
        },
      })
    })
  })

  it('renders populated agent cards and wires agent actions', async () => {
    const user = userEvent.setup()
    const onQueueBackup = vi.fn()
    const onRevoke = vi.fn()
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'online',
      os: 'linux',
      arch: 'arm64',
      agent_version: '0.4.0',
      last_seen_at: '2026-05-18T10:00:00.000Z',
      last_error: 'Last run failed',
      borg_versions: [{ path: '/usr/bin/borg', version: 'borg 1.4.4' }],
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse

    renderWithProviders(
      <AgentList
        agents={[agent]}
        onQueueBackup={onQueueBackup}
        onRevoke={onRevoke}
        isRevoking={false}
      />
    )

    expect(screen.getByText('client-01')).toBeInTheDocument()
    expect(screen.getByText('agent-client-7')).toBeInTheDocument()
    expect(screen.getByText('linux / arm64')).toBeInTheDocument()
    expect(screen.getByText('borg 1.4.4')).toBeInTheDocument()
    expect(screen.getByText('Last run failed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: 'Backup' }))
    expect(onQueueBackup).toHaveBeenCalledWith(agent)

    const buttons = screen.getAllByRole('button')
    await user.click(buttons[1])
    expect(onRevoke).toHaveBeenCalledWith(agent)
  })

  it('renders job rows with progress and action availability', async () => {
    const user = userEvent.setup()
    const onCancel = vi.fn()
    const onViewLogs = vi.fn()
    const agent = {
      id: 3,
      agent_id: 'agent-3',
      name: 'agent-name',
      hostname: 'agent-host',
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    const runningJob = {
      id: 10,
      agent_machine_id: 3,
      job_type: 'backup',
      status: 'running',
      progress_percent: 42.2,
      created_at: '2026-05-18T10:25:00.000Z',
      updated_at: '2026-05-18T10:30:00.000Z',
      payload: { job_kind: 'manual-backup' },
    } as AgentJobResponse
    const completedJob = {
      id: 11,
      agent_machine_id: 99,
      job_type: 'restore',
      status: 'completed',
      progress_percent: 100,
      created_at: '2026-05-18T10:20:00.000Z',
      updated_at: '2026-05-18T10:25:00.000Z',
      payload: {},
    } as AgentJobResponse

    renderWithProviders(
      <JobsTable
        jobs={[runningJob, completedJob]}
        agentsById={new Map([[agent.id, agent]])}
        onCancel={onCancel}
        onViewLogs={onViewLogs}
        isCanceling={false}
      />
    )

    expect(screen.getByText('#10')).toBeInTheDocument()
    expect(screen.getByText('manual-backup')).toBeInTheDocument()
    expect(screen.getByText('agent-host')).toBeInTheDocument()
    expect(screen.getByText('42%')).toBeInTheDocument()
    expect(screen.getByText('#11')).toBeInTheDocument()
    expect(screen.getByText('Unknown agent')).toBeInTheDocument()

    const buttons = screen.getAllByRole('button')
    await user.click(buttons[0])
    await user.click(buttons[1])
    expect(onViewLogs).toHaveBeenCalledWith(runningJob)
    expect(onCancel).toHaveBeenCalledWith(runningJob)
    expect(buttons[3]).toBeDisabled()
  })

  it('renders token statuses and only revokes active tokens', async () => {
    const user = userEvent.setup()
    const onRevoke = vi.fn()

    renderWithProviders(
      <TokensTable
        tokens={[
          {
            id: 1,
            name: 'Fresh token',
            token_prefix: 'borg_enroll_fresh',
            expires_at: '2026-05-18T11:30:00.000Z',
          },
          {
            id: 2,
            name: 'Used token',
            token_prefix: 'borg_enroll_used',
            expires_at: '2026-05-18T11:30:00.000Z',
            used_at: '2026-05-18T10:30:00.000Z',
          },
          {
            id: 3,
            name: 'Revoked token',
            token_prefix: 'borg_enroll_revoked',
            expires_at: '2026-05-18T11:30:00.000Z',
            revoked_at: '2026-05-18T10:35:00.000Z',
          },
        ]}
        onRevoke={onRevoke}
        isRevoking={false}
      />
    )

    expect(screen.getByText('Fresh token')).toBeInTheDocument()
    expect(screen.getByText('active')).toBeInTheDocument()
    expect(screen.getByText('used')).toBeInTheDocument()
    expect(screen.getByText('revoked')).toBeInTheDocument()

    const buttons = screen.getAllByRole('button')
    await user.click(buttons[0])
    expect(onRevoke).toHaveBeenCalledWith(1)
    expect(buttons[1]).toBeDisabled()
    expect(buttons[2]).toBeDisabled()
  })
})
