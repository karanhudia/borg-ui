import { describe, expect, it, vi, beforeEach } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import PassphraseUnsavedSection from '../PassphraseUnsavedSection'
import { repositoriesAPI } from '../../../services/api'

vi.mock('../../../hooks/useAuth', () => ({
  useAuth: () => ({ user: { auth_source: 'local' }, proxyAuthEnabled: false }),
}))

const repos = [
  { id: 7, name: 'Photos', passphrase_unsaved: true },
  { id: 8, name: 'Documents', passphrase_unsaved: false },
]

describe('PassphraseUnsavedSection', () => {
  beforeEach(() => {
    vi.spyOn(repositoriesAPI, 'revealPassphrase').mockResolvedValue({
      data: {
        passphrase: 'example-generated-passphrase',
        encryption: 'repokey',
        has_keyfile: false,
      },
    } as never)
    vi.spyOn(repositoriesAPI, 'acknowledgePassphrase').mockResolvedValue({} as never)
  })

  it('opens the dialog for ?reveal=7 and cleans the URL', async () => {
    renderWithProviders(<PassphraseUnsavedSection repositories={repos} />, {
      initialRoute: '/repositories?reveal=7',
    })
    expect(await screen.findByText('Passphrase of Photos')).toBeInTheDocument()
    await waitFor(() => expect(window.location.search).toBe(''))
  })

  it('ignores ?reveal for a repository without an unsaved passphrase', () => {
    renderWithProviders(<PassphraseUnsavedSection repositories={repos} />, {
      initialRoute: '/repositories?reveal=8',
    })
    expect(screen.queryByText('Passphrase of Documents')).not.toBeInTheDocument()
  })

  it('reveals through the API and acknowledges', async () => {
    renderWithProviders(<PassphraseUnsavedSection repositories={repos} />)
    await userEvent.click(screen.getByRole('button', { name: 'Reveal passphrase of Photos' }))
    await userEvent.type(screen.getByLabelText('Your password'), 'pw')
    await userEvent.click(screen.getByRole('button', { name: 'Show passphrase' }))
    expect(repositoriesAPI.revealPassphrase).toHaveBeenCalledWith(7, { password: 'pw' })
    await userEvent.click(await screen.findByRole('button', { name: "I've saved it" }))
    await waitFor(() => expect(repositoriesAPI.acknowledgePassphrase).toHaveBeenCalledWith(7))
  })
})
