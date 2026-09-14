import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryStats from './RepositoryStats'

const meta = {
  title: 'Components/RepositoryStats',
  component: RepositoryStats,
  decorators: [
    (Story) => (
      <Box sx={{ width: 760, maxWidth: '100%' }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof RepositoryStats>
export default meta
type Story = StoryObj<typeof meta>

export const Borg2Measured: Story = {
  args: {
    borgVersion: 2,
    archiveCount: 35,
    storage: {
      size_bytes: 2523293286,
      size_source: 'borg2_index',
      measured_at: '2026-09-14T10:00:00Z',
      last_modified: '2026-09-14T09:30:00Z',
      archives_consistent: true,
      original_size: 10830000000,
      compressed_size: null,
      deduplicated_size: 3200000000,
      latest_archive_files: 881,
      compact: {
        original_size: 10830000000,
        deduplicated_size: 3200000000,
        compression_factor: 1.3,
      },
      compact_at: '2026-09-14T10:00:00Z',
    },
    compact: true,
  },
}
export const Unknown: Story = { args: { borgVersion: 2, archiveCount: 0, storage: null } }
export const Borg2NotReported: Story = {
  args: {
    borgVersion: 2,
    archiveCount: 1,
    storage: {
      size_bytes: 0,
      size_source: 'compact_stats',
      measured_at: '2026-09-14T10:00:00Z',
      last_modified: null,
      archives_consistent: true,
      original_size: null,
      compressed_size: null,
      deduplicated_size: null,
      latest_archive_files: null,
      compact: null,
      compact_at: null,
    },
  },
}
