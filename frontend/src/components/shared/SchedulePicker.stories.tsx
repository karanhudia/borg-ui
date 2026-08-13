import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'

import SchedulePicker, { type ScheduleMode } from './SchedulePicker'

const meta = {
  title: 'Shared/SchedulePicker',
  component: SchedulePicker,
  parameters: { layout: 'centered' },
} satisfies Meta<typeof SchedulePicker>

export default meta
type Story = StoryObj<typeof meta>

const AvailabilityTriggerPreview = () => {
  const [scheduleMode, setScheduleMode] = useState<ScheduleMode>('availability')
  const [cronExpression, setCronExpression] = useState('0 2 * * *')
  const [timezone, setTimezone] = useState('UTC')
  const [checkMinutes, setCheckMinutes] = useState(30)
  const [minimumHours, setMinimumHours] = useState(20)

  return (
    <SchedulePicker
      cronExpression={cronExpression}
      timezone={timezone}
      scheduleMode={scheduleMode}
      availabilityCheckIntervalMinutes={checkMinutes}
      minimumSuccessIntervalHours={minimumHours}
      showTriggerMode
      onChange={(updates) => {
        if (updates.scheduleMode) setScheduleMode(updates.scheduleMode)
        if (updates.cronExpression !== undefined) setCronExpression(updates.cronExpression)
        if (updates.timezone) setTimezone(updates.timezone)
        if (updates.availabilityCheckIntervalMinutes !== undefined) {
          setCheckMinutes(updates.availabilityCheckIntervalMinutes)
        }
        if (updates.minimumSuccessIntervalHours !== undefined) {
          setMinimumHours(updates.minimumSuccessIntervalHours)
        }
      }}
    />
  )
}

export const AvailabilityTrigger: Story = {
  args: {
    cronExpression: '0 2 * * *',
    timezone: 'UTC',
    onChange: () => {},
  },
  render: () => <AvailabilityTriggerPreview />,
}
