import type { JSX } from 'react'
import type { TFunction } from 'i18next'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import i18n from '../../../i18n'
import type { SSHHostKeyResponse } from '../../../services/api'
import type { SSHConnection } from '../types'
import { HostKeyDialog } from './HostKeyDialog'

const t = i18n.t.bind(i18n) as TFunction

const connection: SSHConnection = {
  id: 1,
  ssh_key_id: 1,
  ssh_key_name: 'System key',
  host: 'storage.example.com',
  username: 'borg',
  port: 2222,
  use_sftp_mode: true,
  use_sudo: false,
  status: 'connected',
  created_at: '2026-01-01T00:00:00Z',
}

const OBSERVED = 'SHA256:Zx9Q3n1sKk2Yy8bV0pRfT4uJ6mE7cD1aS5gH2wN0qLk'
const PINNED = 'SHA256:Ab1Cd2Ef3Gh4Ij5Kl6Mn7Op8Qr9St0Uv1Wx2Yz3A4B5'

function HostKeyDialogStory({
  hostKey,
  loading = false,
}: {
  hostKey: SSHHostKeyResponse | null
  loading?: boolean
}): JSX.Element {
  return (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <HostKeyDialog
        t={t}
        open
        onClose={() => {}}
        connection={connection}
        hostKey={hostKey}
        loading={loading}
        pending={false}
        onTrust={() => {}}
        onForget={() => {}}
      />
    </Box>
  )
}

const meta = {
  title: 'Remote Machines/HostKeyDialog',
  component: HostKeyDialogStory,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof HostKeyDialogStory>

export default meta

type Story = StoryObj<typeof meta>

const base: SSHHostKeyResponse = {
  connection_id: connection.id,
  host: connection.host,
  port: connection.port,
  status: 'unknown',
  trusted_fingerprint: null,
  observed_fingerprint: OBSERVED,
  observed_key: 'storage.example.com ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAA',
}

export const FirstConnect: Story = {
  args: { hostKey: base },
}

export const Trusted: Story = {
  args: {
    hostKey: { ...base, status: 'trusted', trusted_fingerprint: OBSERVED },
  },
}

export const KeyChanged: Story = {
  args: {
    hostKey: { ...base, status: 'changed', trusted_fingerprint: PINNED },
  },
}

export const HostUnreachable: Story = {
  args: {
    hostKey: {
      ...base,
      status: 'unreachable',
      trusted_fingerprint: PINNED,
      observed_fingerprint: null,
      observed_key: null,
    },
  },
}

export const Loading: Story = {
  args: { hostKey: null, loading: true },
}
