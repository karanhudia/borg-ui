import { useEffect, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import MockAdapter from 'axios-mock-adapter'
import ArchiveContentsDialog from './ArchiveContentsDialog'
import { httpClient, type Repository } from '../services/borgApi/client'
import type { Archive } from '../types'

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
