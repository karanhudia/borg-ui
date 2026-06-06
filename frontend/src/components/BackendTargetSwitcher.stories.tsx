import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { BrowserRouter } from 'react-router-dom'
import BackendTargetSwitcher from './BackendTargetSwitcher'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'
import { communitySystemInfo, proSystemInfo } from '../services/remoteBackends/planStoryFixtures'

const meta = {
  title: 'Components/BackendTargetSwitcher',
  component: BackendTargetSwitcher,
  parameters: {
    layout: 'centered',
    systemInfo: proSystemInfo,
  },
} satisfies Meta<typeof BackendTargetSwitcher>

export default meta

type Story = StoryObj<typeof meta>

function renderSwitcher(state: 'mixed' | 'activeRemote', props = {}) {
  return (
    <BrowserRouter>
      <RemoteBackendStoryProvider state={state}>
        <Box sx={{ width: 280 }}>
          <BackendTargetSwitcher {...props} />
        </Box>
      </RemoteBackendStoryProvider>
    </BrowserRouter>
  )
}

export const LocalSelected: Story = {
  render: () => renderSwitcher('mixed'),
}

export const RemoteSelected: Story = {
  render: () => renderSwitcher('activeRemote'),
}

export const Compact: Story = {
  args: {
    compact: true,
  },
  render: (args) => renderSwitcher('activeRemote', args),
}

export const LockedCommunity: Story = {
  parameters: {
    systemInfo: communitySystemInfo,
  },
  render: () => renderSwitcher('mixed'),
  play: async ({ canvasElement }) => {
    await new Promise((resolve) => window.setTimeout(resolve, 0))
    canvasElement.querySelector('button')?.click()
  },
}
