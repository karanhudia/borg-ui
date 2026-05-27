import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ReactNode } from 'react'
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
    redacted_config: { type: 's3', provider: 'AWS', access_key_id: '***' },
    last_test_status: 'connected',
    last_error: null,
  },
  {
    id: 2,
    name: 'archive-b2',
    provider: 'b2',
    usage_count: 0,
    config_source: 'managed',
    redacted_config: { type: 'b2', account: '***' },
    last_test_status: 'failed',
    last_error: 'Credential validation failed',
  },
]

const noop = () => {}
const noopAsync = async () => {}

const renderPage = (children: ReactNode) => (
  <Box sx={{ p: 3, bgcolor: 'background.default', minHeight: '100vh' }}>{children}</Box>
)

const commonProps = {
  status: { available: true, version: 'rclone v1.66.0' },
  onRefresh: noop,
  onAddRemote: noop,
  onCloseAddRemote: noop,
  onCreateRemote: noopAsync,
  onEditRemote: noop,
  onCloseEditRemote: noop,
  onUpdateRemote: noopAsync,
  onRequestDeleteRemote: noop,
  onCloseDeleteRemote: noop,
  onConfirmDeleteRemote: noopAsync,
  onTestRemote: noop,
  onBrowseRemote: noop,
  onCloseBrowse: noop,
}

const meta = {
  title: 'Pages/CloudStorage',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const Overview: Story = {
  render: () =>
    renderPage(
      <CloudStorageContent {...commonProps} remotes={remotes} testingRemoteId={remotes[0].id} />
    ),
}

export const Empty: Story = {
  render: () => renderPage(<CloudStorageContent {...commonProps} remotes={[]} />),
}

export const Unavailable: Story = {
  render: () =>
    renderPage(
      <CloudStorageContent
        {...commonProps}
        status={{
          available: false,
          version: null,
          error: 'rclone binary was not found on PATH',
        }}
        remotes={[]}
      />
    ),
}

export const EditingRemote: Story = {
  render: () =>
    renderPage(
      <CloudStorageContent
        {...commonProps}
        remotes={remotes}
        editingRemote={remotes[0]}
        updateError="Credential validation failed"
      />
    ),
}

export const DeleteConfirmation: Story = {
  render: () =>
    renderPage(
      <CloudStorageContent {...commonProps} remotes={remotes} deleteRemote={remotes[1]} />
    ),
}

export const BrowseDialog: Story = {
  render: () =>
    renderPage(
      <CloudStorageContent
        {...commonProps}
        remotes={remotes}
        browseState={{
          remote: remotes[0],
          path: '',
          entries: [
            { name: 'borg-ui', path: 'borg-ui', is_dir: true, size: null, modified: null },
            {
              name: 'README.md',
              path: 'README.md',
              is_dir: false,
              size: 128,
              modified: null,
            },
          ],
        }}
      />
    ),
}
