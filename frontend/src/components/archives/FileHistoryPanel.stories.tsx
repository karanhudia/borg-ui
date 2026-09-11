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

const archive = (
  id: number,
  name: string,
  start: string,
  overrides: Partial<ArchiveRow> = {}
): ArchiveRow => ({
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
  ...overrides,
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

// The panel says what its answer is based on. A repository executed by an
// agent has no index at all (the server cannot diff it), and a repository
// indexed only in part covers the indexed archives only; both seed a
// history of their own under a different path so the decorator's full
// index is left alone.
function SeededCoverage({
  children,
  storyPath,
  response,
  listing,
}: {
  children: ReactNode
  storyPath: string
  response: PathHistoryResponse
  listing?: { series: string; response: ArchiveListResponse }
}) {
  const queryClient = useQueryClient()
  useState(() => {
    queryClient.setQueryData(['path-history', repositoryId, storyPath], response)
    if (listing) {
      queryClient.setQueryData(
        ['archive-series-for-history', repositoryId, listing.series],
        listing.response
      )
    }
    return null
  })
  return <>{children}</>
}

const agentPath = 'etc/hosts'
const partialPath = 'home/karan/notes.md'

export const AgentUnsupported: Story = {
  args: { path: agentPath },
  parameters: { systemInfo: proSystemInfo },
  render: (args) => (
    <SeededCoverage
      storyPath={agentPath}
      response={{
        path: agentPath,
        entries: [],
        present: [],
        present_in_latest: false,
        coverage: { indexed: 0, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      }}
    >
      <FileHistoryPanel {...args} />
    </SeededCoverage>
  ),
}

// The path's series decides the coverage once its listing is known: a
// series of its own here, with archives the index has not reached yet.
const partialSeries = 'weekly'
const partialListing = (state: ArchiveRow['history_state']): ArchiveListResponse => ({
  archives: [
    archive(11, 'weekly-2026-08-23', '2026-08-23T03:00:00Z', { series: partialSeries }),
    archive(12, 'weekly-2026-08-30', '2026-08-30T03:00:00Z', { series: partialSeries }),
    archive(13, 'weekly-2026-09-06', '2026-09-06T03:00:00Z', {
      series: partialSeries,
      history_state: state,
    }),
    archive(14, 'weekly-2026-09-13', '2026-09-13T03:00:00Z', {
      series: partialSeries,
      history_state: state,
    }),
  ],
  series: [partialSeries],
  sync_state: 'fresh',
  last_synced_at: '2026-09-13T03:10:00Z',
  history_available: true,
})

export const PartiallyIndexed: Story = {
  args: { path: partialPath },
  parameters: { systemInfo: proSystemInfo },
  render: (args) => (
    <SeededCoverage
      storyPath={partialPath}
      response={{
        path: partialPath,
        entries: [
          entry({
            archive_id: 12,
            archive_name: 'weekly-2026-08-30',
            series: partialSeries,
            start: '2026-08-30T03:00:00Z',
          }),
        ],
        present: [{ series: partialSeries, from_archive_id: 12, to_archive_id: null }],
        present_in_latest: true,
        coverage: { indexed: 5, exhausted: 0, total: 12, capability: 'available' },
      }}
      listing={{ series: partialSeries, response: partialListing('pending') }}
    >
      <FileHistoryPanel {...args} />
    </SeededCoverage>
  ),
}

// An index built on the server before the repository moved to an agent:
// the entries stay, the archives listed since are skipped, and the
// coverage says how far the index got.
export const AgentWithOlderIndex: Story = {
  args: { path: partialPath },
  parameters: { systemInfo: proSystemInfo },
  render: (args) => (
    <SeededCoverage
      storyPath={partialPath}
      response={{
        path: partialPath,
        entries: [
          entry({
            archive_id: 12,
            archive_name: 'weekly-2026-08-30',
            series: partialSeries,
            start: '2026-08-30T03:00:00Z',
          }),
        ],
        present: [{ series: partialSeries, from_archive_id: 12, to_archive_id: null }],
        present_in_latest: true,
        coverage: { indexed: 5, exhausted: 0, total: 12, capability: 'agent_unsupported' },
      }}
      listing={{ series: partialSeries, response: partialListing('skipped') }}
    >
      <FileHistoryPanel {...args} />
    </SeededCoverage>
  ),
}
