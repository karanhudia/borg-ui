import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveStatsHeader from './ArchiveStatsHeader'
import type { ArchiveDetailResponse } from '../../types/archives'

const archive: ArchiveDetailResponse = {
  id: 12,
  repository_id: 7,
  borg_id: 'abc123',
  name: 'nas-2026-09-02T02:00',
  series: 'nightly',
  start: '2026-09-02T02:00:00Z',
  end: '2026-09-02T02:14:00Z',
  duration_seconds: 840,
  nfiles: 12000,
  original_size: 90_000_000_000,
  compressed_size: 60_000_000_000,
  deduplicated_size: 41_200_000_000,
  stats_measured_at: '2026-09-02T02:20:00Z',
  hostname: 'nas',
  username: 'root',
  comment: null,
  backup_operation_id: 55,
  history_state: 'indexed',
  history_indexed_at: '2026-09-02T02:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-09-02T02:00:00Z',
  last_seen_at: '2026-09-02T02:00:00Z',
  predecessor_id: 11,
  successor_id: null,
  predecessor_stats: {
    id: 11,
    nfiles: 11000,
    original_size: 80_000_000_000,
    deduplicated_size: 30_000_000_000,
    duration_seconds: 900,
  },
  history_available: true,
}

const meta = {
  title: 'Components/Archives/ArchiveStatsHeader',
  component: ArchiveStatsHeader,
} satisfies Meta<typeof ArchiveStatsHeader>

export default meta
type Story = StoryObj<typeof meta>

export const Pro: Story = {
  args: { archive, totals: { added: 5, removed: 2, modified: 9 }, totalsState: 'ready' },
}
// The counts are Community too; only the file list behind them is Pro.
export const NotIndexed: Story = { args: { archive, totalsState: 'not_indexed' } }
export const Stale: Story = {
  args: {
    archive: { ...archive, stats_measured_at: null },
    totalsState: 'ready',
    totals: { added: 0, removed: 0, modified: 0 },
  },
}
export const NeverMeasured: Story = {
  args: {
    archive: {
      ...archive,
      stats_measured_at: null,
      original_size: null,
      compressed_size: null,
      deduplicated_size: null,
      nfiles: null,
      duration_seconds: null,
    },
    totalsState: 'not_indexed',
  },
}
export const Borg2FirstOfSeries: Story = {
  args: {
    archive: { ...archive, compressed_size: null, predecessor_stats: null, predecessor_id: null },
    totalsState: 'ready',
    totals: { added: 12000, removed: 0, modified: 0 },
  },
}
