import { describe, it, expect, vi } from 'vitest'
import { renderWithProviders, screen } from '../../test/test-utils'
import RestoreWizard from '../RestoreWizard'
import { BorgApiClient } from '../../services/borgApi/client'
import type { Repository } from '@/types'

vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn(function () {
    return { getArchiveContents: vi.fn().mockResolvedValue({ data: { items: [] } }) }
  }),
}))

vi.mock('../../services/api', () => ({
  sshKeysAPI: { getSSHConnections: vi.fn().mockResolvedValue({ data: { connections: [] } }) },
}))

const repository = { id: 1, name: 'Repo', path: '/repo', borg_version: 1 } as Repository
const archive = { id: 'a1', name: 'a1' }

describe('RestoreWizard with preselected paths', () => {
  it('skips the file step when paths are handed in', async () => {
    renderWithProviders(
      <RestoreWizard
        open
        onClose={vi.fn()}
        archive={archive}
        repository={repository}
        repositoryType="local"
        onRestore={vi.fn()}
        initialSelectedPaths={['home/karan/docs']}
      />
    )
    expect(await screen.findByRole('dialog')).toBeInTheDocument()
    expect(screen.queryByText('Select files to restore')).not.toBeInTheDocument()
    expect(BorgApiClient).not.toHaveBeenCalled()
  })

  it('starts on the file step without preselected paths', async () => {
    renderWithProviders(
      <RestoreWizard
        open
        onClose={vi.fn()}
        archive={archive}
        repository={repository}
        repositoryType="local"
        onRestore={vi.fn()}
      />
    )
    expect(await screen.findByText('Select files to restore')).toBeInTheDocument()
  })
})
