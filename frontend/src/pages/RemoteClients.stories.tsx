import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { RemoteClientsContent } from './RemoteClients'
import PlanGate from '../components/shared/PlanGate'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'
import { communitySystemInfo } from '../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Pages/RemoteClients',
  component: RemoteClientsContent,
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta<typeof RemoteClientsContent>

export default meta

type Story = StoryObj<typeof meta>

function renderPage(state: 'empty' | 'mixed' | 'activeRemote') {
  return (
    <RemoteBackendStoryProvider state={state}>
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', p: 3 }}>
        <RemoteClientsContent />
      </Box>
    </RemoteBackendStoryProvider>
  )
}

function renderLockedPage() {
  return (
    <RemoteBackendStoryProvider state="mixed">
      <Box sx={{ minHeight: '100vh', bgcolor: 'background.default', p: 3 }}>
        <PlanGate
          feature="remote_clients"
          message="Remote client switching is available on Pro and Enterprise plans. Upgrade to add or switch to remote Borg UI servers."
          surface="remote_clients_story"
          operation="view_locked_story"
        >
          <RemoteClientsContent />
        </PlanGate>
      </Box>
    </RemoteBackendStoryProvider>
  )
}

export const Overview: Story = {
  render: () => renderPage('mixed'),
}

export const Empty: Story = {
  render: () => renderPage('empty'),
}

export const ActiveRemote: Story = {
  render: () => renderPage('activeRemote'),
}

export const LockedCommunity: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => renderLockedPage(),
}
