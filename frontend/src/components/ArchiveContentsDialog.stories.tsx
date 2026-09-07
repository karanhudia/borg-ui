import { useEffect, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import ArchiveContentsDialog from './ArchiveContentsDialog'
import { httpClient, type Repository } from '../services/borgApi/client'
import type { Archive } from '../types'
import type { ArchiveRow } from '../types/archives'

const repository = {
  id: 1,
  name: 'Test Repo',
  path: '/test',
  borg_version: 1,
} as Repository

const archive = {
  id: '1',
  name: 'backup-2026-07-08',
  archive: 'backup-2026-07-08',
  start: '2026-07-08T10:00:00Z',
  time: '2026-07-08T10:00:00Z',
} as Archive

// Keep the v1 browse endpoint replying 202 so the dialog stays in the async
// "still listing" state and renders the slow-loading hint over the skeletons.
function usePendingBrowse() {
  useEffect(() => {
    const mock = new MockAdapter(httpClient, { onNoMatch: 'passthrough' })
    mock.onGet(/\/browse\//).reply(202, { status: 'pending', jobId: 1 })
    return () => {
      mock.restore()
    }
  }, [])
}

const meta = {
  title: 'Components/ArchiveContentsDialog',
  component: ArchiveContentsDialog,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof ArchiveContentsDialog>

export default meta
type Story = StoryObj<typeof meta>

function AwaitingAgentStory(args: ComponentProps<typeof ArchiveContentsDialog>) {
  usePendingBrowse()
  return <ArchiveContentsDialog {...args} />
}

// The 202 slow-loading hint rendered above the skeletons while a managed-agent
// listing is still running.
export const AwaitingAgentListing: Story = {
  args: {
    open: true,
    archive,
    repository,
    onClose: () => {},
  },
  render: (args) => <AwaitingAgentStory {...args} />,
}

// The matched database row is what turns the dialog title into a link to the
// archive's own page, so the story hands one in.
const storedArchive: ArchiveRow = {
  id: 12,
  repository_id: 1,
  borg_id: '1',
  name: 'backup-2026-07-08',
  series: 'nightly',
  start: '2026-07-08T10:00:00Z',
  end: '2026-07-08T10:14:00Z',
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
  history_indexed_at: '2026-07-08T10:20:00Z',
  history_rows: 40,
  history_truncated: false,
  first_seen_at: '2026-07-08T10:00:00Z',
  last_seen_at: '2026-07-08T10:00:00Z',
}

export const WithFullPageLink: Story = {
  args: {
    open: true,
    archive,
    repository,
    storedArchives: [storedArchive],
    onClose: () => {},
  },
  render: (args) => <AwaitingAgentStory {...args} />,
}
