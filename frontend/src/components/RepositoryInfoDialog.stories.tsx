import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryInfoDialog from './RepositoryInfoDialog'
import type { Repository } from '../types'

const brokenRepository: Repository = {
  id: 42,
  name: 'Broken Archive',
  path: '/mnt/borg/broken',
  borg_version: 1,
  encryption: 'repokey',
  compression: 'lz4',
  mode: 'full',
}

const meta = {
  title: 'Components/RepositoryInfoDialog',
  component: RepositoryInfoDialog,
  parameters: {
    layout: 'centered',
  },
  args: {
    open: true,
    repository: brokenRepository,
    repositoryInfo: null,
    isLoading: false,
    onClose: () => {},
  },
  render: (args) => (
    <Box sx={{ width: 760, minHeight: 520 }}>
      <RepositoryInfoDialog {...args} />
    </Box>
  ),
} satisfies Meta<typeof RepositoryInfoDialog>

export default meta

type Story = StoryObj<typeof meta>

export const FailedInfoRecovery: Story = {}
