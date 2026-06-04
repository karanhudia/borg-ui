import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import RcloneRemoteSelect, { type RcloneRemoteSummary } from './RcloneRemoteSelect'

const remotes: RcloneRemoteSummary[] = [
  {
    id: 3,
    name: 'GoogleDrive',
    provider: 'drive',
    last_test_status: 'connected',
  },
  {
    id: 4,
    name: 's3-archive',
    provider: 's3',
    last_test_status: 'success',
  },
]

const meta = {
  title: 'Components/RcloneRemoteSelect',
  component: RcloneRemoteSelect,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RcloneRemoteSelect>

export default meta

type Story = StoryObj<typeof meta>

function RcloneRemoteSelectPreview({
  initialValue = 3,
  options = remotes,
  disabled = false,
  width = 420,
}: {
  initialValue?: number | ''
  options?: RcloneRemoteSummary[]
  disabled?: boolean
  width?: number
}) {
  const [value, setValue] = useState<number | ''>(initialValue)

  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <RcloneRemoteSelect
        value={value}
        onChange={setValue}
        remotes={options}
        label="Rclone Remote"
        emptyMessage="No rclone remotes configured."
        disabled={disabled}
      />
    </Box>
  )
}

export const ConfiguredRemote: Story = {
  args: {
    value: 3,
    onChange: () => {},
    remotes,
    label: 'Rclone Remote',
    emptyMessage: 'No rclone remotes configured.',
  },
  render: (args) => <RcloneRemoteSelectPreview initialValue={args.value} options={args.remotes} />,
}

export const EmptyState: Story = {
  args: {
    value: '',
    onChange: () => {},
    remotes: [],
    label: 'Rclone Remote',
    emptyMessage: 'No rclone remotes configured.',
  },
  render: (args) => <RcloneRemoteSelectPreview initialValue="" options={args.remotes} />,
}

export const DisabledControl: Story = {
  args: {
    value: 4,
    onChange: () => {},
    remotes,
    label: 'Rclone Remote',
    emptyMessage: 'No rclone remotes configured.',
    disabled: true,
  },
  render: (args) => (
    <RcloneRemoteSelectPreview
      initialValue={args.value}
      options={args.remotes}
      disabled={args.disabled}
    />
  ),
}
