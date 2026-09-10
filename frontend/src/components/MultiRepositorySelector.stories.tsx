import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MultiRepositorySelector from './MultiRepositorySelector'
import type { Repository } from '../types'

const repositories = [
  { id: 1, name: 'NAS', path: '/mnt/nas/borg', borg_version: 1, mode: 'full' },
  { id: 2, name: 'rsync.net', path: 'ssh://rsync.net/borg', borg_version: 1, mode: 'full' },
  { id: 3, name: 'USB Drive', path: '/Volumes/usb/borg', borg_version: 2, mode: 'full' },
] as Repository[]

function SkipToggleSelector() {
  const [ids, setIds] = useState([1, 2, 3])
  const [disabledIds, setDisabledIds] = useState([2])
  return (
    <Box sx={{ p: 3, maxWidth: 640 }}>
      <MultiRepositorySelector
        repositories={repositories}
        selectedIds={ids}
        onChange={setIds}
        allowReorder
        disabledIds={disabledIds}
        onToggleEnabled={(id) =>
          setDisabledIds((prev) =>
            prev.includes(id) ? prev.filter((item) => item !== id) : [...prev, id]
          )
        }
        label="Repositories"
        helperText="Select one or more repositories. Execution order is used in series mode."
      />
    </Box>
  )
}

const meta = {
  title: 'Components/MultiRepositorySelector',
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const SkipToggle: Story = {
  render: () => <SkipToggleSelector />,
}
