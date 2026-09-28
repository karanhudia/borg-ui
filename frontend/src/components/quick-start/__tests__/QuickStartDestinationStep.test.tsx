import { describe, expect, it, vi } from 'vitest'

import { managedAgentsAPI, sshKeysAPI } from '../../../services/api'
import { renderWithProviders, screen, waitFor } from '../../../test/test-utils'
import { createInitialQuickStartAnswers } from '../quickStartState'
import QuickStartDestinationStep from '../steps/QuickStartDestinationStep'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    sshKeysAPI: { ...actual.sshKeysAPI, getSSHConnections: vi.fn() },
    managedAgentsAPI: { ...actual.managedAgentsAPI, listAgents: vi.fn() },
  }
})

describe('QuickStartDestinationStep', () => {
  it('suggests a remote path once the chosen connection has loaded', async () => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: {
        connections: [
          { id: 5, host: 'nas.local', username: 'backup', port: 22, status: 'connected' },
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
      expect(onChange).toHaveBeenCalledWith({ destinationPath: '/home/backup/borg-backups/home' })
    )
    expect(onChange).toHaveBeenCalledTimes(1)
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
