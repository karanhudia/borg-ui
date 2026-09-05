import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack, Typography } from '@mui/material'
import RunStatusIcon from './RunStatusIcon'

const meta: Meta<typeof RunStatusIcon> = {
  title: 'Activity/RunStatusIcon',
  component: RunStatusIcon,
}

export default meta

type Story = StoryObj<typeof RunStatusIcon>

const STATUSES = [
  'completed',
  'completed_with_warnings',
  'running',
  'queued',
  'failed',
  'cancelled',
  'skipped',
]

export const AllStatuses: Story = {
  render: () => (
    <Stack spacing={1}>
      {STATUSES.map((status) => (
        <Stack key={status} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <RunStatusIcon status={status} />
          <Typography variant="body2">{status}</Typography>
        </Stack>
      ))}
    </Stack>
  ),
}
