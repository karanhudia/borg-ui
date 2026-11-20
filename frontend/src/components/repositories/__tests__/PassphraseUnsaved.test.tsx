import { describe, expect, it, vi } from 'vitest'
import { screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { renderWithProviders } from '../../../test/test-utils'
import PassphraseUnsavedBanner from '../PassphraseUnsavedBanner'
import RevealPassphraseDialog from '../RevealPassphraseDialog'

vi.mock('../../../utils/clipboard', () => ({ copyText: vi.fn().mockResolvedValue(true) }))

const revealed = {
  passphrase: 'example-generated-passphrase',
  encryption: 'repokey',
  has_keyfile: false,
}

describe('PassphraseUnsavedBanner', () => {
  it('lists only flagged repositories with a reveal button each', async () => {
    const onReveal = vi.fn()
    renderWithProviders(
      <PassphraseUnsavedBanner
        repositories={[
          { id: 1, name: 'Photos', passphrase_unsaved: true },
          { id: 2, name: 'Documents', passphrase_unsaved: false },
        ]}
        onReveal={onReveal}
      />
    )
    expect(screen.getByText(/Photos/)).toBeInTheDocument()
    expect(screen.queryByText(/Documents/)).not.toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: 'Reveal passphrase of Photos' }))
    expect(onReveal).toHaveBeenCalledWith(1)
  })

  it('renders nothing when no passphrase is unsaved', () => {
    renderWithProviders(
      <PassphraseUnsavedBanner repositories={[{ id: 2, name: 'Documents' }]} onReveal={vi.fn()} />
    )
    expect(screen.queryByRole('alert')).not.toBeInTheDocument()
  })
})

describe('RevealPassphraseDialog', () => {
  const base = {
    open: true,
    repositoryName: 'Photos',
    onClose: vi.fn(),
    onDownloadKeyfile: vi.fn(),
  }

  it('asks a local user for their password', async () => {
    const onReveal = vi.fn().mockResolvedValue(revealed)
    renderWithProviders(
      <RevealPassphraseDialog
        {...base}
        reauth="password"
        onReveal={onReveal}
        onAcknowledge={vi.fn()}
      />
    )
    await userEvent.type(screen.getByLabelText('Your password'), 'pw')
    await userEvent.click(screen.getByRole('button', { name: 'Show passphrase' }))
    expect(onReveal).toHaveBeenCalledWith({ password: 'pw' })
    expect(await screen.findByText('example-generated-passphrase')).toBeInTheDocument()
  })

  it('asks a single sign-on user to type the repository name', async () => {
    const onReveal = vi.fn().mockResolvedValue(revealed)
    renderWithProviders(
      <RevealPassphraseDialog {...base} reauth="name" onReveal={onReveal} onAcknowledge={vi.fn()} />
    )
    await userEvent.type(screen.getByLabelText('Repository name'), 'Photos')
    await userEvent.click(screen.getByRole('button', { name: 'Show passphrase' }))
    expect(onReveal).toHaveBeenCalledWith({ repository_name: 'Photos' })
  })

  it('shows the error and no passphrase when re-authentication fails', async () => {
    const onReveal = vi.fn().mockRejectedValue({
      response: { data: { detail: { key: 'backend.errors.repo.reauthFailed' } } },
    })
    renderWithProviders(
      <RevealPassphraseDialog
        {...base}
        reauth="password"
        onReveal={onReveal}
        onAcknowledge={vi.fn()}
      />
    )
    await userEvent.type(screen.getByLabelText('Your password'), 'wrong')
    await userEvent.click(screen.getByRole('button', { name: 'Show passphrase' }))
    expect(await screen.findByRole('alert')).toHaveTextContent('That did not match')
    expect(screen.queryByText('example-generated-passphrase')).not.toBeInTheDocument()
  })

  it('closing after the reveal does not acknowledge', async () => {
    const onAcknowledge = vi.fn()
    const onClose = vi.fn()
    renderWithProviders(
      <RevealPassphraseDialog
        {...base}
        onClose={onClose}
        reauth="password"
        onReveal={vi.fn()}
        onAcknowledge={onAcknowledge}
        initialRevealed={revealed}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: 'Close' }))
    expect(onClose).toHaveBeenCalled()
    expect(onAcknowledge).not.toHaveBeenCalled()
  })

  it("I've saved it acknowledges and closes", async () => {
    const onAcknowledge = vi.fn().mockResolvedValue(undefined)
    const onClose = vi.fn()
    renderWithProviders(
      <RevealPassphraseDialog
        {...base}
        onClose={onClose}
        reauth="password"
        onReveal={vi.fn()}
        onAcknowledge={onAcknowledge}
        initialRevealed={revealed}
      />
    )
    await userEvent.click(screen.getByRole('button', { name: "I've saved it" }))
    await waitFor(() => expect(onAcknowledge).toHaveBeenCalled())
    expect(onClose).toHaveBeenCalled()
  })

  it('offers the keyfile download for keyfile repositories', async () => {
    const onDownloadKeyfile = vi.fn()
    renderWithProviders(
      <RevealPassphraseDialog
        {...base}
        onDownloadKeyfile={onDownloadKeyfile}
        reauth="password"
        onReveal={vi
          .fn()
          .mockResolvedValue({ ...revealed, encryption: 'keyfile', has_keyfile: true })}
        onAcknowledge={vi.fn()}
      />
    )
    await userEvent.type(screen.getByLabelText('Your password'), 'pw')
    await userEvent.click(screen.getByRole('button', { name: 'Show passphrase' }))
    await userEvent.click(await screen.findByRole('button', { name: 'Download keyfile' }))
    expect(onDownloadKeyfile).toHaveBeenCalled()
  })
})
