import { describe, it, expect, vi } from 'vitest'
import userEvent from '@testing-library/user-event'
import { renderWithProviders, screen } from '../../test/test-utils'
import RestoreWizard from '../RestoreWizard'
import type { Repository } from '@/types'

vi.mock('../../services/borgApi/client', () => ({
  BorgApiClient: vi.fn(function () {
    return { getArchiveContents: vi.fn().mockResolvedValue({ data: { items: [] } }) }
  }),
}))

vi.mock('../../services/api', () => ({
  sshKeysAPI: { getSSHConnections: vi.fn().mockResolvedValue({ data: { connections: [] } }) },
}))

const archive = { id: 'a1', name: 'a1' }

const renderWizard = (borgVersion: 1 | 2, onRestore = vi.fn()) =>
  renderWithProviders(
    <RestoreWizard
      open
      onClose={vi.fn()}
      archive={archive}
      repository={{ id: 1, name: 'Repo', path: '/repo', borg_version: borgVersion } as Repository}
      repositoryType="local"
      onRestore={onRestore}
      initialSelectedPaths={['home/alex/docs']}
    />
  )

// Borg 2.0.0b25 extracts only into an empty directory (#1261).
describe('RestoreWizard and existing files', () => {
  it('starts a Borg 2 restore on a custom path with the exact restore', async () => {
    const user = userEvent.setup()
    const onRestore = vi.fn()
    renderWizard(2, onRestore)
    await screen.findByRole('dialog')

    expect(screen.getByRole('radio', { name: /Custom Location/i })).toBeChecked()
    expect(screen.getByRole('radio', { name: /Exact restore \(empty directory\)/ })).toBeChecked()

    await user.type(screen.getByLabelText(/Custom Destination Path/i), '/recovery')
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Restore Files' }))

    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({
        restore_strategy: 'custom',
        custom_path: '/recovery',
        existing_files: 'refuse',
      })
    )
  })

  it('holds a Borg 2 restore to the original location until existing files are chosen', async () => {
    const user = userEvent.setup()
    const onRestore = vi.fn()
    renderWizard(2, onRestore)
    await screen.findByRole('dialog')

    await user.click(screen.getByRole('radio', { name: /Original Location/i }))
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()

    await user.click(screen.getByText('Restore into existing files'))
    expect(screen.getByRole('button', { name: 'Next' })).toBeEnabled()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Restore Files' }))

    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({ restore_strategy: 'original', existing_files: 'continue' })
    )
  })

  it('keeps the original location as the Borg 1 default', async () => {
    const user = userEvent.setup()
    const onRestore = vi.fn()
    renderWizard(1, onRestore)
    await screen.findByRole('dialog')

    expect(screen.getByRole('radio', { name: /Original Location/i })).toBeChecked()
    expect(screen.getByText(/Files at the same path are overwritten/)).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Next' }))
    await user.click(screen.getByRole('button', { name: 'Restore Files' }))

    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({ restore_strategy: 'original', existing_files: 'refuse' })
    )
  })

  it('does not let the step bar skip the choice', async () => {
    const user = userEvent.setup()
    const onRestore = vi.fn()
    renderWizard(2, onRestore)
    await screen.findByRole('dialog')

    await user.click(screen.getByRole('radio', { name: /Original Location/i }))
    await user.click(screen.getByText('Review'))

    expect(screen.queryByRole('button', { name: 'Restore Files' })).not.toBeInTheDocument()
    expect(screen.getByText(/To restore to the original location/)).toBeInTheDocument()
    expect(onRestore).not.toHaveBeenCalled()
  })

  it('still restores a whole archive through the step bar', async () => {
    const user = userEvent.setup()
    const onRestore = vi.fn()
    renderWithProviders(
      <RestoreWizard
        open
        onClose={vi.fn()}
        archive={archive}
        repository={{ id: 1, name: 'Repo', path: '/repo', borg_version: 1 } as Repository}
        repositoryType="local"
        onRestore={onRestore}
      />
    )
    await screen.findByText('Select files to restore')

    await user.click(screen.getByText('Review'))
    await user.click(screen.getByRole('button', { name: 'Restore Files' }))

    expect(onRestore).toHaveBeenCalledWith(
      expect.objectContaining({ selected_paths: [], existing_files: 'refuse' })
    )
  })
})
