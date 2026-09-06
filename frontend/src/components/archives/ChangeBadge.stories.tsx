import type { Meta, StoryObj } from '@storybook/react-vite'
import { Stack, Typography } from '@mui/material'
import ChangeBadge from './ChangeBadge'

const meta: Meta<typeof ChangeBadge> = {
  title: 'Components/Archives/ChangeBadge',
  component: ChangeBadge,
}

export default meta

type Story = StoryObj<typeof ChangeBadge>

export const AllTypes: Story = {
  render: () => (
    <Stack spacing={1}>
      {(['added', 'removed', 'modified', 'summary'] as const).map((change) => (
        <Stack key={change} direction="row" spacing={1} sx={{ alignItems: 'center' }}>
          <ChangeBadge change={change} />
          <Typography variant="body2">{change}</Typography>
        </Stack>
      ))}
    </Stack>
  ),
}
