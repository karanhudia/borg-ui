import type { Meta, StoryObj } from '@storybook/react-vite'
import type { Repository } from '../types'
import PermanentDeleteRepositoryDialog from './PermanentDeleteRepositoryDialog'

const repository: Repository = {
  id: 42,
  name: 'Production Archive',
  path: '/mnt/borg/production',
  repository_type: 'local',
  storage_backend: 'local',
  execution_target: 'local',
  executor_type: 'server',
  borg_version: 2,
  encryption: 'repokey-blake2',
  compression: 'zstd,6',
  mode: 'full',
}

const meta = {
  title: 'Components/PermanentDeleteRepositoryDialog',
  component: PermanentDeleteRepositoryDialog,
  parameters: {
    layout: 'centered',
  },
  args: {
    open: true,
    repository,
    isPending: false,
    onClose: () => {},
    onConfirm: () => {},
  },
} satisfies Meta<typeof PermanentDeleteRepositoryDialog>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {}

export const Deleting: Story = {
  args: {
    isPending: true,
  },
}
