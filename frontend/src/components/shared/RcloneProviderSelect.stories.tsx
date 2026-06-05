import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import type { RcloneProvider } from '../../services/api'
import RcloneProviderSelect from './RcloneProviderSelect'

const providers: RcloneProvider[] = [
  {
    type: 'drive',
    label: 'Google Drive',
    description: 'Google Drive and shared drives through rclone.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/drive/',
    config_template: { type: 'drive', token: '' },
    fields: [],
    oauth_mode: 'borg_ui',
  },
  {
    type: 'gphotos',
    label: 'Google Photos',
    description: 'Google Photos media library.',
    auth_type: 'oauth_token',
    type_editable: false,
    docs_url: 'https://rclone.org/googlephotos/',
    config_template: { type: 'gphotos', token: '' },
    fields: [],
    oauth_mode: 'rclone_loopback',
  },
  {
    type: 'koofr',
    label: 'Koofr, Digi Storage and other Koofr-compatible storage providers',
    description: 'Koofr-compatible storage.',
    auth_type: 'basic',
    type_editable: false,
    docs_url: 'https://rclone.org/koofr/',
    config_template: { type: 'koofr' },
    fields: [],
  },
  {
    type: 's3',
    label: 'Amazon S3 compatible storage providers with a deliberately long label',
    description: 'S3-compatible object storage.',
    auth_type: 'access_key',
    type_editable: false,
    docs_url: 'https://rclone.org/s3/',
    config_template: { type: 's3' },
    fields: [],
  },
]

const meta = {
  title: 'Components/RcloneProviderSelect',
  component: RcloneProviderSelect,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof RcloneProviderSelect>

export default meta

type Story = StoryObj<typeof meta>

function RcloneProviderSelectPreview({
  initialValue = 'gphotos',
  width = 430,
}: {
  initialValue?: string
  width?: number
}) {
  const [value, setValue] = useState(initialValue)

  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <RcloneProviderSelect
        value={value}
        onChange={setValue}
        providers={providers}
        label="Provider"
        required
      />
    </Box>
  )
}

export const ProviderSearch: Story = {
  args: {
    value: 'gphotos',
    onChange: () => {},
    providers,
    label: 'Provider',
    required: true,
  },
  render: (args) => <RcloneProviderSelectPreview initialValue={args.value} />,
}

export const NarrowWidth: Story = {
  args: {
    value: 'koofr',
    onChange: () => {},
    providers,
    label: 'Provider',
    required: true,
  },
  render: (args) => <RcloneProviderSelectPreview initialValue={args.value} width={280} />,
}
