import { beforeEach, describe, expect, it, vi } from 'vitest'

import { sshKeysAPI } from '../../../services/api'
import { connectNewMachine, SshConnectError } from '../quickStartSsh'

vi.mock('../../../services/api', () => ({
  sshKeysAPI: {
    getSystemKey: vi.fn(),
    generateSSHKey: vi.fn(),
    deploySSHKey: vi.fn(),
    getSSHConnections: vi.fn(),
  },
}))

const machine = { host: ' nas.local ', username: 'backup', port: 22, password: 'secret' }

describe('connectNewMachine', () => {
  beforeEach(() => {
    vi.mocked(sshKeysAPI.getSystemKey).mockReset()
    vi.mocked(sshKeysAPI.generateSSHKey).mockReset()
    vi.mocked(sshKeysAPI.deploySSHKey).mockReset()
  })

  it('deploys the existing system key', async () => {
    vi.mocked(sshKeysAPI.getSystemKey).mockResolvedValue({
      data: { exists: true, ssh_key: { id: 7 } },
    } as never)
    vi.mocked(sshKeysAPI.deploySSHKey).mockResolvedValue({
      data: { success: true, connection: { id: 12 } },
    } as never)

    await expect(connectNewMachine(machine)).resolves.toBe(12)
    expect(sshKeysAPI.generateSSHKey).not.toHaveBeenCalled()
    expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(7, {
      host: 'nas.local',
      username: 'backup',
      port: 22,
      password: 'secret',
    })
  })

  it('generates the system key when there is none', async () => {
    vi.mocked(sshKeysAPI.getSystemKey).mockResolvedValue({ data: { exists: false } } as never)
    vi.mocked(sshKeysAPI.generateSSHKey).mockResolvedValue({
      data: { ssh_key: { id: 9 } },
    } as never)
    vi.mocked(sshKeysAPI.deploySSHKey).mockResolvedValue({
      data: { success: true, connection: { id: 13 } },
    } as never)

    await expect(connectNewMachine(machine)).resolves.toBe(13)
    expect(sshKeysAPI.deploySSHKey).toHaveBeenCalledWith(9, expect.anything())
  })

  it('fails with the backend message when deploy reports success false', async () => {
    vi.mocked(sshKeysAPI.getSystemKey).mockResolvedValue({
      data: { exists: true, ssh_key: { id: 7 } },
    } as never)
    vi.mocked(sshKeysAPI.deploySSHKey).mockResolvedValue({
      data: { success: false, connection: { id: 12, error_message: 'Permission denied' } },
    } as never)

    const attempt = connectNewMachine(machine)
    await expect(attempt).rejects.toBeInstanceOf(SshConnectError)
    await expect(attempt).rejects.toThrow('Permission denied')
  })
})
