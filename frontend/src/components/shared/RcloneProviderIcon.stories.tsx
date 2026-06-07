import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack, Typography } from '@mui/material'
import RcloneProviderIcon from './RcloneProviderIcon'

const oauthProviders = [
  { type: 'drive', label: 'Google Drive', status: 'Borg UI callback' },
  { type: 'onedrive', label: 'Microsoft OneDrive', status: 'Borg UI callback' },
  { type: 'dropbox', label: 'Dropbox', status: 'Borg UI callback' },
  { type: 'box', label: 'Box', status: 'Borg UI callback' },
  { type: 'pcloud', label: 'pCloud', status: 'Borg UI callback' },
  { type: 'gcs', label: 'Google Cloud Storage', status: 'Borg UI callback' },
  { type: 'gphotos', label: 'Google Photos', status: 'Borg UI callback' },
  { type: 'hidrive', label: 'HiDrive', status: 'Borg UI callback' },
  { type: 'huaweidrive', label: 'Huawei Drive', status: 'Borg UI callback' },
  { type: 'jottacloud', label: 'Jottacloud', status: 'Manual setup only' },
  { type: 'mailru', label: 'Mail.ru Cloud', status: 'Basic setup only' },
  { type: 'premiumizeme', label: 'Premiumize.me', status: 'Borg UI callback' },
  { type: 'putio', label: 'Put.io', status: 'Borg UI callback' },
  { type: 'sharefile', label: 'ShareFile', status: 'Borg UI callback' },
  { type: 'yandex', label: 'Yandex Disk', status: 'Borg UI callback' },
  { type: 'zoho', label: 'Zoho', status: 'Borg UI callback' },
]

const meta = {
  title: 'Components/Shared/Rclone Provider Icon',
  component: RcloneProviderIcon,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RcloneProviderIcon>

export default meta

type Story = StoryObj<typeof meta>

export const OAuthProviderCoverage: Story = {
  args: {
    provider: 'drive',
  },
  render: () => (
    <Box
      sx={{
        width: 760,
        maxWidth: 'calc(100vw - 32px)',
        display: 'grid',
        gridTemplateColumns: 'repeat(auto-fill, minmax(220px, 1fr))',
        gap: 1,
      }}
    >
      {oauthProviders.map((provider) => (
        <Stack
          key={provider.type}
          direction="row"
          spacing={1.25}
          alignItems="center"
          sx={{
            minWidth: 0,
            border: '1px solid',
            borderColor: 'divider',
            borderRadius: 1,
            p: 1,
          }}
        >
          <RcloneProviderIcon provider={provider.type} size={32} iconSize={17} />
          <Box sx={{ minWidth: 0 }}>
            <Typography variant="body2" fontWeight={600} noWrap>
              {provider.label}
            </Typography>
            <Typography variant="caption" color="text.secondary" noWrap>
              {provider.status}
            </Typography>
          </Box>
        </Stack>
      ))}
    </Box>
  ),
}
