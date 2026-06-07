import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Chip } from '@mui/material'
import { Cloud, HardDrive, Laptop } from 'lucide-react'
import RichSelect, { type RichSelectOption } from './RichSelect'

const options: RichSelectOption[] = [
  {
    value: 'server',
    icon: <HardDrive size={16} />,
    primary: 'Borg UI server',
    secondary: 'Store backups on the server running Borg UI',
    group: 'Local',
  },
  {
    value: 'remote',
    icon: <Cloud size={16} />,
    primary: 'Koofr, Digi Storage and other Koofr-compatible storage providers',
    secondary: 'Use an SSH connection as the backup target',
    group: 'Remote',
    indicator: (
      <Chip size="small" label="SSH" variant="outlined" sx={{ height: 20, fontSize: '0.65rem' }} />
    ),
  },
  {
    value: 'agent',
    icon: <Laptop size={16} />,
    primary: 'Managed agent',
    secondary: 'Run backups on an enrolled agent machine',
    group: 'Remote',
  },
]

const meta = {
  title: 'Components/RichSelect',
  component: RichSelect,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RichSelect>

export default meta

type Story = StoryObj<typeof meta>

function RichSelectPreview({
  initialValue = 'remote',
  width = 420,
  searchEnabled = false,
}: {
  initialValue?: string
  width?: number
  searchEnabled?: boolean
}) {
  const [value, setValue] = useState(initialValue)

  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <RichSelect
        value={value}
        onChange={setValue}
        options={options}
        label="Destination"
        searchEnabled={searchEnabled}
        searchPlaceholder="Search destinations"
      />
    </Box>
  )
}

export const Default: Story = {
  args: {
    value: 'remote',
    onChange: () => {},
    options,
    label: 'Destination',
  },
  render: (args) => <RichSelectPreview initialValue={args.value} />,
}

export const SearchEnabled: Story = {
  args: {
    value: 'remote',
    onChange: () => {},
    options,
    label: 'Destination',
    searchEnabled: true,
  },
  render: (args) => <RichSelectPreview initialValue={args.value} searchEnabled />,
}

export const NarrowWidth: Story = {
  args: {
    value: 'remote',
    onChange: () => {},
    options,
    label: 'Destination',
    searchEnabled: true,
  },
  render: (args) => <RichSelectPreview initialValue={args.value} width={280} searchEnabled />,
}
