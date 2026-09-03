import { useEffect, useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import ArchiveNameTemplateInput from './ArchiveNameTemplateInput'

const meta = {
  title: 'Components/ArchiveNameTemplateInput',
  component: ArchiveNameTemplateInput,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof ArchiveNameTemplateInput>

export default meta

type Story = StoryObj<typeof meta>

function InteractiveTemplate({ value, jobName }: { value: string; jobName?: string }) {
  // Local state keeps the input interactive; the effect re-syncs it when
  // the value arrives from the Controls panel.
  const [current, setCurrent] = useState(value)
  useEffect(() => setCurrent(value), [value])
  return (
    <Box sx={{ width: 560 }}>
      <ArchiveNameTemplateInput value={current} onChange={setCurrent} jobName={jobName} />
    </Box>
  )
}

export const LocalTimeTemplate: Story = {
  args: { value: '{job_name}-{now}', jobName: 'nightly-plan', onChange: () => {} },
  render: (args) => <InteractiveTemplate value={args.value} jobName={args.jobName} />,
}

export const UtcTemplate: Story = {
  args: { value: '{job_name}-{utcnow}', jobName: 'nightly-plan', onChange: () => {} },
  render: (args) => <InteractiveTemplate value={args.value} jobName={args.jobName} />,
}

export const LocalVersusUtcPreview: Story = {
  // The two placeholders side by side make the zone difference visible in
  // the preview: {now} renders in the creating machine's local time,
  // {utcnow} in UTC.
  args: { value: '{now}-vs-{utcnow}', jobName: 'nightly-plan', onChange: () => {} },
  render: (args) => <InteractiveTemplate value={args.value} jobName={args.jobName} />,
}
