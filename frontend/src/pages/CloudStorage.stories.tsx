import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ReactNode } from 'react'
import { Box } from '@mui/material'
import { CloudStorageContent } from './CloudStorage'
import type { RcloneProvider, RcloneRemote } from '../services/api'

const providers: RcloneProvider[] = [
  {
    type: 'drive',
    label: 'Google Drive',
    description: 'Google Drive and shared drives through rclone.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/drive/',
    config_template: { type: 'drive', scope: 'drive', token: '' },
    fields: [{ name: 'token', label: 'OAuth token JSON', kind: 'json', secret: true }],
  },
  {
    type: 'onedrive',
    label: 'Microsoft OneDrive',
    description: 'OneDrive personal and business drives.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/onedrive/',
    config_template: { type: 'onedrive', token: '' },
    fields: [{ name: 'token', label: 'OAuth token JSON', kind: 'json', secret: true }],
  },
  {
    type: 's3',
    label: 'Amazon S3 / S3-compatible',
    description: 'S3-compatible object storage.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/s3/',
    config_template: { type: 's3', provider: 'AWS' },
    fields: [],
  },
  {
    type: 'b2',
    label: 'Backblaze B2',
    description: 'Backblaze B2 buckets.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/b2/',
    config_template: { type: 'b2', account: '' },
    fields: [],
  },
  {
    type: 'local',
    label: 'Local filesystem',
    description: 'Local path remote.',
    auth_type: 'none',
    type_editable: false,
    docs_url: 'https://rclone.org/local/',
    config_template: { type: 'local' },
    fields: [],
  },
  {
    type: 'custom',
    label: 'Custom rclone backend',
    description: 'Manual setup for any rclone backend.',
    auth_type: 'manual',
    type_editable: true,
    docs_url: 'https://rclone.org/docs/',
    config_template: { type: '' },
    fields: [],
  },
]

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
  providers,
  onRefresh: noop,
  onAddRemote: noop,
  onCloseAddRemote: noop,
  onCreateRemote: noopAsync,
  onStartOAuth: async () => ({
    session_id: 'storybook-oauth',
    provider: 'drive',
    status: 'awaiting_callback' as const,
    authorization_url: '/rclone/oauth/sessions/storybook-oauth/authorize',
    local_authorization_url: 'http://127.0.0.1:53682/auth?state=storybook',
    config: null,
    error: null,
  }),
  onGetOAuthSession: async () => ({
    session_id: 'storybook-oauth',
    provider: 'drive',
    status: 'authorized' as const,
    authorization_url: '/rclone/oauth/sessions/storybook-oauth/authorize',
    local_authorization_url: 'http://127.0.0.1:53682/auth?state=storybook',
    config: {
      type: 'drive',
      token: '{"access_token":"storybook","refresh_token":"storybook"}',
    },
    error: null,
  }),
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

export const AddGuidedRemote: Story = {
  render: () =>
    renderPage(<CloudStorageContent {...commonProps} remotes={remotes} addDialogOpen />),
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
          path: 'borg-ui',
          entries: [
            {
              name: 'archives',
              path: 'borg-ui/archives',
              is_dir: true,
              size: null,
              modified: null,
            },
            {
              name: 'manifest.json',
              path: 'borg-ui/manifest.json',
              is_dir: false,
              size: 128,
              modified: '2026-05-27T12:00:00Z',
            },
          ],
        }}
      />
    ),
}
