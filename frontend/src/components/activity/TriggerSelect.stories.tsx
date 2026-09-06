import type { Meta, StoryObj } from '@storybook/react-vite'
import { useState } from 'react'
import TriggerSelect from './TriggerSelect'

const meta: Meta<typeof TriggerSelect> = {
  title: 'Activity/TriggerSelect',
  component: TriggerSelect,
}

export default meta

type Story = StoryObj<typeof TriggerSelect>

function Controlled({ initial }: { initial: string }) {
  const [value, setValue] = useState(initial)
  return <TriggerSelect value={value} onChange={setValue} />
}

export const AllTriggers: Story = { render: () => <Controlled initial="all" /> }
export const Schedule: Story = { render: () => <Controlled initial="schedule" /> }
