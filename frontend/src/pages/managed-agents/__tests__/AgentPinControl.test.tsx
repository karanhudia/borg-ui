import { describe, expect, it, vi } from 'vitest'
import { screen } from '@testing-library/react'
import { renderWithProviders, userEvent } from '../../../test/test-utils'
import AgentPinControl from '../AgentPinControl'
import type { AgentMachineResponse } from '../../../services/api'

const agent = (overrides: Partial<AgentMachineResponse> = {}): AgentMachineResponse =>
  ({
    id: 1,
    agent_id: 'agt_1',
    name: 'db-01',
    status: 'online',
    available_agent_version: '0.1.3',
    created_at: '2026-05-10T08:00:00.000Z',
    updated_at: '2026-09-09T08:00:00.000Z',
    ...overrides,
  }) as AgentMachineResponse

describe('AgentPinControl', () => {
  it('defaults an unpinned endpoint to tracking the server', () => {
    renderWithProviders(
      <AgentPinControl open agent={agent()} onSave={vi.fn()} onCancel={vi.fn()} />
    )
    expect(screen.getByText(/track server/i)).toBeInTheDocument()
  })

  it('saves a cleared pin as null rather than an empty string', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    const target = agent({ desired_agent_version: '0.1.3', desired_borg_version: '2' })

    renderWithProviders(<AgentPinControl open agent={target} onSave={onSave} onCancel={vi.fn()} />)
    await user.click(screen.getByRole('combobox', { name: /agent version/i }))
    await user.click(await screen.findByRole('option', { name: /track server/i }))
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(target, {
      desired_agent_version: null,
      desired_borg_version: '2',
    })
  })

  it('saves the served version as the pin', async () => {
    const user = userEvent.setup()
    const onSave = vi.fn()
    const target = agent()

    renderWithProviders(<AgentPinControl open agent={target} onSave={onSave} onCancel={vi.fn()} />)
    await user.click(screen.getByRole('combobox', { name: /agent version/i }))
    await user.click(await screen.findByRole('option', { name: '0.1.3' }))
    await user.click(screen.getByRole('button', { name: /save/i }))

    expect(onSave).toHaveBeenCalledWith(target, {
      desired_agent_version: '0.1.3',
      desired_borg_version: null,
    })
  })

  it('shows a pin this server no longer serves and refuses to re-save it', () => {
    renderWithProviders(
      <AgentPinControl
        open
        agent={agent({ desired_agent_version: '0.1.1' })}
        onSave={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/0\.1\.1 \(no longer served\)/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /save/i })).toBeDisabled()
  })
})
