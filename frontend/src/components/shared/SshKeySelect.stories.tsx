import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import SshKeySelect, { type SshKeyOptionSummary } from './SshKeySelect'

const keys: SshKeyOptionSummary[] = [
  {
    id: 1,
    name: 'System SSH Key',
    key_type: 'ed25519',
    fingerprint: 'SHA256:3b1f9c0d7a42e8b5',
    is_system_key: true,
  },
  {
    id: 2,
    name: 'borgserver-repo1',
    key_type: 'ed25519',
    fingerprint: 'SHA256:9a77d1c4e0b2f6a8',
  },
  {
    id: 3,
    name: 'rsync-net-restricted',
    key_type: 'rsa',
    fingerprint: 'SHA256:c04e5b8d12f3a9e7',
  },
]

const meta = {
  title: 'Components/SshKeySelect',
  component: SshKeySelect,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof SshKeySelect>

export default meta

type Story = StoryObj<typeof meta>

function Preview({ initial, width = 420 }: { initial: number | ''; width?: number }) {
  const [value, setValue] = useState<number | ''>(initial)
  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <SshKeySelect value={value} onChange={setValue} keys={keys} />
    </Box>
  )
}

export const SystemKeySelected: Story = {
  args: { value: 1, onChange: () => {}, keys },
  render: () => <Preview initial={1} />,
}

export const ExtraKeySelected: Story = {
  args: { value: 2, onChange: () => {}, keys },
  render: () => <Preview initial={2} />,
}

export const NarrowWidth: Story = {
  args: { value: 3, onChange: () => {}, keys },
  render: () => <Preview initial={3} width={280} />,
}
