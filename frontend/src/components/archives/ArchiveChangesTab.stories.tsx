import type { Meta, StoryObj } from '@storybook/react-vite'
import ArchiveChangesTab from './ArchiveChangesTab'
import { communitySystemInfo, proSystemInfo } from '../../services/remoteBackends/planStoryFixtures'
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
}

export const Truncated: Story = {
  args: {
    archive: { ...archive, history_truncated: true },
  },
  parameters: {
    systemInfo: proSystemInfo,
  },
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
