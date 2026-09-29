import { describe, expect, it, vi } from 'vitest'

import api, { managedAgentsAPI, sshKeysAPI } from '../../../services/api'
import { renderWithProviders, screen, waitFor } from '../../../test/test-utils'
import { createInitialQuickStartAnswers } from '../quickStartState'
import QuickStartDestinationStep from '../steps/QuickStartDestinationStep'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    default: { ...actual.default, get: vi.fn() },
    sshKeysAPI: { ...actual.sshKeysAPI, getSSHConnections: vi.fn() },
    managedAgentsAPI: { ...actual.managedAgentsAPI, listAgents: vi.fn() },
  }
})

describe('QuickStartDestinationStep', () => {
  it('suggests a remote path once the chosen connection has loaded', async () => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: {
        connections: [
          {
            id: 5,
            host: 'nas.local',
            username: 'backup',
            port: 22,
            status: 'connected',
            default_path: '/srv',
          },
        ],
      },
    } as never)
    const onChange = vi.fn()
    renderWithProviders(
      <QuickStartDestinationStep
        answers={{
          ...createInitialQuickStartAnswers(),
          name: 'home',
          destinationKind: 'ssh',
          destinationConnectionId: 5,
        }}
        onChange={onChange}
      />
    )
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ destinationPath: '/srv/borg-backups/home' })
    )
    expect(onChange).toHaveBeenCalledTimes(1)
  })
  it('asks the machine for its home folder when there is no default path', async () => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: {
        connections: [
          {
            id: 5,
            host: 'nas.local',
            username: 'backup',
            port: 22,
            status: 'connected',
            ssh_key_id: 1,
          },
        ],
      },
    } as never)
    vi.mocked(api.get).mockResolvedValue({ data: { path: '/volume1/homes/backup' } })
    const onChange = vi.fn()
    renderWithProviders(
      <QuickStartDestinationStep
        answers={{
          ...createInitialQuickStartAnswers(),
          name: 'home',
          destinationKind: 'ssh',
          destinationConnectionId: 5,
        }}
        onChange={onChange}
      />
    )
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({
        destinationPath: '/volume1/homes/backup/borg-backups/home',
      })
    )
    expect(api.get).toHaveBeenCalledWith('/filesystem/ssh-home', {
      params: { ssh_key_id: 1, host: 'nas.local', username: 'backup', port: 22 },
    })
    expect(onChange).toHaveBeenCalledTimes(1)
  })
  it('leaves the remote path empty when the machine does not report a home folder', async () => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: {
        connections: [
          {
            id: 5,
            host: 'nas.local',
            username: 'backup',
            port: 22,
            status: 'connected',
            ssh_key_id: 1,
          },
        ],
      },
    } as never)
    vi.mocked(api.get).mockResolvedValue({ data: { path: null } })
    const onChange = vi.fn()
    renderWithProviders(
      <QuickStartDestinationStep
        answers={{
          ...createInitialQuickStartAnswers(),
          name: 'home',
          destinationKind: 'ssh',
          destinationConnectionId: 5,
        }}
        onChange={onChange}
      />
    )
    await waitFor(() => expect(api.get).toHaveBeenCalled())
    // The path field only renders once the connection has loaded.
    expect((await screen.findAllByText(/backup@nas\.local/)).length).toBeGreaterThan(0)
    expect(onChange).not.toHaveBeenCalled()
  })
  it('suggests an agent path once the agent has loaded, and disables browsing while offline', async () => {
    vi.mocked(managedAgentsAPI.listAgents).mockResolvedValue({
      data: [
        {
          id: 7,
          name: 'laptop',
          hostname: 'laptop.local',
          status: 'offline',
          default_path: '/data',
        },
      ],
    } as never)
    const onChange = vi.fn()
    renderWithProviders(
      <QuickStartDestinationStep
        answers={{
          ...createInitialQuickStartAnswers(),
          name: 'home',
          sourceKind: 'agent',
          sourceAgentId: 7,
          sourcePaths: ['/home/alex'],
          destinationKind: 'agent',
        }}
        onChange={onChange}
      />
    )
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ destinationPath: '/data/borg-backups/home' })
    )
    expect(screen.getByText(/laptop.local is offline/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /browse/i })).toBeDisabled()
  })
})
