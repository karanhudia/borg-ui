import { describe, expect, it, vi } from 'vitest'
import { fireEvent, screen } from '@testing-library/react'
import { renderWithProviders } from '../../../test/test-utils'
import AgentUpgradeDialog from '../AgentUpgradeDialog'
import type { AgentMachineResponse } from '../../../services/api'

const agent = (overrides: Partial<AgentMachineResponse> = {}): AgentMachineResponse =>
  ({
    id: 1,
    agent_id: 'agt_1',
    name: 'db-01',
    hostname: 'db-01.internal',
    status: 'online',
    agent_version: '0.1.2',
    available_agent_version: '0.1.3',
    created_at: '2026-05-10T08:00:00.000Z',
    updated_at: '2026-09-09T08:00:00.000Z',
    ...overrides,
  }) as AgentMachineResponse

describe('AgentUpgradeDialog', () => {
  it('names the endpoint and the version it will come back on', () => {
    renderWithProviders(
      <AgentUpgradeDialog open agents={[agent()]} onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByText(/db-01\.internal/)).toBeInTheDocument()
    expect(screen.getByText(/0\.1\.3/)).toBeInTheDocument()
  })

  it('names the pinned version rather than the served one', () => {
    renderWithProviders(
      <AgentUpgradeDialog
        open
        agents={[agent({ desired_agent_version: '0.1.1' })]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/0\.1\.1/)).toBeInTheDocument()
  })

  it('confirms with the agent', () => {
    const onConfirm = vi.fn()
    const target = agent()
    renderWithProviders(
      <AgentUpgradeDialog open agents={[target]} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /^upgrade$/i }))
    expect(onConfirm).toHaveBeenCalledWith([target])
  })

  it('does not confirm while a request is in flight', () => {
    const onConfirm = vi.fn()
    renderWithProviders(
      <AgentUpgradeDialog open busy agents={[agent()]} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /^upgrade$/i }))
    expect(onConfirm).not.toHaveBeenCalled()
  })

  it('lists every affected endpoint by name and hostname', () => {
    renderWithProviders(
      <AgentUpgradeDialog
        open
        agents={[agent(), agent({ id: 2, name: 'web-01', hostname: 'web-01.internal' })]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/db-01\.internal/)).toBeInTheDocument()
    expect(screen.getByText(/web-01\.internal/)).toBeInTheDocument()
  })

  it('confirms with every endpoint it listed', () => {
    const onConfirm = vi.fn()
    const targets = [agent(), agent({ id: 2, name: 'web-01' })]
    renderWithProviders(
      <AgentUpgradeDialog open agents={targets} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /^upgrade$/i }))
    expect(onConfirm).toHaveBeenCalledWith(targets)
  })

  it('does not name a version when the endpoints target different ones', () => {
    renderWithProviders(
      <AgentUpgradeDialog
        open
        agents={[agent(), agent({ id: 2, name: 'web-01', desired_agent_version: '0.1.2' })]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/its own configured version/i)).toBeInTheDocument()
    expect(screen.queryByText(/comes back on version/i)).not.toBeInTheDocument()
  })

  it('warns that a large request is upgraded a few endpoints at a time', () => {
    renderWithProviders(
      <AgentUpgradeDialog
        open
        agents={[agent(), agent({ id: 2, name: 'web-01' })]}
        onConfirm={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/a few at a time/i)).toBeInTheDocument()
  })
})
