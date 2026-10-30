import type { Meta, StoryObj } from '@storybook/react-vite'
import { fn } from 'storybook/test'
import type { SSHConnection, SSHKeySummary } from '../types'
import { DeleteExtraKeyDialog } from './DeleteExtraKeyDialog'

const sshKey: SSHKeySummary = {
  id: 2,
  name: 'borgserver-repo1',
  key_type: 'ed25519',
  fingerprint: 'SHA256:9a77d1c4e0b2f6a8',
  is_system_key: false,
  connection_count: 2,
}

const connection = (id: number, host: string): SSHConnection => ({
  id,
  ssh_key_id: sshKey.id,
  ssh_key_name: sshKey.name,
  host,
  username: 'borg',
  port: 22,
  use_sftp_mode: true,
  use_sudo: false,
  status: 'connected',
  created_at: '2026-06-01T10:00:00.000Z',
})

const meta = {
  title: 'Remote Machines/DeleteExtraKeyDialog',
  component: DeleteExtraKeyDialog,
  parameters: { layout: 'fullscreen' },
  args: { sshKey, connectionsUsingKey: [], onClose: fn(), onDelete: fn() },
} satisfies Meta<typeof DeleteExtraKeyDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Unused: Story = {}

/** Deleting is blocked while connections use the key; the backend refuses it too. */
export const InUse: Story = {
  args: {
    connectionsUsingKey: [connection(1, 'repo1.borgserver.example'), connection(2, 'nas.example')],
  },
}
