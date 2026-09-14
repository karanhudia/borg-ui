import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryStatsGrid from './RepositoryStatsGrid'

const meta = {
  title: 'Archive page/RepositoryStatsGrid',
  component: RepositoryStatsGrid,
  decorators: [
    (Story) => (
      <Box sx={{ width: 1000, maxWidth: '100%' }}>
        <Story />
      </Box>
    ),
  ],
} satisfies Meta<typeof RepositoryStatsGrid>
export default meta
type Story = StoryObj<typeof meta>

export const Borg1Header: Story = {
  args: {
    borgVersion: 1,
    archivesCount: 20,
    storage: {
      size_bytes: 2_400_000_000_000,
      size_source: 'borg1_cache_stats',
      measured_at: '2026-09-14T10:00:00Z',
      last_modified: null,
      archives_consistent: true,
      original_size: 18_680_000_000_000,
      compressed_size: 16_180_000_000_000,
      deduplicated_size: 2_400_000_000_000,
      latest_archive_files: 922,
      compact: null,
      compact_at: null,
    },
  },
}
export const Borg2Header: Story = {
  args: {
    borgVersion: 2,
    archivesCount: 35,
    storage: {
      size_bytes: 2_350_000_000,
      size_source: 'borg2_index',
      measured_at: '2026-09-14T10:00:00Z',
      last_modified: null,
      archives_consistent: true,
      original_size: 10_830_000_000,
      compressed_size: null,
      deduplicated_size: null,
      latest_archive_files: 881,
      compact: null,
      compact_at: null,
    },
  },
}
