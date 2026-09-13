import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import AgentUninstallDialog from '../AgentUninstallDialog'
import type { AgentMachineResponse } from '../../../services/api'

const agent = {
  id: 1,
  agent_id: 'agt_1',
  name: 'db-01',
  hostname: 'db-01.internal',
  status: 'offline',
} as AgentMachineResponse

const renderDialog = () => {
  const onCopy = vi.fn()
  render(
    <AgentUninstallDialog
      agent={agent}
      open
      serverUrl="https://borg-ui.example.com"
      onCopy={onCopy}
      onCancel={vi.fn()}
    />
  )
  return { onCopy }
}

describe('AgentUninstallDialog', () => {
  it('renders the uninstall command', () => {
    renderDialog()
    expect(
      screen.getByText('curl -fsSL "https://borg-ui.example.com/agent/uninstall.sh" | sudo bash')
    ).toBeInTheDocument()
  })

  it('quotes the URL, which is pasted into a root shell', () => {
    render(
      <AgentUninstallDialog
        agent={agent}
        open
        serverUrl="https://borg-ui.example.com/a$b"
        onCopy={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(
      screen.getByText(
        'curl -fsSL "https://borg-ui.example.com/a\\$b/agent/uninstall.sh" | sudo bash'
      )
    ).toBeInTheDocument()
  })

  it('warns when the command would fetch over plain HTTP', () => {
    render(
      <AgentUninstallDialog
        agent={agent}
        open
        serverUrl="http://192.168.1.82:8083"
        onCopy={vi.fn()}
        onCancel={vi.fn()}
      />
    )
    expect(screen.getByText(/runs it as root/i)).toBeInTheDocument()
  })

  it('copies the command', async () => {
    const { onCopy } = renderDialog()
    await userEvent.click(screen.getByRole('button', { name: /copy/i }))
    expect(onCopy).toHaveBeenCalledWith(expect.stringContaining('uninstall.sh'))
  })

  it('says plainly that Borg and the repositories are not touched', () => {
    renderDialog()
    expect(screen.getByText(/your own Borg installation/i)).toBeInTheDocument()
    expect(screen.getByText(/backup repositories/i)).toBeInTheDocument()
  })

  it('lists what the script removes', () => {
    renderDialog()
    expect(screen.getByText(/borg-ui-agent service and its upgrade helper/i)).toBeInTheDocument()
    expect(screen.getByText(/\/opt\/borg-ui-agent/)).toBeInTheDocument()
  })
})
