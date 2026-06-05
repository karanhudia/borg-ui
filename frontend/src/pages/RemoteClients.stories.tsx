import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { RemoteClientsContent } from './RemoteClients'
import { RemoteBackendStoryProvider } from '../services/remoteBackends/storyFixtures'

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

export const Overview: Story = {
  render: () => renderPage('mixed'),
}

export const Empty: Story = {
  render: () => renderPage('empty'),
}

export const ActiveRemote: Story = {
  render: () => renderPage('activeRemote'),
}
