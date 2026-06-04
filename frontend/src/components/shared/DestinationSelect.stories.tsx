import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { Cloud, HardDrive, Laptop } from 'lucide-react'

import DestinationSelect, { type DestinationOption } from './DestinationSelect'

const destinations: DestinationOption[] = [
  {
    key: 'server',
    icon: <HardDrive size={16} />,
    label: 'Borg UI server',
    description: 'Store backups on the server running Borg UI',
  },
  {
    key: 'remote',
    icon: <Cloud size={16} />,
    label: 'Remote machine',
    description: 'Use an SSH connection as the backup target',
  },
  {
    key: 'agent',
    icon: <Laptop size={16} />,
    label: 'Managed agent',
    description: 'Run backups on an enrolled agent machine',
  },
]

const destinationsWithDisabledRemote = destinations.map((destination) =>
  destination.key === 'remote'
    ? {
        ...destination,
        description: 'Add an SSH connection before selecting this destination',
        disabled: true,
      }
    : destination
)

const meta = {
  title: 'Components/DestinationSelect',
  component: DestinationSelect,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof DestinationSelect>

export default meta

type Story = StoryObj<typeof meta>

function DestinationSelectPreview({
  initialValue = 'server',
  options = destinations,
  disabled = false,
  width = 420,
}: {
  initialValue?: string
  options?: DestinationOption[]
  disabled?: boolean
  width?: number
}) {
  const [value, setValue] = useState(initialValue)

  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <DestinationSelect
        value={value}
        onChange={setValue}
        destinations={options}
        label="Destination"
        disabled={disabled}
      />
    </Box>
  )
}

export const RepositoryDestinations: Story = {
  args: {
    value: 'server',
    onChange: () => {},
    destinations,
    label: 'Destination',
  },
  render: (args) => (
    <DestinationSelectPreview initialValue={args.value} options={args.destinations} />
  ),
}

export const RemoteUnavailable: Story = {
  args: {
    value: 'server',
    onChange: () => {},
    destinations: destinationsWithDisabledRemote,
    label: 'Destination',
  },
  render: (args) => (
    <DestinationSelectPreview initialValue={args.value} options={args.destinations} />
  ),
}

export const DisabledControl: Story = {
  args: {
    value: 'agent',
    onChange: () => {},
    destinations,
    label: 'Destination',
    disabled: true,
  },
  render: (args) => (
    <DestinationSelectPreview
      initialValue={args.value}
      options={args.destinations}
      disabled={args.disabled}
    />
  ),
}
