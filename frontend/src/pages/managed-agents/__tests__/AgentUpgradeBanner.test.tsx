import { describe, expect, it } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import AgentUpgradeBanner from '../AgentUpgradeBanner'
import type { AgentMachineResponse } from '../../../services/api'

const agent = (overrides: Partial<AgentMachineResponse>): AgentMachineResponse =>
  ({
    id: 1,
    agent_id: 'agt_1',
    name: 'node',
    status: 'online',
    created_at: '2026-05-10T08:00:00.000Z',
    updated_at: '2026-09-07T08:00:00.000Z',
    ...overrides,
  }) as AgentMachineResponse

describe('AgentUpgradeBanner', () => {
  it('renders nothing when no agent is behind', () => {
    renderWithProviders(
      <AgentUpgradeBanner
        agents={[
          agent({ upgrade_status: 'up_to_date', available_agent_version: '0.1.3' }),
          agent({ id: 2, upgrade_status: 'pinned', available_agent_version: '0.1.3' }),
        ]}
      />
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })

  it('names the served version when every outdated agent shares it', () => {
    renderWithProviders(
      <AgentUpgradeBanner
        agents={[
          agent({
            upgrade_status: 'outdated',
            agent_version: '0.1.2',
            available_agent_version: '0.1.3',
          }),
          agent({
            id: 2,
            upgrade_status: 'outdated',
            agent_version: '0.1.1',
            available_agent_version: '0.1.3',
          }),
        ]}
      />
    )
    expect(screen.getByText(/2 endpoints are running an older agent/i)).toBeInTheDocument()
    expect(screen.getByText(/current agent version is 0\.1\.3/i)).toBeInTheDocument()
  })

  it('does not name one version when outdated agents have different targets', () => {
    // A pinned agent that is behind its own pin is outdated against the pin,
    // not against the version the server serves. Naming the served version
    // here would tell the operator to install something the pin forbids.
    renderWithProviders(
      <AgentUpgradeBanner
        agents={[
          agent({
            upgrade_status: 'outdated',
            agent_version: '0.1.2',
            available_agent_version: '0.1.3',
          }),
          agent({
            id: 2,
            upgrade_status: 'outdated',
            agent_version: '0.1.1',
            desired_agent_version: '0.1.2',
            available_agent_version: '0.1.3',
          }),
        ]}
      />
    )
    expect(screen.getByText(/2 endpoints are running an older agent/i)).toBeInTheDocument()
    expect(screen.queryByText(/current agent version is 0\.1\.3/i)).not.toBeInTheDocument()
    expect(screen.getByText(/each one targets its own configured version/i)).toBeInTheDocument()
  })

  it('names the pinned target when every outdated agent shares that pin', () => {
    renderWithProviders(
      <AgentUpgradeBanner
        agents={[
          agent({
            upgrade_status: 'outdated',
            agent_version: '0.1.1',
            desired_agent_version: '0.1.2',
            available_agent_version: '0.1.3',
          }),
        ]}
      />
    )
    expect(screen.getByText(/current agent version is 0\.1\.2/i)).toBeInTheDocument()
  })
})
