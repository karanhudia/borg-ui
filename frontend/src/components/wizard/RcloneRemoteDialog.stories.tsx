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
    oauth_mode: 'borg_ui',
    oauth_configured: true,
    oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/drive',
    oauth_setup_key: null,
    oauth_credentials_source: 'database',
    oauth_client_id_set: true,
    oauth_client_secret_set: true,
    fields: [
      {
        name: 'token',
        label: 'OAuth token JSON',
        kind: 'json',
        required: true,
        secret: true,
        helper: 'Start browser authorization from Borg UI, then return to the dialog.',
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
    oauth_mode: 'borg_ui',
    oauth_configured: true,
    oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/onedrive',
    oauth_setup_key: null,
    oauth_credentials_source: 'database',
    oauth_client_id_set: true,
    oauth_client_secret_set: true,
    fields: [
      {
        name: 'token',
        label: 'OAuth token JSON',
        kind: 'json',
        required: true,
        secret: true,
        helper: 'Start browser authorization from Borg UI, then return to the dialog.',
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
      oauth_mode: 'borg_ui',
      authorization_url: '/rclone/oauth/sessions/storybook-oauth/authorize',
      local_authorization_url: null,
      config: null,
      error: null,
    }),
    onGetOAuthSession: async () => ({
      session_id: 'storybook-oauth',
      provider: 'drive',
      status: 'authorized',
      oauth_mode: 'borg_ui',
      authorization_url: '/rclone/oauth/sessions/storybook-oauth/authorize',
      local_authorization_url: null,
      config: {
        type: 'drive',
        _borg_ui_oauth_provider: 'drive',
        _borg_ui_oauth_session_id: 'storybook-oauth',
      },
      token_status: {
        status: 'valid',
        expires_at: '2026-05-30T01:00:00Z',
        refresh_available: true,
      },
      error: null,
    }),
    onSaveOAuthCredentials: async () => {},
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

export const BorgUiOAuthSetupMissing: Story = {
  args: {
    ...CreateManagedRemote.args,
    initialRemote: {
      name: 'gdrive-prod',
      provider: 'drive',
      config_source: 'managed',
      redacted_config: { type: 'drive', scope: 'drive', token: '' },
    },
    providers: providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: null,
            oauth_setup_key: 'backend.errors.rclone.oauthPublicBaseUrlRequired',
            oauth_credentials_source: 'unset',
            oauth_client_id_set: false,
            oauth_client_secret_set: false,
          }
        : provider
    ),
  },
  render: renderDialog,
}

export const BorgUiOAuthCredentialsMissing: Story = {
  args: {
    ...CreateManagedRemote.args,
    initialRemote: {
      name: 'gdrive-prod',
      provider: 'drive',
      config_source: 'managed',
      redacted_config: { type: 'drive', scope: 'drive', token: '' },
    },
    providers: providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/drive',
            oauth_setup_key: 'backend.errors.rclone.oauthProviderCredentialsRequired',
            oauth_credentials_source: 'unset',
            oauth_client_id_set: false,
            oauth_client_secret_set: false,
          }
        : provider
    ),
  },
  render: renderDialog,
}

export const BorgUiOAuthCredentialsPartiallySaved: Story = {
  args: {
    ...CreateManagedRemote.args,
    initialRemote: {
      name: 'gdrive-prod',
      provider: 'drive',
      config_source: 'managed',
      redacted_config: { type: 'drive', scope: 'drive', token: '' },
    },
    providers: providers.map((provider) =>
      provider.type === 'drive'
        ? {
            ...provider,
            oauth_configured: false,
            oauth_callback_url: 'https://backups.example.com/api/rclone/oauth/callback/drive',
            oauth_setup_key: 'backend.errors.rclone.oauthProviderCredentialsRequired',
            oauth_credentials_source: 'database',
            oauth_client_id_set: true,
            oauth_client_secret_set: false,
          }
        : provider
    ),
  },
  render: renderDialog,
}
