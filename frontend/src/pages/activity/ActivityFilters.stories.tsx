import { useState } from 'react'
import type { Meta, StoryObj } from '@storybook/react-vite'
import { Box } from '@mui/material'
import { ActivityFilters } from './ActivityFilters'

function ActivityFiltersStory({ initialStatusFilter = 'all' }: { initialStatusFilter?: string }) {
  const [typeFilter, setTypeFilter] = useState('all')
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter)

  return (
    <Box sx={{ maxWidth: 1120, mx: 'auto', p: 3 }}>
      <ActivityFilters
        typeFilter={typeFilter}
        statusFilter={statusFilter}
        onTypeFilterChange={setTypeFilter}
        onStatusFilterChange={setStatusFilter}
      />
    </Box>
  )
}

const meta = {
  title: 'Pages/Activity/ActivityFilters',
  parameters: {
    layout: 'fullscreen',
  },
} satisfies Meta

export default meta

type Story = StoryObj<typeof meta>

export const AllActivity: Story = {
  render: () => <ActivityFiltersStory />,
}

export const CompletedWithWarningsFilter: Story = {
  render: () => <ActivityFiltersStory initialStatusFilter="completed_with_warnings" />,
}
