import { useState, type ReactNode } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { useQueryClient } from '@tanstack/react-query'
import ArchiveChangesTab from './ArchiveChangesTab'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'
import type { ArchiveDetailResponse, ChangeRow } from '../../types/archives'

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
  history_available: true,
}

const changeRows: ChangeRow[] = [
  {
    path: 'home/karan/docs/invoices.xlsx',
    change: 'modified',
    size_before: 374_000,
    size_after: 412_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
  {
    path: 'home/karan/photos/2026-08-30.raf',
    change: 'added',
    size_before: null,
    size_after: 28_400_000,
    mode_changed: false,
    owner_changed: false,
    summary_count: null,
  },
]

const changesResponse = (overrides: Record<string, unknown> = {}) => ({
  archive_id: archive.id,
  compare_to_id: archive.predecessor_id,
  changes: changeRows,
  totals: { added: 1, removed: 0, modified: 1, summary: 0 },
  next_cursor: null,
  incomplete: false,
  unindexed_archive_ids: [],
  history_state: 'indexed' as const,
  history_truncated: false,
  ...overrides,
})

// The tab reads its rows and the truncation flag from the changes route, so
// the stories seed that response instead of reaching for a backend.
function SeededChanges({
  children,
  response,
}: {
  children: ReactNode
  response: ReturnType<typeof changesResponse>
}) {
  const queryClient = useQueryClient()
  useState(() => {
    queryClient.setQueryData(
      ['archive-changes', 7, archive.id, archive.predecessor_id, []],
      response
    )
    queryClient.setQueryData(['archive-series-older', 7, archive.series, archive.id], {
      archives: [],
      series: [archive.series],
      sync_state: 'fresh',
      last_synced_at: null,
      history_available: true,
    })
    return null
  })
  return <>{children}</>
}

const meta = {
  title: 'Components/Archives/ArchiveChangesTab',
  component: ArchiveChangesTab,
  args: {
    repositoryId: 7,
    archive,
  },
} satisfies Meta<typeof ArchiveChangesTab>

export default meta

type Story = StoryObj<typeof meta>

export const Default: Story = {
  parameters: {
    systemInfo: proSystemInfo,
  },
  render: (args) => (
    <SeededChanges response={changesResponse()}>
      <ArchiveChangesTab {...args} />
    </SeededChanges>
  ),
}

export const Truncated: Story = {
  args: {
    archive: { ...archive, history_truncated: true },
  },
  parameters: {
    systemInfo: proSystemInfo,
  },
  render: (args) => (
    <SeededChanges response={changesResponse({ history_truncated: true })}>
      <ArchiveChangesTab {...args} />
    </SeededChanges>
  ),
}

export const Pending: Story = {
  args: {
    archive: { ...archive, history_state: 'pending' },
  },
  parameters: {
    systemInfo: proSystemInfo,
  },
}

export const Locked: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
}

// An archive of a repository executed by a managed agent: the server cannot
// diff it, so the state is `skipped` for good and no rebuild is offered.
export const AgentUnsupported: Story = {
  args: {
    archive: {
      ...archive,
      history_state: 'skipped',
      history_capability: 'agent_unsupported',
    },
  },
  parameters: {
    systemInfo: proSystemInfo,
  },
  render: (args) => (
    <SeededChanges
      response={changesResponse({
        changes: [],
        totals: { added: 0, removed: 0, modified: 0, summary: 0 },
        history_state: 'skipped',
        history_capability: 'agent_unsupported',
      })}
    >
      <ArchiveChangesTab {...args} />
    </SeededChanges>
  ),
}
