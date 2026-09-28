import { describe, expect, it, vi } from 'vitest'

import { sshKeysAPI } from '../../../services/api'
import { renderWithProviders, waitFor } from '../../../test/test-utils'
import { createInitialQuickStartAnswers } from '../quickStartState'
import QuickStartDestinationStep from '../steps/QuickStartDestinationStep'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return { ...actual, sshKeysAPI: { ...actual.sshKeysAPI, getSSHConnections: vi.fn() } }
})

describe('QuickStartDestinationStep', () => {
  it('suggests a remote path once the chosen connection has loaded', async () => {
    vi.mocked(sshKeysAPI.getSSHConnections).mockResolvedValue({
      data: {
        connections: [
          { id: 5, host: 'nas.local', username: 'backup', port: 22, status: 'connected' },
        ],
      },
    } as never)
    const onChange = vi.fn()
    renderWithProviders(
      <QuickStartDestinationStep
        answers={{
          ...createInitialQuickStartAnswers(),
          name: 'home',
          destinationKind: 'ssh',
          destinationConnectionId: 5,
        }}
        onChange={onChange}
      />
    )
    await waitFor(() =>
      expect(onChange).toHaveBeenCalledWith({ destinationPath: '/home/backup/borg-backups/home' })
    )
    expect(onChange).toHaveBeenCalledTimes(1)
  })
})
