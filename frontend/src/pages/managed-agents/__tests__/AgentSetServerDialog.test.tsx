import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AgentSetServerDialog from '../AgentSetServerDialog'
import type { AgentMachineResponse } from '../../../services/api'

const agent = (agentVersion: string | null) =>
  ({
    id: 1,
    agent_id: 'agt_1',
    name: 'db-01',
    hostname: 'db-01.internal',
    status: 'offline',
    agent_version: agentVersion,
  }) as AgentMachineResponse

const renderDialog = (agentVersion: string | null) => {
  const onCopy = vi.fn()
  render(
    <AgentSetServerDialog
      agent={agent(agentVersion)}
      open
      defaultServerUrl="http://192.168.1.82:8083"
      onCopy={onCopy}
      onCancel={vi.fn()}
    />
  )
  return { onCopy }
}

describe('AgentSetServerDialog', () => {
  it('prefills the field with this server own URL', () => {
    renderDialog('0.1.5')
    expect(screen.getByRole('textbox')).toHaveValue('http://192.168.1.82:8083')
  })

  it('shows the subcommand form for a current agent', () => {
    renderDialog('0.1.5')
    expect(screen.getByText(/borg-ui-agent set-server/)).toBeInTheDocument()
    expect(screen.queryByText(/sed -i/)).not.toBeInTheDocument()
  })

  it('shows the sed form for an older agent, without explaining a fork', () => {
    renderDialog('0.1.4')
    expect(screen.getByText(/sed -i/)).toBeInTheDocument()
    expect(screen.queryByText(/borg-ui-agent set-server/)).not.toBeInTheDocument()
  })

  it('rerenders the command as the URL is edited', async () => {
    renderDialog('0.1.5')
    const field = screen.getByRole('textbox')
    await userEvent.clear(field)
    await userEvent.type(field, 'https://borg.example.com')
    expect(screen.getByText(/https:\/\/borg\.example\.com/)).toBeInTheDocument()
  })

  it('copies the rendered command', async () => {
    const { onCopy } = renderDialog('0.1.5')
    await userEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('set-server'))
  })

  it('names borg-ui-agent status as the way to read the current URL', () => {
    renderDialog('0.1.5')
    expect(screen.getByText(/borg-ui-agent status/)).toBeInTheDocument()
  })

  it('renders no command while the URL is unusable', async () => {
    renderDialog('0.1.5')
    const field = screen.getByRole('textbox')
    await userEvent.clear(field)
    await userEvent.type(field, 'borg.example.com')
    expect(screen.queryByText(/set-server|sed -i/)).not.toBeInTheDocument()
    expect(screen.getByText(/http:\/\/ or https:\/\//)).toBeInTheDocument()
  })
})
