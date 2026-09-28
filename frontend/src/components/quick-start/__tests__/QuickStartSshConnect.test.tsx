import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sshKeysAPI } from '../../../services/api'
import { renderWithProviders, screen, userEvent, waitFor } from '../../../test/test-utils'
import QuickStartSshConnect from '../QuickStartSshConnect'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    sshKeysAPI: {
      getSystemKey: vi.fn(),
      generateSSHKey: vi.fn(),
      deploySSHKey: vi.fn(),
      getSSHConnections: vi.fn(),
    },
  }
})

describe('QuickStartSshConnect', () => {
  beforeEach(() => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: { connections: [] },
    } as never)
    vi.mocked(sshKeysAPI.getSystemKey).mockResolvedValue({
      data: { exists: true, ssh_key: { id: 7 } },
    } as never)
  })

  it('adds a machine with a one-time password and selects it', async () => {
    vi.mocked(sshKeysAPI.deploySSHKey).mockResolvedValue({
      data: { success: true, connection: { id: 12 } },
    } as never)
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <QuickStartSshConnect value="" onChange={onChange} label="Computer" canAddMachine />
    )

    await user.type(await screen.findByLabelText(/Host name/), 'nas.local')
    await user.type(screen.getByLabelText(/^Username/), 'backup')
    await user.type(screen.getByLabelText(/^Password/), 'secret')
    await user.click(screen.getByRole('button', { name: 'Connect' }))

    await waitFor(() => expect(onChange).toHaveBeenCalledWith(12))
    expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(7, {
      host: 'nas.local',
      username: 'backup',
      port: 22,
      password: 'secret',
    })
  })

  it('shows why the connection failed', async () => {
    vi.mocked(sshKeysAPI.deploySSHKey).mockResolvedValue({
      data: { success: false, connection: { id: 12, error_message: 'Permission denied' } },
    } as never)
    const onChange = vi.fn()
    const user = userEvent.setup()
    renderWithProviders(
      <QuickStartSshConnect value="" onChange={onChange} label="Computer" canAddMachine />
    )

    await user.type(await screen.findByLabelText(/Host name/), 'nas.local')
    await user.type(screen.getByLabelText(/^Username/), 'backup')
    await user.type(screen.getByLabelText(/^Password/), 'wrong')
    await user.click(screen.getByRole('button', { name: 'Connect' }))

    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Could not connect: Permission denied'
    )
    expect(onChange).not.toHaveBeenCalled()
  })
})
