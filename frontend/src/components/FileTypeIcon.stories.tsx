import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack, Typography } from '@mui/material'
import FileTypeIcon from './FileTypeIcon'

const meta: Meta<typeof FileTypeIcon> = {
  title: 'Components/FileTypeIcon',
  component: FileTypeIcon,
}

export default meta

type Story = StoryObj<typeof FileTypeIcon>

const SAMPLES: Array<{ name: string; type: 'file' | 'directory' }> = [
  { name: 'Documents', type: 'directory' },
  { name: 'holiday.jpg', type: 'file' },
  { name: 'talk.mp4', type: 'file' },
  { name: 'contract.pdf', type: 'file' },
  { name: 'budget.xlsx', type: 'file' },
  { name: 'config.yaml', type: 'file' },
  { name: 'site-backup.tar.gz', type: 'file' },
  { name: 'notes.md', type: 'file' },
  { name: 'id_ed25519', type: 'file' },
  { name: 'unknown.bin', type: 'file' },
]

export const AllKinds: Story = {
  render: () => (
    <Stack spacing={1}>
      {SAMPLES.map((sample) => (
        <Stack key={sample.name} direction="row" spacing={1.5} sx={{ alignItems: 'center' }}>
          <FileTypeIcon name={sample.name} type={sample.type} />
          <Typography variant="body2">{sample.name}</Typography>
        </Stack>
      ))}
    </Stack>
  ),
}
