import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'

import BackupPlanSelect, { type BackupPlanSummary } from './BackupPlanSelect'

const plans: BackupPlanSummary[] = [
  {
    id: 11,
    name: 'Docker volumes',
    source_type: 'local',
    repository_count: 2,
    schedule_enabled: true,
  },
  {
    id: 12,
    name: 'Postgres data',
    source_type: 'remote',
    repository_count: 1,
    schedule_enabled: false,
  },
  {
    id: 13,
    name: 'Agent media libraries',
    source_type: 'agent',
    repository_count: 3,
    schedule_enabled: true,
  },
]

const meta = {
  title: 'Components/BackupPlanSelect',
  component: BackupPlanSelect,
  parameters: {
    layout: 'centered',
  },
} satisfies Meta<typeof BackupPlanSelect>

export default meta

type Story = StoryObj<typeof meta>

function BackupPlanSelectPreview({
  initialValue = 11,
  options = plans,
  disabled = false,
  placeholder,
  width = 420,
}: {
  initialValue?: number | ''
  options?: BackupPlanSummary[]
  disabled?: boolean
  placeholder?: string
  width?: number
}) {
  const [value, setValue] = useState<number | ''>(initialValue)

  return (
    <Box sx={{ width, maxWidth: 'calc(100vw - 32px)' }}>
      <BackupPlanSelect
        value={value}
        onChange={setValue}
        plans={options}
        label="Backup Plan"
        emptyMessage="No enabled backup plans are available."
        placeholder={placeholder}
        disabled={disabled}
      />
    </Box>
  )
}

export const ConfiguredPlan: Story = {
  args: {
    value: 11,
    onChange: () => {},
    plans,
    label: 'Backup Plan',
    emptyMessage: 'No enabled backup plans are available.',
  },
  render: (args) => <BackupPlanSelectPreview initialValue={args.value} options={args.plans} />,
}

export const EmptySelection: Story = {
  args: {
    value: '',
    onChange: () => {},
    plans,
    label: 'Backup Plan',
    emptyMessage: 'No enabled backup plans are available.',
    placeholder: 'Select a backup plan',
  },
  render: (args) => (
    <BackupPlanSelectPreview initialValue="" options={args.plans} placeholder={args.placeholder} />
  ),
}

export const EmptyState: Story = {
  args: {
    value: '',
    onChange: () => {},
    plans: [],
    label: 'Backup Plan',
    emptyMessage: 'No enabled backup plans are available.',
  },
  render: (args) => <BackupPlanSelectPreview initialValue="" options={args.plans} />,
}

export const DisabledControl: Story = {
  args: {
    value: 13,
    onChange: () => {},
    plans,
    label: 'Backup Plan',
    emptyMessage: 'No enabled backup plans are available.',
    disabled: true,
  },
  render: (args) => (
    <BackupPlanSelectPreview
      initialValue={args.value}
      options={args.plans}
      disabled={args.disabled}
    />
  ),
}
