import { beforeEach, describe, expect, it, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../../test/test-utils'
import RestoreWizard from '../RestoreWizard'
import type { Repository } from '@/types'

const { trackEventMock } = vi.hoisted(() => ({ trackEventMock: vi.fn() }))
vi.mock('../../utils/analytics', async (importOriginal) => ({
  ...(await importOriginal<typeof import('../../utils/analytics')>()),
  trackEvent: trackEventMock,
}))
vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn(function () {
    return { getArchiveContents: vi.fn().mockResolvedValue({ data: { items: [] } }) }
  }),
}))
vi.mock('../../services/api', () => ({
  sshKeysAPI: { getSSHConnections: vi.fn().mockResolvedValue({ data: { connections: [] } }) },
}))

const repository = { id: 1, name: 'Repo', path: '/repo', borg_version: 1 } as Repository

describe('RestoreWizard funnel', () => {
  beforeEach(() => trackEventMock.mockClear())

  it('reports the step a user abandons the restore on', async () => {
    const user = userEvent.setup()
    const onClose = vi.fn()
    renderWithProviders(
      <RestoreWizard
        open
        onClose={onClose}
        archive={{ id: 'a1', name: 'a1' }}
        repository={repository}
        repositoryType="local"
        onRestore={vi.fn()}
        initialSelectedPaths={['home/alex/docs']}
      />
    )
    await screen.findByRole('dialog')
    await user.click(screen.getByRole('button', { name: 'Cancel' }))

    const calls = trackEventMock.mock.calls.filter(([category]) => category === 'Wizard')
    expect(calls[0]).toEqual(['Wizard', 'Start', { wizard: 'restore' }])
    expect(calls[calls.length - 1]).toEqual([
      'Wizard',
      'Cancel',
      { step: expect.any(String), wizard: 'restore' },
    ])
    expect(onClose).toHaveBeenCalled()
  })
})
