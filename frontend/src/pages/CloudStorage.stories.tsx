import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { CloudStorageContent } from './CloudStorage'
import type { RcloneRemote } from '../services/api'

const remotes: RcloneRemote[] = [
  {
    id: 1,
    name: 'prod-s3',
    provider: 's3',
    usage_count: 2,
    config_source: 'managed',
    last_test_status: 'connected',
    last_error: null,
  },
  {
    id: 2,
    name: 'archive-b2',
    provider: 'b2',
    usage_count: 0,
    config_source: 'managed',
    last_test_status: 'failed',
    last_error: 'Credential validation failed',
  },
]

const meta = {
  title: 'Pages/CloudStorage',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const Overview: Story = {
  render: () => (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <CloudStorageContent
        status={{ available: true, version: 'rclone v1.66.0' }}
        remotes={remotes}
        onRefresh={() => {}}
        onAddRemote={() => {}}
        onTestRemote={() => {}}
        onBrowseRemote={() => {}}
      />
    </Box>
  ),
}

export const Empty: Story = {
  render: () => (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <CloudStorageContent
        status={{ available: true, version: 'rclone v1.66.0' }}
        remotes={[]}
        onRefresh={() => {}}
        onAddRemote={() => {}}
      />
    </Box>
  ),
}

export const Unavailable: Story = {
  render: () => (
    <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>
      <CloudStorageContent
        status={{
          available: false,
          version: null,
          error: 'rclone binary was not found on PATH',
        }}
        remotes={[]}
        onRefresh={() => {}}
        onAddRemote={() => {}}
      />
    </Box>
  ),
}
