import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveHourlyHeatmap from './ArchiveHourlyHeatmap'
import type { ArchiveRow } from '../../types/archives'

const rows: ArchiveRow[] = []
const now = new Date()
let id = 1
for (let dayOffset = 27; dayOffset >= 0; dayOffset--) {
  for (const hour of [1, 7, 13, 19]) {
    if ((dayOffset + hour) % 9 === 0) continue
    const start = new Date(now)
    start.setDate(now.getDate() - dayOffset)
    start.setHours(hour, 5, 0, 0)
    rows.push({
      id: id++,
      repository_id: 1,
      borg_id: `b${id}`,
      name: `db-${start.toISOString().slice(0, 16)}`,
      series: 'db-every-6h',
      start: start.toISOString().replace('Z', ''),
      end: null,
      duration_seconds: 120,
      nfiles: 40,
      original_size: 5_000_000,
      compressed_size: 4_000_000,
      deduplicated_size: 200_000,
      hostname: 'db1',
      username: 'root',
      comment: null,
      backup_operation_id: null,
      history_state: 'indexed',
      history_indexed_at: null,
      history_rows: 0,
      history_truncated: false,
      first_seen_at: null,
      last_seen_at: null,
    })
  }
}

const meta = {
  title: 'Components/Archives/ArchiveHourlyHeatmap',
  component: ArchiveHourlyHeatmap,
  args: { onSelectArchive: () => {} },
} satisfies Meta<typeof ArchiveHourlyHeatmap>

export default meta

type Story = StoryObj<typeof meta>

export const EverySixHours: Story = { args: { archives: rows } }
export const Empty: Story = { args: { archives: [] } }
