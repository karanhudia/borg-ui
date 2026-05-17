import { describe, it, expect, vi, beforeEach } from 'vitest'
import { screen } from '@testing-library/react'
import ManagedAgents from '../ManagedAgents'
import { renderWithProviders } from '../../test/test-utils'
import { managedAgentsAPI, settingsAPI } from '../../services/api'
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
        'Create an enrollment token, then run the registration command on the client.'
      )
    ).toBeInTheDocument()
    expect(
      screen.getByText(/borg-ui-agent register --server .* --token <enrollment-token>/)
    ).toBeInTheDocument()
  })
})
