import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepoSelect from './RepoSelect'
import type { Repository } from '../types'

const repositories = [
  { id: 1, name: 'nas', path: '/mnt/nas', borg_version: 1 },
  { id: 2, name: 'offsite', path: 'ssh://backup@offsite/repo', borg_version: 2 },
] as Repository[]

function Wrapper({ label }: { label?: string }) {
  const [value, setValue] = useState<number | string>('/mnt/nas')
  return (
    <Box sx={{ p: 3, maxWidth: 420 }}>
      <RepoSelect repositories={repositories} value={value} onChange={setValue} label={label} />
    </Box>
  )
}

const meta = {
  title: 'Components/RepoSelect',
} satisfies Meta<typeof RepoSelect>

export default meta

type Story = StoryObj<typeof meta>

// The labelled state: the InputLabel is tied to the select through the
// generated id, so clicking the label focuses the control.
export const Labelled: Story = {
  render: () => <Wrapper label="Repository" />,
}

export const WithoutLabel: Story = {
  render: () => <Wrapper />,
}
