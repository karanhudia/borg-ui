import { useEffect, type ComponentProps } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import MockAdapter from 'axios-mock-adapter'
import ArchivePathSelector from './ArchivePathSelector'
import { httpClient, type Repository } from '../services/borgApi/client'
import type { Archive } from '../types'

const repository = {
  id: 1,
  name: 'Test Repo',
  path: '/test',
  borg_version: 1,
} as Repository

const archive: Pick<Archive, 'id' | 'name'> = {
  id: '1',
  name: 'backup-2026-07-08',
}

// Keep the browse endpoint replying 202 so the selector stays in the async
// "still listing" state and renders the spinner + slow-loading hint.
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
  title: 'Components/ArchivePathSelector',
  component: ArchivePathSelector,
  parameters: { layout: 'fullscreen' },
} satisfies Meta<typeof ArchivePathSelector>

export default meta
type Story = StoryObj<typeof meta>

function AwaitingAgentStory(args: ComponentProps<typeof ArchivePathSelector>) {
  usePendingBrowse()
  return (
    <Box sx={{ p: 3, maxWidth: 720 }}>
      <ArchivePathSelector {...args} />
    </Box>
  )
}

// The awaiting-agent state: the spinner plus the slow-loading hint while a
// managed-agent listing is still running.
export const AwaitingAgentListing: Story = {
  args: {
    repository,
    archive,
    data: { selectedPaths: [] },
    onChange: () => {},
  },
  render: (args) => <AwaitingAgentStory {...args} />,
}
