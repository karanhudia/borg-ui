import type { Meta, StoryObj } from '@storybook/react-vite'
import { expect, fn, userEvent, within } from 'storybook/test'
import RevealPassphraseDialog from './RevealPassphraseDialog'

const revealed = {
  passphrase: 'EXAMPLE-generated-passphrase-not-real-0123',
  encryption: 'repokey',
  has_keyfile: false,
}

const meta: Meta<typeof RevealPassphraseDialog> = {
  title: 'Repositories/RevealPassphraseDialog',
  component: RevealPassphraseDialog,
  args: {
    open: true,
    repositoryName: 'Photos',
    reauth: 'password',
    onReveal: fn(async () => revealed),
    onAcknowledge: fn(async () => undefined),
    onDownloadKeyfile: fn(),
    onClose: fn(),
  },
}
export default meta
type Story = StoryObj<typeof RevealPassphraseDialog>

export const PasswordReauth: Story = {}

export const RepositoryNameReauth: Story = { args: { reauth: 'name' } }

export const WrongPassword: Story = {
  args: {
    onReveal: fn(async () => {
      throw { response: { data: { detail: { key: 'backend.errors.repo.reauthFailed' } } } }
    }),
  },
  play: async () => {
    const body = within(document.body)
    // Enter submits the form, so the play does not depend on the dialog's
    // enter transition having finished.
    await userEvent.type(await body.findByLabelText('Your password'), 'wrong{enter}')
    await expect(await body.findByRole('alert')).toBeInTheDocument()
  },
}

export const RevealedRepokey: Story = { args: { initialRevealed: revealed } }

export const RevealedKeyfile: Story = {
  args: { initialRevealed: { ...revealed, encryption: 'keyfile', has_keyfile: true } },
}
