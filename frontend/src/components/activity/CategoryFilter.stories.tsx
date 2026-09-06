import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import CategoryFilter from './CategoryFilter'
import type { OperationCategory } from '../../types/operations'

const meta: Meta<typeof CategoryFilter> = {
  title: 'Activity/CategoryFilter',
  component: CategoryFilter,
}

export default meta

type Story = StoryObj<typeof CategoryFilter>

function Controlled({ initial }: { initial: OperationCategory[] }) {
  const [value, setValue] = useState<OperationCategory[]>(initial)
  return <CategoryFilter value={value} onChange={setValue} />
}

export const NothingSelected: Story = {
  render: () => <Controlled initial={[]} />,
}

export const BackupAndMaintenance: Story = {
  render: () => <Controlled initial={['backup', 'maintenance']} />,
}
