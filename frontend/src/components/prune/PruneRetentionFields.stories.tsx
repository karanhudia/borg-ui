import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import PruneRetentionFields from './PruneRetentionFields'
import { DEFAULT_RETENTION } from './defaultRetention'

const meta = {
  title: 'Components/Prune/PruneRetentionFields',
  component: PruneRetentionFields,
} satisfies Meta<typeof PruneRetentionFields>

export default meta
type Story = StoryObj<typeof meta>

function Interactive() {
  const [value, setValue] = useState(DEFAULT_RETENTION)
  return <PruneRetentionFields value={value} onChange={setValue} />
}

export const Default: Story = {
  args: { value: DEFAULT_RETENTION, onChange: () => {} },
  render: () => <Interactive />,
}

export const Disabled: Story = {
  args: { value: DEFAULT_RETENTION, onChange: () => {}, disabled: true },
}
