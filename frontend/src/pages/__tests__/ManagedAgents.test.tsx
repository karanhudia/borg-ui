import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen, within } from '@testing-library/react'
import { QueryClient } from '@tanstack/react-query'
import ManagedAgents, {
  AgentList,
  AgentSetupGuide,
  AgentSetupHelpContent,
  JobsTable,
  TokensTable,
} from '../ManagedAgents'
import AgentInstallCommand from '../managed-agents/AgentInstallCommand'
import { buildAgentInstallCommand } from '../managed-agents/agentInstallCommandText'
import { isLocalAgentServerUrl, resolveAgentServerUrl } from '../managed-agents/agentServerUrl'
import { renderWithProviders, userEvent } from '../../test/test-utils'
import { AgentJobResponse, AgentMachineResponse, managedAgentsAPI } from '../../services/api'
import type { AxiosResponse } from 'axios'
import { buildAgentReinstallCommand } from '../managed-agents/agentInstallCommandText'

vi.mock('../../services/api', () => ({
  managedAgentsAPI: {
    listAgents: vi.fn(),
    listEnrollmentTokens: vi.fn(),
    listJobs: vi.fn(),
    listJobLogs: vi.fn(),
    listAgentLogs: vi.fn(),
    createEnrollmentToken: vi.fn(),
    revokeEnrollmentToken: vi.fn(),
    revokeAgent: vi.fn(),
    deleteAgent: vi.fn(),
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
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listEnrollmentTokens).mockResolvedValue({
      data: [],
    } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listJobs).mockResolvedValue({ data: [] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listJobLogs).mockResolvedValue({ data: [] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listAgentLogs).mockResolvedValue({ data: [] } as AxiosResponse)
  })

  it('shows concrete remote setup instructions before any agents are enrolled', async () => {
    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    expect(
      await screen.findByText(/Run this on a remote machine to register it/i)
    ).toBeInTheDocument()
    expect(screen.getByText(/curl -fsSL .*\/agent\/install\.sh/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /setup help/i })).toBeInTheDocument()
  })

  it('derives backend server URLs for install commands', () => {
    expect(resolveAgentServerUrl('http://192.168.0.29:8083/api', 'http://localhost:7879')).toBe(
      'http://192.168.0.29:8083'
    )
    expect(resolveAgentServerUrl('/api', 'http://localhost:7879')).toBe('http://localhost:8083')
    expect(resolveAgentServerUrl('/api', 'http://localhost:8093')).toBe('http://localhost:8093')
    expect(isLocalAgentServerUrl('http://127.0.0.1:8083')).toBe(true)
  })

  it('builds explicit service-user installer arguments', () => {
    expect(
      buildAgentInstallCommand('http://192.168.0.29:8083', 'agent-token-secret', 'Client laptop')
    ).toContain('--service-user current')

    expect(
      buildAgentInstallCommand(
        'http://192.168.0.29:8083',
        'agent-token-secret',
        'Dedicated client',
        'borg1',
        'dedicated'
      )
    ).toContain('--service-user borg-ui-agent')

    expect(
      buildAgentInstallCommand(
        'http://192.168.0.29:8083',
        'agent-token-secret',
        'Root client',
        'borg1',
        'root'
      )
    ).toContain('--service-user root')
  })

  it('opens from the shared system settings cache without requiring the former beta flag', async () => {
    const queryClient = new QueryClient({
      defaultOptions: {
        queries: { retry: false },
        mutations: { retry: false },
      },
    })
    queryClient.setQueryData(['systemSettings'], {
      settings: { managed_agents_beta_enabled: false },
    })

    renderWithProviders(<ManagedAgents />, {
      initialRoute: '/managed-agents',
      queryClient,
    })

    expect(await screen.findByText('Managed Agents')).toBeInTheDocument()
    expect(window.location.pathname).toBe('/managed-agents')
    expect(managedAgentsAPI.listAgents).toHaveBeenCalled()
  })

  it('manually refreshes managed-agent status with visible feedback', async () => {
    const user = userEvent.setup()
    let resolveRefresh: ((value: AxiosResponse<AgentMachineResponse[]>) => void) | undefined
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'offline',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    vi.mocked(managedAgentsAPI.listAgents)
      .mockResolvedValueOnce({ data: [agent] } as AxiosResponse)
      .mockReturnValueOnce(
        new Promise((resolve) => {
          resolveRefresh = resolve
        })
      )

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    expect(await screen.findByText('offline')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^refresh$/i }))

    expect(screen.getByRole('button', { name: /refreshing agents/i })).toBeDisabled()
    expect(managedAgentsAPI.listAgents).toHaveBeenCalledTimes(2)

    resolveRefresh?.({
      data: [{ ...agent, status: 'online' }],
    } as AxiosResponse<AgentMachineResponse[]>)

    expect(await screen.findByText('online')).toBeInTheDocument()
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
    expect(screen.queryByText(/Clone Borg UI on the client machine/i)).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy setup command'))
    expect(onCopy).toHaveBeenCalledWith(
      'borg-ui-agent register --server http://localhost:7879 --token <enrollment-token> --name <machine-name>'
    )

    await user.click(screen.getByRole('button', { name: /setup help/i }))

    expect(screen.getByText(/localhost only works when the agent/i)).toBeInTheDocument()
    expect(screen.getByText(/enables systemd by default/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy install command'))
    await user.click(screen.getByLabelText('Copy install commands'))
    await user.click(screen.getByLabelText('Copy status command'))
    await user.click(screen.getByLabelText('Copy systemd commands'))

    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('git clone'))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('systemctl status'))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('systemctl enable --now'))
  }, 60000)

  it('renders setup help details as a standalone story surface', async () => {
    const user = userEvent.setup()
    const onCopy = vi.fn()

    renderWithProviders(
      <AgentSetupHelpContent
        command="borg-ui-agent register --server http://localhost:7879 --token <enrollment-token> --name <machine-name>"
        onCopy={onCopy}
      />
    )

    expect(screen.getByText(/Run this on the Linux machine/i)).toBeInTheDocument()
    expect(screen.queryByText(/Raspberry\s+Pi/i)).not.toBeInTheDocument()
    expect(screen.getByText(/localhost only works when the agent/i)).toBeInTheDocument()
    expect(screen.getByText(/enables systemd by default/i)).toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy install commands'))

    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('git clone'))
  })

  it('uses a single waiting indicator in the add-agent install command', () => {
    const { container } = renderWithProviders(
      <AgentInstallCommand
        serverUrl="http://192.168.0.29:8083"
        token="agent-token-secret"
        agentName="Client laptop"
        onCopy={vi.fn()}
      />
    )

    expect(screen.getByText(/waiting for agent to connect/i)).toBeInTheDocument()
    expect(screen.queryByText(/^Waiting…$/)).not.toBeInTheDocument()
    expect(container.querySelectorAll('[aria-hidden="true"] > span')).toHaveLength(0)
  })

  it('creates enrollment tokens from the Add Agent wizard only after confirming details', async () => {
    const user = userEvent.setup()
    vi.mocked(managedAgentsAPI.createEnrollmentToken).mockResolvedValue({
      data: {
        id: 1,
        name: 'Client laptop',
        token: 'agent-token-secret',
        token_prefix: 'agent-token-secret',
        expires_at: '2026-05-28T00:00:00.000Z',
        created_at: '2026-05-21T00:00:00.000Z',
      },
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await user.click(await screen.findByRole('button', { name: /add agent/i }))
    expect(managedAgentsAPI.createEnrollmentToken).not.toHaveBeenCalled()

    await screen.findByRole('dialog', { name: /add agent/i })
    await user.clear(screen.getByLabelText(/server url/i))
    await user.type(screen.getByLabelText(/server url/i), 'http://192.168.0.29:8083')
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.clear(screen.getByLabelText(/agent name/i))
    await user.type(screen.getByLabelText(/agent name/i), 'Client laptop')
    await user.click(screen.getByRole('button', { name: /generate install command/i }))

    expect(vi.mocked(managedAgentsAPI.createEnrollmentToken).mock.calls[0][0]).toEqual({
      name: 'Client laptop',
      expires_in_days: 7,
    })
    expect(await screen.findByText(/waiting for agent to connect/i)).toBeInTheDocument()
    expect(
      screen.getByText((content) =>
        [
          'curl -fsSL http://192.168.0.29:8083/agent/install.sh',
          '--token agent-token-secret',
          '--name "Client laptop"',
          '--borg-version 1',
        ].every((part) => content.includes(part))
      )
    ).toBeInTheDocument()
  }, 60000)

  it('includes the default browse path when creating a managed-agent enrollment token', async () => {
    const user = userEvent.setup()
    vi.mocked(managedAgentsAPI.createEnrollmentToken).mockResolvedValue({
      data: {
        id: 1,
        name: 'Odroid M1',
        token: 'agent-token-secret',
        token_prefix: 'agent-token-secret',
        expires_at: '2026-05-28T00:00:00.000Z',
        created_at: '2026-05-21T00:00:00.000Z',
        default_path: '/home/karanhudia',
      },
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await user.click(await screen.findByRole('button', { name: /add agent/i }))
    await screen.findByRole('dialog', { name: /add agent/i })
    await user.clear(screen.getByLabelText(/server url/i))
    await user.type(screen.getByLabelText(/server url/i), 'http://192.168.0.29:8083')
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.clear(screen.getByLabelText(/agent name/i))
    await user.type(screen.getByLabelText(/agent name/i), 'Odroid M1')
    await user.type(screen.getByLabelText(/default path/i), ' /home/karanhudia ')
    await user.click(screen.getByRole('button', { name: /generate install command/i }))

    expect(vi.mocked(managedAgentsAPI.createEnrollmentToken).mock.calls[0][0]).toEqual({
      name: 'Odroid M1',
      default_path: '/home/karanhudia',
      expires_in_days: 7,
    })
  }, 60000)

  it('generates Borg 2 beta installer commands from the Add Agent wizard', async () => {
    const user = userEvent.setup()
    vi.mocked(managedAgentsAPI.createEnrollmentToken).mockResolvedValue({
      data: {
        id: 1,
        name: 'Borg 2 client',
        token: 'agent-token-secret',
        token_prefix: 'agent-token-secret',
        expires_at: '2026-05-28T00:00:00.000Z',
        created_at: '2026-05-21T00:00:00.000Z',
      },
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await user.click(await screen.findByRole('button', { name: /add agent/i }))
    await screen.findByRole('dialog', { name: /add agent/i })
    await user.clear(screen.getByLabelText(/server url/i))
    await user.type(screen.getByLabelText(/server url/i), 'http://192.168.0.29:8083')
    await user.click(screen.getByRole('button', { name: /next/i }))
    await user.click(screen.getByRole('radio', { name: /borg 2\.x beta only/i }))
    await user.clear(screen.getByLabelText(/agent name/i))
    await user.type(screen.getByLabelText(/agent name/i), 'Borg 2 client')
    await user.click(screen.getByRole('button', { name: /generate install command/i }))

    expect(
      screen.getByText((content) =>
        [
          'curl -fsSL http://192.168.0.29:8083/agent/install.sh',
          '--token agent-token-secret',
          '--name "Borg 2 client"',
          '--borg-version 2',
        ].every((part) => content.includes(part))
      )
    ).toBeInTheDocument()
  }, 90000)

  it('shows a localhost warning in the Add Agent wizard', async () => {
    const user = userEvent.setup()

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await user.click(await screen.findByRole('button', { name: /add agent/i }))
    await screen.findByRole('dialog', { name: /add agent/i })

    expect(screen.getByText(/localhost only works when the agent/i)).toBeInTheDocument()
  }, 60000)

  it('renders populated agent cards and wires the revoke action', async () => {
    const user = userEvent.setup()
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

    const onDelete = vi.fn()

    renderWithProviders(
      <AgentList
        agents={[agent]}
        serverUrl="https://borg-ui.example.com"
        onCopy={vi.fn()}
        onRevoke={onRevoke}
        onDelete={onDelete}
        onViewLogs={vi.fn()}
        isRevoking={false}
        isDeleting={false}
      />
    )

    expect(screen.getByText('client-01')).toBeInTheDocument()
    expect(screen.getByText('agent-client-7')).toBeInTheDocument()
    expect(screen.getByText('linux / arm64')).toBeInTheDocument()
    expect(screen.getByText('borg 1.4.4')).toBeInTheDocument()
    expect(screen.getByText('Last run failed')).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /revoke agent/i }))
    expect(onRevoke).toHaveBeenCalledWith(agent)
  })

  it('builds a tokenless reinstall command for existing agents', () => {
    const command = buildAgentReinstallCommand('https://borg-ui.example.com')

    expect(command).toBe(
      'curl -fsSL https://borg-ui.example.com/agent/install.sh | sudo bash -s -- --reinstall'
    )
    expect(command).not.toContain('--token')
    expect(command).not.toContain('<enrollment-token>')
    expect(command).not.toContain('--name')
    expect(command).not.toContain(' register ')
  })

  it('opens a tokenless reinstall script from an agent card', async () => {
    const user = userEvent.setup()
    const onCopy = vi.fn()
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
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse

    renderWithProviders(
      <AgentList
        agents={[agent]}
        serverUrl="https://borg-ui.example.com"
        onCopy={onCopy}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
        onViewLogs={vi.fn()}
        isRevoking={false}
        isDeleting={false}
      />
    )

    await user.click(screen.getByRole('button', { name: /reinstall agent/i }))

    const dialog = screen.getByRole('dialog', { name: /reinstall agent/i })
    expect(dialog).toBeInTheDocument()
    expect(within(dialog).getByText(/client-01/i)).toBeInTheDocument()
    expect(
      within(dialog).getByText(/No enrollment token or registration step is required/i)
    ).toBeInTheDocument()
    expect(
      within(dialog).getByText((content) =>
        ['curl -fsSL https://borg-ui.example.com/agent/install.sh', '--reinstall'].every((part) =>
          content.includes(part)
        )
      )
    ).toBeInTheDocument()
    expect(screen.queryByText(/--token/)).not.toBeInTheDocument()
    expect(screen.queryByText(/<enrollment-token>/)).not.toBeInTheDocument()

    await user.click(screen.getByLabelText('Copy reinstall command'))

    expect(onCopy).toHaveBeenCalledWith(
      'curl -fsSL https://borg-ui.example.com/agent/install.sh | sudo bash -s -- --reinstall'
    )
  }, 60000)

  it('opens recent agent session logs from an agent card', async () => {
    const user = userEvent.setup()
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [agent] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listAgentLogs).mockResolvedValue({
      data: [
        {
          id: 'session-7-1',
          agent_machine_id: 7,
          job_id: null,
          command_id: 'cmd-1',
          stream: 'session',
          level: 'info',
          message: 'Agent session connected',
          created_at: '2026-05-18T10:00:00.000Z',
        },
      ],
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await screen.findByText('client-01', undefined, { timeout: 10000 })
    await user.click(screen.getByRole('button', { name: /view agent logs/i }))

    expect(managedAgentsAPI.listAgentLogs).toHaveBeenCalledWith(7)
    expect(await screen.findByRole('dialog', { name: /agent logs/i })).toBeInTheDocument()
    expect(screen.getByText(/Agent session connected/i)).toBeInTheDocument()
    expect(screen.getByText(/cmd-1/i)).toBeInTheDocument()
  }, 60000)

  it('uses the standard view icon for managed agent log actions', () => {
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    const job = {
      id: 501,
      agent_machine_id: 7,
      job_type: 'backup',
      status: 'running',
      payload: { job_kind: 'backup.create' },
      progress_percent: 42,
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentJobResponse

    const { container: agentContainer } = renderWithProviders(
      <AgentList
        agents={[agent]}
        serverUrl="https://borg-ui.example.com"
        onCopy={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
        onViewLogs={vi.fn()}
        isRevoking={false}
        isDeleting={false}
      />
    )
    const agentLogButton = within(agentContainer).getByRole('button', {
      name: /view agent logs/i,
    })

    expect(agentLogButton.querySelector('svg.lucide-eye')).toBeInTheDocument()
    expect(agentLogButton.querySelector('svg.lucide-terminal')).not.toBeInTheDocument()

    const { container: jobsContainer } = renderWithProviders(
      <JobsTable
        jobs={[job]}
        agentsById={new Map([[agent.id, agent]])}
        onCancel={vi.fn()}
        onViewLogs={vi.fn()}
        isCanceling={false}
      />
    )
    const jobLogButton = within(jobsContainer).getByRole('button', { name: /view logs/i })

    expect(jobLogButton.querySelector('svg.lucide-eye')).toBeInTheDocument()
    expect(jobLogButton.querySelector('svg.lucide-terminal')).not.toBeInTheDocument()
  })

  it('opens managed-agent job logs in the shared log viewer', async () => {
    const user = userEvent.setup()
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse
    const job = {
      id: 501,
      agent_machine_id: 7,
      job_type: 'backup',
      status: 'completed',
      payload: { job_kind: 'backup.create' },
      progress_percent: 100,
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentJobResponse
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({ data: [agent] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listJobs).mockResolvedValue({ data: [job] } as AxiosResponse)
    vi.mocked(managedAgentsAPI.listJobLogs).mockResolvedValue({
      data: [
        {
          id: 1,
          agent_job_id: 501,
          sequence: 1,
          stream: 'stdout',
          message: 'borg create started',
          created_at: '2026-05-18T10:00:00.000Z',
          received_at: '2026-05-18T10:00:01.000Z',
        },
      ],
    } as AxiosResponse)

    renderWithProviders(<ManagedAgents />, { initialRoute: '/managed-agents' })

    await screen.findByText('Managed Agents')
    await user.click(screen.getByRole('tab', { name: /jobs/i }))
    await screen.findByText('#501')
    await user.click(screen.getByRole('button', { name: /view logs/i }))

    expect(managedAgentsAPI.listJobLogs).toHaveBeenCalledWith(501)
    expect(
      await screen.findByRole('dialog', { name: /Agent Job Logs - Job #501/i })
    ).toBeInTheDocument()
    expect(screen.getByText(/stdout: borg create started/i)).toBeInTheDocument()
  }, 60000)

  it('warns when an agent has no usable Borg binary', () => {
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      os: 'linux',
      arch: 'arm64',
      agent_version: '0.4.0',
      borg_versions: [],
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse

    renderWithProviders(
      <AgentList
        agents={[agent]}
        serverUrl="https://borg-ui.example.com"
        onCopy={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={vi.fn()}
        onViewLogs={vi.fn()}
        isRevoking={false}
        isDeleting={false}
      />
    )

    expect(screen.getByText(/No usable Borg binary reported/i)).toBeInTheDocument()
  })

  it('requires confirmation before deleting an agent', async () => {
    const user = userEvent.setup()
    const onDelete = vi.fn()
    const agent = {
      id: 7,
      agent_id: 'agent-client-7',
      name: 'client',
      hostname: 'client-01',
      status: 'online',
      created_at: '2026-05-18T09:00:00.000Z',
      updated_at: '2026-05-18T10:00:00.000Z',
    } as AgentMachineResponse

    renderWithProviders(
      <AgentList
        agents={[agent]}
        serverUrl="https://borg-ui.example.com"
        onCopy={vi.fn()}
        onRevoke={vi.fn()}
        onDelete={onDelete}
        onViewLogs={vi.fn()}
        isRevoking={false}
        isDeleting={false}
      />
    )

    await user.click(screen.getByRole('button', { name: /delete agent/i }))
    expect(onDelete).not.toHaveBeenCalled()
    expect(
      screen.getByText(/removes it from the fleet list.*local service may still run/i)
    ).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /^delete agent$/i }))
    expect(onDelete).toHaveBeenCalledWith(agent)
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
