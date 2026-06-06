import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { RemoteClientsContent } from './RemoteClients'
import PlanGate from '../components/shared/PlanGate'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'
import type { SystemInfo } from '../hooks/useSystemInfo'

const featureMap = {
  borg_v2: 'pro',
  backup_plan_multi_repository: 'pro',
  backup_plan_mixed_sources: 'pro',
  rclone: 'pro',
  managed_agents: 'pro',
  remote_clients: 'pro',
  multi_user: 'community',
  extra_users: 'pro',
  rbac: 'enterprise',
} as const

const communitySystemInfo: SystemInfo = {
  app_version: '2.2.2-alpha.1',
  borg_version: 'borg 1.4.1',
  borg2_version: 'borg2 2.0.0b19',
  plan: 'community',
  features: featureMap,
  feature_access: { remote_clients: false },
}

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
