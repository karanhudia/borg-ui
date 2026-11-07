import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { fn } from 'storybook/test'
import type { SSHKeySummary } from '../types'
import { ExtraKeysCard } from './ExtraKeysCard'

const keys: SSHKeySummary[] = [
  {
    id: 2,
    name: 'borgserver-repo1',
    key_type: 'ed25519',
    fingerprint: 'SHA256:9a77d1c4e0b2f6a8d3c19e55b7a0f412',
    public_key: 'ssh-ed25519 AAAA borgserver-repo1',
    is_system_key: false,
    connection_count: 2,
  },
  {
    id: 3,
    name: 'rsync-net-restricted',
    key_type: 'rsa',
    fingerprint: 'SHA256:c04e5b8d12f3a9e7b6d84c2105ae3f90',
    public_key: 'ssh-rsa AAAA rsync-net-restricted',
    is_system_key: false,
    connection_count: 0,
  },
]

const handlers = { onAdd: fn(), onCopyPublicKey: fn(), onDelete: fn() }

const meta = {
  title: 'Remote Machines/ExtraKeysCard',
  component: ExtraKeysCard,
  parameters: { layout: 'fullscreen' },
  render: (args) => (
    <Box sx={{ p: 3, maxWidth: 720, bgcolor: 'background.default' }}>
      <ExtraKeysCard {...args} />
    </Box>
  ),
} satisfies Meta<typeof ExtraKeysCard>

export default meta

type Story = StoryObj<typeof meta>

export const Empty: Story = { args: { keys: [], ...handlers } }

export const WithKeys: Story = { args: { keys, ...handlers } }
