import { useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useQueryClient } from '@tanstack/react-query'
import FileHistoryPanel from './FileHistoryPanel'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'
import type {
  ArchiveListResponse,
  ArchiveRow,
  HistoryEntry,
  PathHistoryResponse,
} from '../../types/archives'

const repositoryId = 7
const path = 'home/karan/docs/invoices.xlsx'
const series = 'daily'

const entry = (overrides: Partial<HistoryEntry>): HistoryEntry => ({
  archive_id: 1,
  archive_name: 'daily-2026-09-01',
  series,
  start: '2026-09-01T02:00:00Z',
  change: 'added',
  size_before: null,
  size_after: 18_432,
  mode_changed: false,
  owner_changed: false,
  ...overrides,
})

const history: PathHistoryResponse = {
  path,
  entries: [
    entry({}),
    entry({
      archive_id: 2,
      archive_name: 'daily-2026-09-03',
      start: '2026-09-03T02:00:00Z',
      change: 'modified',
      size_before: 18_432,
      size_after: 20_995,
    }),
    entry({
      archive_id: 3,
      archive_name: 'daily-2026-09-05',
      start: '2026-09-05T02:00:00Z',
      change: 'removed',
      size_before: 20_995,
      size_after: null,
    }),
  ],
  present: [{ series, from_archive_id: 1, to_archive_id: 2 }],
  present_in_latest: false,
}

const archive = (id: number, name: string, start: string): ArchiveRow => ({
  id,
  repository_id: repositoryId,
  borg_id: `borg-${id}`,
  name,
  series,
  start,
  end: null,
  duration_seconds: null,
  nfiles: null,
  original_size: null,
  compressed_size: null,
  deduplicated_size: null,
  hostname: null,
  username: null,
  comment: null,
  backup_operation_id: null,
  history_state: 'indexed',
  history_indexed_at: null,
  history_rows: null,
  history_truncated: false,
  first_seen_at: null,
  last_seen_at: null,
})

const seriesArchives: ArchiveListResponse = {
  archives: [
    archive(1, 'daily-2026-09-01', '2026-09-01T02:00:00Z'),
    archive(2, 'daily-2026-09-03', '2026-09-03T02:00:00Z'),
    archive(3, 'daily-2026-09-05', '2026-09-05T02:00:00Z'),
  ],
  series: [series],
  sync_state: 'fresh',
  last_synced_at: '2026-09-05T02:10:00Z',
  history_available: true,
}

// The panel reads both of its queries through react-query, so the stories seed
// the preview's own client rather than reaching for a backend Storybook has
// none of. Without data the panel renders nothing and the snapshot run times
// out waiting for a visible root.
function SeededHistory({ children }: { children: ReactNode }) {
  const queryClient = useQueryClient()
  useState(() => {
    queryClient.setQueryData(['path-history', repositoryId, path], history)
    queryClient.setQueryData(['archive-series-for-history', repositoryId, series], seriesArchives)
    return null
  })
  return <>{children}</>
}

const meta = {
  title: 'Components/Archives/FileHistoryPanel',
  component: FileHistoryPanel,
  args: {
    repositoryId,
    path,
    onRestoreEntry: () => {},
  },
  decorators: [
    (Story) => (
      <SeededHistory>
        <Story />
      </SeededHistory>
    ),
  ],
} satisfies Meta<typeof FileHistoryPanel>

export default meta

type Story = StoryObj<typeof meta>

export const Unlocked: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
}

export const Locked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
}
