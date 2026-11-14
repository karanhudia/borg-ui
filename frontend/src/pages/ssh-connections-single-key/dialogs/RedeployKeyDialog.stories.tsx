import type { Meta, StoryObj } from '@storybook/react-vite'
import type { TFunction } from 'i18next'
import { fn } from 'storybook/test'
import i18n from '../../../i18n'
import type { SSHConnection } from '../types'
import { RedeployKeyDialog } from './RedeployKeyDialog'

const connection: SSHConnection = {
  id: 5,
  ssh_key_id: 2,
  ssh_key_name: 'borgserver-repo1',
  host: 'repo1.example',
  username: 'borg',
  port: 22,
  use_sftp_mode: true,
  use_sudo: false,
  status: 'failed',
  created_at: '2026-06-01T10:00:00.000Z',
}

const meta = {
  title: 'Remote Machines/RedeployKeyDialog',
  component: RedeployKeyDialog,
  parameters: { layout: 'fullscreen' },
  args: {
    t: i18n.t.bind(i18n) as TFunction,
    open: true,
    setOpen: fn(),
    selectedConnection: connection,
    setSelectedConnection: fn(),
    redeployPassword: '',
    setRedeployPassword: fn(),
    pending: false,
    onConfirmRedeploy: fn(),
  },
} satisfies Meta<typeof RedeployKeyDialog>

export default meta

type Story = StoryObj<typeof meta>

export const ConnectionKey: Story = {}
