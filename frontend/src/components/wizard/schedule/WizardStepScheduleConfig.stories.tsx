import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box, Stack } from '@mui/material'

import WizardStepScheduleConfig from './WizardStepScheduleConfig'

const meta = {
  title: 'Schedule/WizardStepScheduleConfig',
  component: WizardStepScheduleConfig,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof WizardStepScheduleConfig>

export default meta

type Story = StoryObj<typeof meta>

function ScheduleConfigPreview({ initialScheduleEnabled }: { initialScheduleEnabled: boolean }) {
  const [data, setData] = useState({
    scheduleEnabled: initialScheduleEnabled,
    cronExpression: '0 2 * * *',
    timezone: 'UTC',
    archiveNameTemplate: '{job_name}-{now}',
  })

  return (
    <Box sx={{ width: 560, maxWidth: 'calc(100vw - 32px)' }}>
      <WizardStepScheduleConfig
        data={data}
        jobName="external-drive-maintenance"
        onChange={(updates) => setData((current) => ({ ...current, ...updates }))}
      />
    </Box>
  )
}

export const Scheduled: Story = {
  args: {
    data: {
      scheduleEnabled: true,
      cronExpression: '0 2 * * *',
      timezone: 'UTC',
      archiveNameTemplate: '{job_name}-{now}',
    },
    jobName: 'external-drive-maintenance',
    onChange: () => {},
  },
  render: () => <ScheduleConfigPreview initialScheduleEnabled />,
}

export const ManualOnly: Story = {
  args: {
    data: {
      scheduleEnabled: false,
      cronExpression: '0 2 * * *',
      timezone: 'UTC',
      archiveNameTemplate: '{job_name}-{now}',
    },
    jobName: 'external-drive-maintenance',
    onChange: () => {},
  },
  render: () => (
    <Stack spacing={2}>
      <ScheduleConfigPreview initialScheduleEnabled={false} />
    </Stack>
  ),
}
