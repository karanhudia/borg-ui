import { beforeEach, describe, expect, it, vi } from 'vitest'

import { backupPlansAPI } from '../../../services/api'
import { BorgApiClient } from '../../../services/borgApi'
import { renderWithProviders, screen, userEvent, waitFor } from '../../../test/test-utils'
import QuickStartDialog from '../QuickStartDialog'

vi.mock('../../../services/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../services/api')>()
  return {
    ...actual,
    backupPlansAPI: { ...actual.backupPlansAPI, create: vi.fn(), run: vi.fn() },
  }
})
vi.mock('../../../services/borgApi', () => ({
  BorgApiClient: { createRepository: vi.fn() },
}))

describe('QuickStartDialog', () => {
  beforeEach(() => {
    vi.mocked(BorgApiClient.createRepository).mockResolvedValue({ data: { id: 4 } } as never)
    vi.mocked(backupPlansAPI.create).mockResolvedValue({ data: { id: 9 } } as never)
  })

  it('walks a local setup and creates the repository and plan', async () => {
    const user = userEvent.setup()
    renderWithProviders(<QuickStartDialog open onClose={() => {}} />)

    const next = () => user.click(screen.getByRole('button', { name: 'Next' }))

    expect(screen.getByRole('radio', { name: /Files on this server/ })).toBeChecked()
    await next()

    const nextButton = screen.getByRole('button', { name: 'Next' })
    expect(nextButton).toBeDisabled()
    await user.type(screen.getByLabelText('Folder'), '/local/home{Enter}')
    await next()

    // The name and location are suggested from the first folder.
    expect(screen.getByLabelText(/Backup location/)).toHaveValue('/local/borg-backups/home')
    await next()

    expect(screen.getByLabelText(/^Name/)).toHaveValue('home')
    await user.type(screen.getByLabelText(/^Passphrase/), 'correct horse')
    await user.type(screen.getByLabelText(/Repeat passphrase/), 'correct horse')
    expect(screen.getByRole('button', { name: 'Next' })).toBeDisabled()
    await user.click(screen.getByLabelText(/I have saved my passphrase/))
    await next()

    expect(screen.getByRole('radio', { name: /Every day/ })).toBeChecked()
    await next()

    expect(screen.getByText('Repository "home" and backup plan "home"')).toBeInTheDocument()
    await user.click(screen.getByRole('button', { name: 'Create backup' }))

    await waitFor(() => expect(screen.getByText('Your backup is ready')).toBeInTheDocument())
    expect(BorgApiClient.createRepository).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'home', path: '/local/borg-backups/home' })
    )
    expect(backupPlansAPI.create).toHaveBeenCalledWith(
      expect.objectContaining({ name: 'home', schedule_enabled: true, run_prune_after: true })
    )
  })
})
