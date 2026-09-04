import type { Meta, StoryObj } from '@storybook/react-vite'
import SyncStateChip from './SyncStateChip'

const meta = {
  title: 'Components/Archives/SyncStateChip',
  component: SyncStateChip,
  args: {
    onRebuild: () => {},
  },
} satisfies Meta<typeof SyncStateChip>

export default meta

type Story = StoryObj<typeof meta>

export const Fresh: Story = {
  args: {
    state: 'fresh',
    lastSyncedAt: new Date(Date.now() - 120_000).toISOString(),
  },
}

export const Syncing: Story = {
  args: {
    state: 'syncing',
    lastSyncedAt: null,
  },
}

export const Stale: Story = {
  args: {
    state: 'stale',
    lastSyncedAt: new Date(Date.now() - 86_400_000 * 3).toISOString(),
  },
}

export const Never: Story = {
  args: {
    state: 'never',
    lastSyncedAt: null,
  },
}
