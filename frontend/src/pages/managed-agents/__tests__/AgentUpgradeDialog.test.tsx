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
      <AgentUpgradeDialog open agent={agent()} onConfirm={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByText(/db-01\.internal/)).toBeInTheDocument()
    expect(screen.getByText(/0\.1\.3/)).toBeInTheDocument()
  })

  it('names the pinned version rather than the served one', () => {
    renderWithProviders(
      <AgentUpgradeDialog
        open
        agent={agent({ desired_agent_version: '0.1.1' })}
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
      <AgentUpgradeDialog open agent={target} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /upgrade/i }))
    expect(onConfirm).toHaveBeenCalledWith(target)
  })

  it('does not confirm while a request is in flight', () => {
    const onConfirm = vi.fn()
    renderWithProviders(
      <AgentUpgradeDialog open busy agent={agent()} onConfirm={onConfirm} onCancel={vi.fn()} />
    )
    fireEvent.click(screen.getByRole('button', { name: /upgrade/i }))
    expect(onConfirm).not.toHaveBeenCalled()
  })
})
