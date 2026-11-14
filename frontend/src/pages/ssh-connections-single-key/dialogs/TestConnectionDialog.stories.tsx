import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import { fn } from 'storybook/test'
import i18n from '../../../i18n'
import { createTestConnectionForm } from '../formDefaults'
import type { SSHKeySummary } from '../types'
import { TestConnectionDialog } from './TestConnectionDialog'

const t = i18n.t.bind(i18n) as TFunction

const systemKey: SSHKeySummary = {
  id: 1,
  name: 'System SSH Key',
  key_type: 'ed25519',
  fingerprint: 'SHA256:Zx9Q3n1sKk2Yy8bV0pRfT4uJ6mE7cD1aS5gH2wN0qLk',
  is_system_key: true,
  connection_count: 3,
}

const extraKey: SSHKeySummary = {
  id: 2,
  name: 'borgserver-repo1',
  key_type: 'ed25519',
  fingerprint: 'SHA256:9a77d1c4e0b2f6a8d3c19e55b7a0f412',
  is_system_key: false,
  connection_count: 0,
}

function TestConnectionDialogStory({ sshKeys }: { sshKeys: SSHKeySummary[] }) {
  const [form, setForm] = useState(createTestConnectionForm)
  return (
    <TestConnectionDialog
      t={t}
      open
      setOpen={fn()}
      sshKeys={sshKeys}
      systemKeyId={systemKey.id}
      testConnectionForm={form}
      setTestConnectionForm={setForm}
      setHostError={fn()}
      pending={false}
      onTest={fn()}
    />
  )
}

const meta = {
  title: 'Remote Machines/TestConnectionDialog',
  component: TestConnectionDialogStory,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof TestConnectionDialogStory>

export default meta

type Story = StoryObj<typeof meta>

export const SystemKeyOnly: Story = { args: { sshKeys: [systemKey] } }

/** The key picker appears once there is a second key, as in the deploy dialog. */
export const WithKeyPicker: Story = { args: { sshKeys: [systemKey, extraKey] } }
