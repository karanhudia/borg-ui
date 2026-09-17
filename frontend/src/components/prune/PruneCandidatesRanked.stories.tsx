import type { Meta, StoryObj } from '@storybook/react-vite'
import PruneCandidatesRanked from './PruneCandidatesRanked'
import type { PrunePreviewArchive } from '../../types/archives'

const archive = (
  id: number,
  name: string,
  size: number | null,
  stale = false
): PrunePreviewArchive => ({
  id,
  borg_id: `${id}`,
  name,
  series: 'nas',
  start: '2026-09-01T02:00:00',
  verdict: 'deleted',
  rule: null,
  deduplicated_size: size,
  stats_measured_at: stale ? null : '2026-09-17T09:00:00',
  stale,
})

const meta = {
  title: 'Components/Prune/PruneCandidatesRanked',
  component: PruneCandidatesRanked,
} satisfies Meta<typeof PruneCandidatesRanked>

export default meta
type Story = StoryObj<typeof meta>

export const Default: Story = {
  args: {
    archives: [
      archive(1, 'nas-2026-09-01', 30_000_000_000),
      archive(2, 'nas-2026-08-31', 12_000_000_000),
      archive(3, 'nas-2026-08-30', 4_000_000_000),
    ],
    partialMeasure: false,
    onOpen: () => {},
  },
}

export const PartialAndStale: Story = {
  args: {
    archives: [
      archive(1, 'nas-2026-09-01', 30_000_000_000),
      archive(2, 'nas-2026-08-31', null, true),
    ],
    partialMeasure: true,
    onOpen: () => {},
  },
}
