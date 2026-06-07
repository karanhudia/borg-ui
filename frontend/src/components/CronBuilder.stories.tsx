import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack, Typography } from '@mui/material'

import CronBuilder from './CronBuilder'

const meta = {
  title: 'Components/CronBuilder',
  component: CronBuilder,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof CronBuilder>

export default meta

type Story = StoryObj<typeof meta>

function CronBuilderStory({ initialValue }: { initialValue: string }) {
  const [value, setValue] = useState(initialValue)

  return (
    <Stack spacing={2} sx={{ width: 560, maxWidth: 'calc(100vw - 32px)' }}>
      <CronBuilder value={value} onChange={setValue} label="Schedule" />
      <Box
        sx={{
          px: 1.5,
          py: 1,
          border: 1,
          borderColor: 'divider',
          borderRadius: 1,
          bgcolor: 'background.default',
        }}
      >
        <Typography variant="caption" color="text.secondary">
          Generated cron
        </Typography>
        <Typography variant="body2" fontFamily="monospace">
          {value}
        </Typography>
      </Box>
    </Stack>
  )
}

export const Daily: Story = {
  args: {
    value: '0 2 * * *',
    onChange: () => {},
    label: 'Schedule',
  },
  render: (args) => <CronBuilderStory initialValue={args.value} />,
}

export const Weekly: Story = {
  args: {
    value: '30 9 * * 1,3,5',
    onChange: () => {},
    label: 'Schedule',
  },
  render: (args) => <CronBuilderStory initialValue={args.value} />,
}
