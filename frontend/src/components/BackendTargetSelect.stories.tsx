import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import BackendTargetSelect from './BackendTargetSelect'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'
import { communitySystemInfo, proSystemInfo } from '../services/remoteBackends/planStoryFixtures'

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
