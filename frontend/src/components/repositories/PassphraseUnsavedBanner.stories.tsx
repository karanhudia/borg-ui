import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import PassphraseUnsavedBanner from './PassphraseUnsavedBanner'

const meta: Meta<typeof PassphraseUnsavedBanner> = {
  title: 'Repositories/PassphraseUnsavedBanner',
  component: PassphraseUnsavedBanner,
  args: { onReveal: fn() },
}
export default meta
type Story = StoryObj<typeof PassphraseUnsavedBanner>

export const OneRepository: Story = {
  args: { repositories: [{ id: 1, name: 'Photos', passphrase_unsaved: true }] },
}

export const ThreeRepositories: Story = {
  args: {
    repositories: [
      { id: 1, name: 'Photos', passphrase_unsaved: true },
      { id: 2, name: 'Postgres nightly dumps on the example NAS', passphrase_unsaved: true },
      { id: 3, name: 'Documents', passphrase_unsaved: true },
      { id: 4, name: 'Saved already', passphrase_unsaved: false },
    ],
  },
}
