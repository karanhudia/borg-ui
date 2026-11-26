import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import SshConnectionSelect, { type SshConnectionSummary } from '../SshConnectionSelect'

// Two connections to one borg server, each with its own key (#1601).
const connections: SshConnectionSummary[] = [
  {
    id: 1,
    host: 'borg.example.com',
    username: 'borg',
    port: 22,
    ssh_key_name: 'borgserver-repo1',
    status: 'connected',
  },
  {
    id: 2,
    host: 'borg.example.com',
    username: 'borg',
    port: 22,
    ssh_key_name: 'borgserver-repo2',
    status: 'connected',
  },
]

describe('SshConnectionSelect', () => {
  it('tells apart connections to the same user@host by their SSH key name', async () => {
    const user = userEvent.setup()
    render(
      <SshConnectionSelect
        value=""
        onChange={vi.fn()}
        connections={connections}
        label="SSH Connection"
        emptyMessage="No connections"
      />
    )

    await user.click(screen.getByRole('combobox', { name: /SSH Connection/i }))
    const options = screen.getAllByRole('option')
    expect(options).toHaveLength(2)
    expect(options[0]).toHaveTextContent('borg@borg.example.com')
    expect(options[0]).toHaveTextContent('borgserver-repo1 • Port 22')
    expect(options[1]).toHaveTextContent('borgserver-repo2 • Port 22')
  })

  it('leaves out the key name when the connection has none', async () => {
    const user = userEvent.setup()
    render(
      <SshConnectionSelect
        value=""
        onChange={vi.fn()}
        connections={[{ ...connections[0], ssh_key_name: null, default_path: '/backups' }]}
        label="SSH Connection"
        emptyMessage="No connections"
      />
    )

    await user.click(screen.getByRole('combobox', { name: /SSH Connection/i }))
    const [option] = screen.getAllByRole('option')
    expect(option).toHaveTextContent('Port 22 • /backups')
    expect(option).not.toHaveTextContent('null')
  })
})
