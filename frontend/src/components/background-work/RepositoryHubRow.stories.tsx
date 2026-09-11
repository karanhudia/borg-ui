import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import RepositoryHubRow from './RepositoryHubRow'
import { deriveTrack } from './repositoryTrack'
import { busyQueue, hubRepositories, hubRepository } from './storyFixtures'

const trackFor = (repositoryId: number) => {
  const group = busyQueue.repositories.find((r) => r.repository_id === repositoryId)
  return group ? deriveTrack(group, busyQueue.limits, busyQueue.paused) : null
}

const meta = {
  title: 'BackgroundWork/RepositoryHubRow',
  component: RepositoryHubRow,
  parameters: { layout: 'fullscreen' },
  decorators: [
    (Story) => (
      <Box sx={{ p: 3, maxWidth: 1100 }}>
        <Story />
      </Box>
    ),
  ],
  args: {
    repository: hubRepository(),
    track: null,
    historyAvailable: true,
    totalHistoryRows: 27393,
    onOpen: () => {},
    onRetry: () => {},
  },
} satisfies Meta<typeof RepositoryHubRow>

export default meta

type Story = StoryObj<typeof meta>

export const AtRest: Story = {}

export const WithProblems: Story = {
  args: { repository: hubRepositories[3] },
}

export const NeverBuilt: Story = {
  args: { repository: hubRepositories[0] },
}

export const Community: Story = {
  args: { historyAvailable: false },
}

// Spec 6.8: an opted-out repository reads as a choice, not a problem.
export const ArchivesOnly: Story = {
  args: { repository: hubRepository({ index_mode: 'archives' }) },
}

export const NotIndexed: Story = {
  args: {
    repository: hubRepository({ index_mode: 'off', sync_state: 'stale' }),
  },
}

export const Running: Story = {
  args: { repository: hubRepositories[2], track: trackFor(3) },
}

export const BackupHoldsTheLane: Story = {
  args: { repository: hubRepositories[1], track: trackFor(2) },
}

export const FailedStage: Story = {
  args: { repository: hubRepositories[3], track: trackFor(4) },
}

export const SystemLane: Story = {
  args: {
    repository: null,
    track: {
      repositoryId: null,
      repositoryName: 'System',
      foreground: null,
      stages: [
        { key: 'connect', status: 'idle', operation: null, reason: null },
        { key: 'stats', status: 'idle', operation: null, reason: null },
        { key: 'archives', status: 'idle', operation: null, reason: null },
        { key: 'history', status: 'idle', operation: null, reason: null },
      ],
    },
  },
}

// A repository executed by a managed agent has no history stage: the cell
// says so instead of showing a plan chip or "no file history yet".
export const AgentRepository: Story = {
  args: {
    repository: hubRepository({
      repository_name: 'k8s-node',
      history: { indexed: 0, pending: 0, failed: 0, skipped: 18, truncated: 0, rows: 0 },
      history_capability: 'agent_unsupported',
    }),
  },
}
