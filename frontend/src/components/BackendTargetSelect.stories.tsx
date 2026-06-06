import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import BackendTargetSelect from './BackendTargetSelect'
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

const proSystemInfo: SystemInfo = {
  app_version: '2.2.2-alpha.1',
  borg_version: 'borg 1.4.1',
  borg2_version: 'borg2 2.0.0b19',
  plan: 'pro',
  features: featureMap,
  feature_access: { remote_clients: true },
}

const communitySystemInfo: SystemInfo = {
  ...proSystemInfo,
  plan: 'community',
  feature_access: { remote_clients: false },
}

const meta = {
  title: 'Components/BackendTargetSelect',
  component: BackendTargetSelect,
  parameters: {
    layout: 'centered',
    systemInfo: proSystemInfo,
  },
} satisfies Meta<typeof BackendTargetSelect>

export default meta

type Story = StoryObj<typeof meta>

export const LoginFormSelector: Story = {
  render: () => (
    <RemoteBackendStoryProvider state="mixed">
      <Box sx={{ width: 360 }}>
        <BackendTargetSelect />
      </Box>
    </RemoteBackendStoryProvider>
  ),
}

export const RemoteSelected: Story = {
  render: () => (
    <RemoteBackendStoryProvider state="activeRemote">
      <Box sx={{ width: 360 }}>
        <BackendTargetSelect />
      </Box>
    </RemoteBackendStoryProvider>
  ),
}

export const LockedCommunity: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => (
    <RemoteBackendStoryProvider state="mixed">
      <Box sx={{ width: 360 }}>
        <BackendTargetSelect />
      </Box>
    </RemoteBackendStoryProvider>
  ),
}
