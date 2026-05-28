import type { Meta, StoryObj } from '@storybook/react-vite'
import type { ComponentProps } from 'react'
import { Box } from '@mui/material'
import RcloneRemoteDialog from './RcloneRemoteDialog'
import type { RcloneProvider } from '../../services/api'

const providers: RcloneProvider[] = [
  {
    type: 'drive',
    label: 'Google Drive',
    description: 'Google Drive and shared drives through rclone.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/drive/',
    config_template: { type: 'drive', scope: 'drive', token: '' },
    fields: [
      {
        name: 'token',
        label: 'OAuth token JSON',
        kind: 'json',
        required: true,
        secret: true,
        helper: 'Start browser authorization from Borg UI, then check authorization.',
      },
    ],
  },
  {
    type: 'onedrive',
    label: 'Microsoft OneDrive',
    description: 'OneDrive personal, business, and SharePoint document libraries.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/onedrive/',
    config_template: { type: 'onedrive', token: '' },
    fields: [
      {
        name: 'token',
        label: 'OAuth token JSON',
        kind: 'json',
        required: true,
        secret: true,
        helper: 'Start browser authorization from Borg UI, then check authorization.',
      },
    ],
  },
  {
    type: 'local',
    label: 'Local filesystem',
    description: 'A local path remote for testing and mounted storage.',
    auth_type: 'none',
    type_editable: false,
    docs_url: 'https://rclone.org/local/',
    config_template: { type: 'local' },
    fields: [],
  },
  {
    type: 'custom',
    label: 'Custom rclone backend',
    description: 'Manual setup for any rclone backend not listed above.',
    auth_type: 'manual',
    type_editable: true,
    docs_url: 'https://rclone.org/docs/',
    config_template: { type: '' },
    fields: [],
  },
]

const meta = {
  title: 'Components/Wizard/Rclone Remote Dialog',
  component: RcloneRemoteDialog,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RcloneRemoteDialog>

export default meta

type Story = StoryObj<typeof meta>

const renderDialog = (args: ComponentProps<typeof RcloneRemoteDialog>) => (
  <Box sx={{ width: 720, minHeight: 620 }}>
    <RcloneRemoteDialog {...args} disablePortal />
  </Box>
)

export const CreateManagedRemote: Story = {
  args: {
    open: true,
    isCreating: false,
    error: null,
    providers,
    onClose: () => {},
    onCreate: () => {},
    onStartOAuth: async () => ({
      session_id: 'storybook-oauth',
      provider: 'drive',
      status: 'awaiting_callback',
      authorization_url: 'http://127.0.0.1:53682/auth?state=storybook',
      config: null,
      error: null,
    }),
    onGetOAuthSession: async () => ({
      session_id: 'storybook-oauth',
      provider: 'drive',
      status: 'authorized',
      authorization_url: 'http://127.0.0.1:53682/auth?state=storybook',
      config: {
        type: 'drive',
        token: '{"access_token":"storybook","refresh_token":"storybook"}',
      },
      error: null,
    }),
  },
  render: renderDialog,
}

export const GuidedGoogleDriveRemote: Story = {
  args: {
    ...CreateManagedRemote.args,
    initialRemote: {
      name: 'gdrive-prod',
      provider: 'drive',
      config_source: 'managed',
      redacted_config: { type: 'drive', scope: 'drive', token: '***' },
    },
  },
  render: renderDialog,
}

export const CustomBackendRemote: Story = {
  args: {
    ...CreateManagedRemote.args,
    initialRemote: {
      name: 'mega-archive',
      provider: 'mega',
      config_source: 'managed',
      redacted_config: { type: 'mega', user: 'archive@example.com' },
    },
  },
  render: renderDialog,
}

export const CreateError: Story = {
  args: {
    ...CreateManagedRemote.args,
    error: 'Remote name already exists.',
  },
  render: renderDialog,
}
