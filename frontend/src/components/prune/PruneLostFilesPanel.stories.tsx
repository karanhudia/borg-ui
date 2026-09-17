import type { Meta, StoryObj } from '@storybook/react-vite'
import PruneLostFilesPanel from './PruneLostFilesPanel'

const meta = {
  title: 'Components/Prune/PruneLostFilesPanel',
  component: PruneLostFilesPanel,
} satisfies Meta<typeof PruneLostFilesPanel>

export default meta
type Story = StoryObj<typeof meta>

export const Available: Story = {
  args: {
    repositoryId: 7,
    lost: {
      available: true,
      capability: 'available',
      incomplete: false,
      unindexed_archive_ids: [],
      total_count: 2,
      total_size: 30_000_000,
      top: [
        {
          path: 'srv/media/raw/show1.mkv',
          size: 20_000_000,
          series: 'nas',
          last_held_archive_id: 4,
          last_held_archive_name: 'nas-2026-08-30',
        },
        {
          path: 'srv/media/raw/show2.mkv',
          size: 10_000_000,
          series: 'nas',
          last_held_archive_id: 4,
          last_held_archive_name: 'nas-2026-08-30',
        },
      ],
      by_folder: [{ folder: 'srv/media/raw', count: 2, size: 30_000_000 }],
    },
  },
}

export const Incomplete: Story = {
  args: {
    repositoryId: 7,
    lost: {
      available: true,
      capability: 'available',
      incomplete: true,
      unindexed_archive_ids: [3, 4],
      total_count: 0,
      total_size: 0,
      top: [],
      by_folder: [],
    },
  },
}

export const AgentUnsupported: Story = {
  args: {
    repositoryId: 7,
    lost: { available: false, capability: 'agent_unsupported' },
  },
}

export const Empty: Story = {
  args: {
    repositoryId: 7,
    lost: {
      available: true,
      capability: 'available',
      incomplete: false,
      unindexed_archive_ids: [],
      total_count: 0,
      total_size: 0,
      top: [],
      by_folder: [],
    },
  },
}
