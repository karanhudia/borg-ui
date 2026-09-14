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
    onRunRecoveryCheck: () => {},
    canRunRecoveryCheck: true,
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

export const FailedInfoRecoveryUnavailable: Story = {
  args: {
    canRunRecoveryCheck: false,
  },
}

export const FailedInfoWithAgentReason: Story = {
  args: {
    errorMessage:
      "repository.info exited with code 2: Failed to create/acquire the lock /mnt/borg/broken/lock.exclusive ([Errno 13] Permission denied: '/mnt/borg/broken/lock.exclusive.5ic2kcji.tmp').",
  },
}
